# Concurrency (ETag / If-Match)

The API uses optimistic concurrency. A GET, POST or PUT answer carries an `ETag`; a PUT or DELETE must send it back in
`If-Match`:

- no `If-Match` -> **400** (`validation`);
- an `If-Match` that no longer matches -> **412** (`stale-version`): someone saved first; reload and apply your change again.

```python
current = client.reference_data.get_public_holiday(holiday_id)          # ETag: "..."
client.reference_data.update_public_holiday(
    holiday_id,
    m.PublicHolidayRequest(id=holiday_id, name="Australia Day", date=current.data.date, country_id=current.data.country_id, states=current.data.states),
    options=RequestOptions.with_if_match(current.etag),                   # 412 StaleVersionError if someone saved first
)
```

## Read-modify-write helper

The helper loads the record (with its ETag), lets you build the change, saves it with `If-Match`, and on a stale version
loads again and repeats (3 attempts by default):

```python
saved = transynq.read_modify_write(
    lambda: client.reference_data.get_public_holiday(holiday_id),
    lambda current, options: client.reference_data.update_public_holiday(
        holiday_id,
        m.PublicHolidayRequest(id=current.id, name=current.name + " (observed)", date=current.date, country_id=current.country_id, states=current.states),
        options=options,
    ),
    max_attempts=3,
)
# asyncio: await transynq.read_modify_write_async(load, save)
```

The ETag is passed through verbatim (quotes included); never build one yourself.
