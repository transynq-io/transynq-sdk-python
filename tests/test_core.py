"""Unit and contract tests of the Python SDK. No network: every request is answered by respx."""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import uuid
from decimal import Decimal
from typing import Any, Dict, List, Tuple

import httpx
import pytest
import respx

import transynq
from transynq import (
    ApiKeyCredential,
    AsyncTransynqClient,
    DriverLoginCredential,
    RequestOptions,
    SessionCredential,
    TransynqClient,
)
from transynq import (
    models as m,
)
from transynq._core import jsonenc

BASE = "https://api.test.local"
ID = uuid.UUID("6f1c7a52-3d6b-4b5e-9a3e-0c1d2e3f4a5b")
HOLIDAY = {"id": str(ID), "name": "Anzac Day", "date": "2026-04-25", "countryId": 1, "states": []}


def make(**kwargs: Any) -> Tuple[TransynqClient, List[float]]:
    delays: List[float] = []
    client = TransynqClient(BASE, sleep=delays.append, jitter=lambda: 1.0, **kwargs)
    return client, delays


def login_response(session: str = "s1", csrf: str = "csrf-1", expires: str = "2099-01-01T00:00:00Z") -> httpx.Response:
    return httpx.Response(200, json={"userName": "ann", "csrfToken": csrf, "sessionExpiresUtc": expires},
                          headers={"Set-Cookie": f"__Host-tq_session={session}; path=/; secure; httponly"})


# ---------------------------------------------------------------------------------------------------------------- contract


@respx.mock
def test_get_by_id_builds_path_headers_and_reads_etag() -> None:
    route = respx.get(f"{BASE}/api/v1/public-holidays/{ID}").respond(
        200, json=HOLIDAY, headers={"ETag": '"v1"', "X-Api-Version": "1.0.0", "X-Correlation-Id": "abc12345"})
    client, _ = make(user_agent_suffix="acme/1.0")

    response = client.reference_data.get_public_holiday(ID)

    request = route.calls.last.request
    assert request.headers["User-Agent"] == f"transynq-sdk-python/{transynq.SDK_VERSION} acme/1.0"
    assert request.headers["Accept"] == "application/json"
    assert len(request.headers["X-Correlation-Id"]) == 32
    assert response.data.date == dt.date(2026, 4, 25)
    assert response.etag == '"v1"'
    assert response.api_version == "1.0.0"
    assert response.correlation_id == "abc12345"


@respx.mock
def test_query_parameters_are_formatted_and_nones_skipped() -> None:
    route = respx.get(f"{BASE}/api/v1/public-holidays").respond(200, json={"items": [], "page": 2, "pageSize": 20, "total": 0})
    client, _ = make()

    client.reference_data.list_public_holidays(country_id=1, year=2026, page=2, page_size=20, sort="-date,name", q="a b")

    assert route.calls.last.request.url.raw_path == b"/api/v1/public-holidays?countryId=1&year=2026&page=2&pageSize=20&sort=-date%2Cname&q=a%20b"


@respx.mock
def test_instants_in_queries_are_utc() -> None:
    route = respx.get(f"{BASE}/api/v1/driver/legs").respond(200, json=[])
    client, _ = make()

    client.driver_app.driver_legs(from_=dt.datetime(2026, 10, 2, 13, 4, 5, tzinfo=dt.timezone(dt.timedelta(hours=10))))

    assert route.calls.last.request.url.params["from"] == "2026-10-02T03:04:05Z"


@respx.mock
def test_put_sends_json_body_and_if_match() -> None:
    route = respx.put(f"{BASE}/api/v1/public-holidays/{ID}").respond(200, json=HOLIDAY, headers={"ETag": '"v2"'})
    client, _ = make()

    response = client.reference_data.update_public_holiday(
        ID, m.PublicHolidayRequest(id=ID, name="X", date=dt.date(2026, 1, 26), country_id=1, states=["NSW"]),
        options=RequestOptions.with_if_match('"v1"'))

    request = route.calls.last.request
    assert request.headers["If-Match"] == '"v1"'
    assert request.headers["Content-Type"].startswith("application/json")
    assert request.content == f'{{"id":"{ID}","name":"X","date":"2026-01-26","countryId":1,"states":["NSW"]}}'.encode()
    assert response.etag == '"v2"'


