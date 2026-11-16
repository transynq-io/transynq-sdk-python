# Dates, money and enums (type mapping)

| OpenAPI | Meaning | Python |
|---|---|---|
| `string` | text | `str` |
| `string` / `uuid` | identifier | `uuid.UUID` |
| `string` / `date` (C# `DateOnly`) | calendar day `yyyy-MM-dd`, never a midnight instant | `datetime.date` |
| `string` / `date-time` | instant, always UTC on the wire (`2026-10-02T03:04:05Z`) | `datetime.datetime`, always timezone-aware UTC (naive values are treated as UTC) |
| `integer` / `int32`, `int64` | whole number (the API also accepts it as a string) | `int` |
| `number` | money, rates, quantities: `decimal(18,2)` in the API (the spec cannot tell decimals from doubles, so every number is a decimal) | `decimal.Decimal` (JSON is parsed with `parse_float=Decimal` and decimals are written as exact JSON numbers) |
| `boolean` | flag | `bool` |
| `array`, `additionalProperties` | list, map | `list[T]`, `dict[str, T]` |
| untyped object, `JsonElement` | free-form JSON (grid rows, long-operation results) | `Any` / `dict[str, Any]` |
| `binary` (`IFormFile`) | uploaded file | `FileUpload` |

Models are Pydantic v2 classes with snake_case attributes and the API's camelCase names as aliases (both are accepted when you build one). Required members must be given; nullable and optional members default to `None`, and `None` members are left out of request bodies. Unknown JSON properties are ignored. Codes such as `status` or `kind` are plain `str` (the contract declares no enums), so a new code never breaks validation; well-known long-operation states are `transynq.QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`.

## Rules worth knowing

- **Calendar days are not instants.** A `date` member (delivery day, public holiday) is `yyyy-MM-dd`. Never send a midnight
  instant for it.
- **Instants are UTC.** The SDK always writes them in UTC with `Z`; the company's time zone (`MeResponse.timeZone`) is for display only.
- **Money is decimal.** The API stores `decimal(18,2)` values and rounds them in its domain; the SDK never converts them through
  binary floating point.
- **Codes are open.** `status`, `kind`, `reasonType` and similar members are strings. New values may appear in later API versions;
  handle unknown values instead of failing.
- **Forward compatible.** Properties the SDK does not know yet are ignored when reading.
