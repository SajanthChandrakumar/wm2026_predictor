"""Authenticated scheduler entry point for provider maintenance."""

from __future__ import annotations

import hmac
import os

from fastapi import APIRouter, HTTPException, Request

from src.services.maintenance import run_maintenance


def init_router(cache_collections, odds_provider, *, cron_secret: str | None = None, now_fn=None):
    router = APIRouter(prefix="/api/internal")
    configured_secret = cron_secret if cron_secret is not None else os.getenv("CRON_SECRET", "")

    @router.post("/maintenance")
    def maintenance(request: Request, competition: str | None = None, force: bool = False):
        authorization = request.headers.get("authorization", "")
        presented = authorization[7:] if authorization.startswith("Bearer ") else ""
        if not configured_secret or not hmac.compare_digest(presented, configured_secret):
            raise HTTPException(status_code=401, detail="Unauthorized")
        return run_maintenance(
            cache_collections,
            odds_provider,
            competition=competition,
            force=force,
            now=(now_fn() if now_fn else None),
        )

    return router
