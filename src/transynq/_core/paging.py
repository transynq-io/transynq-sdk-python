"""Auto-paging over ``PagedResponse`` operations."""
from __future__ import annotations

from typing import Any, AsyncIterator, Awaitable, Callable, Iterator, TypeVar

from .models import PagedResponse
from .types import ApiResponse

T = TypeVar("T")


def _done(page: "PagedResponse[Any]") -> bool:
    return not page.items or page.page * page.page_size >= page.total


def iterate_pages(fetch: Callable[[int], "ApiResponse[PagedResponse[T]]"], start: int = 1) -> Iterator[T]:
    """Reads page after page until an empty page or ``page * page_size >= total``."""
    page = max(1, start)
    while True:
        data = fetch(page).data
        if data is None or not data.items:
            return
        yield from data.items
        if _done(data):
            return
        page += 1


async def iterate_pages_async(fetch: Callable[[int], Awaitable["ApiResponse[PagedResponse[T]]"]], start: int = 1) -> AsyncIterator[T]:
    """Async version of :func:`iterate_pages`."""
    page = max(1, start)
    while True:
        data = (await fetch(page)).data
        if data is None or not data.items:
            return
        for item in data.items:
            yield item
        if _done(data):
            return
        page += 1
