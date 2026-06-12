from fastapi import Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, Response
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

    @app.post("/app/operator/run", dependencies=[Depends(require_web_session)])
    def trigger_run(request: Request, run_type: str = Form("main"),
                    csrf_token: str = Form("")):
        if not request.app.state.web_security.valid_csrf(csrf_token):
            raise HTTPException(status_code=403)
        if run_type not in _VALID_RUN:
            raise HTTPException(status_code=422)
        runner = request.app.state.runner_factory()
        getattr(runner, f"run_{run_type}")()
        _audit(request, "run_triggered", run_type)
        return Response(status_code=204)
