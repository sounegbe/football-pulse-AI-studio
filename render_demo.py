"""Disposable Render demo: explicit account bootstrap and visible storage notice."""
import os
import re
import uuid
from contextlib import asynccontextmanager
from fastapi.responses import Response
from main import create_app
from app.backend.database import timestamp

if os.getenv("STUDIO_DEMO_MODE") != "1":
    raise RuntimeError("This entry point is only for an explicitly disposable demo.")
app = create_app()
original_lifespan = app.router.lifespan_context

@asynccontextmanager
async def demo_lifespan(application):
    async with original_lifespan(application):
        password_hash = os.environ["STUDIO_DEMO_PASSWORD_HASH"]
        if not re.fullmatch(r"pbkdf2_sha256\$600000\$[0-9a-f]{32}\$[0-9a-f]{64}", password_hash):
            raise RuntimeError("A valid demo account password hash is required.")
        with application.state.database.transaction(write=True) as db:
            db.execute("INSERT OR IGNORE INTO users VALUES (?,?,?,?)",
                       (str(uuid.uuid4()), "2solo", password_hash, timestamp()))
        yield

app.router.lifespan_context = demo_lifespan

@app.middleware("http")
async def demo_notice(request, call_next):
    response = await call_next(request)
    if "text/html" not in response.headers.get("content-type", ""):
        return response
    body = b"".join([chunk async for chunk in response.body_iterator]).decode("utf-8")
    notice = '<div role="status" style="position:fixed;bottom:0;left:0;right:0;z-index:9999;background:#392400;color:#fff;padding:10px;text-align:center;font:14px sans-serif">Free demo: saved work is temporary and clears on restart. Live AI is disabled. Copy important drafts before leaving.</div>'
    body = body.replace("</body>", notice + "</body>")
    headers = dict(response.headers)
    headers.pop("content-length", None)
    headers["Cache-Control"] = "no-store"
    return Response(body, status_code=response.status_code, headers=headers, background=response.background)
