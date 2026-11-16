"""Lossless JSON: decimals in and out as exact JSON numbers, UTC instants, ISO dates."""
from __future__ import annotations

import datetime as _dt
import decimal
import enum
import json
import uuid
from typing import Any

from pydantic import BaseModel


def loads(data: bytes) -> Any:
    """Parses JSON; non-integer numbers become :class:`decimal.Decimal` (no float rounding)."""
    return json.loads(data, parse_float=decimal.Decimal)


def format_instant(value: _dt.datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=_dt.timezone.utc)
    value = value.astimezone(_dt.timezone.utc)
    text = value.strftime("%Y-%m-%dT%H:%M:%S")
    if value.microsecond:
        text += f".{value.microsecond:06d}".rstrip("0")
    return text + "Z"


def to_plain(value: Any) -> Any:
    """Models to dictionaries (JSON names, ``None`` omitted); everything else unchanged."""
    if isinstance(value, BaseModel):
        return to_plain(value.model_dump(by_alias=True, exclude_none=True, mode="python"))
    if isinstance(value, dict):
        return {str(k): to_plain(v) for k, v in value.items() if v is not None}
    if isinstance(value, (list, tuple)):
        return [to_plain(v) for v in value]
    return value


def format_scalar(value: Any) -> str:
    """Formats a path/query/form value the way the API binds it."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, _dt.datetime):
        return format_instant(value)
    if isinstance(value, _dt.date):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return format(value, "f")
    if isinstance(value, enum.Enum):
        return str(value.value)
    return str(value)


def _encode(value: Any, out: list[str]) -> None:
    if value is None:
        out.append("null")
    elif value is True:
        out.append("true")
    elif value is False:
        out.append("false")
    elif isinstance(value, str):
        out.append(json.dumps(value, ensure_ascii=False))
    elif isinstance(value, int):
        out.append(str(int(value)))
    elif isinstance(value, decimal.Decimal):
        if not value.is_finite():
            raise ValueError("NaN and infinite decimals cannot be sent")
        out.append(format(value, "f"))
    elif isinstance(value, float):
        out.append(json.dumps(value))
    elif isinstance(value, (_dt.datetime, _dt.date, uuid.UUID, enum.Enum)):
        out.append(json.dumps(format_scalar(value)))
    elif isinstance(value, dict):
        out.append("{")
        first = True
        for k, v in value.items():
            if not first:
                out.append(",")
            first = False
            out.append(json.dumps(str(k), ensure_ascii=False))
            out.append(":")
            _encode(v, out)
        out.append("}")
    elif isinstance(value, (list, tuple)):
        out.append("[")
        for i, v in enumerate(value):
            if i:
                out.append(",")
            _encode(v, out)
        out.append("]")
    elif isinstance(value, BaseModel):
        _encode(to_plain(value), out)
    else:
        raise TypeError(f"cannot serialise {type(value).__name__}")


def dumps(value: Any) -> bytes:
    """Serialises to compact UTF-8 JSON (decimals as exact numbers, instants as UTC ``Z``)."""
    out: list[str] = []
    _encode(to_plain(value), out)
    return "".join(out).encode("utf-8")
