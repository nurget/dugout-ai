"""Local ingestion for user-owned rulebook PDFs."""

import hashlib
import json
import os
import re
import shutil
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

from pypdf import PdfReader

from app.tools.private_rule_search import PRIVATE_KNOWLEDGE_ROOT

MAX_PRIVATE_RULEBOOK_BYTES = 20 * 1024 * 1024
MAX_PRIVATE_RULEBOOK_PAGES = 500
MAX_CHUNK_CHARS = 1200
OVERLAP_CHARS = 180
RULE_PATTERN = re.compile(r"(?<!\d)(\d+\.\d+(?:\([a-z0-9]+\))?)")
PRINTED_PAGE_PATTERN = re.compile(r"(?m)^\s*[․·•]\s*(\d{1,3})\s*[․·•]\s*$")


class PrivateRulebookError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def page_chunks(page_text: str, pdf_page: int) -> list[dict]:
    text = "\n".join(line.rstrip() for line in page_text.splitlines()).strip()
    if not text:
        return []
    matches = list(RULE_PATTERN.finditer(text))
    printed_pages = PRINTED_PAGE_PATTERN.findall(text)
    printed_page = int(printed_pages[-1]) if printed_pages else None

    output = []
    start = 0
    while start < len(text):
        end = min(start + MAX_CHUNK_CHARS, len(text))
        if end < len(text):
            newline = text.rfind("\n", start + MAX_CHUNK_CHARS // 2, end)
            if newline > start:
                end = newline
        chunk = text[start:end].strip()
        if chunk:
            chunk_rules = [match for match in matches if start <= match.start() < end]
            page_rules = [match for match in matches if match.start() <= start]
            specific_rules = [match for match in chunk_rules if "(" in match.group(1)]
            heading = (
                specific_rules[0]
                if specific_rules
                else chunk_rules[0] if chunk_rules
                else page_rules[-1] if page_rules
                else None
            )
            output.append({
                "title": "2026 공식야구규칙",
                "edition": "2026",
                "rule_number": heading.group(1) if heading else None,
                "pdf_page": pdf_page,
                "printed_page": printed_page,
                "text": chunk,
            })
        if end >= len(text):
            break
        start = max(end - OVERLAP_CHARS, start + 1)
    return output


def extract_private_rulebook(pdf_bytes: bytes) -> tuple[dict, list[dict]]:
    if not pdf_bytes:
        raise PrivateRulebookError(400, "EMPTY_UPLOAD", "업로드 파일이 비어 있습니다.")
    if len(pdf_bytes) > MAX_PRIVATE_RULEBOOK_BYTES:
        raise PrivateRulebookError(413, "FILE_TOO_LARGE", "PDF는 20MB 이하만 업로드할 수 있습니다.")
    if not pdf_bytes.startswith(b"%PDF-"):
        raise PrivateRulebookError(415, "INVALID_PDF", "PDF 파일을 업로드해 주세요.")

    try:
        reader = PdfReader(BytesIO(pdf_bytes), strict=False)
        if reader.is_encrypted:
            raise PrivateRulebookError(422, "ENCRYPTED_PDF", "암호화된 PDF는 색인할 수 없습니다.")
        page_count = len(reader.pages)
        if page_count == 0 or page_count > MAX_PRIVATE_RULEBOOK_PAGES:
            raise PrivateRulebookError(422, "INVALID_PAGE_COUNT", "PDF 페이지 수는 1~500페이지여야 합니다.")
        chunks = []
        nonempty_pages = 0
        for page_number, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text() or ""
            if page_text.strip():
                nonempty_pages += 1
                chunks.extend(page_chunks(page_text, page_number))
    except PrivateRulebookError:
        raise
    except Exception as error:
        raise PrivateRulebookError(422, "PDF_PARSE_FAILED", "PDF를 읽거나 텍스트를 추출하지 못했습니다.") from error

    if not chunks:
        raise PrivateRulebookError(422, "NO_EXTRACTABLE_TEXT", "텍스트를 추출할 수 있는 페이지가 없습니다.")
    return {
        "pdf_pages": page_count,
        "nonempty_pages": nonempty_pages,
        "blank_pages": page_count - nonempty_pages,
        "chunks": len(chunks),
    }, chunks


def _current_sha256(owner_dir: Path) -> str | None:
    pointer = owner_dir / "current.json"
    if pointer.is_file():
        try:
            payload = json.loads(pointer.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        digest = payload.get("sha256") if isinstance(payload, dict) else None
        return digest if isinstance(digest, str) and re.fullmatch(r"[a-f0-9]{64}", digest) else None
    # A flat index was used by the first local-only version. Treat it as an
    # existing document so an upload cannot silently replace it.
    if (owner_dir / "index.jsonl").is_file():
        return "legacy-index"
    return None


def store_private_rulebook(
    *,
    owner_user_id: str,
    pdf_bytes: bytes,
    replace: bool = False,
    prepared: tuple[dict, list[dict]] | None = None,
) -> dict:
    try:
        owner_id = str(UUID(owner_user_id))
    except (ValueError, TypeError, AttributeError) as error:
        raise PrivateRulebookError(400, "INVALID_OWNER", "사용자 식별자가 올바르지 않습니다.") from error

    if len(pdf_bytes) > MAX_PRIVATE_RULEBOOK_BYTES:
        raise PrivateRulebookError(413, "FILE_TOO_LARGE", "PDF는 20MB 이하만 업로드할 수 있습니다.")
    digest = hashlib.sha256(pdf_bytes).hexdigest()
    owner_dir = PRIVATE_KNOWLEDGE_ROOT / owner_id
    previous_digest = _current_sha256(owner_dir)
    version_dir = owner_dir / digest
    if previous_digest == digest and (version_dir / "index.jsonl").is_file():
        metadata, _ = prepared or extract_private_rulebook(pdf_bytes)
        return {**metadata, "sha256": digest, "replaced": False, "unchanged": True}
    if previous_digest is not None and not replace:
        raise PrivateRulebookError(409, "DOCUMENT_EXISTS", "이미 등록된 문서가 있습니다. 교체하려면 replace=true로 요청하세요.")

    metadata, chunks = prepared or extract_private_rulebook(pdf_bytes)
    PRIVATE_KNOWLEDGE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(PRIVATE_KNOWLEDGE_ROOT, 0o700)
    owner_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(owner_dir, 0o700)

    if not (version_dir / "index.jsonl").is_file():
        if version_dir.exists():
            shutil.rmtree(version_dir)
        staging_dir = owner_dir / f".staging-{uuid4().hex}"
        staging_dir.mkdir(mode=0o700)
        try:
            with (staging_dir / "original.pdf").open("wb") as pdf_file:
                pdf_file.write(pdf_bytes)
            with (staging_dir / "index.jsonl").open("w", encoding="utf-8") as index_file:
                for row in chunks:
                    index_file.write(json.dumps(row, ensure_ascii=False) + "\n")
            (staging_dir / "manifest.json").write_text(
                json.dumps({
                    "title": "2026 공식야구규칙",
                    "edition": "2026",
                    "sha256": digest,
                    **metadata,
                }, ensure_ascii=False),
                encoding="utf-8",
            )
            for path in staging_dir.iterdir():
                os.chmod(path, 0o600)
            if version_dir.exists():
                shutil.rmtree(staging_dir)
            else:
                os.replace(staging_dir, version_dir)
            os.chmod(version_dir, 0o700)
        except Exception:
            if staging_dir.exists():
                shutil.rmtree(staging_dir)
            raise

    pointer_tmp = owner_dir / f".current-{uuid4().hex}.tmp"
    pointer_tmp.write_text(json.dumps({"sha256": digest}), encoding="utf-8")
    os.chmod(pointer_tmp, 0o600)
    os.replace(pointer_tmp, owner_dir / "current.json")
    return {
        **metadata,
        "sha256": digest,
        "replaced": previous_digest is not None and previous_digest != digest,
        "unchanged": False,
    }
