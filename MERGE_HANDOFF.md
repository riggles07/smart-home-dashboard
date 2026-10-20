# MERGE HANDOFF — worker branches to `main`

Written 2026-10-20. Fresh session: read this, then execute. `main` is `1cc813a`.

## State

Four worker cards completed. Their work is committed on `wt/*` branches (I
committed it by hand — the workers leave work uncommitted, and a worker stashes at
startup, so it was one dispatch away from being destroyed).

```
wt/t_8edef3d9  1d22891  ahead=1   tests/test_ha_tile_grid.py (+13 tests)   487 pass
wt/t_ff8c5949  72029b4  ahead=1   docs/INTERACTIVITY_AUDIT.md + audit script  (no fixes)
wt/t_c2217a3c  d0f52a1  ahead=1   css/dashboard.css +181/-20, 09-activity-chart 475 pass
wt/t_073eb9fc  f050a9d  ahead=1   css/dashboard.css +152, 07-ha flow +95       474 pass
```

All three code branches pass `pytest tests/` in their own worktree.

## The one thing to decide before merging

`flows/*.json` are **generated** by `tools/gen_flows.py`, which inlines
`css/dashboard.css` into the theme template. Consequences:

- **CSS changes are reproducible.** Regenerating after merging the CSS reproduces
  the flow diff automatically. Merge CSS, then run the generator, and the flow
  files follow. This is verified: running `gen_flows.py` in `wt/t_c2217a3c`
  produced a clean tree, i.e. its committed flows equal its regenerated flows.
- **`flows/09-activity-chart.flow.json` is an ORPHAN.** `gen_flows.py` does not
  reference it (verified by grep). It is a hand-made file that no regen will
  recreate, and `all-flows.flow.json` (the deploy bundle) is generated from the
  generator's own list — so the P3 activity chart's nodes are NOT in the bundle
  unless they were added to `tools/gen_flows.py`, which they were not.

⇒ **P3's chart does not currently exist as deployable nodes.** Merging its CSS
gives dead styles. To land it properly, port the 09 nodes into `gen_flows.py` as a
real tab/group/template and let the generator emit both the per-tab file and the
bundle.

## Recommended order

1. `git merge --no-ff wt/t_8edef3d9` — tests only, new file, zero conflict risk.
   Run `pytest tests/ -q` → expect 487.
2. `git merge --no-ff wt/t_ff8c5949` — docs + `tools/audit_interactivity.py`.
   Read `docs/INTERACTIVITY_AUDIT.md`; it is the P4 deliverable and it contains
   **no fixes**, only findings. Reopen P4 or scope a follow-up from its findings.
3. `git merge --no-ff wt/t_073eb9fc` (P5) then `wt/t_c2217a3c` (P3) — BOTH touch
   `css/dashboard.css`, so expect conflicts. Prefer resolving in favour of P5
   first then re-applying P3's block, since P3's CSS is only useful once its nodes
   exist.
4. After any CSS merge: `python3 tools/gen_flows.py && git diff --stat` and confirm
   the flow diff matches what you intended. Never hand-edit `flows/*.json`.
5. Deploy with credentials (see `tools/mqtt_wire_and_verify.py` for the v2 object
   form), then verify in the LIVE DOM — not in source.

## Card state that does not match reality

- **`t_b14ea66d` (P2) is marked done with ZERO work.** Verified: `git diff --stat`
  empty, `git ls-files --others` empty, HEAD still `1f01446`. It only "analysed".
  **Reopen it.** The greeting header and house-status hero were never built.
- `t_ff8c5949` (P4) is done but delivered an audit, not the "wiring fixes" in its
  title. Scope a follow-up from the audit's findings.
- `t_74bf675d` sits in `triage` (unblock-loop guard) — needs WallPanel MQTT
  configured before it can measure anything.

## Also true right now

- `kanban.dispatch_in_gateway=false`; cron `shd-sequential-dispatcher` (5m) drives
  the board. It will keep dispatching whatever is ready — check the board before
  starting the merge so a worker is not writing to a worktree mid-merge.
- No workers are alive as of this handoff (`workers alive: 0`).
