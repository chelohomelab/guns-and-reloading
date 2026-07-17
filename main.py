import os
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

import database as models
from config import UPLOAD_DIR
from routers import auth, pages, firearms, scopes, tc, ammunition, components, settings, profile, admin, performance, barcode, wishlist, scanner, backup, export, ladder, product_import

app = FastAPI(title="Homelab Modular Firearm Catalog")


class NoCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if "text/html" in response.headers.get("content-type", ""):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response


class AuthMiddleware(BaseHTTPMiddleware):
    # /import/capture is exempt: it's authenticated by its own X-Import-Token header
    # (checked inside the route), not the session cookie — it's called cross-origin
    # from whatever retailer site the import bookmarklet runs on, which never has
    # this app's session cookie.
    _PUBLIC = {"/login", "/setup", "/import/capture"}

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in self._PUBLIC or path.startswith("/static/"):
            return await call_next(request)

        token = request.cookies.get("session")
        if not token:
            return RedirectResponse("/login", status_code=302)

        db = models.SessionLocal()
        try:
            sess = db.query(models.UserSession).filter(models.UserSession.token == token).first()
            now = datetime.utcnow()
            if not sess or datetime.fromisoformat(sess.expires_at) < now:
                if sess:
                    db.delete(sess)
                    db.commit()
                resp = RedirectResponse("/login", status_code=302)
                resp.delete_cookie("session")
                return resp
            user = db.query(models.User).filter(models.User.id == sess.user_id).first()
            if not user or not user.is_active:
                db.delete(sess)
                db.commit()
                resp = RedirectResponse("/login", status_code=302)
                resp.delete_cookie("session")
                return resp
            db.expunge(user)
            request.state.user = user
        finally:
            db.close()

        return await call_next(request)


app.add_middleware(NoCacheMiddleware)
app.add_middleware(AuthMiddleware)
models.init_db()
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(auth.router)
app.include_router(pages.router)
app.include_router(firearms.router)
app.include_router(scopes.router)
app.include_router(tc.router)
app.include_router(ammunition.router)
app.include_router(components.router)
app.include_router(settings.router)
app.include_router(profile.router)
app.include_router(admin.router)
app.include_router(performance.router)
app.include_router(ladder.router)
app.include_router(barcode.router)
app.include_router(wishlist.router)
app.include_router(scanner.router)
app.include_router(backup.router)
app.include_router(export.router)
app.include_router(product_import.router)
