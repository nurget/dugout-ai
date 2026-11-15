"""Create a local user-scoped index for a private PDF rulebook."""

import argparse
import json
import os
import re
import shutil
from pathlib import Path
from uuid import UUID

from pypdf import PdfReader

from app.tools.private_rule_search import PRIVATE_KNOWLEDGE_ROOT

MAX_CHUNK_CHARS = 1200
OVERLAP_CHARS = 180
RULE_PATTERN = re.compile(r"(?<!\d)(\d+\.\d+(?:\([a-z0-9]+\))?)")
PRINTED_PAGE_PATTERN = re.compile(r"(?m)^\s*[․·•]\s*(\d{1,3})\s*[․·•]\s*$")


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--owner-user-id", required=True, help="로그인 계정 UUID")
    parser.add_argument("--apply", action="store_true", help="원문과 인덱스를 data/private/rag에 저장")
    args = parser.parse_args()
    owner_id = str(UUID(args.owner_user_id))
    source = args.pdf.resolve(strict=True)
    reader = PdfReader(str(source))
    chunks = []
    nonempty_pages = 0
    for page_number, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        if page_text.strip():
            nonempty_pages += 1
            chunks.extend(page_chunks(page_text, page_number))

    print(json.dumps({
        "pdf_pages": len(reader.pages),
        "nonempty_pages": nonempty_pages,
        "blank_pages": len(reader.pages) - nonempty_pages,
        "chunks": len(chunks),
        "owner_user_id": owner_id,
        "applied": args.apply,
    }, ensure_ascii=False))
    if not args.apply:
        return

    owner_dir = PRIVATE_KNOWLEDGE_ROOT / owner_id
    PRIVATE_KNOWLEDGE_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(PRIVATE_KNOWLEDGE_ROOT, 0o700)
    owner_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(owner_dir, 0o700)
    destination_pdf = owner_dir / "2026_official_baseball_rules.pdf"
    index_path = owner_dir / "index.jsonl"
    shutil.copyfile(source, destination_pdf)
    os.chmod(destination_pdf, 0o600)
    with index_path.open("w", encoding="utf-8") as index_file:
        for row in chunks:
            index_file.write(json.dumps(row, ensure_ascii=False) + "\n")
    os.chmod(index_path, 0o600)


if __name__ == "__main__":
    main()
