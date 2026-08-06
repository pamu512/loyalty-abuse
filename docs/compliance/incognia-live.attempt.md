# Incognia live attempt — 2026-08-06 (v2 follow-up)

**Goal:** Evidence for live device-intel path.  
**Result:** **BLOCKED**

## Environment

| Variable | Present |
|---|---|
| `INCOGNIA_CLIENT_ID` | no |
| `INCOGNIA_CLIENT_SECRET` | no |
| `INCOGNIA_POLICY_ID` | no |

## Actions taken

1. Re-checked process environment for Incognia credentials (still missing).
2. Confirmed `adapters.incognia.env_creds_ready()` → `False`.
3. Did **not** invent live assessment responses or forge success artifacts.
4. Fixture-mode adapter tests remain the in-repo device-intel path *path* proof only.

## Status file

`docs/compliance/incognia-live.status` = `BLOCKED — reason: credentials not configured`

## Unblock

Set `INCOGNIA_CLIENT_ID`, `INCOGNIA_CLIENT_SECRET`, `INCOGNIA_POLICY_ID`, then re-run live adapter smoke against sandbox and attach assessment ids + latency.
