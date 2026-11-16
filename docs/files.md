# File upload and download

## Upload (multipart/form-data)

27 operations take files (documents, PODs, photos, imports, logos). Their parts are typed: a `FileUpload` per file part, plain
values for text parts.

```python
added = client.jobs.add_job_pods(job_id, files=[
    FileUpload.from_path("pod.pdf", "application/pdf"),
    FileUpload(photo_bytes, "photo.jpg", "image/jpeg"),
])
print(added.data.ids)
```

`FileUpload(content, file_name, content_type)` takes bytes or a binary file object; `FileUpload.from_path` reads a file. A request built from a non-seekable stream is not retried.

## Download (streamed)

Operations that answer with a file (document, POD, photo and attachment downloads, exports, journals, long-operation results)
return a streamed `FileDownload` with its media type, file name (from `Content-Disposition`) and length.

```python
with client.jobs.download_job_pod(job_id, pod_id).data as pod:   # streamed: close it
    print(pod.file_name, pod.content_type, pod.length)
    pod.save(f"pods/{pod.file_name or 'pod.pdf'}")

# asyncio
async with (await async_client.jobs.download_job_pod(job_id, pod_id)).data as pod:
    await pod.asave("pod.pdf")
```

## Operations with an undeclared answer

The contract does not declare the answer of about 400 operations; they return a buffered `ResponseBody` that may hold JSON, a
small file or nothing:

```python
answer = client.reference_data.list_country_states(country_id)   # an operation whose answer the contract does not declare
if answer.data.is_json:
    print(answer.data.json())
states = answer.data.parse(list[dict[str, object]])                # or validate into a type you know
```
