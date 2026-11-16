"""Request building and the sync/async send loops: credentials, headers, timeouts, retries, error mapping."""
from __future__ import annotations

import asyncio
import email.utils
import http.cookiejar
import json
import logging
import random
import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple, Union
from urllib.parse import quote

import httpx
from pydantic import TypeAdapter

from . import jsonenc
from .errors import ConnectionError, TimeoutError, error_from_response
from .types import ApiResponse, FileDownload, FileUpload, Headers, RequestOptions, ResponseBody, file_name_of

SDK_VERSION = "1.0.2"
USER_AGENT_PREFIX = "transynq-sdk-python/"
API_KEY_HEADER = "X-Transynq-APIKey"
CSRF_HEADER = "X-CSRF-Token"
CORRELATION_HEADER = "X-Correlation-Id"
IDEMPOTENCY_HEADER = "Idempotency-Key"

_REDACTED = {"authorization", "cookie", "set-cookie", API_KEY_HEADER.lower(), CSRF_HEADER.lower(), "proxy-authorization"}
_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "PUT", "DELETE"}

_log = logging.getLogger("transynq")

Hook = Callable[[Dict[str, Any]], None]


@dataclass
class ClientOptions:
    """Settings shared by :class:`TransynqClient` and :class:`AsyncTransynqClient`."""

    base_url: str
    credential: Optional[Any] = None
    timeout: float = 60.0
    max_retries: int = 2
    retry_base_delay: float = 0.5
    max_retry_delay: float = 8.0
    max_retry_after: float = 60.0
    user_agent_suffix: Optional[str] = None
    logger: Optional[logging.Logger] = None
    on_request: Optional[Hook] = None
    on_response: Optional[Hook] = None
    sleep: Optional[Callable[[float], Any]] = None
    """Replaces the wait between retries and polls (tests). Sync clients call it; async clients await it when it returns an awaitable."""
    jitter: Callable[[], float] = field(default=random.random)

    def validate(self) -> None:
        if not self.base_url or not self.base_url.startswith(("http://", "https://")):
            raise ValueError("base_url must be an absolute http(s) URL")
        if self.max_retries < 0:
            raise ValueError("max_retries must be 0 or more")


def new_correlation_id() -> str:
    return secrets.token_hex(16)


def _no_cookie_jar() -> http.cookiejar.CookieJar:
    """The SDK keeps the session cookie itself; the HTTP client's jar stores nothing."""
    return http.cookiejar.CookieJar(policy=http.cookiejar.DefaultCookiePolicy(allowed_domains=[]))


def default_sync_client() -> httpx.Client:
    return httpx.Client(cookies=_no_cookie_jar(), follow_redirects=False)


def default_async_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(cookies=_no_cookie_jar(), follow_redirects=False)


class ApiRequest:
    """A request built by a generated service method."""

    def __init__(self, method: str, path_template: str, operation_id: str) -> None:
        self.method = method
        self.path_template = path_template
        self.operation_id = operation_id
        self._path: Dict[str, str] = {}
        self.query_values: List[Tuple[str, str]] = []
        self.json: Optional[bytes] = None
        self.has_client_id = False
        self.form_texts: List[Tuple[str, str]] = []
        self.form_files: List[Tuple[str, FileUpload]] = []

    def path(self, name: str, value: Any) -> None:
        if value is None:
            raise ValueError(f"{self.operation_id}: path parameter {name} is required")
        self._path[name] = quote(jsonenc.format_scalar(value), safe="")

    def query(self, name: str, value: Any) -> None:
        if value is None:
            return
        if isinstance(value, (list, tuple)):
            for v in value:
                self.query(name, v)
            return
        self.query_values.append((name, jsonenc.format_scalar(value)))

    def json_body(self, body: Any, client_id_create: bool = False) -> None:
        if body is None:
            return
        self.json = jsonenc.dumps(body)
        self.has_client_id = client_id_create and carries_client_id(self.json)

    def form_text(self, name: str, value: Any) -> None:
        if value is not None:
            self.form_texts.append((name, jsonenc.format_scalar(value)))

    def form_file(self, name: str, value: Union[FileUpload, Sequence[FileUpload], None]) -> None:
        if value is None:
            return
        if isinstance(value, FileUpload):
            self.form_files.append((name, value))
        else:
            for f in value:
                self.form_files.append((name, f))

    @property
    def is_multipart(self) -> bool:
        return bool(self.form_files) or bool(self.form_texts)

    def url(self, base_url: str) -> str:
        path = self.path_template
        for name, value in self._path.items():
            path = path.replace("{" + name + "}", value)
        if "{" in path:
            raise ValueError(f"{self.operation_id}: path parameter missing in {path}")
        url = base_url.rstrip("/") + path
        if self.query_values:
            url += "?" + "&".join(f"{quote(k, safe='')}={quote(v, safe='')}" for k, v in self.query_values)
        return url

    def retry_safe(self, options: Optional[RequestOptions]) -> bool:
        if any(not f.replayable for _, f in self.form_files):
            return False
        return self.method in _SAFE_METHODS or bool(options and options.idempotency_key) or self.has_client_id


