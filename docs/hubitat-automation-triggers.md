# Hubitat Automation Triggers

Triggering Hubitat automations from the dashboard, implemented in
`flows/hubitat_integration.py` (`HubitatNode`) with a mirror in
`flows/hubitat-integration.js`, and surfaced as the `hubitat-automation` node in
`flows/dashboard_configuration.py` / `flows/dashboard-configuration.js` (the
Phase 3 "Automation triggers" checkbox).

## Which API is used

**Hubitat has no `/api/v1/automations` resource.** Automations live in Rule
Machine, and the only supported way to fire one from outside the hub is a
**Rule Machine endpoint trigger** — a rule (or rule group) configured with a
"Local End Point" / "Cloud End Point" trigger event. That app exposes:

| Request | Purpose |
| --- | --- |
| `GET /apps/api/<app_id>/trigger/getRuleList?access_token=<token>` | List the rules the endpoint can run: `{"<rule app id>": "<rule name>", ...}` |
| `POST /apps/api/<app_id>/trigger/<action>=<rule ids>?access_token=<token>` | Run an action against one or more rules; ids joined with `&` |
| `GET|POST /apps/api/<app_id>/trigger/<value>?access_token=<token>` | Bare string: sets the rule's built-in `%value%` variable |

`<action>` is a Rule Machine action — `runRuleAct` (default), `stopRuleAct`,
`pauseRule`, `resumeRule`, etc. The hub accepts both GET and POST for these
endpoints; the node defaults to `POST` (`triggerMethod` / `triggerMethod`
config to change).

Documentation: <https://docs2.hubitat.com/en/apps/rule-machine> ("Using Rule
Machine from HTTP requests") and
<https://docs2.hubitat.com/en/apps/maker-api>.

`<app_id>` and its `access_token` come from the Rule Machine endpoint app page,
**not** the Maker API page — the Maker API token only covers device commands.
Both are configurable per node or via `HUBITAT_APP_ID` /
`HUBITAT_ACCESS_TOKEN`; the access token falls back to `HUBITAT_API_KEY`, which
is the repo's existing name for a Hubitat bearer token.

## Dashboard surface

| Method | Purpose |
| --- | --- |
| `getAutomations(callback, session=None, refresh=False)` | List automations (`[{"id", "name"}, ...]`), cached on the node; `refresh=True` re-fetches. Aliased as `listAutomations`. |
| `triggerAutomation(id, callback, action=..., value=..., session=..., method=...)` | Trigger by rule app id **or by rule name** (resolved against the cached list). |
| `handleAutomationTrigger(msg)` | Node-RED entry point: `msg.payload = {automationId, action, value}` (a bare id also works). |
| `handleAutomationList(msg)` | Node-RED entry point for the picker: `msg.payload = {refresh: true}` forces a re-fetch. |

Results are published to the dashboard on `hubitat/automations` (list) and
`hubitat/automation/result/<automation id>` (per-trigger), matching the
`hubitat-automation` node config in `dashboard_configuration.py`.

Both methods return a structured `AutomationResult` and **never raise**.
Failures come back as `ok=False` with a machine-readable `code`:

| `code` | Meaning |
| --- | --- |
| `unknown_automation` | Id/name not in the rule list — no HTTP request is made. |
| `auth_failure` | HTTP 401/403: wrong app id or access token. |
| `http_error` | Other non-2xx; HTTP 404 means the app id has no endpoint trigger configured. |
| `hub_unreachable` | Connection refused / DNS / socket error. |
| `timeout` | The hub did not answer within `timeout` seconds. |
| `transport_error` | Unexpected transport-level error. |
| `malformed_response` | 2xx but the body is not a parseable rule list. |
| `not_configured` | Hub URL, app id or access token missing (partial config is reported honestly rather than silently simulated). |

## Configuration and secrets

| Setting | Config key | Env | Default |
| --- | --- | --- | --- |
| Hub URL | `url` | `HUBITAT_URL` | `http://hubitat.local:8080` |
| Endpoint app id | `appId` / `automationAppId` | `HUBITAT_APP_ID` / `HUBITAT_AUTOMATION_APP_ID` | unset |
| Access token | `accessToken` / `token` / `apiKey` | `HUBITAT_ACCESS_TOKEN` / `HUBITAT_API_KEY` | unset |
| HTTP timeout (s) | `timeout` | — | `10` |
| Trigger method | `triggerMethod` | — | `POST` |
| Resolve ids | `resolveAutomations` | — | `True` |
| Transport | `session` | — | module-level `session` hook |

* No token is ever logged or published: every URL that reaches a log line, an
  exception or a dashboard event goes through `redact_url()`, which masks
  `access_token` / `token` / `apiKey` values with `***`.
* Only `.env.example` is committed. `.env` is git-ignored.
* Nodes with **no** app id *and* no token keep the legacy simulated behaviour
  (the original flow tests depend on it); a *partial* config is not simulated.

## Tests

* `tests/test_hubitat_automations.py` — 48 tests over listing, triggering,
  every failure code, config/env handling and secret hygiene, all with a mocked
  HTTP transport (`tests/fake_hub.py`); no live hub required.
* `scripts/live_trigger_check.py` — end-to-end check against a real HTTP server
  over genuine TCP using the default stdlib transport (list, trigger by id and
  by name, stop action, unknown id, 401, 404, unreachable, secret hygiene).
* `scripts/live_trigger_check.js` — the same end-to-end path through the JS
  flow, using node's `http` module.

```bash
python3 -m pytest -q
python3 scripts/live_trigger_check.py
node scripts/live_trigger_check.js
```
