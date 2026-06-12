from pathlib import Path
from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from mailbender.web.security import SESSION_COOKIE, SESSION_MAX_AGE

_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(_DIR / "templates"))


def _security(request: Request):
    return request.app.state.web_security


def require_web_session(request: Request):
    sec = _security(request)
    token = request.cookies.get(SESSION_COOKIE)
    if not sec.valid_session(token):
        raise HTTPException(status_code=303, headers={"Location": "/login"})


def mount_web(app: FastAPI) -> None:
    app.mount("/static", StaticFiles(directory=str(_DIR / "static")), name="static")

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
        resp.delete_cookie(SESSION_COOKIE, path="/")
        return resp

    @app.get("/app", response_class=HTMLResponse,
             dependencies=[Depends(require_web_session)])
    def app_home(request: Request):
        return templates.TemplateResponse(request, "app_placeholder.html", {})
