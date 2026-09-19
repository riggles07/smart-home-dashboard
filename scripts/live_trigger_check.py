"""Live end-to-end check of the Hubitat automation trigger path.

Stands up a real HTTP server that mimics a Rule Machine endpoint trigger
(``/apps/api/<appId>/trigger/getRuleList`` and ``.../trigger/runRuleAct=<id>``)
and drives ``HubitatNode`` against it over genuine TCP with the default
stdlib transport -- no mocks. Also exercises the failure paths that need a
real socket: unreachable hub, HTTP 401 and HTTP 404.

Usage:
    python3 scripts/live_trigger_check.py
"""

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "flows"))

import hubitat_integration as hub  # noqa: E402

APP_ID = "10249"
TOKEN = "00000000-1111-2222-3333-444444444444"
RULES = {"943": "Good Morning", "956": "Away Mode", "10217": "Movie Night"}

seen = []


class Handler(BaseHTTPRequestHandler):
    """Fake Rule Machine endpoint trigger."""

    def log_message(self, *args):
        """Silence the default stderr access log."""

    def _send(self, status, payload=None, text=None):
        body = (text if text is not None else json.dumps(payload or {})).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle(self, method):
        parsed = urlparse(self.path)
        query = dict(
            pair.split("=", 1) for pair in parsed.query.split("&") if "=" in pair
        )
        path = unquote(parsed.path)
        seen.append({"method": method, "path": path, "query": query})

        if query.get("access_token") != TOKEN:
            self._send(401, {"error": "Unauthorized"})
            return

        prefix = f"/apps/api/{APP_ID}/trigger"
        if not path.startswith(prefix):
            self._send(404, {"error": "Not Found"})
            return

        rest = path[len(prefix):].lstrip("/")

        if rest == "getRuleList":
            self._send(200, RULES)
            return

        if rest.startswith("runRuleAct="):
            rule_ids = rest[len("runRuleAct="):].split("&")
            unknown = [r for r in rule_ids if r not in RULES]
            if unknown:
                self._send(404, {"error": f"unknown rule {unknown}"})
                return
            self._send(200, {
                "status": "ok",
                "ranRules": [{"id": r, "name": RULES[r]} for r in rule_ids],
            })
            return

        if rest.startswith("stopRuleAct="):
            self._send(200, {"status": "ok", "stopped": rest.split("=", 1)[1]})
            return

        self._send(404, {"error": f"no such endpoint {rest!r}"})

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")


