"""Credentials matching the API's real mechanisms (docs/design.md section 3)."""
from __future__ import annotations

import asyncio
import datetime as _dt
import json
import threading
from abc import ABC, abstractmethod
from typing import Any, Callable, Generic, Iterable, Optional, TypeVar

from .errors import AuthenticationError
from .http import API_KEY_HEADER, CSRF_HEADER, CredentialRequest, SignInResponse

S = TypeVar("S")


class Credential(ABC):
    """How requests authenticate. Implementations must be safe to share between threads (sync) or tasks (async)."""

    @abstractmethod
    def apply(self, request: CredentialRequest) -> None:
        """Adds headers before a request is sent (sync clients), signing in first when needed."""

    async def apply_async(self, request: CredentialRequest) -> None:
        """Adds headers before a request is sent (async clients)."""
        self.apply(request)

    def refresh_after_unauthorized(self, request: CredentialRequest) -> bool:
        """Called on a 401; True when one retry with fresh credentials is worthwhile."""
        return False

    async def refresh_after_unauthorized_async(self, request: CredentialRequest) -> bool:
        return self.refresh_after_unauthorized(request)


class ApiKeyCredential(Credential):
    """An API client key, sent as ``X-Transynq-APIKey``. The key's company is the tenant; no cookie, no CSRF."""

    def __init__(self, api_key: str) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("api_key is required")
        self._key = api_key

    def apply(self, request: CredentialRequest) -> None:
        request.set_header(API_KEY_HEADER, self._key)

    def __repr__(self) -> str:
        return "ApiKeyCredential([redacted])"


class DriverTokenCredential(Credential):
    """An existing driver-app token (``Authorization: Bearer <token>``), valid for ``/api/v1/driver/*``."""

    def __init__(self, token: str) -> None:
        if not token or not token.strip():
            raise ValueError("token is required")
        self._token = token

    def apply(self, request: CredentialRequest) -> None:
        request.set_header("Authorization", "Bearer " + self._token)

    def __repr__(self) -> str:
        return "DriverTokenCredential([redacted])"


def _parse_instant(value: Any) -> Optional[_dt.datetime]:
    if not isinstance(value, str):
        return None
    try:
        parsed = _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=_dt.timezone.utc)


class SignInCredential(Credential, Generic[S]):
    """Base of credentials that sign in: single-flight sign-in, refresh before expiry and once after a 401."""

    refresh_margin = _dt.timedelta(seconds=60)

    def __init__(self) -> None:
        self._state: Optional[S] = None
        self._lock = threading.Lock()
        self._async_lock: Optional[asyncio.Lock] = None
        self.sign_in_count = 0
        self.clock: Callable[[], _dt.datetime] = lambda: _dt.datetime.now(_dt.timezone.utc)

    @property
    def state(self) -> Optional[S]:
        return self._state

    def reset(self) -> None:
        """Forgets the signed-in state (after a sign-out); the next request signs in again."""
        self._state = None

    def _fresh(self, state: Optional[S]) -> bool:
        if state is None:
            return False
        expires = self._expires(state)
        return expires is None or expires - self.refresh_margin > self.clock()

    def apply(self, request: CredentialRequest) -> None:
        state = self._state
        if not self._fresh(state):
            with self._lock:
                state = self._state
                if not self._fresh(state):
                    state = self._from_answer(self._sign_in_call(request.transport.post_json))
                    self.sign_in_count += 1
                    self._state = state
        assert state is not None
        request.applied_state = state
        self._apply(request, state)

    async def apply_async(self, request: CredentialRequest) -> None:
        state = self._state
        if not self._fresh(state):
            if self._async_lock is None:
                self._async_lock = asyncio.Lock()
            async with self._async_lock:
                state = self._state
                if not self._fresh(state):
                    state = self._from_answer(await self._sign_in_call(request.transport.post_json))
                    self.sign_in_count += 1
                    self._state = state
        assert state is not None
        request.applied_state = state
        self._apply(request, state)

    def refresh_after_unauthorized(self, request: CredentialRequest) -> bool:
        with self._lock:
            # only drop the state the failed request used; another caller may already have signed in again
            if self._state is request.applied_state:
                self._state = None
        return True

    async def refresh_after_unauthorized_async(self, request: CredentialRequest) -> bool:
        if self._state is request.applied_state:
            self._state = None
        return True

    @abstractmethod
    def _sign_in_call(self, post_json: Callable[..., Any]) -> Any:
        """Calls ``post_json(path, body, headers, operation_id)`` (returns its result or awaitable)."""

    @abstractmethod
    def _from_answer(self, answer: SignInResponse) -> S: ...

    @abstractmethod
    def _expires(self, state: S) -> Optional[_dt.datetime]: ...

    @abstractmethod
    def _apply(self, request: CredentialRequest, state: S) -> None: ...