@respx.mock
def test_multipart_upload_sends_the_file() -> None:
    route = respx.post(f"{BASE}/api/v1/jobs/{ID}/documents").respond(200, json={"id": str(ID)})
    client, _ = make()

    response = client.jobs.upload_job_document(ID, file=transynq.FileUpload(b"%PDF-1.7", "pod.pdf", "application/pdf"))

    request = route.calls.last.request
    assert request.headers["Content-Type"].startswith("multipart/form-data")
    assert b'name="file"; filename="pod.pdf"' in request.content
    assert b"%PDF-1.7" in request.content
    assert response.data.json() == {"id": str(ID)}


@respx.mock
def test_download_streams_the_file_with_its_name() -> None:
    respx.get(f"{BASE}/api/v1/jobs/documents/{ID}/file").respond(
        200, content=b"\x01\x02\x03", headers={"Content-Type": "application/pdf", "Content-Disposition": 'attachment; filename="pod.pdf"'})
    client, _ = make()

    with client.jobs.download_job_document(ID).data as file:
        assert file.content_type == "application/pdf"
        assert file.file_name == "pod.pdf"
        assert file.read() == b"\x01\x02\x03"


def test_generated_surface_covers_the_spec() -> None:
    client, _ = make()
    assert transynq.OPERATION_COUNT == 705
    assert len(transynq.SPEC_SHA256) == 64
    services = [name for name in dir(client) if name.endswith("_") is False and type(getattr(client, name)).__name__.endswith("Service")]
    assert len(services) == 52


# ---------------------------------------------------------------------------------------------------------------- auth


@respx.mock
def test_api_key_header_and_no_csrf() -> None:
    route = respx.route(host="api.test.local").respond(200, json={})
    client, _ = make(credential=ApiKeyCredential("secret-key"))

    client.authentication.get_api_client()
    client.reference_data.delete_public_holiday(uuid.uuid4(), options=RequestOptions.with_if_match('"x"'))

    for call in route.calls:
        assert call.request.headers["X-Transynq-APIKey"] == "secret-key"
        assert "X-CSRF-Token" not in call.request.headers
    assert "secret-key" not in repr(ApiKeyCredential("secret-key"))


@respx.mock
def test_session_signs_in_once_then_cookie_and_csrf_on_unsafe_verbs() -> None:
    login = respx.post(f"{BASE}/api/v1/auth/login").mock(return_value=login_response())
    me = respx.get(f"{BASE}/api/v1/me").respond(200, json={})
    delete = respx.delete(url__regex=r".*/public-holidays/.*").respond(200, json={})
    credential = SessionCredential("ann", "pw")
    client, _ = make(credential=credential)

    client.authentication.get_me()
    client.reference_data.delete_public_holiday(uuid.uuid4(), options=RequestOptions.with_if_match('"x"'))

    assert json.loads(login.calls.last.request.content) == {"userName": "ann", "password": "pw"}
    assert login.calls.last.request.headers["X-CSRF-Token"]
    assert me.calls.last.request.headers["Cookie"] == "__Host-tq_session=s1"
    assert "X-CSRF-Token" not in me.calls.last.request.headers
    assert delete.calls.last.request.headers["X-CSRF-Token"] == "csrf-1"
    assert credential.sign_in_count == 1
    assert credential.me["userName"] == "ann"


