import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.knowledge_corpus import (
    ManifestValidationError,
    ingest_public_knowledge_documents,
    validate_public_knowledge_manifest,
)


def make_manifest(tmp_path: Path, *, rights_verified: bool = True) -> Path:
    corpus = tmp_path / "data/private/rag"
    corpus.mkdir(parents=True)
    document = corpus / "rule.md"
    document.write_text("Reviewed baseball rule summary.", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "version": 1,
        "documents": [{
            "document_id": "rule-summary-2026",
            "path": "data/private/rag/rule.md",
            "title": "Rule summary",
            "source_url": "https://example.org/rules",
            "effective_date": "2026-01-01",
            "license_name": "CC BY 4.0",
            "rights_basis": "https://example.org/license",
            "rights_verified": rights_verified,
            "sha256": hashlib.sha256(document.read_bytes()).hexdigest(),
        }],
    }), encoding="utf-8")
    return manifest


def test_manifest_validates_rights_provenance_and_checksum(tmp_path):
    manifest = make_manifest(tmp_path)

    documents = validate_public_knowledge_manifest(
        manifest,
        repository_root=tmp_path,
    )

    assert documents[0].attributes == {
        "visibility": "public",
        "document_id": "rule-summary-2026",
        "title": "Rule summary",
        "source_url": "https://example.org/rules",
        "effective_date": "2026-01-01",
        "license_name": "CC BY 4.0",
        "rights_basis": "https://example.org/license",
        "sha256": hashlib.sha256(
            (tmp_path / "data/private/rag/rule.md").read_bytes()
        ).hexdigest(),
    }


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"rights_verified": False}, "rights_verified"),
        ({"source_url": "http://example.org/rules"}, "HTTPS"),
        ({"effective_date": "undated"}, "YYYY-MM-DD"),
        ({"path": "README.md"}, "data/private/rag"),
        ({"sha256": "0" * 64}, "현재 파일과 일치"),
    ],
)
def test_manifest_rejects_unreviewed_or_unverifiable_documents(
    tmp_path,
    change,
    message,
):
    manifest = make_manifest(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["documents"][0].update(change)
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ManifestValidationError, match=message):
        validate_public_knowledge_manifest(
            manifest,
            repository_root=tmp_path,
        )


class FakePage:
    def __init__(self, items):
        self.items = items

    async def _iterate(self):
        for item in self.items:
            yield item

    def auto_paging_iter(self):
        return self._iterate()


@pytest.mark.asyncio
async def test_ingestion_skips_matching_document_and_uploads_new_document(tmp_path):
    manifest = make_manifest(tmp_path)
    document = validate_public_knowledge_manifest(
        manifest,
        repository_root=tmp_path,
    )[0]
    uploaded_content = []

    async def upload(**kwargs):
        uploaded_content.append(kwargs["file"].read())
        return SimpleNamespace(status="completed", id="file_new")

    client = SimpleNamespace(vector_stores=SimpleNamespace(
        files=SimpleNamespace(
            list=AsyncMock(return_value=FakePage([
                SimpleNamespace(
                    id="file_old",
                    attributes={
                        "document_id": "other-doc",
                        "sha256": "already-uploaded",
                    },
                ),
            ])),
            upload_and_poll=AsyncMock(side_effect=upload),
        ),
    ))

    outcome = await ingest_public_knowledge_documents(
        client=client,
        vector_store_id="vs_public",
        documents=[document],
    )

    assert outcome == [{
        "document_id": "rule-summary-2026",
        "status": "uploaded",
        "file_id": "file_new",
    }]
    assert uploaded_content == [b"Reviewed baseball rule summary."]
    upload_kwargs = client.vector_stores.files.upload_and_poll.await_args.kwargs
    assert upload_kwargs["vector_store_id"] == "vs_public"
    assert upload_kwargs["attributes"]["visibility"] == "public"
    assert upload_kwargs["attributes"]["source_url"] == "https://example.org/rules"


@pytest.mark.asyncio
async def test_ingestion_refuses_changed_content_for_existing_document_id(tmp_path):
    manifest = make_manifest(tmp_path)
    document = validate_public_knowledge_manifest(
        manifest,
        repository_root=tmp_path,
    )[0]
    upload = AsyncMock()
    client = SimpleNamespace(vector_stores=SimpleNamespace(
        files=SimpleNamespace(
            list=AsyncMock(return_value=FakePage([
                SimpleNamespace(
                    id="file_previous",
                    attributes={
                        "document_id": document.document_id,
                        "sha256": "f" * 64,
                    },
                ),
            ])),
            upload_and_poll=upload,
        ),
    ))

    with pytest.raises(ManifestValidationError, match="새 저장소로 재색인"):
        await ingest_public_knowledge_documents(
            client=client,
            vector_store_id="vs_public",
            documents=[document],
        )
    upload.assert_not_awaited()


@pytest.mark.asyncio
async def test_ingestion_skips_completed_matching_document(tmp_path):
    manifest = make_manifest(tmp_path)
    document = validate_public_knowledge_manifest(
        manifest,
        repository_root=tmp_path,
    )[0]
    upload = AsyncMock()
    client = SimpleNamespace(vector_stores=SimpleNamespace(
        files=SimpleNamespace(
            list=AsyncMock(return_value=FakePage([
                SimpleNamespace(
                    id="file_current",
                    status="completed",
                    attributes={
                        "document_id": document.document_id,
                        "sha256": document.sha256,
                    },
                ),
            ])),
            upload_and_poll=upload,
            poll=AsyncMock(),
        ),
    ))

    outcome = await ingest_public_knowledge_documents(
        client=client,
        vector_store_id="vs_public",
        documents=[document],
    )

    assert outcome == [{
        "document_id": document.document_id,
        "status": "already_current",
        "file_id": "file_current",
    }]
    upload.assert_not_awaited()
    client.vector_stores.files.poll.assert_not_awaited()


@pytest.mark.asyncio
async def test_ingestion_polls_matching_file_left_in_progress(tmp_path):
    manifest = make_manifest(tmp_path)
    document = validate_public_knowledge_manifest(
        manifest,
        repository_root=tmp_path,
    )[0]
    poll = AsyncMock(return_value=SimpleNamespace(status="completed"))
    upload = AsyncMock()
    client = SimpleNamespace(vector_stores=SimpleNamespace(
        files=SimpleNamespace(
            list=AsyncMock(return_value=FakePage([
                SimpleNamespace(
                    id="file_in_progress",
                    status="in_progress",
                    attributes={
                        "document_id": document.document_id,
                        "sha256": document.sha256,
                    },
                ),
            ])),
            upload_and_poll=upload,
            poll=poll,
        ),
    ))

    outcome = await ingest_public_knowledge_documents(
        client=client,
        vector_store_id="vs_public",
        documents=[document],
    )

    assert outcome[0]["status"] == "already_current"
    poll.assert_awaited_once_with(
        "file_in_progress",
        vector_store_id="vs_public",
        max_wait_seconds=300,
    )
    upload.assert_not_awaited()
