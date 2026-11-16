"""The error hierarchy (docs/design.md section 5)."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional

if TYPE_CHECKING:  # pragma: no cover
    from .._generated.models import LongOperationResponse


class TransynqError(Exception):
    """Base of every error the SDK raises."""


class ConnectionError(TransynqError):
    """No answer: the connection failed (DNS, TLS, reset)."""


class TimeoutError(ConnectionError):
    """No answer within the timeout."""


class ApiError(TransynqError):
    """The API answered with an error (ProblemDetails)."""

    def __init__(
        self,
        message: str,
        *,
        status: int,
        code: Optional[str] = None,
        title: Optional[str] = None,
        detail: Optional[str] = None,
        type: Optional[str] = None,
        correlation_id: Optional[str] = None,
        raw_body: str = "",
        headers: Optional[Mapping[str, str]] = None,
        operation_id: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.title = title
        self.detail = detail
        self.type = type
        self.correlation_id = correlation_id
        self.raw_body = raw_body
        self.headers: Dict[str, str] = dict(headers or {})
        self.operation_id = operation_id


class ValidationError(ApiError):
    """400: malformed input; ``errors`` lists the messages per field."""

    def __init__(self, message: str, *, errors: Optional[Dict[str, List[str]]] = None, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.errors: Dict[str, List[str]] = errors or {}


class AuthenticationError(ApiError):
    """401: not signed in, session ended, invalid key or token."""


class PermissionDeniedError(ApiError):
    """403: signed in but not allowed (or a missing CSRF token)."""


class NotFoundError(ApiError):
    """404: missing, or outside the caller's scope."""


class ConflictError(ApiError):
    """409: the data was changed by someone else."""


class StaleVersionError(ApiError):
    """412: ``If-Match`` does not match the current ETag."""


class BusinessRuleError(ApiError):
    """422: a business rule refused the request; ``code`` is the rule."""


class RateLimitError(ApiError):
    """429: rate limited; ``retry_after`` (seconds) says when to try again."""

    def __init__(self, message: str, *, retry_after: Optional[float] = None, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class ServerError(ApiError):
    """5xx: the API failed (quote ``correlation_id`` to support)."""


class LongOperationFailedError(TransynqError):
    """A long operation ended in ``Failed``."""

    def __init__(self, message: str, operation: "LongOperationResponse") -> None:
        super().__init__(message)
        self.operation = operation


_BY_STATUS = {
    401: AuthenticationError,
    403: PermissionDeniedError,
    404: NotFoundError,
    409: ConflictError,
    412: StaleVersionError,
    422: BusinessRuleError,
}


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    return value if isinstance(value, str) else json.dumps(value)


def error_from_response(
    status: int, body: bytes, headers: Mapping[str, str], operation_id: str, retry_after: Optional[float]
) -> ApiError:
    """Builds the typed error for an error answer."""
    raw = body.decode("utf-8", errors="replace")
    problem: Dict[str, Any] = {}
    if body:
        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict):
                problem = parsed
        except ValueError:
            pass
    code, title, detail = _text(problem.get("code")), _text(problem.get("title")), _text(problem.get("detail"))
    correlation_id = _text(problem.get("correlationId")) or headers.get("x-correlation-id")
    message = f"{operation_id} failed with {status}"
    if code:
        message += f" ({code})"
    message += f": {title or 'no title'}"
    if detail:
        message += f" - {detail}"
    if correlation_id:
        message += f" [correlation id {correlation_id}]"
    kwargs: Dict[str, Any] = dict(
        status=status, code=code, title=title, detail=detail, type=_text(problem.get("type")),
        correlation_id=correlation_id, raw_body=raw, headers=headers, operation_id=operation_id,
    )
    if status == 400:
        errors: Dict[str, List[str]] = {}
        raw_errors = problem.get("errors")
        if isinstance(raw_errors, dict):
            for field, messages in raw_errors.items():
                errors[str(field)] = [str(m) for m in messages] if isinstance(messages, list) else [str(messages)]
        return ValidationError(message, errors=errors, **kwargs)
    if status == 429:
        return RateLimitError(message, retry_after=retry_after, **kwargs)
    if status >= 500:
        return ServerError(message, **kwargs)
    return _BY_STATUS.get(status, ApiError)(message, **kwargs)
