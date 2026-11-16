"""Runnable samples of real Transynq flows.

Configure with environment variables (never hard-code secrets):
    TRANSYNQ_BASE_URL   e.g. https://api.example.com
    TRANSYNQ_API_KEY    an API client key, or
    TRANSYNQ_USER / TRANSYNQ_PASSWORD   a user for session sign-in

Run: python examples/flows.py <flow> [args]
Flows: sign-in | page-grid | create-booking | update-holiday | list-invoices | upload-pod | long-operation | async-sign-in
"""
from __future__ import annotations

import asyncio
import datetime as dt
import os
import sys
import uuid

import transynq
from transynq import (
    ApiKeyCredential,
    AsyncTransynqClient,
    Credential,
    FileUpload,
    LongOperationFailedError,
    SessionCredential,
    TransynqClient,
)
from transynq import (
    models as m,
)


def credential() -> Credential:
    key = os.environ.get("TRANSYNQ_API_KEY")
    if key:
        return ApiKeyCredential(key)
    return SessionCredential(os.environ.get("TRANSYNQ_USER", "user@example.com"), os.environ.get("TRANSYNQ_PASSWORD", "change-me"))


def create_client() -> TransynqClient:
    return TransynqClient(os.environ.get("TRANSYNQ_BASE_URL", "https://api.example.com"), credential=credential(),
                          user_agent_suffix="transynq-examples/1.0")


def sign_in(client: TransynqClient) -> None:
    """Sign in (session or API key) and show who the client acts as."""
    if isinstance(client.options.credential, SessionCredential):
        me = client.authentication.get_me()
        profile = me.data.json()
        print(f"Signed in as {profile['userName']} of {profile['companyName']} (API {me.api_version}).")
        client.sign_out()
    else:
        print(f"API key acts for company {client.authentication.get_api_client().data.json()['companyId']}.")


def page_grid(client: TransynqClient, grid_id: str = "jobs") -> None:
    """List the grids, then read every row of one (jobs are listed through the grid endpoints)."""
    for grid in client.grids.list_grids().data:
        print(f"grid {grid.id}: {grid.title}")
    request = m.GridQueryRequest(columns=None, filters=None, sort=None, page=None, page_size=200, search=None, summaries=None)
    count = 0
    for row in client.iter_grid_rows(grid_id, request):
        count += 1
        if count <= 5:
            print(row)
    print(f"{count} rows")
    # a classic paged collection with auto-paging
    for reason in client.reference_data.list_job_status_reasons_auto_paging(active_only=True, page_size=100):
        print(f"{reason.reason_type}: {reason.name}")


def create_booking(client: TransynqClient, customer_id: uuid.UUID, sender_id: uuid.UUID, recipient_id: uuid.UUID) -> None:
    """Create a job (booking) idempotently: the client-generated id makes a retry return the same record."""
    booking = m.BookingRequestDto(
        id=transynq.new_id(),
        customer_id=customer_id,
        sender_id=sender_id,
        recipient_id=recipient_id,
        book_date=dt.datetime.now(dt.timezone.utc),
        invoicing_only=False,
        special_instructions="Call before delivery",
        products=[],
        legs=[],
        pricings=[],
        notes=[],
    )
    created = client.bookings.create_booking(booking)
    print(f"Booking {booking.id} saved ({created.status_code}); correlation id {created.correlation_id}.")


def update_holiday(client: TransynqClient, holiday_id: uuid.UUID) -> None:
    """Update with optimistic concurrency: read the ETag, send it as If-Match, retry on a stale version."""
    saved = transynq.read_modify_write(
        lambda: client.reference_data.get_public_holiday(holiday_id),
        lambda current, options: client.reference_data.update_public_holiday(
            holiday_id,
            m.PublicHolidayRequest(id=current.id, name=current.name.strip(), date=current.date, country_id=current.country_id, states=current.states),
            options=options,
        ),
    )
    print(f"Saved; new ETag {saved.etag}.")


def list_invoices(client: TransynqClient) -> None:
    """List sales-ledger invoices of the last 30 days."""
    now = dt.datetime.now(dt.timezone.utc)
    response = client.sales_ledger.get_sales_ledger_invoices(from_=now - dt.timedelta(days=30), to=now, take=50)
    print(response.data.json())


def upload_pod(client: TransynqClient, job_id: uuid.UUID, path: str) -> None:
    """Upload a proof of delivery to a job."""
    added = client.jobs.add_job_pods(job_id, files=[FileUpload.from_path(path, "application/pdf")])
    print("Added POD(s):", ", ".join(str(i) for i in added.data.ids))


def long_operation(client: TransynqClient, workbook: str) -> None:
    """Queue a background import and wait for the long operation to finish."""
    accepted = client.imports.import_zones_in_background(
        file=FileUpload.from_path(workbook, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))
    try:
        done = client.poll_long_operation(accepted).wait(poll_interval=2.0, on_progress=lambda op: print(f"{op.kind}: {op.status}"))
        print("Result:", done.result)
    except LongOperationFailedError as failed:
        print("Import failed:", failed.operation.error, file=sys.stderr)


async def async_sign_in() -> None:
    """The same sign-in with the asyncio client."""
    async with AsyncTransynqClient(os.environ.get("TRANSYNQ_BASE_URL", "https://api.example.com"), credential=credential()) as client:
        me = await client.authentication.get_me()
        print(me.data.json())


def main(argv: list[str]) -> int:
    flow = argv[1] if len(argv) > 1 else "sign-in"
    if flow == "async-sign-in":
        asyncio.run(async_sign_in())
        return 0
    with create_client() as client:
        if flow == "sign-in":
            sign_in(client)
        elif flow == "page-grid":
            page_grid(client, argv[2] if len(argv) > 2 else "jobs")
        elif flow == "create-booking":
            create_booking(client, uuid.UUID(argv[2]), uuid.UUID(argv[3]), uuid.UUID(argv[4]))
        elif flow == "update-holiday":
            update_holiday(client, uuid.UUID(argv[2]))
        elif flow == "list-invoices":
            list_invoices(client)
        elif flow == "upload-pod":
            upload_pod(client, uuid.UUID(argv[2]), argv[3])
        elif flow == "long-operation":
            long_operation(client, argv[2])
        else:
            print(f"Unknown flow {flow!r}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
