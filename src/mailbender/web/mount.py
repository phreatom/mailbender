import json as _json
from pathlib import Path
from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from mailbender.web.security import SESSION_COOKIE, SESSION_MAX_AGE

_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(_DIR / "templates"))


class NotAuthenticated(Exception):
    pass


def _security(request: Request):
    return request.app.state.web_security


def require_web_session(request: Request):
    sec = _security(request)
    token = request.cookies.get(SESSION_COOKIE)
    if not sec.valid_session(token):
        raise NotAuthenticated()


def mount_web(app: FastAPI) -> None:
    @app.exception_handler(NotAuthenticated)
    async def _redirect_to_login(request, exc):
        return RedirectResponse(url="/login", status_code=303)

    app.mount("/static", StaticFiles(directory=str(_DIR / "static")), name="static")
    templates.env.filters["fromjson"] = lambda s: _json.loads(s) if s else []

    @app.get("/login", response_class=HTMLResponse)
    def login_form(request: Request):
        sec = _security(request)
        return templates.TemplateResponse(
            request, "login.html",
            {"login_enabled": sec.login_enabled, "error": None})

    @app.post("/login")
    def login_submit(request: Request, password: str = Form("")):
        sec = _security(request)
        if not sec.check_password(password):
            return templates.TemplateResponse(
                request, "login.html",
                {"login_enabled": sec.login_enabled,
                 "error": "Password incorrect."},
                status_code=200)
        resp = RedirectResponse(url="/app", status_code=303)
        resp.set_cookie(
            SESSION_COOKIE, sec.issue_session(),
            max_age=SESSION_MAX_AGE, httponly=True, samesite="lax",
            secure=request.url.scheme == "https", path="/")
        return resp

    @app.get("/logout")
    def logout():
        resp = RedirectResponse(url="/login", status_code=303)
        resp.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="lax")
        return resp

    from mailbender.web.chat_routes import register_chat_routes
    register_chat_routes(app, templates, require_web_session)
