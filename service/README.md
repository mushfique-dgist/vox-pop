# vox-pop API — hosted tier

The OSS package is MIT and self-hostable. What people pay for is not the code:
it is **not maintaining nine scrapers**. Rate limits, IP blocks, HTML changes,
and the 100MB embedding model download are the actual product.

## Surfaces

| Surface | Path | Notes |
|---|---|---|
| REST | `POST /v1/search` | JSON in, JSON out |
| Remote MCP | `/mcp` | streamable HTTP — clients connect with **no install** |
| Usage | `GET /v1/me` | plan, quota, remaining |
| Health | `GET /healthz` | unauthenticated |
| Billing | `POST /webhooks/polar` | HMAC-verified |

Remote MCP is the wedge. Today a user must `pip install vox-pop`, pull a 100MB
model, and manage keys. Hosted, they paste one URL into their MCP client.

## Plans

| Plan | Requests/mo | Price |
|---|---:|---|
| free | 100 | $0 |
| pro | 10,000 | $19 |
| team | 100,000 | $99 |

## Billing: why Polar, not Stripe

**Stripe does not operate in South Korea** — you cannot open an account as a
Korean-resident individual, and Stripe cannot pay out to Korean bank accounts.

Polar is a *merchant of record*: it becomes the legal seller, collects payment,
remits global sales tax/VAT, and pays out internationally. No 사업자등록 needed.

- Polar — 4% + $0.40 (best developer experience)
- Lemon Squeezy — 5% + $0.50
- Paddle — widest tax jurisdiction coverage

Set `POLAR_WEBHOOK_SECRET` from the Polar dashboard. On `subscription.active`
a key is provisioned automatically; on cancel it drops to free.

## Security

- API keys stored as SHA-256 hashes; the raw key is returned exactly once
- Quota consumed atomically per request, per calendar month
- Webhook signatures verified with constant-time HMAC comparison
- Both REST and the MCP mount are auth-gated

## Run locally

```bash
pip install -r requirements.txt
export POLAR_WEBHOOK_SECRET=whsec_...
uvicorn app:app --port 8000
```

## Deploy (Fly.io, Tokyo region)

```bash
fly launch --no-deploy
fly volumes create voxpop_data --size 1 --region nrt
fly secrets set POLAR_WEBHOOK_SECRET=whsec_...
fly deploy
```

`auto_stop_machines` is on, so idle cost is ~$0.

## Roadmap

- Postgres when SQLite write contention appears (single-writer limit)
- Per-platform response caching — biggest margin lever
- Self-serve signup page issuing free keys