def main():
    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    failures = []

    def check(label, condition, detail=""):
        status = "PASS" if condition else "FAIL"
        print(f"  [{status}] {label}{(' -- ' + detail) if detail else ''}")
        if not condition:
            failures.append(label)

    try:
        base = f"http://127.0.0.1:{port}"
        print(f"Live Hubitat stub listening on {base} (real TCP, real HTTP)\n")

        # --- list ---------------------------------------------------------
        print("1. List automations (GET .../trigger/getRuleList)")
        node = hub.HUBITAT_NODE(
            "hubitat-control", {},
            {"url": base, "appId": APP_ID, "accessToken": TOKEN},
            None,
        )
        sent = []
        node.send = lambda *a, **kw: sent.append((a, kw))

        listing = node.getAutomations()
        check("list ok", listing.ok, listing.message)
        check("3 rules returned", len(listing.automations or []) == 3,
              str(listing.automations))
        check("names parsed", {a["name"] for a in listing.automations} == set(RULES.values()))
        check("list published to dashboard",
              sent and sent[-1][1].get("topic") == hub.AUTOMATION_TOPIC)

        # --- trigger by id -------------------------------------------------
        print("\n2. Trigger by rule app id (POST .../trigger/runRuleAct=943)")
        sent.clear()
        result = node.triggerAutomation("943")
        check("trigger ok", result.ok, result.message)
        check("resolved name", result.automation_name == "Good Morning")
        check("action reported", result.action == "runRuleAct")
        check("http 200", result.status_code == 200)
        check("hub ran the rule",
              result.payload and result.payload.get("ranRules", [{}])[0].get("id") == "943",
              json.dumps(result.payload))
        check("result published to per-automation topic",
              sent and sent[-1][1].get("topic") == hub.automation_result_topic("943"),
              str(sent[-1][1].get("topic") if sent else None))
        check("token redacted in result url", TOKEN not in (result.url or ""),
              str(result.url))

        # --- trigger by name ----------------------------------------------
        print("\n3. Trigger by rule name (name -> app id resolution)")
        node2 = hub.HUBITAT_NODE(
            "hubitat-control", {},
            {"url": base, "appId": APP_ID, "accessToken": TOKEN, "session": None},
            None,
        )
        node2.send = lambda *a, **kw: None
        by_name = node2.triggerAutomation("Movie Night")
        check("trigger by name ok", by_name.ok, by_name.message)
        check("resolved to id 10217", by_name.automation_id == "10217",
              str(by_name.automation_id))

        # --- stop action ---------------------------------------------------
        print("\n4. Stop action (POST .../trigger/stopRuleAct=956)")
        stopped = node.triggerAutomation("956", action="stopRuleAct")
        check("stop ok", stopped.ok, stopped.message)
        check("stop reached the hub",
              stopped.payload and stopped.payload.get("stopped") == "956",
              json.dumps(stopped.payload))

        # --- unknown id ----------------------------------------------------
        print("\n5. Unknown automation id (no HTTP call expected)")
        before = len(seen)
        unknown = node.triggerAutomation("0000")
        check("unknown rejected", not unknown.ok)
        check("code=unknown_automation", unknown.code == hub.ERROR_UNKNOWN_AUTOMATION,
              unknown.code)
        check("no HTTP request made", len(seen) == before,
              f"{len(seen) - before} extra call(s)")

        # --- auth failure ---------------------------------------------------
        print("\n6. Auth failure (bad access token -> HTTP 401)")
        bad_token = hub.HUBITAT_NODE(
            "hubitat-control", {},
            {"url": base, "appId": APP_ID, "accessToken": "wrong-token"},
            None,
        )
        bad_token.send = lambda *a, **kw: None
        auth = bad_token.getAutomations()
        check("auth failure reported", not auth.ok)
        check("code=auth_failure", auth.code == hub.ERROR_AUTH_FAILURE, auth.code)
        check("status 401", auth.status_code == 401, str(auth.status_code))

        # --- missing endpoint (404) ----------------------------------------
        print("\n7. No endpoint trigger on the app id (HTTP 404)")
        wrong_app = hub.HUBITAT_NODE(
            "hubitat-control", {},
            {"url": base, "appId": "4711", "accessToken": TOKEN},
            None,
        )
        wrong_app.send = lambda *a, **kw: None
        wrong_app.automations = [{"id": "943", "name": "Good Morning"}]
        wrong_app._automations_resolved = True
        notfound = wrong_app.triggerAutomation("943")
        check("404 reported", not notfound.ok)
        check("code=http_error", notfound.code == hub.ERROR_HTTP_ERROR, notfound.code)
        check("message explains endpoint trigger", "endpoint trigger" in notfound.message,
              notfound.message)

        # --- unreachable hub -------------------------------------------------
        print("\n8. Hub unreachable (connection refused)")
        dead = hub.HUBITAT_NODE(
            "hubitat-control", {},
            {"url": "http://127.0.0.1:1", "appId": APP_ID, "accessToken": TOKEN,
             "timeout": 2},
            None,
        )
        dead.send = lambda *a, **kw: None
        unreachable = dead.getAutomations()
        check("unreachable reported", not unreachable.ok)
        check("code=hub_unreachable",
              unreachable.code == hub.ERROR_HUB_UNREACHABLE, unreachable.code)

        # --- secret hygiene --------------------------------------------------
        print("\n9. Secret hygiene")
        all_urls = [c["path"] + "?" + "&".join(f"{k}=***" for k in c["query"])
                    for c in seen]
        redacted = [hub.redact_url(u) for u in all_urls]
        check("no raw token in any redacted url/result",
              all(TOKEN not in u for u in redacted)
              and all(TOKEN not in (r.url or "")
                      for r in (listing, result, by_name, stopped, unknown, auth,
                                notfound, unreachable)))

        print(f"\n{len(seen)} request(s) served over real TCP.")
    finally:
        server.shutdown()
        server.server_close()

    if failures:
        print(f"\nFAILED: {len(failures)} check(s): {failures}")
        return 1
    print("\nAll live checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