def carries_client_id(body: bytes) -> bool:
    try:
        parsed = json.loads(body)
    except ValueError:
        return False
    if not isinstance(parsed, dict) or not isinstance(parsed.get("id"), str):
        return False
    try:
        return uuid.UUID(parsed["id"]).int != 0
    except ValueError:
        return False


def response_headers(response: httpx.Response) -> Headers:
    h = Headers()
    for k, v in response.headers.multi_items():
        k = k.lower()
        h[k] = f"{h[k]}, {v}" if k in h else v
    return h


def redact(headers: Mapping[str, str]) -> Dict[str, str]:
    return {k: ("[redacted]" if k.lower() in _REDACTED else v) for k, v in headers.items()}


def parse_retry_after(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, when.timestamp() - time.time())


@dataclass
class SignInResponse:
    status_code: int
    body: bytes
    set_cookies: List[str]


class CredentialRequest:
    """A request as a credential sees it."""

    def __init__(self, method: str, url: str, headers: Dict[str, str], transport: Any) -> None:
        self.method = method
        self.url = url
        self.headers = headers
        self.transport = transport
        self.applied_state: Any = None

    @property
    def is_unsafe(self) -> bool:
        return self.method not in ("GET", "HEAD", "OPTIONS")

    def set_header(self, name: str, value: str) -> None:
        for k in [k for k in self.headers if k.lower() == name.lower()]:
            del self.headers[k]
        self.headers[name] = value


