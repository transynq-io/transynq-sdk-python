# Long-running operations

Some operations (background imports, document packs, reports) queue work and answer **202 Accepted** with
`Location: /api/v1/long-operations/{id}` and a body `{ id, status }`. The operation then goes through the states
`Queued` -> `Running` -> `Succeeded` or `Failed`; `GET /api/v1/long-operations/{id}` reads it
(`{ id, kind, inputName, requestedBy, requestedUtc, status, startedUtc, finishedUtc, result, error }`), and
`GET /api/v1/long-operations/{id}/file` downloads a produced file (a workbook or a PDF).

```python
accepted = client.imports.import_zones_in_background(file=FileUpload.from_path("zones.xlsx"))
poller = client.poll_long_operation(accepted)            # from the 202 Location header
done = poller.wait(poll_interval=2.0, timeout=600.0, on_progress=lambda op: print(op.status))
print(done.result)                                       # the import report (JSON)

# a report or document pack: download its file
with poller.download_result() as file:
    file.save(file.file_name or "result.xlsx")

# asyncio: done = await async_client.poll_long_operation(accepted).wait()
```

`wait` raises `LongOperationFailedError` (with `operation.error`) when the operation ends `Failed`, and the built-in `TimeoutError` after `timeout`. `client.poll_long_operation(uuid)` follows an operation by id.

There is no numeric progress in the API: the progress callback receives every state read. Poll intervals of 1 to 5 seconds are
appropriate; the API also notifies the browser UI through SignalR, which SDK clients do not need.