class Session:
    """A signed-in session (the cookie and CSRF token are never printed)."""

    def __init__(self, cookie: str, csrf_token: str, expires_utc: Optional[_dt.datetime], me: Any) -> None:
        self.cookie = cookie
        self.csrf_token = csrf_token
        self.expires_utc = expires_utc
        self.me = me

    def __repr__(self) -> str:
        return f"Session(expires_utc={self.expires_utc!r}, [redacted])"


def session_cookie(set_cookies: Iterable[str]) -> Optional[str]:
    """The ``name=value`` of the session cookie (``tq_session`` or ``__Host-tq_session``)."""
    for header in set_cookies:
        pair = header.split(";", 1)[0].strip()
        name, sep, value = pair.partition("=")
        if sep and value and name.endswith("tq_session"):
            return pair
    return None


class SessionCredential(SignInCredential[Session]):
    """
    A user session: ``POST /api/v1/auth/login`` with user name and password, then the session cookie on every request
    and ``X-CSRF-Token`` on every unsafe one. Signs in again before the session expires and once after a 401.
    """

    def __init__(self, user_name: str, password: str) -> None:
        super().__init__()
        if not user_name or not password:
            raise ValueError("user_name and password are required")
        self._user_name = user_name
        self._password = password

    @property
    def me(self) -> Any:
        """The login answer (``MeResponse`` as a dict), or ``None`` before the first request."""
        return self._state.me if self._state else None

    def _sign_in_call(self, post_json: Callable[..., Any]) -> Any:
        body = json.dumps({"userName": self._user_name, "password": self._password}).encode("utf-8")
        # without a session the CSRF check only needs a non-empty value
        return post_json("/api/v1/auth/login", body, {CSRF_HEADER: "transynq-sdk"}, "Login")

    def _from_answer(self, answer: SignInResponse) -> Session:
        cookie = session_cookie(answer.set_cookies)
        if cookie is None:
            raise AuthenticationError("Login answered without a session cookie.", status=answer.status_code, operation_id="Login")
        me = json.loads(answer.body) if answer.body else {}
        csrf = me.get("csrfToken") if isinstance(me, dict) else None
        if not csrf:
            raise AuthenticationError("Login answered without a csrfToken.", status=answer.status_code, operation_id="Login")
        return Session(cookie, csrf, _parse_instant(me.get("sessionExpiresUtc")), me)

    def _expires(self, state: Session) -> Optional[_dt.datetime]:
        return state.expires_utc

    def _apply(self, request: CredentialRequest, state: Session) -> None:
        request.set_header("Cookie", state.cookie)
        if request.is_unsafe:
            request.set_header(CSRF_HEADER, state.csrf_token)

    def __repr__(self) -> str:
        return f"SessionCredential({self._user_name!r}, [redacted])"


class DriverToken:
    def __init__(self, token: str, expires_utc: Optional[_dt.datetime], session: Any) -> None:
        self.token = token
        self.expires_utc = expires_utc
        self.session = session

    def __repr__(self) -> str:
        return f"DriverToken(expires_utc={self.expires_utc!r}, [redacted])"


class DriverLoginCredential(SignInCredential[DriverToken]):
    """Driver-app sign-in (``POST /api/v1/driver/login``), then ``Authorization: Bearer <token>``."""

    def __init__(self, company_code: str, pin: str, device_id: str, push_token: str, app_version: str, platform: str) -> None:
        super().__init__()
        self._login = {"companyCode": company_code, "pin": pin, "deviceId": device_id, "pushToken": push_token,
                       "appVersion": app_version, "platform": platform}

    @property
    def session(self) -> Any:
        """The last ``DriverSession`` (as a dict), or ``None``."""
        return self._state.session if self._state else None

    def _sign_in_call(self, post_json: Callable[..., Any]) -> Any:
        return post_json("/api/v1/driver/login", json.dumps(self._login).encode("utf-8"), {}, "DriverLogin")

    def _from_answer(self, answer: SignInResponse) -> DriverToken:
        session = json.loads(answer.body) if answer.body else {}
        token = session.get("token") if isinstance(session, dict) else None
        if not token:
            raise AuthenticationError("DriverLogin answered without a token.", status=answer.status_code, operation_id="DriverLogin")
        return DriverToken(token, _parse_instant(session.get("expiresUtc")), session)

    def _expires(self, state: DriverToken) -> Optional[_dt.datetime]:
        return state.expires_utc

    def _apply(self, request: CredentialRequest, state: DriverToken) -> None:
        request.set_header("Authorization", "Bearer " + state.token)

    def __repr__(self) -> str:
        return "DriverLoginCredential([redacted])"