class _TransportBase:
    def __init__(self, options: ClientOptions) -> None:
        options.validate()
        self.options = options
        suffix = (" " + options.user_agent_suffix.strip()) if options.user_agent_suffix else ""
        self.user_agent = USER_AGENT_PREFIX + SDK_VERSION + suffix
        self._adapters: Dict[Any, TypeAdapter[Any]] = {}

    def _headers(self, correlation_id: str, options: Optional[RequestOptions]) -> Dict[str, str]:
        h = {"User-Agent": self.user_agent, "Accept": "application/json", CORRELATION_HEADER: correlation_id}
        if options:
            if options.if_match:
                h["If-Match"] = options.if_match
            if options.idempotency_key:
                h[IDEMPOTENCY_HEADER] = options.idempotency_key
            h.update(options.headers)
        return h

    def _build(self, client: Union[httpx.Client, httpx.AsyncClient], req: ApiRequest, headers: Dict[str, str], timeout: float) -> httpx.Request:
        url = req.url(self.options.base_url)
        if req.json is not None:
            headers = {**headers, "Content-Type": "application/json; charset=utf-8"}
            return client.build_request(req.method, url, headers=headers, content=req.json, timeout=timeout)
        if req.is_multipart:
            files = [(name, f.to_httpx()) for name, f in req.form_files]
            data: Dict[str, Any] = {}
            for name, value in req.form_texts:
                data.setdefault(name, []).append(value)
            return client.build_request(req.method, url, headers=headers, data=data, files=files or None, timeout=timeout)
        return client.build_request(req.method, url, headers=headers, timeout=timeout)

    def _back_off(self, attempt: int) -> float:
        o = self.options
        return min(o.max_retry_delay, o.retry_base_delay * (2.0 ** (attempt - 1))) * o.jitter()

    def _log(self, op: str, attempt: int, outcome: Any, elapsed: float, correlation_id: str) -> None:
        logger = self.options.logger or _log
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Transynq %s attempt %d -> %s in %.0f ms (correlation id %s)", op, attempt, outcome, elapsed * 1000, correlation_id)

    def _hook_request(self, req: ApiRequest, url: str, attempt: int, headers: Mapping[str, str]) -> Dict[str, Any]:
        info = {"method": req.method, "url": url, "operation_id": req.operation_id, "attempt": attempt, "headers": redact(headers)}
        if self.options.on_request:
            self.options.on_request(info)
        return info

    def _hook_response(self, info: Dict[str, Any], response: httpx.Response, elapsed: float) -> None:
        if self.options.on_response:
            self.options.on_response({"request": info, "status_code": response.status_code, "elapsed": elapsed,
                                      "headers": redact(dict(response.headers))})

    def _decide_retry(self, req: ApiRequest, response: httpx.Response, attempt: int, max_retries: int, retry_safe: bool) -> Optional[float]:
        retry_after = parse_retry_after(response.headers.get("retry-after"))
        if (response.status_code in _RETRYABLE_STATUS and (retry_safe or response.status_code == 429)
                and attempt <= max_retries and (retry_after is None or retry_after <= self.options.max_retry_after)):
            return retry_after if retry_after is not None else self._back_off(attempt)
        return None

    def _error(self, req: ApiRequest, response: httpx.Response, body: bytes) -> Exception:
        return error_from_response(response.status_code, body, response_headers(response), req.operation_id,
                                   parse_retry_after(response.headers.get("retry-after")))

    def _adapter(self, type_: Any) -> "TypeAdapter[Any]":
        key = repr(type_)
        adapter = self._adapters.get(key)
        if adapter is None:
            adapter = TypeAdapter(type_)
            self._adapters[key] = adapter
        return adapter

    def _parse(self, type_: Any, body: bytes) -> Any:
        return None if not body else self._adapter(type_).validate_python(jsonenc.loads(body))