@respx.mock
def test_session_signs_in_again_once_after_401() -> None:
    respx.post(f"{BASE}/api/v1/auth/login").mock(side_effect=[login_response("s1"), login_response("s2")])
    me = respx.get(f"{BASE}/api/v1/me").mock(side_effect=[httpx.Response(401), httpx.Response(200, json={})])
    credential = SessionCredential("ann", "pw")
    client, _ = make(credential=credential)

    client.authentication.get_me()

    assert me.calls.last.request.headers["Cookie"] == "__Host-tq_session=s2"
    assert credential.sign_in_count == 2


@respx.mock
def test_second_401_raises_and_failed_login_is_not_retried() -> None:
    respx.post(f"{BASE}/api/v1/auth/login").mock(return_value=httpx.Response(401, json={"title": "Invalid user name or password."}))
    client, _ = make(credential=SessionCredential("ann", "bad"))

    with pytest.raises(transynq.AuthenticationError) as error:
        client.authentication.get_me()
    assert error.value.title == "Invalid user name or password."


@respx.mock
def test_session_renews_before_expiry() -> None:
    respx.post(f"{BASE}/api/v1/auth/login").mock(side_effect=lambda r: login_response(expires="2026-11-16T01:00:00Z"))
    respx.get(f"{BASE}/api/v1/me").respond(200, json={})
    credential = SessionCredential("ann", "pw")
    now = [dt.datetime(2026, 11, 16, tzinfo=dt.timezone.utc)]
    credential.clock = lambda: now[0]
    client, _ = make(credential=credential)

    client.authentication.get_me()
    now[0] += dt.timedelta(minutes=59, seconds=30)
    client.authentication.get_me()

    assert credential.sign_in_count == 2


@respx.mock
async def test_async_concurrent_requests_share_one_sign_in() -> None:
    login = respx.post(f"{BASE}/api/v1/auth/login").mock(side_effect=lambda r: login_response())
    respx.get(f"{BASE}/api/v1/me").respond(200, json={})
    credential = SessionCredential("ann", "pw")
    async with AsyncTransynqClient(BASE, credential=credential) as client:
        await asyncio.gather(*(client.authentication.get_me() for _ in range(20)))
    assert login.call_count == 1
    assert credential.sign_in_count == 1


@respx.mock
def test_driver_login_uses_bearer_token() -> None:
    respx.post(f"{BASE}/api/v1/driver/login").respond(200, json={"token": "0b7c9f8e-1111-2222-3333-444455556666",
                                                                  "expiresUtc": "2099-01-01T00:00:00Z", "driver": {}, "company": {}, "settings": {}})
    me = respx.post(f"{BASE}/api/v1/driver/logout").respond(204)
    client, _ = make(credential=DriverLoginCredential("ACME", "1234", "d", "p", "1", "android"))

    client.driver_app.driver_logout()

    assert me.calls.last.request.headers["Authorization"] == "Bearer 0b7c9f8e-1111-2222-3333-444455556666"


@respx.mock
def test_hooks_never_see_secrets() -> None:
    respx.get(f"{BASE}/api/v1/api-client").respond(200, json={})
    seen: List[Dict[str, Any]] = []
    client, _ = make(credential=ApiKeyCredential("secret-key"), on_request=seen.append)

    client.authentication.get_api_client()

    assert seen[0]["headers"]["X-Transynq-APIKey"] == "[redacted]"


# ---------------------------------------------------------------------------------------------------------------- retries


@respx.mock
def test_get_is_retried_with_back_off_and_one_correlation_id() -> None:
    route = respx.get(f"{BASE}/api/v1/countries").mock(side_effect=[httpx.Response(503), httpx.Response(502), httpx.Response(200, json=[])])
    client, delays = make()

    client.reference_data.list_countries()

    assert route.call_count == 3
    assert delays == [0.5, 1.0]
    assert len({c.request.headers["X-Correlation-Id"] for c in route.calls}) == 1


