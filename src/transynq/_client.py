"""The entry clients."""
from __future__ import annotations

import uuid
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, Iterator, Optional, TypeVar, Union

import httpx

from ._core.credentials import Credential, DriverLoginCredential, SessionCredential
from ._core.errors import LongOperationFailedError, StaleVersionError
from ._core.http import AsyncTransport, ClientOptions, SyncTransport
from ._core.types import ApiResponse, FileDownload, RequestOptions, ResponseBody
from ._generated import models as m
from ._generated.client_services import AsyncServices, SyncServices

T = TypeVar("T")
R = TypeVar("R")

QUEUED, RUNNING, SUCCEEDED, FAILED = "Queued", "Running", "Succeeded", "Failed"
"""Long operation states (an open set: compare as strings)."""


def _options(
    base_url: str, credential: Optional[Credential], timeout: float, max_retries: int, user_agent_suffix: Optional[str], **extra: Any
) -> ClientOptions:
    return ClientOptions(base_url=base_url, credential=credential, timeout=timeout, max_retries=max_retries,
                         user_agent_suffix=user_agent_suffix, **extra)


def operation_id_from(response: "ApiResponse[ResponseBody]") -> uuid.UUID:
    """The long operation a 202 answer started (its ``Location``, else its body's ``id``)."""
    location = response.location
    if location and "/long-operations/" in location.lower():
        try:
            return uuid.UUID(location.split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1])
        except ValueError:
            pass
    body = response.data.json() if isinstance(response.data, ResponseBody) else None
    if isinstance(body, dict) and isinstance(body.get("id"), str):
        return uuid.UUID(body["id"])
    raise ValueError("the response is not a long-operation answer (no Location and no id)")


def _check(op: m.LongOperationResponse, operation_id: uuid.UUID) -> bool:
    if op.status.lower() == SUCCEEDED.lower():
        return True
    if op.status.lower() == FAILED.lower():
        raise LongOperationFailedError(f"Long operation {operation_id} ({op.kind}) failed: {op.error or 'no reason given'}.", op)
    return False


class LongOperationPoller:
    """Follows a long-running operation (``GET /api/v1/long-operations/{id}``) to its end."""

    def __init__(self, client: "TransynqClient", operation_id: uuid.UUID) -> None:
        self._client = client
        self.id = operation_id
        self.last: Optional[m.LongOperationResponse] = None

    def status(self) -> m.LongOperationResponse:
        self.last = self._client.long_operations.get_long_operation(self.id).data
        return self.last

    def wait(self, poll_interval: float = 2.0, timeout: float = 1800.0,
             on_progress: Optional[Callable[[m.LongOperationResponse], None]] = None) -> m.LongOperationResponse:
        """Polls until ``Succeeded`` (returns it) or ``Failed`` (raises :class:`LongOperationFailedError`)."""
        waited = 0.0
        while True:
            op = self.status()
            if on_progress:
                on_progress(op)
            if _check(op, self.id):
                return op
            if waited >= timeout:
                raise TimeoutError(f"long operation {self.id} did not finish within {timeout} s")
            self._client._transport._sleep(poll_interval)
            waited += poll_interval

    def download_result(self) -> FileDownload:
        """The operation's result file (a workbook or PDF). Close it after reading."""
        return self._client.long_operations.get_long_operation_file(self.id).data


class AsyncLongOperationPoller:
    """Async version of :class:`LongOperationPoller`."""

    def __init__(self, client: "AsyncTransynqClient", operation_id: uuid.UUID) -> None:
        self._client = client
        self.id = operation_id
        self.last: Optional[m.LongOperationResponse] = None

    async def status(self) -> m.LongOperationResponse:
        self.last = (await self._client.long_operations.get_long_operation(self.id)).data
        return self.last

    async def wait(self, poll_interval: float = 2.0, timeout: float = 1800.0,
                   on_progress: Optional[Callable[[m.LongOperationResponse], None]] = None) -> m.LongOperationResponse:
        waited = 0.0
        while True:
            op = await self.status()
            if on_progress:
                on_progress(op)
            if _check(op, self.id):
                return op
            if waited >= timeout:
                raise TimeoutError(f"long operation {self.id} did not finish within {timeout} s")
            await self._client._transport._sleep(poll_interval)
            waited += poll_interval

    async def download_result(self) -> FileDownload:
        return (await self._client.long_operations.get_long_operation_file(self.id)).data


