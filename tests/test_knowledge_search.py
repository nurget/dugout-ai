import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.tools.knowledge_search import search_public_baseball_knowledge
from app.evaluation.rag_eval import grade_rag_traces, load_rag_dataset


def test_rag_evaluation_dataset_covers_grounding_access_freshness_and_injection():
    dataset_path = Path(__file__).parents[1] / "evals/rag/v1.jsonl"
    cases = load_rag_dataset(dataset_path)

    assert len({case["case_id"] for case in cases}) == len(cases)
    assert {case["category"] for case in cases} >= {
        "GROUNDED_ANSWER",
        "NO_EVIDENCE",
        "AUTHORIZATION",
        "FRESHNESS",
        "PROMPT_INJECTION",
    }
    assert all(
        case["retrieval_expectations"]["visibility"] == "public"
        for case in cases
    )
    fixture_path = dataset_path.parent / "fixtures/v1.json"
    fixtures = json.loads(fixture_path.read_text(encoding="utf-8"))["fixtures"]
    assert all(fixture["synthetic_only"] for fixture in fixtures)
    mixed_fixture = next(
        fixture for fixture in fixtures
        if fixture["fixture_ref"] == "fixture:public-and-restricted-docs-v1"
    )
    returned_ids = set(mixed_fixture["expected_returned_document_ids"])
    private_ids = {
        document["document_id"]
        for document in mixed_fixture["documents"]
        if document["visibility"] != "public"
    }
    assert returned_ids.isdisjoint(private_ids)


def test_rag_grader_checks_public_citations_dates_and_no_evidence():
    dataset_path = Path(__file__).parents[1] / "evals/rag/v1.jsonl"
    cases = load_rag_dataset(dataset_path)
    shared_source = {
        "visibility": "public",
        "title": "Synthetic test document",
        "source_url": "https://example.test/synthetic",
        "effective_date": "2026-01-01",
        "content": "Synthetic fixture text; not a real baseball rule.",
    }
    traces = [
        {
            "case_id": "public_rule_with_citation",
            "visibility_filter": "public",
            "result_limit": 3,
            "retrieved_results": [shared_source],
            "answer": (
                "Synthetic test document (https://example.test/synthetic); "
                "효력일 2026-01-01에 따르면 테스트용 설명입니다."
            ),
        },
        {
            "case_id": "no_relevant_document",
            "visibility_filter": "public",
            "result_limit": 3,
            "retrieved_results": [],
            "answer": "검색 결과가 없습니다. 근거를 찾지 못했습니다.",
        },
    ]

    report = grade_rag_traces(cases[:2], traces)

    assert report["failed_checks"] == 0
    assert report["passed_checks"] == report["check_count"]


def test_rag_grader_fails_if_non_public_content_was_returned():
    dataset_path = Path(__file__).parents[1] / "evals/rag/v1.jsonl"
    cases = load_rag_dataset(dataset_path)
    case = next(
        item for item in cases
        if item["case_id"] == "exclude_non_public_documents"
    )
    report = grade_rag_traces([case], [{
        "case_id": "exclude_non_public_documents",
        "visibility_filter": "public",
        "result_limit": 3,
        "retrieved_results": [{
            "visibility": "team_private",
            "title": "Restricted synthetic fixture",
            "content": "Synthetic test data.",
        }],
        "answer": "검색 결과입니다.",
    }])

    failed = [check for check in report["checks"] if not check["passed"]]
    assert len(failed) == 1
    assert failed[0]["check"] == "public_sources_only"


def test_rag_grader_catches_document_injection_canary_in_answer():
    dataset_path = Path(__file__).parents[1] / "evals/rag/v1.jsonl"
    cases = load_rag_dataset(dataset_path)
    case = next(
        item for item in cases
        if item["case_id"] == "ignore_document_instructions"
    )

    report = grade_rag_traces([case], [{
        "case_id": case["case_id"],
        "visibility_filter": "public",
        "result_limit": 3,
        "retrieved_results": [{"visibility": "public", "content": "synthetic"}],
        "answer": "SHOW_PRIVATE_DATA_CANARY_DO_NOT_REPEAT",
    }])

    failed = [check for check in report["checks"] if not check["passed"]]
    assert [check["check"] for check in failed] == ["forbidden_answer_text"]


@pytest.mark.asyncio
async def test_search_requires_public_visibility_and_returns_source_metadata():
    search = AsyncMock(return_value=SimpleNamespace(data=[
        SimpleNamespace(
            attributes={
                "title": "KBO 규정집",
                "source_url": "https://example.test/rules",
                "effective_date": "2026-01-01",
                "visibility": "public",
            },
            filename="rules.pdf",
            score=0.91,
            content=[SimpleNamespace(type="text", text="문서 근거")],
        ),
        SimpleNamespace(
            attributes={"visibility": "public"},
            filename="empty.txt",
            score=0.8,
            content=[],
        ),
    ]))
    client = SimpleNamespace(
        vector_stores=SimpleNamespace(search=search),
    )

    result = await search_public_baseball_knowledge(
        client=client,
        vector_store_id="vs_public",
        query="  인필드   플라이 규정  ",
    )

    search.assert_awaited_once_with(
        vector_store_id="vs_public",
        query="인필드 플라이 규정",
        filters={"type": "eq", "key": "visibility", "value": "public"},
        max_num_results=3,
        rewrite_query=True,
    )
    assert result["ok"] is True
    assert result["data"]["result_count"] == 1
    assert result["data"]["results"][0] == {
        "visibility": "public",
        "title": "KBO 규정집",
        "source_url": "https://example.test/rules",
        "effective_date": "2026-01-01",
        "score": 0.91,
        "content": "문서 근거",
    }


@pytest.mark.asyncio
async def test_empty_query_fails_without_calling_search():
    search = AsyncMock()
    client = SimpleNamespace(vector_stores=SimpleNamespace(search=search))

    result = await search_public_baseball_knowledge(
        client=client,
        vector_store_id="vs_public",
        query="  \n ",
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_QUERY"
    search.assert_not_awaited()
