from fastapi import FastAPI, Depends, HTTPException, Header, Body
from mailbender.api import routes


def create_app(api_token: str) -> FastAPI:
    app = FastAPI(title="Mailbender")
    app.state.api_token = api_token
    app.state.repo_factory = None
    app.state.runner_factory = None
    app.state.chat_factory = None

    def require_auth(authorization: str = Header(default="")):
        expected = f"Bearer {app.state.api_token}"
        if authorization != expected:
            raise HTTPException(status_code=401, detail="Unauthorized")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/categories", dependencies=[Depends(require_auth)])
    def categories():
        return routes.list_categories(app.state.repo_factory())

    @app.post("/chat", dependencies=[Depends(require_auth)])
    def chat(question: str = Body(..., embed=True)):
        return routes.chat_answer(app.state.chat_factory(), question)

    @app.post("/run", dependencies=[Depends(require_auth)])
    def run():
        return routes.run_main(app.state.runner_factory())

    @app.get("/priorities", dependencies=[Depends(require_auth)])
    def priorities():
        return routes.priorities(app.state.repo_factory())

    @app.get("/history", dependencies=[Depends(require_auth)])
    def history(limit: int = 50):
        return routes.recent_history(app.state.repo_factory(), limit)

    @app.get("/audit", dependencies=[Depends(require_auth)])
    def audit(limit: int = 50):
        return routes.recent_audit(app.state.repo_factory(), limit)

    @app.get("/mappings", dependencies=[Depends(require_auth)])
    def list_mappings():
        return routes.list_mappings(app.state.repo_factory())

    @app.post("/mappings", dependencies=[Depends(require_auth)])
    def add_mapping(category: str = Body(...), folder: str = Body(...)):
        return routes.add_mapping(app.state.repo_factory(), category, folder)

    @app.delete("/mappings/{category}", dependencies=[Depends(require_auth)])
    def remove_mapping(category: str):
        return routes.remove_mapping(app.state.repo_factory(), category)

    return app
