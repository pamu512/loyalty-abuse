# Loyalty Abuse v2 Ops Runbook

## Deploy

### Docker Compose (prod profile)

```bash
export LOYALTY_ABUSE_BOOTSTRAP_ADMIN_KEY='…'
docker compose --profile prod up -d --build
curl -sf localhost:8080/healthz
curl -sf localhost:8080/readyz
```

### Kubernetes

```bash
kubectl create secret generic loyalty-abuse-secrets \
  --from-literal=bootstrap_admin_key='…'
kubectl apply -f deploy/k8s/deployment.yaml
kubectl apply -f deploy/k8s/service.yaml
kubectl rollout status deploy/loyalty-abuse
```

## API key rotation

1. Mint a new tenant key with bootstrap admin:
   `POST /v1/admin/keys` with `Authorization: Bearer $BOOTSTRAP` body `{"tenant_id":"…","name":"…"}`.
2. Distribute the returned `api_key` (shown once).
3. Revoke the old key in SQLite (`UPDATE api_keys SET revoked=1 WHERE key_id=…`) — add admin revoke endpoint in a follow-up if needed.
4. Confirm clients use the new key; `/v1/evaluate` without Bearer → 401.

## Shadow → live flip

1. `GET /v1/admin/tenants/{tenant}/mode` — confirm current mode.
2. Deploy `friction_v3_0` and run adversarial + external holdout green.
3. Keep tenant in `shadow` while comparing `/v1/analytics/summary` shadow vs live insult proxies.
4. `PUT /v1/admin/tenants/{tenant}/mode` `{"evaluation_mode":"live"}`.
5. Export audit: `GET /v1/export/decisions`.

## Metrics

- Scrapes: `GET /metrics` (Prometheus text).
- Logs: JSON lines with `request_id`, `path`, `status`, `latency_ms`.

## Auth note

Production must **not** set `LOYALTY_ABUSE_AUTH_DISABLED`. That flag is test-only.
