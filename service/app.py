"""vox-pop hosted API.

Two surfaces over the same engine:
  * REST      ``POST /v1/search``
  * Remote MCP ``/mcp`` (streamable HTTP) — clients connect with no install

Auth is a bearer API key; quota is enforced per key per calendar month.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import billing
import db
from vox_pop.core import (
    format_context,
    get_default_providers,
    get_provider,
    list_providers,
    search_multiple,
)

MCP_PATH = "/mcp"


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    yield


app = FastAPI(
    title="vox-pop API",
    version="0.2.0",
    description="Public opinion for LLMs — 9 discussion platforms behind one endpoint.",
    lifespan=lifespan,
)


class Principal:
    def __init__(self, row: Any, used: int) -> None:
        self.key_hash = row["key_hash"]
        self.email = row["email"]
        self.plan = row["plan"]
        self.quota = row["quota"]
        self.used = used


async def require_key(authorization: str = Header(default="")) -> Principal:
    """Validate bearer key and consume one unit of quota."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing bearer token. Send 'Authorization: Bearer vp_live_...'")
    raw = authorization.removeprefix("Bearer ").strip()
    row = db.lookup(raw)
    if row is None:
        raise HTTPException(401, "Invalid or revoked API key")
    allowed, used = db.consume(row["key_hash"], row["quota"])
    if not allowed:
        raise HTTPException(
            429,
            f"Monthly quota exhausted ({row['quota']} requests on plan '{row['plan']}').",
        )
    return Principal(row, used)


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    platforms: list[str] | None = Field(
        default=None, description="Omit for automatic semantic routing."
    )
    limit: int = Field(default=5, ge=1, le=25)


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    return {"status": "ok", "platforms": list_providers()}


@app.get("/v1/me")
async def me(p: Principal = Depends(require_key)) -> dict[str, Any]:
    return {
        "email": p.email,
        "plan": p.plan,
        "quota": p.quota,
        "used_this_month": p.used,
        "remaining": max(0, p.quota - p.used),
    }


@app.post("/v1/search")
async def v1_search(req: SearchRequest, p: Principal = Depends(require_key)) -> dict[str, Any]:
    if req.platforms:
        unknown = set(req.platforms) - set(list_providers())
        if unknown:
            raise HTTPException(400, f"Unknown platforms: {sorted(unknown)}")
        providers = [get_provider(n) for n in req.platforms]
    else:
        providers = get_default_providers()

    results = await search_multiple(
        req.query, providers=providers, limit_per_platform=req.limit
    )
    return {
        "query": req.query,
        "quota": {"used": p.used, "limit": p.quota},
        "results": [
            {
                "platform": r.platform,
                "total_found": r.total_found,
                "count": len(r.results),
                "error": r.error,
                "items": [
                    {
                        "text": i.text[:1500],
                        "url": i.url,
                        "author": i.author,
                        "score": i.score,
                        "num_replies": i.num_replies,
                        "created_at": i.created_at,
                    }
                    for i in r.results
                ],
            }
            for r in results
        ],
    }


@app.post("/webhooks/polar")
async def polar_webhook(request: Request) -> dict[str, Any]:
    """Provision or downgrade keys when Polar reports a subscription change."""
    raw = await request.body()
    sig = request.headers.get("webhook-signature", "")
    if not billing.verify(raw, sig):
        raise HTTPException(401, "Invalid webhook signature")
    import json as _json

    try:
        event = _json.loads(raw)
    except ValueError:
        raise HTTPException(400, "Malformed JSON body")
    return billing.handle(event)


@app.exception_handler(HTTPException)
async def http_exc(request: Request, exc: HTTPException):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


# --- Remote MCP endpoint -------------------------------------------------
# Reuses the existing FastMCP tools verbatim; clients connect over HTTP
# with no pip install. Auth is enforced by the ASGI wrapper below.
from vox_pop.server import mcp  # noqa: E402

_mcp_asgi = mcp.streamable_http_app()


async def _guarded_mcp(scope, receive, send):
    if scope["type"] == "http":
        headers = {k.decode(): v.decode() for k, v in scope.get("headers", [])}
        auth = headers.get("authorization", "")
        raw = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""
        row = db.lookup(raw) if raw else None
        if row is None:
            await JSONResponse({"error": "Invalid or missing API key"}, status_code=401)(
                scope, receive, send
            )
            return
        allowed, _ = db.consume(row["key_hash"], row["quota"])
        if not allowed:
            await JSONResponse({"error": "Monthly quota exhausted"}, status_code=429)(
                scope, receive, send
            )
            return
    await _mcp_asgi(scope, receive, send)


app.mount(MCP_PATH, _guarded_mcp)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