@respx.mock
def test_retries_stop_at_max_and_server_error_is_typed() -> None:
    route = respx.get(f"{BASE}/api/v1/countries").respond(500, json={"title": "An unexpected error occurred.", "code": "unexpected", "correlationId": "c-1"})
    client, _ = make(max_retries=1)

    with pytest.raises(transynq.ServerError) as error:
        client.reference_data.list_countries()
    assert route.call_count == 2
    assert error.value.code == "unexpected"
    assert error.value.correlation_id == "c-1"


def _reprice() -> m.JobRepriceRequest:
    return m.JobRepriceRequest(grid=m.GridQueryRequest(columns=None, filters=None, sort=None, page=None, page_size=None, search=None, summaries=None),
                               dry_run=True)


@respx.mock
def test_post_is_only_retried_with_an_idempotency_key() -> None:
    route = respx.post(f"{BASE}/api/v1/jobs/pricing/reprice").respond(503)
    client, _ = make()
    with pytest.raises(transynq.ServerError):
        client.jobs.reprice_jobs(_reprice())
    assert route.call_count == 1

    route.side_effect = [httpx.Response(503), httpx.Response(200, json={})]
    client.jobs.reprice_jobs(_reprice(), options=RequestOptions(idempotency_key="key-1"))
    assert route.call_count == 3
    assert all(c.request.headers.get("Idempotency-Key") == "key-1" for c in route.calls[1:])


@respx.mock
def test_create_with_client_id_is_retried() -> None:
    route = respx.post(f"{BASE}/api/v1/public-holidays").mock(side_effect=[httpx.Response(503), httpx.Response(200, json={})])
    client, _ = make()

    client.reference_data.create_public_holiday(m.PublicHolidayRequest(id=transynq.new_id(), name="X"))

    assert route.call_count == 2


@respx.mock
def test_rate_limit_honours_retry_after_and_long_waits_raise() -> None:
    route = respx.post(f"{BASE}/api/v1/jobs/pricing/reprice").mock(
        side_effect=[httpx.Response(429, headers={"Retry-After": "3"}), httpx.Response(200, json={})])
    client, delays = make()
    client.jobs.reprice_jobs(_reprice())
    assert delays == [3.0]
    assert route.call_count == 2

    respx.get(f"{BASE}/api/v1/countries").respond(429, headers={"Retry-After": "600"})
    with pytest.raises(transynq.RateLimitError) as error:
        client.reference_data.list_countries()
    assert error.value.retry_after == 600.0


@respx.mock
def test_network_errors_and_timeouts() -> None:
    route = respx.get(f"{BASE}/api/v1/countries").mock(side_effect=httpx.ConnectError("reset"))
    client, _ = make(max_retries=2)
    with pytest.raises(transynq.ConnectionError):
        client.reference_data.list_countries()
    assert route.call_count == 3

    route.side_effect = httpx.ReadTimeout("slow")
    client0, _ = make(max_retries=0)
    with pytest.raises(transynq.TimeoutError):
        client0.reference_data.list_countries()


@respx.mock
def test_max_retries_zero_and_501_are_not_retried() -> None:
    route = respx.get(f"{BASE}/api/v1/countries").respond(503)
    client, _ = make(max_retries=0)
    with pytest.raises(transynq.ServerError):
        client.reference_data.list_countries()
    assert route.call_count == 1

    route.return_value = httpx.Response(501, json={"code": "not-implemented"})
    client2, _ = make()
    with pytest.raises(transynq.ServerError):
        client2.reference_data.list_countries()
    assert route.call_count == 2


# ---------------------------------------------------------------------------------------------------------------- errors


@respx.mock
def test_validation_problem_exposes_field_errors() -> None:
    respx.get(f"{BASE}/api/v1/countries").respond(400, json={"title": "The request is not valid.", "status": 400, "code": "validation",
                                                              "correlationId": "c-9", "errors": {"name": ["Name is required."]}})
    client, _ = make()
    with pytest.raises(transynq.ValidationError) as error:
        client.reference_data.list_countries()
    assert error.value.status == 400
    assert error.value.errors == {"name": ["Name is required."]}
    assert '"validation"' in error.value.raw_body


