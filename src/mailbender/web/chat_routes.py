import json
from fastapi import Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from mailbender.audit.log import AuditLogger


def _audit(request, actor, action, target="", result="success"):
    factory = getattr(request.app.state, "repo_factory", None)
    if not factory:
        return
    try:
        AuditLogger(factory().session).record(actor, action, target, result)
    except Exception:
        pass


def register_chat_routes(app, templates, require_web_session):

    def _csrf(request):
        return request.app.state.web_security.issue_csrf()

    @app.get("/app", response_class=HTMLResponse,
             dependencies=[Depends(require_web_session)])
    def chat_home(request: Request):
        repo = request.app.state.repo_factory()
        convs = repo.list_conversations()
        active = convs[0] if convs else None
        if active is not None:
            active = repo.get_conversation(active.id)
        return templates.TemplateResponse(request, "chat.html", {
            "conversations": convs, "active": active,
            "csrf_token": _csrf(request)})

    @app.get("/app/chat/{cid}", response_class=HTMLResponse,
             dependencies=[Depends(require_web_session)])
    def chat_thread(request: Request, cid: int):
        repo = request.app.state.repo_factory()
        active = repo.get_conversation(cid)
        if active is None:
            raise HTTPException(status_code=404)
        return templates.TemplateResponse(request, "chat.html", {
            "conversations": repo.list_conversations(), "active": active,
            "csrf_token": _csrf(request)})

    @app.post("/app/chat/new", dependencies=[Depends(require_web_session)])
    def chat_new(request: Request, csrf_token: str = Form("")):
        if not request.app.state.web_security.valid_csrf(csrf_token):
            raise HTTPException(status_code=403)
        conv = request.app.state.repo_factory().create_conversation("New chat")
        return RedirectResponse(url=f"/app/chat/{conv.id}", status_code=303)

    @app.post("/app/chat/{cid}/message", response_class=HTMLResponse,
              dependencies=[Depends(require_web_session)])
    def chat_message(request: Request, cid: int, question: str = Form(...),
                     csrf_token: str = Form("")):
        if not request.app.state.web_security.valid_csrf(csrf_token):
            raise HTTPException(status_code=403)
        repo = request.app.state.repo_factory()
        conv = repo.get_conversation(cid)
        if conv is None:
            raise HTTPException(status_code=404)
        history = [(m.role, m.text) for m in conv.messages]
        repo.append_message(cid, "user", question, sources=[])
        chat = request.app.state.chat_factory()
        _audit(request, "web", "chat_query")
        _audit(request, "web", "provider_use", type(chat.provider).__name__)
        answer = chat.ask(question, history=history)
        sources = [{"uid": s.uid, "subject": s.subject} for s in answer.sources]
        repo.append_message(cid, "assistant", answer.text, sources=sources)

        class _M:
            def __init__(self, role, text, sources_json):
                self.role = role; self.text = text; self.sources_json = sources_json
        turns = [_M("user", question, "[]"),
                 _M("assistant", answer.text, json.dumps(sources))]
        html = "".join(
            templates.get_template("_chat_turn.html").render(m=m) for m in turns)
        return HTMLResponse(html)
