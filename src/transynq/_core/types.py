"""Responses, files and per-call options."""
from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass, field
from typing import IO, Any, AsyncIterator, Dict, Generic, Iterator, Mapping, Optional, Type, TypeVar, Union

import httpx
from pydantic import TypeAdapter

from . import jsonenc

T = TypeVar("T")
M = TypeVar("M")


@dataclass(frozen=True)
class RequestOptions:
    """Per-call options."""

    if_match: Optional[str] = None
    """Sent as ``If-Match`` (PUT and DELETE require it; take it from :attr:`ApiResponse.etag`)."""
    idempotency_key: Optional[str] = None
    """Sent as ``Idempotency-Key``; also makes a POST retryable."""
    headers: Mapping[str, str] = field(default_factory=dict)
    """Extra request headers."""
    timeout: Optional[float] = None
    """Overrides the client's timeout (seconds) for this call."""
    max_retries: Optional[int] = None
    """Overrides the client's retries for this call."""
    correlation_id: Optional[str] = None
    """Overrides the generated ``X-Correlation-Id``."""

    @staticmethod
    def with_if_match(etag: str) -> "RequestOptions":
        return RequestOptions(if_match=etag)

    @staticmethod
    def with_new_idempotency_key() -> "RequestOptions":
        return RequestOptions(idempotency_key=uuid.uuid4().hex)


class Headers(Dict[str, str]):
    """Response headers with case-insensitive lookup (keys stored lower-case; repeated values joined by ``, ``)."""

    def get_header(self, name: str) -> Optional[str]:
        return self.get(name.lower())


@dataclass(frozen=True)
class ApiResponse(Generic[T]):
    """An answer of the API: the data plus ETag, API version, correlation id and Location."""

    status_code: int
    data: T
    headers: Headers

    @property
    def etag(self) -> Optional[str]:
        """The ``ETag`` header verbatim (quotes kept), to send back as ``if_match``."""
        return self.headers.get_header("etag")

    @property
    def api_version(self) -> Optional[str]:
        """The contract version that answered (``X-Api-Version``)."""
        return self.headers.get_header("x-api-version")

    @property
    def correlation_id(self) -> Optional[str]:
        """The request's correlation id (``X-Correlation-Id``)."""
        return self.headers.get_header("x-correlation-id")

    @property
    def location(self) -> Optional[str]:
        """The ``Location`` header (a 202 points at ``/api/v1/long-operations/{id}``)."""
        return self.headers.get_header("location")

    @property
    def is_accepted(self) -> bool:
        """Whether the API accepted long-running work (202)."""
        return self.status_code == 202


def file_name_of(headers: Mapping[str, str]) -> Optional[str]:
    disposition = headers.get("content-disposition")
    if not disposition:
        return None
    star = re.search(r"filename\*\s*=\s*(?:UTF-8'')?([^;]+)", disposition, re.IGNORECASE)
    if star:
        from urllib.parse import unquote

        return unquote(star.group(1).strip().strip('"'))
    plain = re.search(r'filename\s*=\s*"?([^";]+)"?', disposition, re.IGNORECASE)
    return plain.group(1).strip() if plain else None


@dataclass(frozen=True)
class ResponseBody:
    """A buffered body of an operation whose contract does not declare its response (JSON, a small file, or nothing)."""

    content: bytes
    content_type: Optional[str]
    file_name: Optional[str] = None

    @property
    def is_empty(self) -> bool:
        return len(self.content) == 0

    @property
    def is_json(self) -> bool:
        return bool(self.content_type and "json" in self.content_type.lower())

    def text(self) -> str:
        return self.content.decode("utf-8")

    def json(self) -> Any:
        """The body parsed as JSON (decimals as :class:`decimal.Decimal`), or ``None`` when empty."""
        return None if self.is_empty else jsonenc.loads(self.content)

    def parse(self, model: Type[M]) -> M:
        """The body validated as a generated model (or any type Pydantic can validate)."""
        return TypeAdapter(model).validate_python(self.json())


class FileDownload:
    """A streamed file answer. Close it (or use ``with`` / ``async with``) after reading."""

    def __init__(self, response: httpx.Response) -> None:
        self._response = response
        headers = {k.lower(): v for k, v in response.headers.items()}
        self.content_type: Optional[str] = (headers.get("content-type") or "").split(";")[0] or None
        self.file_name: Optional[str] = file_name_of(headers)
        length = headers.get("content-length")
        self.length: Optional[int] = int(length) if length and length.isdigit() else None

    # sync
    def iter_bytes(self, chunk_size: int = 65536) -> Iterator[bytes]:
        return self._response.iter_bytes(chunk_size)

    def read(self) -> bytes:
        return self._response.read()

    def save(self, path: Union[str, "os.PathLike[str]"]) -> None:
        with open(path, "wb") as f:
            for chunk in self.iter_bytes():
                f.write(chunk)

    def close(self) -> None:
        self._response.close()

    def __enter__(self) -> "FileDownload":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # async
    def aiter_bytes(self, chunk_size: int = 65536) -> AsyncIterator[bytes]:
        return self._response.aiter_bytes(chunk_size)

    async def aread(self) -> bytes:
        return await self._response.aread()

    async def asave(self, path: Union[str, "os.PathLike[str]"]) -> None:
        with open(path, "wb") as f:
            async for chunk in self.aiter_bytes():
                f.write(chunk)

    async def aclose(self) -> None:
        await self._response.aclose()

    async def __aenter__(self) -> "FileDownload":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()


class FileUpload:
    """A file to upload in a multipart form."""

    def __init__(self, content: Union[bytes, IO[bytes]], file_name: str, content_type: str = "application/octet-stream") -> None:
        self._content = content
        self._start = content.tell() if not isinstance(content, bytes) and content.seekable() else 0
        self.file_name = file_name
        self.content_type = content_type

    @classmethod
    def from_path(cls, path: Union[str, "os.PathLike[str]"], content_type: str = "application/octet-stream") -> "FileUpload":
        with open(path, "rb") as f:
            return cls(f.read(), os.path.basename(os.fspath(path)), content_type)

    @property
    def replayable(self) -> bool:
        """Whether the content can be sent again (bytes or a seekable stream), so the request can be retried."""
        return isinstance(self._content, bytes) or self._content.seekable()

    def to_httpx(self) -> "tuple[str, Any, str]":
        if isinstance(self._content, bytes):
            return (self.file_name, self._content, self.content_type)
        if self._content.seekable():
            self._content.seek(self._start)
        return (self.file_name, self._content, self.content_type)