class TransynqClient(SyncServices):
    """
    The Transynq TMS API client (blocking). One attribute per API area (``client.jobs``, ``client.customers``...),
    one method per operation. Thread-safe; create one and reuse it. Use as a context manager or call :meth:`close`.
    """

    def __init__(
        self,
        base_url: str,
        *,
        credential: Optional[Credential] = None,
        timeout: float = 60.0,
        max_retries: int = 2,
        user_agent_suffix: Optional[str] = None,
        http_client: Optional[httpx.Client] = None,
        **options: Any,
    ) -> None:
        self.options = _options(base_url, credential, timeout, max_retries, user_agent_suffix, **options)
        self._transport = SyncTransport(self.options, http_client)
        self._init_services(self._transport)

    @property
    def user_agent(self) -> str:
        return self._transport.user_agent

    def poll_long_operation(self, accepted: Union["ApiResponse[ResponseBody]", uuid.UUID]) -> LongOperationPoller:
        """A poller for the long operation a 202 answer started, or for an operation id."""
        return LongOperationPoller(self, accepted if isinstance(accepted, uuid.UUID) else operation_id_from(accepted))

    def iter_grid_rows(self, grid_id: str, request: m.GridQueryRequest, options: Optional[RequestOptions] = None) -> Iterator[Dict[str, Any]]:
        """Every row of ``POST /api/v1/grids/{grid_id}/query``, page by page (page size default 500, the maximum)."""
        page, size = request.page or 1, request.page_size or 500
        while True:
            data = self.grids.query_grid(grid_id, request.model_copy(update={"page": page, "page_size": size}), options=options).data
            if not data.rows:
                return
            yield from data.rows
            if data.page * data.page_size >= data.total:
                return
            page += 1

    def sign_out(self) -> None:
        """Ends a session or driver sign-in on the server and forgets it locally."""
        credential = self.options.credential
        if isinstance(credential, SessionCredential) and credential.state is not None:
            self.authentication.logout()
            credential.reset()
        elif isinstance(credential, DriverLoginCredential) and credential.state is not None:
            self.driver_app.driver_logout()
            credential.reset()

    def close(self) -> None:
        self._transport.close()

    def __enter__(self) -> "TransynqClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class AsyncTransynqClient(AsyncServices):
    """The Transynq TMS API client (asyncio). Same surface as :class:`TransynqClient`, every method awaitable."""

    def __init__(
        self,
        base_url: str,
        *,
        credential: Optional[Credential] = None,
        timeout: float = 60.0,
        max_retries: int = 2,
        user_agent_suffix: Optional[str] = None,
        http_client: Optional[httpx.AsyncClient] = None,
        **options: Any,
    ) -> None:
        self.options = _options(base_url, credential, timeout, max_retries, user_agent_suffix, **options)
        self._transport = AsyncTransport(self.options, http_client)
        self._init_services(self._transport)

    @property
    def user_agent(self) -> str:
        return self._transport.user_agent

    def poll_long_operation(self, accepted: Union["ApiResponse[ResponseBody]", uuid.UUID]) -> AsyncLongOperationPoller:
        return AsyncLongOperationPoller(self, accepted if isinstance(accepted, uuid.UUID) else operation_id_from(accepted))

    async def iter_grid_rows(self, grid_id: str, request: m.GridQueryRequest,
                             options: Optional[RequestOptions] = None) -> AsyncIterator[Dict[str, Any]]:
        page, size = request.page or 1, request.page_size or 500
        while True:
            data = (await self.grids.query_grid(grid_id, request.model_copy(update={"page": page, "page_size": size}), options=options)).data
            if not data.rows:
                return
            for row in data.rows:
                yield row
            if data.page * data.page_size >= data.total:
                return
            page += 1

    async def sign_out(self) -> None:
        credential = self.options.credential
        if isinstance(credential, SessionCredential) and credential.state is not None:
            await self.authentication.logout()
            credential.reset()
        elif isinstance(credential, DriverLoginCredential) and credential.state is not None:
            await self.driver_app.driver_logout()
            credential.reset()

    async def aclose(self) -> None:
        await self._transport.aclose()

    async def __aenter__(self) -> "AsyncTransynqClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()


def read_modify_write(
    load: Callable[[], "ApiResponse[T]"],
    save: Callable[[T, RequestOptions], "ApiResponse[R]"],
    max_attempts: int = 3,
) -> "ApiResponse[R]":
    """Loads (with its ETag), saves with ``If-Match``; on :class:`StaleVersionError` reloads and repeats."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    attempt = 0
    while True:
        attempt += 1
        current = load()
        if not current.etag:
            raise ValueError("the loaded record has no ETag")
        try:
            return save(current.data, RequestOptions.with_if_match(current.etag))
        except StaleVersionError:
            if attempt >= max_attempts:
                raise


async def read_modify_write_async(
    load: Callable[[], Awaitable["ApiResponse[T]"]],
    save: Callable[[T, RequestOptions], Awaitable["ApiResponse[R]"]],
    max_attempts: int = 3,
) -> "ApiResponse[R]":
    """Async version of :func:`read_modify_write`."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    attempt = 0
    while True:
        attempt += 1
        current = await load()
        if not current.etag:
            raise ValueError("the loaded record has no ETag")
        try:
            return await save(current.data, RequestOptions.with_if_match(current.etag))
        except StaleVersionError:
            if attempt >= max_attempts:
                raise


def new_id() -> uuid.UUID:
    """A new client id for an idempotent create (``POST`` with ``id`` in the body)."""
    return uuid.uuid4()


def new_idempotency_key() -> str:
    return uuid.uuid4().hex


