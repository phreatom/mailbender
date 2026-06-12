from fastapi import FastAPI, Depends, HTTPException, Header
from mailagent.api import routes


def create_app(api_token: str) -> FastAPI:
    app = FastAPI(title="Mailagent")
    app.state.api_token = api_token
    app.state.repo_factory = None

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

    return app
