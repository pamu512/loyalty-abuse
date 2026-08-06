# Incognia live attempt — 2026-08-06

**Goal:** Evidence for production A++ device-intel path.  
**Result:** **BLOCKED**

## Environment

| Variable | Present |
|---|---|
| `INCOGNIA_CLIENT_ID` | no |
| `INCOGNIA_CLIENT_SECRET` | no |
| `INCOGNIA_POLICY_ID` | no |

## Actions taken

1. Checked process environment for Incognia credentials (missing).
2. Confirmed fixture-mode adapter tests pass under `tests/adapters/test_incognia.py`.
3. Did **not** invent live assessment responses or forge success artifacts.

## Status file

`docs/compliance/incognia-live.status` = `BLOCKED — reason: credentials not configured`

## Unblock

Set `INCOGNIA_CLIENT_ID`, `INCOGNIA_CLIENT_SECRET`, `INCOGNIA_POLICY_ID`, then re-run live adapter smoke against sandbox and attach assessment ids + latency.
