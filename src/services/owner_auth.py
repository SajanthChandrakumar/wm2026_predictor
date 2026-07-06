import os

from fastapi import HTTPException, Request


def require_owner(request: Request) -> None:
    """Reject writes unless the caller sent the OWNER_SECRET header.

    If OWNER_SECRET isn't set in the environment, this is a no-op — keeps
    local/dev usage frictionless while making shared deployments read-only
    to anyone without the secret.
    """
    secret = os.getenv("OWNER_SECRET")
    if not secret:
        return
    if request.headers.get("X-Owner-Secret") != secret:
        raise HTTPException(status_code=403, detail="Owner secret required")