@pytest.mark.parametrize("status,expected", [
    (403, transynq.PermissionDeniedError), (404, transynq.NotFoundError), (409, transynq.ConflictError),
    (412, transynq.StaleVersionError), (422, transynq.BusinessRuleError), (418, transynq.ApiError)])
@respx.mock
def test_status_maps_to_typed_error(status: int, expected: type) -> None:
    respx.get(f"{BASE}/api/v1/countries").respond(status, json={"title": "t", "detail": "d", "code": "year-exists"},
                                                  headers={"X-Correlation-Id": "hdr-1"})
    client, _ = make()
    with pytest.raises(transynq.ApiError) as error:
        client.reference_data.list_countries()
    assert type(error.value) is expected
    assert error.value.code == "year-exists"
    assert error.value.detail == "d"
    assert error.value.correlation_id == "hdr-1"
    assert error.value.operation_id == "ListCountries"


# ---------------------------------------------------------------------------------------------------------------- etag, paging, LRO


@respx.mock
def test_read_modify_write_retries_on_stale_version() -> None:
    respx.get(f"{BASE}/api/v1/public-holidays/{ID}").mock(side_effect=[
        httpx.Response(200, json=HOLIDAY, headers={"ETag": '"1"'}), httpx.Response(200, json=HOLIDAY, headers={"ETag": '"2"'})])
    put = respx.put(f"{BASE}/api/v1/public-holidays/{ID}").mock(side_effect=[
        httpx.Response(412, json={"code": "stale-version"}), httpx.Response(200, json=HOLIDAY, headers={"ETag": '"3"'})])
    client, _ = make()

    saved = transynq.read_modify_write(
        lambda: client.reference_data.get_public_holiday(ID),
        lambda current, options: client.reference_data.update_public_holiday(
            ID, m.PublicHolidayRequest(id=current.id, name=current.name + "!", date=current.date, country_id=current.country_id), options=options))

    assert saved.etag == '"3"'
    assert [c.request.headers["If-Match"] for c in put.calls] == ['"1"', '"2"']


def _reason() -> Dict[str, Any]:
    return {"id": str(uuid.uuid4()), "name": "Late", "reasonType": "delay", "active": True}


@respx.mock
def test_auto_paging_reads_until_total() -> None:
    route = respx.get(f"{BASE}/api/v1/job-status-reasons").mock(side_effect=[
        httpx.Response(200, json={"items": [_reason(), _reason()], "page": 1, "pageSize": 2, "total": 3}),
        httpx.Response(200, json={"items": [_reason()], "page": 2, "pageSize": 2, "total": 3})])
    client, _ = make()

    items = list(client.reference_data.list_job_status_reasons_auto_paging(page_size=2))

    assert len(items) == 3
    assert route.calls[1].request.url.params["page"] == "2"


@respx.mock
async def test_async_auto_paging() -> None:
    respx.get(f"{BASE}/api/v1/job-status-reasons").mock(side_effect=[
        httpx.Response(200, json={"items": [_reason()], "page": 1, "pageSize": 1, "total": 2}),
        httpx.Response(200, json={"items": [_reason()], "page": 2, "pageSize": 1, "total": 2})])
    async with AsyncTransynqClient(BASE) as client:
        items = [i async for i in client.reference_data.list_job_status_reasons_auto_paging(page_size=1)]
    assert len(items) == 2


