"""Read-only retrieval from the configured public baseball knowledge store."""

from typing import Any

MAX_QUERY_LENGTH = 500
MAX_RESULTS = 3
MAX_CHUNK_LENGTH = 2400


def _value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


async def search_public_baseball_knowledge(
    *,
    client: Any,
    vector_store_id: str,
    query: str,
) -> dict[str, Any]:
    """Search only documents explicitly tagged as public.

    The source uploader must set ``visibility=public`` and source metadata such
    as ``source_url`` and ``effective_date``. An absent URL is reported as
    unavailable rather than fabricated.
    """
    normalized_query = " ".join(query.split())[:MAX_QUERY_LENGTH]
    if not normalized_query:
        return {
            "ok": False,
            "error": {"code": "INVALID_QUERY", "message": "검색어가 비어 있습니다."},
        }

    response = await client.vector_stores.search(
        vector_store_id=vector_store_id,
        query=normalized_query,
        filters={"type": "eq", "key": "visibility", "value": "public"},
        max_num_results=MAX_RESULTS,
        rewrite_query=True,
    )

    raw_results = _value(response, "data", []) or []
    results = []
    for item in raw_results[:MAX_RESULTS]:
        attributes = _value(item, "attributes", {}) or {}
        content = _value(item, "content", []) or []
        text = "\n".join(
            str(_value(part, "text", ""))
            for part in content
            if _value(part, "type", "text") == "text"
        ).strip()
        if not text:
            continue
        results.append({
            "visibility": "public",
            "title": str(attributes.get("title") or _value(item, "filename", "공개 야구 문서")),
            "source_url": attributes.get("source_url"),
            "effective_date": attributes.get("effective_date"),
            "score": _value(item, "score"),
            "content": text[:MAX_CHUNK_LENGTH],
        })

    return {
        "ok": True,
        "data": {
            "query": normalized_query,
            "result_count": len(results),
            "results": results,
        },
    }
