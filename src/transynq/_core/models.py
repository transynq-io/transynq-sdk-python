"""Base model and shared model types."""
from __future__ import annotations

import datetime as _dt
from typing import Generic, List, TypeVar

from pydantic import AfterValidator, BaseModel, ConfigDict, Field
from typing_extensions import Annotated

T = TypeVar("T")


def _to_utc(value: _dt.datetime) -> _dt.datetime:
    """Instants are UTC: a value without an offset is UTC; one with an offset is converted."""
    if value.tzinfo is None:
        return value.replace(tzinfo=_dt.timezone.utc)
    return value.astimezone(_dt.timezone.utc)


Instant = Annotated[_dt.datetime, AfterValidator(_to_utc)]
"""A UTC instant (always timezone-aware after validation)."""


class TransynqModel(BaseModel):
    """Base of every generated model: Python or JSON field names accepted, unknown JSON properties ignored."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore", protected_namespaces=())


class PagedResponse(TransynqModel, Generic[T]):
    """A page of a collection (``GET /resource?page=&pageSize=``)."""

    items: List[T] = Field(default_factory=list)
    page: int
    page_size: int = Field(alias="pageSize")
    total: int