@respx.mock
def test_grid_rows_iterate_across_pages() -> None:
    route = respx.post(f"{BASE}/api/v1/grids/jobs/query").mock(side_effect=[
        httpx.Response(200, json={"rows": [{"a": 1}, {"a": 2}], "page": 1, "pageSize": 2, "total": 3, "summaries": {}}),
        httpx.Response(200, json={"rows": [{"a": 3}], "page": 2, "pageSize": 2, "total": 3, "summaries": {}})])
    client, _ = make()

    request = m.GridQueryRequest(columns=["a"], filters=None, sort=None, page=None, page_size=2, search=None, summaries=None)
    rows = [r["a"] for r in client.iter_grid_rows("jobs", request)]

    assert rows == [1, 2, 3]
    assert json.loads(route.calls[1].request.content)["page"] == 2


def _op(status: str, result: Any = None, error: Any = None) -> Dict[str, Any]:
    return {"id": str(ID), "kind": "zones", "inputName": "z.xlsx", "requestedBy": "ann", "requestedUtc": "2026-11-16T00:00:00Z",
            "status": status, "startedUtc": None, "finishedUtc": None, "result": result, "error": error}


@respx.mock
def test_accepted_long_operation_is_polled_to_success() -> None:
    respx.post(f"{BASE}/api/v1/imports/zones/background").respond(
        202, json={"id": str(ID), "status": "Queued"}, headers={"Location": f"/api/v1/long-operations/{ID}"})
    respx.get(f"{BASE}/api/v1/long-operations/{ID}").mock(side_effect=[
        httpx.Response(200, json=_op("Running")), httpx.Response(200, json=_op("Succeeded", {"created": 3}))])
    client, delays = make()

    accepted = client.imports.import_zones_in_background(file=transynq.FileUpload(b"x", "z.xlsx"))
    assert accepted.is_accepted
    seen: List[str] = []
    done = client.poll_long_operation(accepted).wait(poll_interval=1.0, on_progress=lambda s: seen.append(s.status))

    assert seen == ["Running", "Succeeded"]
    assert done.result == {"created": 3}
    assert delays == [1.0]


@respx.mock
def test_failed_long_operation_raises() -> None:
    respx.get(f"{BASE}/api/v1/long-operations/{ID}").respond(200, json=_op("Failed", error="Bad file"))
    client, _ = make()
    with pytest.raises(transynq.LongOperationFailedError) as error:
        client.poll_long_operation(ID).wait()
    assert error.value.operation.error == "Bad file"


# ---------------------------------------------------------------------------------------------------------------- serialisation


def test_decimals_are_lossless_and_numbers_may_be_strings() -> None:
    raw = b'{"ratePercentage":1234567890123456.78,"minPercentage":"0.10","maxPercentage":1,"optionalPricingRatePercentage":0,' \
          b'"decimalPlaces":"2","allowUpdateOptionalPricings":true,"unknownFutureField":{"x":1}}'
    item = m.ScheduleRateUpdateRequest.model_validate(jsonenc.loads(raw))
    assert item.rate_percentage == Decimal("1234567890123456.78")
    assert item.min_percentage == Decimal("0.10")
    assert item.decimal_places == 2
    assert b'"ratePercentage":1234567890123456.78' in jsonenc.dumps(item)


def test_instants_are_utc_and_unknown_codes_are_kept() -> None:
    op = m.LongOperationResponse.model_validate(
        {"id": str(ID), "kind": "brand-new-kind", "inputName": None, "requestedBy": "a", "requestedUtc": "2026-10-02T03:04:05",
         "status": "Paused", "startedUtc": None, "finishedUtc": None, "result": None, "error": None, "newField": [1, 2]})
    assert op.requested_utc == dt.datetime(2026, 10, 2, 3, 4, 5, tzinfo=dt.timezone.utc)
    assert op.status == "Paused"
    assert b'"requestedUtc":"2026-10-02T03:04:05Z"' in jsonenc.dumps(op)


def test_nulls_omitted_and_dates_are_calendar_days() -> None:
    assert jsonenc.dumps(m.PublicHolidayRequest(id=uuid.UUID(int=0), date=dt.date(2026, 12, 25))) == \
        b'{"id":"00000000-0000-0000-0000-000000000000","date":"2026-12-25"}'
