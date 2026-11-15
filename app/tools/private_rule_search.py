"""User-scoped retrieval over locally stored private baseball rule documents."""

import json
import re
from pathlib import Path
from typing import Any
from uuid import UUID

MAX_QUERY_LENGTH = 500
MAX_RESULTS = 3
MAX_CHUNK_LENGTH = 1500
PROJECT_ROOT = Path(__file__).resolve().parents[2]
PRIVATE_KNOWLEDGE_ROOT = PROJECT_ROOT / "data/private/rag"


def _owner_dir(owner_user_id: str) -> Path:
    # UUID validation prevents path traversal and ties a corpus to an app user.
    owner_id = str(UUID(owner_user_id))
    return PRIVATE_KNOWLEDGE_ROOT / owner_id


def has_private_rulebook(owner_user_id: str | None) -> bool:
    if not owner_user_id:
        return False
    try:
        return (_owner_dir(owner_user_id) / "index.jsonl").is_file()
    except ValueError:
        return False


def _terms(value: str) -> set[str]:
    words = re.findall(r"[\w가-힣]+", value.casefold())
    terms = set(words)
    for word in words:
        if len(word) > 2:
            terms.update(word[i : i + 2] for i in range(len(word) - 1))
    return terms


def _value(item: Any, key: str, default: Any = None) -> Any:
    return item.get(key, default) if isinstance(item, dict) else getattr(item, key, default)


def search_private_baseball_rules(
    *,
    owner_user_id: str,
    query: str,
) -> dict[str, Any]:
    """Search only the private local index owned by the authenticated user."""
    normalized_query = " ".join(query.split())[:MAX_QUERY_LENGTH]
    if not normalized_query:
        return {
            "ok": False,
            "error": {"code": "INVALID_QUERY", "message": "검색어가 비어 있습니다."},
        }

    try:
        index_path = _owner_dir(owner_user_id) / "index.jsonl"
    except ValueError:
        return {
            "ok": False,
            "error": {"code": "PRIVATE_INDEX_UNAVAILABLE", "message": "비공개 규정 인덱스를 찾을 수 없습니다."},
        }
    if not index_path.is_file():
        return {
            "ok": False,
            "error": {"code": "PRIVATE_INDEX_UNAVAILABLE", "message": "이 계정에 연결된 비공개 규정 문서가 없습니다."},
        }

    query_terms = _terms(normalized_query)
    ranked: list[tuple[float, dict[str, Any]]] = []
    try:
        with index_path.open(encoding="utf-8") as index_file:
            for line in index_file:
                row = json.loads(line)
                text = str(row.get("text", ""))
                overlap = query_terms & _terms(text)
                if not overlap:
                    continue
                # Favor exact phrase and explicit rule-number matches.
                score = len(overlap) / max(len(query_terms) ** 0.5, 1)
                if normalized_query.casefold() in text.casefold():
                    score += 2.0
                rule_number = str(row.get("rule_number") or "")
                if rule_number and rule_number in normalized_query:
                    score += 3.0
                ranked.append((score, row))
    except (OSError, json.JSONDecodeError):
        return {
            "ok": False,
            "error": {"code": "PRIVATE_INDEX_READ_ERROR", "message": "비공개 규정 인덱스를 읽을 수 없습니다."},
        }

    ranked.sort(key=lambda item: item[0], reverse=True)
    results = [
        {
            "visibility": "private",
            "title": str(row.get("title") or "2026 공식야구규칙"),
            "edition": str(row.get("edition") or "2026"),
            "rule_number": row.get("rule_number"),
            "pdf_page": row.get("pdf_page"),
            "printed_page": row.get("printed_page"),
            "score": round(score, 4),
            "content": str(row.get("text", ""))[:MAX_CHUNK_LENGTH],
        }
        for score, row in ranked[:MAX_RESULTS]
    ]
    return {
        "ok": True,
        "data": {
            "query": normalized_query,
            "result_count": len(results),
            "results": results,
        },
    }