class SyncTransport(_TransportBase):
    """The blocking send loop over ``httpx.Client``."""

    def __init__(self, options: ClientOptions, client: Optional[httpx.Client] = None) -> None:
        super().__init__(options)
        self.client = client or default_sync_client()
        self.owns_client = client is None

    def _sleep(self, seconds: float) -> None:
        (self.options.sleep or time.sleep)(seconds)

    def send(self, req: ApiRequest, options: Optional[RequestOptions], stream: bool = False) -> httpx.Response:
        correlation_id = (options.correlation_id if options else None) or new_correlation_id()
        max_retries = max(0, options.max_retries if options and options.max_retries is not None else self.options.max_retries)
        timeout = options.timeout if options and options.timeout is not None else self.options.timeout
        credential = self.options.credential
        retry_safe = req.retry_safe(options)
        auth_retried = False
        attempt = 0
        while True:
            attempt += 1
            headers = self._headers(correlation_id, options)
            cred_req = CredentialRequest(req.method, req.url(self.options.base_url), headers, self)
            if credential is not None:
                credential.apply(cred_req)
            request = self._build(self.client, req, cred_req.headers, timeout)
            info = self._hook_request(req, str(request.url), attempt, cred_req.headers)
            started = time.monotonic()
            try:
                response = self.client.send(request, stream=True)
            except httpx.TimeoutException as ex:
                self._log(req.operation_id, attempt, "timeout", time.monotonic() - started, correlation_id)
                if retry_safe and attempt <= max_retries:
                    self._sleep(self._back_off(attempt))
                    continue
                raise TimeoutError(f"{req.operation_id} timed out after {timeout} s [correlation id {correlation_id}]") from ex
            except httpx.TransportError as ex:
                self._log(req.operation_id, attempt, type(ex).__name__, time.monotonic() - started, correlation_id)
                if retry_safe and attempt <= max_retries:
                    self._sleep(self._back_off(attempt))
                    continue
                raise ConnectionError(f"{req.operation_id} could not reach the API: {ex} [correlation id {correlation_id}]") from ex
            elapsed = time.monotonic() - started
            self._log(req.operation_id, attempt, response.status_code, elapsed, correlation_id)
            self._hook_response(info, response, elapsed)
            if response.is_success:
                if not stream:
                    response.read()
                    response.close()
                return response
            if (response.status_code == 401 and credential is not None and not auth_retried
                    and credential.refresh_after_unauthorized(cred_req)):
                auth_retried = True
                attempt -= 1
                response.close()
                continue
            delay = self._decide_retry(req, response, attempt, max_retries, retry_safe)
            if delay is not None:
                response.close()
                self._sleep(delay)
                continue
            body = response.read()
            response.close()
            raise self._error(req, response, body)

    def send_json(self, req: ApiRequest, type_: Any, options: Optional[RequestOptions]) -> ApiResponse[Any]:
        response = self.send(req, options)
        return ApiResponse(response.status_code, self._parse(type_, response.content), response_headers(response))

    def send_raw(self, req: ApiRequest, options: Optional[RequestOptions]) -> ApiResponse[ResponseBody]:
        response = self.send(req, options)
        headers = response_headers(response)
        ct = (headers.get("content-type") or "").split(";")[0] or None
        return ApiResponse(response.status_code, ResponseBody(response.content, ct, file_name_of(headers)), headers)

    def send_download(self, req: ApiRequest, options: Optional[RequestOptions]) -> ApiResponse[FileDownload]:
        response = self.send(req, options, stream=True)
        return ApiResponse(response.status_code, FileDownload(response), response_headers(response))

    def post_json(self, path: str, body: bytes, headers: Mapping[str, str], operation_id: str) -> SignInResponse:
        """Sign-in calls made by credentials: no credential, no retries, errors mapped."""
        req = ApiRequest("POST", path, operation_id)
        req.json = body
        correlation_id = new_correlation_id()
        all_headers = {**self._headers(correlation_id, None), **headers}
        request = self._build(self.client, req, all_headers, self.options.timeout)
        info = self._hook_request(req, str(request.url), 1, all_headers)
        started = time.monotonic()
        try:
            response = self.client.send(request)
        except httpx.TimeoutException as ex:
            raise TimeoutError(f"{operation_id} timed out [correlation id {correlation_id}]") from ex
        except httpx.TransportError as ex:
            raise ConnectionError(f"{operation_id} could not reach the API: {ex} [correlation id {correlation_id}]") from ex
        self._log(operation_id, 1, response.status_code, time.monotonic() - started, correlation_id)
        self._hook_response(info, response, time.monotonic() - started)
        if not response.is_success:
            raise self._error(req, response, response.content)
        return SignInResponse(response.status_code, response.content, response.headers.get_list("set-cookie"))

    def close(self) -> None:
        if self.owns_client:
            self.client.close()


