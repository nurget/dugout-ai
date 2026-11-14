"""Manifest validation and controlled ingestion for public RAG documents."""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


DOCUMENT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{2,63}$")
SUPPORTED_SUFFIXES = {".md", ".txt", ".pdf"}
MAX_DOCUMENT_BYTES = 50 * 1024 * 1024


class ManifestValidationError(ValueError):
    pass


@dataclass(frozen=True)
class PublicKnowledgeDocument:
    document_id: str
    path: Path
    title: str
    source_url: str
    effective_date: date
    license_name: str
    rights_basis: str
    sha256: str

    @property
    def attributes(self) -> dict[str, str]:
        return {
            "visibility": "public",
            "document_id": self.document_id,
            "title": self.title,
            "source_url": self.source_url,
            "effective_date": self.effective_date.isoformat(),
            "license_name": self.license_name,
            "rights_basis": self.rights_basis,
            "sha256": self.sha256,
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_public_knowledge_manifest(
    manifest_path: Path,
    *,
    repository_root: Path,
) -> list[PublicKnowledgeDocument]:
    """Validate rights attestation, provenance, date, location, and digest."""
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestValidationError(
            f"manifest를 읽을 수 없습니다: {exc}"
        ) from exc

    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise ManifestValidationError("manifest version은 1이어야 합니다.")
    raw_documents = payload.get("documents")
    if not isinstance(raw_documents, list) or not raw_documents:
        raise ManifestValidationError("documents에는 문서가 한 건 이상 필요합니다.")

    private_corpus_root = (repository_root / "data/private/rag").resolve()
    documents: list[PublicKnowledgeDocument] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(raw_documents, start=1):
        label = f"documents[{index}]"
        if not isinstance(raw, dict):
            raise ManifestValidationError(f"{label}은 객체여야 합니다.")
        required = {
            "document_id", "path", "title", "source_url", "effective_date",
            "license_name", "rights_basis", "rights_verified", "sha256",
        }
        missing = required - raw.keys()
        if missing:
            raise ManifestValidationError(
                f"{label} 필수 항목 누락: {', '.join(sorted(missing))}"
            )
        document_id = raw["document_id"]
        if (
            not isinstance(document_id, str)
            or not DOCUMENT_ID_PATTERN.fullmatch(document_id)
            or document_id in seen_ids
        ):
            raise ManifestValidationError(
                f"{label}.document_id 형식 오류 또는 중복"
            )
        seen_ids.add(document_id)
        if raw["rights_verified"] is not True:
            raise ManifestValidationError(
                f"{label}.rights_verified가 true가 아닙니다. 권리 확인 후 적재하세요."
            )

        for field in ("title", "license_name", "rights_basis"):
            value = raw[field]
            if not isinstance(value, str) or not value.strip() or len(value) > 512:
                raise ManifestValidationError(
                    f"{label}.{field}는 1~512자의 문자열이어야 합니다."
                )
        source_url = raw["source_url"]
        parsed_url = urlparse(source_url) if isinstance(source_url, str) else None
        if not parsed_url or parsed_url.scheme != "https" or not parsed_url.netloc:
            raise ManifestValidationError(
                f"{label}.source_url은 HTTPS URL이어야 합니다."
            )
        try:
            effective_date = date.fromisoformat(raw["effective_date"])
        except (TypeError, ValueError) as exc:
            raise ManifestValidationError(
                f"{label}.effective_date는 YYYY-MM-DD 형식이어야 합니다."
            ) from exc

        relative_path = raw["path"]
        if not isinstance(relative_path, str) or not relative_path:
            raise ManifestValidationError(f"{label}.path는 필수입니다.")
        source_path = (repository_root / relative_path).resolve()
        if not source_path.is_relative_to(private_corpus_root):
            raise ManifestValidationError(
                f"{label}.path는 data/private/rag/ 내부여야 합니다."
            )
        if source_path.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise ManifestValidationError(
                f"{label}.path는 md, txt, pdf 파일이어야 합니다."
            )
        if not source_path.is_file():
            raise ManifestValidationError(f"{label}.path 파일이 없습니다.")
        if source_path.stat().st_size > MAX_DOCUMENT_BYTES:
            raise ManifestValidationError(
                f"{label}.path 파일이 50 MiB 제한을 초과합니다."
            )

        expected_hash = raw["sha256"]
        actual_hash = _sha256(source_path)
        if (
            not isinstance(expected_hash, str)
            or not re.fullmatch(r"[0-9a-f]{64}", expected_hash)
            or expected_hash != actual_hash
        ):
            raise ManifestValidationError(
                f"{label}.sha256가 현재 파일과 일치하지 않습니다. "
                f"계산값: {actual_hash}"
            )

        documents.append(PublicKnowledgeDocument(
            document_id=document_id,
            path=source_path,
            title=raw["title"].strip(),
            source_url=source_url,
            effective_date=effective_date,
            license_name=raw["license_name"].strip(),
            rights_basis=raw["rights_basis"].strip(),
            sha256=actual_hash,
        ))
    return documents


async def ingest_public_knowledge_documents(
    *,
    client: Any,
    vector_store_id: str,
    documents: list[PublicKnowledgeDocument],
) -> list[dict[str, str]]:
    """Upload missing approved documents; refuse changed IDs to avoid drift."""
    existing: dict[str, list[tuple[str, str | None, str]]] = {}
    page = await client.vector_stores.files.list(vector_store_id, limit=100)
    async for item in page.auto_paging_iter():
        attributes = getattr(item, "attributes", None) or {}
        document_id = attributes.get("document_id")
        if document_id:
            existing.setdefault(document_id, []).append((
                item.id,
                attributes.get("sha256"),
                getattr(item, "status", "unknown"),
            ))

    for document in documents:
        attached = existing.get(document.document_id, [])
        if len(attached) > 1:
            raise ManifestValidationError(
                f"저장소에 {document.document_id} 문서가 중복되어 있습니다."
            )
        if attached and attached[0][1] != document.sha256:
            raise ManifestValidationError(
                f"{document.document_id}의 내용이 바뀌었습니다. "
                "기존 Vector Store를 덮어쓰지 않습니다. 새 저장소로 재색인하세요."
            )

    outcomes: list[dict[str, str]] = []
    for document in documents:
        attached = existing.get(document.document_id, [])
        if attached:
            file_id, _, status = attached[0]
            if status == "in_progress":
                processed = await client.vector_stores.files.poll(
                    file_id,
                    vector_store_id=vector_store_id,
                    max_wait_seconds=300,
                )
                status = getattr(processed, "status", "unknown")
            if status != "completed":
                raise RuntimeError(
                    f"{document.document_id} 기존 파일 처리 상태가 "
                    f"{status}입니다. 완료 상태를 확인한 뒤 다시 실행하세요."
                )
            outcomes.append({
                "document_id": document.document_id,
                "status": "already_current",
                "file_id": file_id,
            })
            continue
        with document.path.open("rb") as source_file:
            result = await client.vector_stores.files.upload_and_poll(
                vector_store_id=vector_store_id,
                file=source_file,
                attributes=document.attributes,
                max_wait_seconds=300,
            )
        if getattr(result, "status", None) != "completed":
            raise RuntimeError(
                f"{document.document_id} 처리 실패: "
                f"{getattr(result, 'status', 'unknown')}"
            )
        outcomes.append({
            "document_id": document.document_id,
            "status": "uploaded",
            "file_id": result.id,
        })
    return outcomes
