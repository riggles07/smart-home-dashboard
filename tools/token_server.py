"""Tiny CORS-enabled server that hands the HA token to the headless browser.

Why: to verify kiosk mode I need an *authenticated* HA frontend in the browser. The HA
frontend keeps its session in localStorage (`hassTokens`), which a script can only write
from a page, and a page can only fetch cross-origin with CORS. Serving the token from
this local origin keeps the secret out of the transcript and out of shell history.

Serves exactly one path: /token.json
"""
import http.server
import json
import socketserver
import threading

env = {}
for line in open("/root/.hermes/.env"):
    if "=" in line:
        k, v = line.strip().split("=", 1)
        env[k] = v

BODY = json.dumps({"access_token": env["HA_TOKEN"], "ha_url": env["HA_URL"]}).encode()


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/token.json":
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(BODY)))
        self.end_headers()
        self.wfile.write(BODY)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("0.0.0.0", 8905), H) as srv:
        print("serving token on 8905")
        srv.serve_forever()
