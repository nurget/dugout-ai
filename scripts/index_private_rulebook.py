"""Create a local user-scoped index for a private PDF rulebook."""

import argparse
import json
from pathlib import Path
from uuid import UUID

from app.services.private_rulebook import (
    PrivateRulebookError,
    extract_private_rulebook,
    store_private_rulebook,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--owner-user-id", required=True, help="로그인 계정 UUID")
    parser.add_argument("--apply", action="store_true", help="원문과 인덱스를 data/private/rag에 저장")
    parser.add_argument("--replace", action="store_true", help="기존 계정 문서를 새 PDF로 교체")
    args = parser.parse_args()
    owner_id = str(UUID(args.owner_user_id))
    source = args.pdf.resolve(strict=True)
    pdf_bytes = source.read_bytes()
    try:
        metadata, chunks = extract_private_rulebook(pdf_bytes)
    except PrivateRulebookError as error:
        parser.error(error.message)

    print(json.dumps({
        **metadata,
        "owner_user_id": owner_id,
        "applied": args.apply,
    }, ensure_ascii=False))
    if not args.apply:
        return
    try:
        result = store_private_rulebook(
            owner_user_id=owner_id,
            pdf_bytes=pdf_bytes,
            replace=args.replace,
            prepared=(metadata, chunks),
        )
    except PrivateRulebookError as error:
        parser.error(error.message)
    print(json.dumps({"stored": True, **result}, ensure_ascii=False))


if __name__ == "__main__":
    main()