class AsyncTransport(_TransportBase):
    """The asyncio send loop over ``httpx.AsyncClient``."""

    def __init__(self, options: ClientOptions, client: Optional[httpx.AsyncClient] = None) -> None:
        super().__init__(options)
        self.client = client or default_async_client()
        self.owns_client = client is None

    async def _sleep(self, seconds: float) -> None:
        if self.options.sleep is not None:
            result = self.options.sleep(seconds)
            if asyncio.iscoroutine(result):
                await result
            return
        await asyncio.sleep(seconds)

    async def send(self, req: ApiRequest, options: Optional[RequestOptions], stream: bool = False) -> httpx.Response:
        correlation_id = (options.correlation_id if options else None) or new_correlation_id()
        max_retries = max(0, options.max_retries if options and options.max_retries is not None else self.options.max_retries)
        timeout = options.timeout if options and options.timeout is not None else self.options.timeout
        credential = self.options.credential
        retry_safe = req.retry_safe(options)
        auth_retried = False
        attempt = 0
        while True:
            attempt += 1
            headers = self._headers(correlation_id, options)
            cred_req = CredentialRequest(req.method, req.url(self.options.base_url), headers, self)
            if credential is not None:
                await credential.apply_async(cred_req)
            request = self._build(self.client, req, cred_req.headers, timeout)
            info = self._hook_request(req, str(request.url), attempt, cred_req.headers)
            started = time.monotonic()
            try:
                response = await self.client.send(request, stream=True)
            except httpx.TimeoutException as ex:
                self._log(req.operation_id, attempt, "timeout", time.monotonic() - started, correlation_id)
                if retry_safe and attempt <= max_retries:
                    await self._sleep(self._back_off(attempt))
                    continue
                raise TimeoutError(f"{req.operation_id} timed out after {timeout} s [correlation id {correlation_id}]") from ex
            except httpx.TransportError as ex:
                self._log(req.operation_id, attempt, type(ex).__name__, time.monotonic() - started, correlation_id)
                if retry_safe and attempt <= max_retries:
                    await self._sleep(self._back_off(attempt))
                    continue
                raise ConnectionError(f"{req.operation_id} could not reach the API: {ex} [correlation id {correlation_id}]") from ex
            elapsed = time.monotonic() - started
            self._log(req.operation_id, attempt, response.status_code, elapsed, correlation_id)
            self._hook_response(info, response, elapsed)
            if response.is_success:
                if not stream:
                    await response.aread()
                    await response.aclose()
                return response
            if (response.status_code == 401 and credential is not None and not auth_retried
                    and await credential.refresh_after_unauthorized_async(cred_req)):
                auth_retried = True
                attempt -= 1
                await response.aclose()
                continue
            delay = self._decide_retry(req, response, attempt, max_retries, retry_safe)
            if delay is not None:
                await response.aclose()
                await self._sleep(delay)
                continue
            body = await response.aread()
            await response.aclose()
            raise self._error(req, response, body)

    async def send_json(self, req: ApiRequest, type_: Any, options: Optional[RequestOptions]) -> ApiResponse[Any]:
        response = await self.send(req, options)
        return ApiResponse(response.status_code, self._parse(type_, response.content), response_headers(response))

    async def send_raw(self, req: ApiRequest, options: Optional[RequestOptions]) -> ApiResponse[ResponseBody]:
        response = await self.send(req, options)
        headers = response_headers(response)
        ct = (headers.get("content-type") or "").split(";")[0] or None
        return ApiResponse(response.status_code, ResponseBody(response.content, ct, file_name_of(headers)), headers)

    async def send_download(self, req: ApiRequest, options: Optional[RequestOptions]) -> ApiResponse[FileDownload]:
        response = await self.send(req, options, stream=True)
        return ApiResponse(response.status_code, FileDownload(response), response_headers(response))

    async def post_json(self, path: str, body: bytes, headers: Mapping[str, str], operation_id: str) -> SignInResponse:
        """Sign-in calls made by credentials: no credential, no retries, errors mapped."""
        req = ApiRequest("POST", path, operation_id)
        req.json = body
        correlation_id = new_correlation_id()
        all_headers = {**self._headers(correlation_id, None), **headers}
        request = self._build(self.client, req, all_headers, self.options.timeout)
        info = self._hook_request(req, str(request.url), 1, all_headers)
        started = time.monotonic()
        try:
            response = await self.client.send(request)
        except httpx.TimeoutException as ex:
            raise TimeoutError(f"{operation_id} timed out [correlation id {correlation_id}]") from ex
        except httpx.TransportError as ex:
            raise ConnectionError(f"{operation_id} could not reach the API: {ex} [correlation id {correlation_id}]") from ex
        self._log(operation_id, 1, response.status_code, time.monotonic() - started, correlation_id)
        self._hook_response(info, response, time.monotonic() - started)
        if not response.is_success:
            raise self._error(req, response, response.content)
        return SignInResponse(response.status_code, response.content, response.headers.get_list("set-cookie"))

    async def aclose(self) -> None:
        if self.owns_client:
            await self.client.aclose()
