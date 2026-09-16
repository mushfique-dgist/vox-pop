"""Polar (merchant-of-record) webhook handling.

Polar is the seller of record: it collects payment, handles global sales tax,
and pays out internationally — so no Korean business registration is required.

Set POLAR_WEBHOOK_SECRET from the Polar dashboard. Events we act on:
  subscription.active / subscription.created  -> provision or upgrade
  subscription.canceled / subscription.revoked -> downgrade to free
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os

import db

SECRET = os.environ.get("POLAR_WEBHOOK_SECRET", "")

# Map Polar product slugs to internal plans.
PRODUCT_PLANS = {
    "vox-pop-pro": "pro",
    "vox-pop-team": "team",
}


def verify(payload: bytes, sig_header: str) -> bool:
    """Constant-time HMAC-SHA256 check (standard-webhooks format).

    The header may carry several space-separated `v1,<b64sig>` values during
    secret rotation; any one matching is sufficient.
    """
    if not SECRET or not sig_header:
        return False
    secret = SECRET
    if secret.startswith("whsec_"):
        secret = secret[len("whsec_") :]
    try:
        key = base64.b64decode(secret)
    except Exception:
        key = secret.encode()
    expected = hmac.new(key, payload, hashlib.sha256).digest()
    for part in sig_header.split():
        candidate = part.split(",", 1)[-1]
        try:
            if hmac.compare_digest(expected, base64.b64decode(candidate)):
                return True
        except Exception:
            continue
    return False


def handle(event: dict) -> dict:
    """Apply a verified Polar event. Returns a small audit dict."""
    etype = event.get("type", "")
    data = event.get("data", {}) or {}
    customer = data.get("customer") or {}
    email = (customer.get("email") or data.get("customer_email") or "").strip().lower()
    if not email:
        return {"ok": False, "reason": "no customer email in event"}

    if etype in ("subscription.active", "subscription.created", "subscription.updated"):
        product = (data.get("product") or {}).get("slug") or data.get("product_id", "")
        plan = PRODUCT_PLANS.get(product, "pro")
        changed = db.set_plan(email, plan)
        if changed == 0:
            raw = db.issue_key(email, plan)
            return {"ok": True, "action": "provisioned", "email": email,
                    "plan": plan, "api_key": raw}
        return {"ok": True, "action": "upgraded", "email": email,
                "plan": plan, "keys": changed}

    if etype in ("subscription.canceled", "subscription.revoked"):
        changed = db.set_plan(email, "free")
        return {"ok": True, "action": "downgraded", "email": email, "keys": changed}

    return {"ok": True, "action": "ignored", "type": etype}
