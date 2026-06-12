import hmac
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

SESSION_COOKIE = "mb_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 7  # 7 days
CSRF_MAX_AGE = 60 * 60 * 8          # 8 hours


class WebSecurity:
    """Signs/verifies the session cookie and CSRF tokens.

    The signer is keyed off MAILBENDER_SECRET_KEY (not the password), so
    rotating the password does not invalidate existing sessions.
    """

    def __init__(self, secret_key: str, password: str | None):
        self._password = password or ""
        self._session_serializer = URLSafeTimedSerializer(secret_key, salt="mb-session")
        self._csrf_serializer = URLSafeTimedSerializer(secret_key, salt="mb-csrf")

    @property
    def login_enabled(self) -> bool:
        return bool(self._password)

    def check_password(self, candidate: str) -> bool:
        if not self._password:
            return False
        return hmac.compare_digest(candidate, self._password)

    def issue_session(self) -> str:
        return self._session_serializer.dumps({"auth": True})

    def valid_session(self, token: str | None) -> bool:
        if not token:
            return False
        try:
            data = self._session_serializer.loads(token, max_age=SESSION_MAX_AGE)
        except (BadSignature, SignatureExpired):
            return False
        return isinstance(data, dict) and data.get("auth") is True

    def issue_csrf(self) -> str:
        return self._csrf_serializer.dumps("csrf")

    def valid_csrf(self, token: str | None) -> bool:
        if not token:
            return False
        try:
            value = self._csrf_serializer.loads(token, max_age=CSRF_MAX_AGE)
        except (BadSignature, SignatureExpired):
            return False
        return value == "csrf"
