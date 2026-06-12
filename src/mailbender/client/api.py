import httpx


class ApiError(Exception):
    def __init__(self, message: str, *, exit_code: int = 1):
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code


class NotConfigured(ApiError):
    pass


class ApiClient:
    def __init__(self, config, *, transport=None, timeout: float = 10.0):
        if not config.url or not config.token:
            raise NotConfigured(
                "Not logged in — run `mailbender login` "
                "(or set MAILBENDER_API_URL/MAILBENDER_API_TOKEN).")
        self._url = config.url.rstrip("/")
        self._client = httpx.Client(
            base_url=self._url,
            headers={"Authorization": f"Bearer {config.token}"},
            timeout=timeout, transport=transport)

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _request(self, method, path, **kw):
        try:
            resp = self._client.request(method, path, **kw)
        except httpx.ConnectError:
            raise ApiError(
                f"API unreachable at {self._url} — is the server running?")
        except httpx.HTTPError as exc:
            raise ApiError(f"request failed: {exc}")
        if resp.status_code == 401:
            raise ApiError("unauthorized — run `mailbender login` again.")
        if resp.status_code == 404:
            raise ApiError("not found (404).")
        if resp.status_code >= 500:
            raise ApiError(f"server error ({resp.status_code}): {resp.text}")
        if resp.status_code >= 400:
            raise ApiError(f"request rejected ({resp.status_code}): {resp.text}")
        return resp

    def health(self):
        return self._request("GET", "/health").json()

    def chat(self, question):
        return self._request("POST", "/chat", json={"question": question}).json()

    def run(self, run_type="main"):
        return self._request("POST", "/run", json={"run_type": run_type}).json()

    def priorities(self):
        return self._request("GET", "/priorities").json()

    def history(self, limit=50):
        return self._request("GET", "/history", params={"limit": limit}).json()

    def audit(self, limit=50):
        return self._request("GET", "/audit", params={"limit": limit}).json()

    def categories_list(self):
        return self._request("GET", "/categories").json()

    def categories_add(self, name, description=""):
        return self._request("POST", "/categories",
                             json={"name": name, "description": description}).json()

    def categories_remove(self, name):
        return self._request("DELETE", f"/categories/{name}").json()

    def categories_seed(self):
        return self._request("POST", "/categories/seed").json()

    def mappings_list(self):
        return self._request("GET", "/mappings").json()

    def mappings_add(self, category, folder):
        return self._request("POST", "/mappings",
                             json={"category": category, "folder": folder}).json()

    def mappings_remove(self, category):
        return self._request("DELETE", f"/mappings/{category}").json()
