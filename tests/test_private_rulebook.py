import json
import os
from io import BytesIO
from uuid import uuid4

import pytest
from pypdf import PdfWriter

from app.services import private_rulebook
from app.tools import private_rule_search


def test_page_chunks_preserve_rule_and_printed_page_metadata():
    chunks = private_rulebook.page_chunks(
        "5.02 수비위치\n․ 22 ․\n수비 위치 제한. 5.02(c) 위반 시 벌칙",
        pdf_page=46,
    )

    assert chunks[0]["rule_number"] == "5.02(c)"
    assert chunks[0]["pdf_page"] == 46
    assert chunks[0]["printed_page"] == 22


def test_private_rulebook_store_versions_documents_and_limits_replacement(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(private_rulebook, "PRIVATE_KNOWLEDGE_ROOT", tmp_path)
    monkeypatch.setattr(private_rule_search, "PRIVATE_KNOWLEDGE_ROOT", tmp_path)
    owner_id = str(uuid4())
    prepared = ({
        "pdf_pages": 1,
        "nonempty_pages": 1,
        "blank_pages": 0,
        "chunks": 1,
    }, [{
        "title": "2026 공식야구규칙",
        "edition": "2026",
        "rule_number": "5.02(c)",
        "pdf_page": 46,
        "printed_page": 22,
        "text": "5.02(c) 투구 시 내야 수비 위치 제한",
    }])

    first = private_rulebook.store_private_rulebook(
        owner_user_id=owner_id,
        pdf_bytes=b"%PDF-first-version",
        prepared=prepared,
    )
    owner_dir = tmp_path / owner_id
    first_version = owner_dir / first["sha256"]

    assert first["replaced"] is False
    assert first["unchanged"] is False
    assert os.stat(owner_dir).st_mode & 0o777 == 0o700
    assert os.stat(first_version / "original.pdf").st_mode & 0o777 == 0o600
    assert json.loads((owner_dir / "current.json").read_text()) == {
        "sha256": first["sha256"],
    }

    retrieved = private_rule_search.search_private_baseball_rules(
        owner_user_id=owner_id,
        query="5.02(c) 내야 수비 위치",
    )
    assert retrieved["data"]["results"][0]["printed_page"] == 22

    unchanged = private_rulebook.store_private_rulebook(
        owner_user_id=owner_id,
        pdf_bytes=b"%PDF-first-version",
        prepared=prepared,
    )
    assert unchanged["unchanged"] is True

    replacement_bytes = b"%PDF-second-version"
    with pytest.raises(private_rulebook.PrivateRulebookError) as error:
        private_rulebook.store_private_rulebook(
            owner_user_id=owner_id,
            pdf_bytes=replacement_bytes,
            prepared=prepared,
        )
    assert error.value.status_code == 409
    assert error.value.code == "DOCUMENT_EXISTS"

    replacement = private_rulebook.store_private_rulebook(
        owner_user_id=owner_id,
        pdf_bytes=replacement_bytes,
        replace=True,
        prepared=prepared,
    )
    assert replacement["replaced"] is True
    assert replacement["unchanged"] is False
    assert (owner_dir / first["sha256"] / "index.jsonl").is_file()
    assert json.loads((owner_dir / "current.json").read_text()) == {
        "sha256": replacement["sha256"],
    }


def test_private_rulebook_rejects_non_pdf_and_missing_text():
    with pytest.raises(private_rulebook.PrivateRulebookError) as error:
        private_rulebook.extract_private_rulebook(b"not a pdf")
    assert error.value.code == "INVALID_PDF"

    buffer = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(buffer)
    with pytest.raises(private_rulebook.PrivateRulebookError) as blank_error:
        private_rulebook.extract_private_rulebook(buffer.getvalue())
    assert blank_error.value.code == "NO_EXTRACTABLE_TEXT"
