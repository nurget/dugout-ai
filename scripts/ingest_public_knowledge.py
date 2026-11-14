"""Validate and optionally ingest reviewed public documents into a Vector Store."""

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Sequence

from app.services.knowledge_corpus import (
    ingest_public_knowledge_documents,
    validate_public_knowledge_manifest,
)


async def ingest(manifest_path: Path, vector_store_id: str, *, apply: bool) -> None:
    repository_root = Path(__file__).resolve().parents[1]
    documents = validate_public_knowledge_manifest(
        manifest_path,
        repository_root=repository_root,
    )
    print(f"권리·출처·날짜·경로·해시 검증 통과: {len(documents)}건")
    for document in documents:
        print(json.dumps({
            "document_id": document.document_id,
            "title": document.title,
            "source_url": document.source_url,
            "effective_date": document.effective_date.isoformat(),
            "path": str(document.path.relative_to(repository_root)),
            "sha256": document.sha256,
        }, ensure_ascii=False))

    if not apply:
        print("검증만 진행했습니다. 외부 Vector Store는 변경하지 않았습니다.")
        return

    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY가 필요합니다. 업로드를 진행하지 않았습니다.")

    from openai import AsyncOpenAI

    async with AsyncOpenAI() as client:
        outcomes = await ingest_public_knowledge_documents(
            client=client,
            vector_store_id=vector_store_id,
            documents=documents,
        )
    for outcome in outcomes:
        print(json.dumps(outcome, ensure_ascii=False))


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="검토 완료된 공개 문서를 검증하고 Vector Store에 적재합니다."
    )
    parser.add_argument("manifest", type=Path, help="검증된 권리·출처 정보를 포함한 JSON")
    parser.add_argument(
        "--vector-store-id",
        default=os.environ.get("OPENAI_PUBLIC_KNOWLEDGE_VECTOR_STORE_ID"),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="외부 OpenAI Vector Store에 파일을 업로드합니다. 기본값은 로컬 검증만 합니다.",
    )
    args = parser.parse_args(argv)
    if args.apply and not args.vector_store_id:
        parser.error("--apply에는 --vector-store-id 또는 환경 변수가 필요합니다.")
    asyncio.run(ingest(
        args.manifest,
        args.vector_store_id or "",
        apply=args.apply,
    ))


if __name__ == "__main__":
    main()
