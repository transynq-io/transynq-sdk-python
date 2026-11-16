# Pagination and grid queries

## Paged collections

Collections answer `PagedResponse { items, page, pageSize, total }` (`page` starts at 1, `pageSize` 1..200, default 50;
`sort` is a comma list such as `-date,name` from the resource's whitelist). Operations that return one also have an
**auto-paging** variant that reads page after page until an empty page or `page * pageSize >= total`.

```python
# one page
page = client.reference_data.list_public_holidays(country_id=1, year=2026, page=1, page_size=50, sort="-date")
print(len(page.data.items), "of", page.data.total)

# every item, page by page (a generator)
for holiday in client.reference_data.list_public_holidays_auto_paging(country_id=1, year=2026):
    print(holiday.date, holiday.name)

# asyncio
async for holiday in async_client.reference_data.list_public_holidays_auto_paging(country_id=1, year=2026):
    print(holiday.name)
```

## Grid queries (large lists)

Large lists - jobs, invoices, manifests - are read through the grid endpoints: `GET /api/v1/grids` lists the grids,
`GET /api/v1/grids/{id}` is a grid's definition (its columns, filter operators and sort keys are the whitelist), and
`POST /api/v1/grids/{id}/query` reads one page of rows (page size up to 500, at most 4 sort keys; filter values as text, dates
`yyyy-MM-dd` or relative such as `today-30`). The SDK's grid helper iterates every row:

```python
from transynq import models as m

definition = client.grids.get_grid("jobs").data            # the columns and operators you may use
request = m.GridQueryRequest(
    columns=["jobNumber", "customer", "status"],
    filters=[m.GridFilterDto(column="status", operator="eq", values=["Booked"])],
    sort=None, page=None, page_size=500, search=None, summaries=None,
)
for row in client.iter_grid_rows("jobs", request):          # a dict per row
    print(row["jobNumber"])
```

Value lists (`.../facets/{column}`), CSV export (`.../export`, up to 100,000 rows, a streamed file) and saved views
(`.../views/{viewId}`) are ordinary operations of the Grids group; see the [resource index](resources/README.md#grids).
