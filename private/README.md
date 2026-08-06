# Private ratings & grades

Letter-grade maturity ratings (and claim-lock status tables that publish them) are **not** part of the public repository.

## Where ratings live

Maintain them only under `private/` on local disks or in a non-public store:

| File (local) | Purpose |
|---|---|
| `private/CLAIM_LOCK.md` | Internal maturity / claim statuses |
| `private/live-shadow-readiness.status` | Live shadow readiness MET / NOT MET |
| `private/live-shadow-readiness.evidence.json` | Evidence packet when live readiness is claimed |

`private/*` is gitignored except this folder’s tracked `README.md` (see `.gitignore`).

## Public language

Public docs, READMEs, playbooks, and scripts describe **capabilities and gates** only:

- adversarial suite / external holdout
- calibration + economics (in-repo)
- device-intel + ops loop (in-repo path)
- live shadow readiness (≥28d live traffic + real outcome labels)
- live device-intel (Incognia credentials + live smoke)

Do **not** publish letter grades, MET/NOT MET grade tables, or “we are at X grade” language in this repo.

## Gate script (no grades)

```bash
python3 scripts/assert_live_shadow_readiness.py
```

Fails closed if a public or private status file claims MET without valid live evidence.
