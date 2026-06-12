from fastapi import Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, Response, RedirectResponse
from mailbender.audit.log import AuditLogger
from mailbender.web.operator import group_by_priority, next_run_countdown

_VALID_RUN = {"main", "style", "feedback"}


def _audit(request, action, target="", result="success"):
    factory = getattr(request.app.state, "repo_factory", None)
    if not factory:
        return
    try:
        AuditLogger(factory().session).record("web", action, target, result)
    except Exception:
        pass


def _schedule_minutes(request) -> int:
    return int(getattr(request.app.state, "schedule_minutes", 0) or 0)


def register_operator_routes(app, templates, require_web_session):

    def _csrf(request):
        return request.app.state.web_security.issue_csrf()

    def _status_ctx(request):
        repo = request.app.state.repo_factory()
        last = repo.last_run_at("main")
        return {
            "last_run": last.isoformat(timespec="minutes") if last else None,
            "processed_count": repo.count_processed(),
            "countdown": next_run_countdown(last, _schedule_minutes(request)),
            "csrf_token": _csrf(request),
        }

    def _priorities_ctx(request):
        repo = request.app.state.repo_factory()
        return {"groups": group_by_priority(repo.processed_by_priority())}

    @app.get("/app/operator", response_class=HTMLResponse,
             dependencies=[Depends(require_web_session)])
    def overview(request: Request):
        ctx = {"nav": "overview"}
        ctx.update(_status_ctx(request))
        ctx.update(_priorities_ctx(request))
        return templates.TemplateResponse(request, "operator/overview.html", ctx)

    @app.get("/app/operator/status", response_class=HTMLResponse,
             dependencies=[Depends(require_web_session)])
    def status_partial(request: Request):
        return templates.TemplateResponse(
            request, "operator/_status.html", _status_ctx(request))

    @app.get("/app/operator/priorities", response_class=HTMLResponse,
             dependencies=[Depends(require_web_session)])
    def priorities_partial(request: Request):
        return templates.TemplateResponse(
            request, "operator/_priorities.html", _priorities_ctx(request))

    def _require_csrf(request, token):
        if not request.app.state.web_security.valid_csrf(token):
            raise HTTPException(status_code=403)

    @app.post("/app/operator/run", dependencies=[Depends(require_web_session)])
    def trigger_run(request: Request, run_type: str = Form("main"),
                    csrf_token: str = Form("")):
        _require_csrf(request, csrf_token)
        if run_type not in _VALID_RUN:
            raise HTTPException(status_code=422)
        _audit(request, "run_triggered", run_type)
        runner = request.app.state.runner_factory()
        getattr(runner, f"run_{run_type}")()
        return Response(status_code=204)

    @app.get("/app/operator/runs", response_class=HTMLResponse,
             dependencies=[Depends(require_web_session)])
    def runs_view(request: Request):
        repo = request.app.state.repo_factory()
        return templates.TemplateResponse(request, "operator/runs.html",
                                          {"nav": "runs", "rows": repo.recent_runs(50)})

    @app.get("/app/operator/audit", response_class=HTMLResponse,
             dependencies=[Depends(require_web_session)])
    def audit_view(request: Request):
        repo = request.app.state.repo_factory()
        return templates.TemplateResponse(request, "operator/audit.html",
                                          {"nav": "audit", "rows": repo.recent_audit(50)})

    @app.get("/app/operator/categories", response_class=HTMLResponse,
             dependencies=[Depends(require_web_session)])
    def categories_view(request: Request):
        repo = request.app.state.repo_factory()
        return templates.TemplateResponse(request, "operator/categories.html", {
            "nav": "categories", "categories": repo.list_categories(),
            "csrf_token": _csrf(request)})

    @app.post("/app/operator/categories/add",
              dependencies=[Depends(require_web_session)])
    def category_add(request: Request, name: str = Form(...),
                     description: str = Form(""), csrf_token: str = Form("")):
        _require_csrf(request, csrf_token)
        request.app.state.repo_factory().add_category(name, description)
        _audit(request, "category_add", name)
        return RedirectResponse("/app/operator/categories", status_code=303)

    @app.post("/app/operator/categories/remove",
              dependencies=[Depends(require_web_session)])
    def category_remove(request: Request, name: str = Form(...),
                        csrf_token: str = Form("")):
        _require_csrf(request, csrf_token)
        removed = request.app.state.repo_factory().remove_category(name)
        _audit(request, "category_remove", name,
               result="success" if removed else "skipped")
        return RedirectResponse("/app/operator/categories", status_code=303)

    @app.get("/app/operator/mappings", response_class=HTMLResponse,
             dependencies=[Depends(require_web_session)])
    def mappings_view(request: Request):
        repo = request.app.state.repo_factory()
        return templates.TemplateResponse(request, "operator/mappings.html", {
            "nav": "mappings", "mappings": repo.list_mappings(),
            "csrf_token": _csrf(request)})

    @app.post("/app/operator/mappings/add",
              dependencies=[Depends(require_web_session)])
    def mapping_add(request: Request, category: str = Form(...),
                    folder: str = Form(...), csrf_token: str = Form("")):
        _require_csrf(request, csrf_token)
        request.app.state.repo_factory().add_mapping(category, folder)
        _audit(request, "mapping_add", f"{category} -> {folder}")
        return RedirectResponse("/app/operator/mappings", status_code=303)

    @app.post("/app/operator/mappings/remove",
              dependencies=[Depends(require_web_session)])
    def mapping_remove(request: Request, category: str = Form(...),
                       csrf_token: str = Form("")):
        _require_csrf(request, csrf_token)
        removed = request.app.state.repo_factory().remove_mapping(category)
        _audit(request, "mapping_remove", category,
               result="success" if removed else "skipped")
        return RedirectResponse("/app/operator/mappings", status_code=303)
