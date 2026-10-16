"""Tests for document-extract extractor and plugin."""

from __future__ import annotations

import base64
from typing import Any
from unittest.mock import AsyncMock, MagicMock
import pytest

from extensions.document_extract.src.extractor import (
    DocumentExtractionRequest,
    PdfPasswordError,
    create_pdf_document_extractor,
)


class MockPdfDocument:
    def __init__(self, page_count: int = 2) -> None:
        self.page_count = page_count
        self.extract = AsyncMock()
        self.destroy = MagicMock()


class MockPdfEngine:
    def __init__(self, doc: MockPdfDocument) -> None:
        self.doc = doc
        self.open = AsyncMock(return_value=doc)


def make_request(**kwargs: Any) -> DocumentExtractionRequest:
    default_kwargs: dict[str, Any] = {
        "buffer": b"%PDF-1.4",
        "mime_type": "application/pdf",
        "max_pages": 2,
        "max_pixels": 100,
        "min_text_chars": 10,
    }
    default_kwargs.update(kwargs)
    return DocumentExtractionRequest(**default_kwargs)


def test_declares_pdf_support() -> None:
    extractor = create_pdf_document_extractor()
    assert extractor.id == "pdf"
    assert extractor.label == "PDF"
    assert extractor.mime_types == ["application/pdf"]
    assert extractor.auto_detect_order == 10


@pytest.mark.asyncio
async def test_extracts_text_first_and_renders_fallback_images() -> None:
    doc = MockPdfDocument(page_count=2)
    doc.extract.side_effect = [
        {"text": "", "images": []},
        {
            "text": "",
            "images": [
                {
                    "type": "image",
                    "bytes": b"png1",
                    "mimeType": "image/png",
                    "page": 1,
                    "width": 5,
                    "height": 10,
                }
            ],
        },
        {
            "text": "",
            "images": [
                {
                    "type": "image",
                    "bytes": b"png2",
                    "mimeType": "image/png",
                    "page": 2,
                    "width": 5,
                    "height": 10,
                }
            ],
        },
    ]
    engine = MockPdfEngine(doc)
    extractor = create_pdf_document_extractor(engine=engine)

    req = make_request()
    result = await extractor.extract(req)

    engine.open.assert_awaited_once_with(req.buffer, password=None)
    assert doc.extract.await_count == 3
    assert result.text == ""
    assert len(result.images) == 2
    assert result.images[0].data == base64.b64encode(b"png1").decode("ascii")
    assert result.images[1].data == base64.b64encode(b"png2").decode("ascii")
    doc.destroy.assert_called_once()


@pytest.mark.asyncio
async def test_skips_image_fallback_when_enough_text() -> None:
    doc = MockPdfDocument(page_count=2)
    doc.extract.return_value = {"text": "enough text is present here", "images": []}
    engine = MockPdfEngine(doc)
    extractor = create_pdf_document_extractor(engine=engine)

    result = await extractor.extract(make_request(min_text_chars=5))
    assert result.text == "enough text is present here"
    assert len(result.images) == 0
    assert doc.extract.await_count == 1
    doc.destroy.assert_called_once()


@pytest.mark.asyncio
async def test_opens_encrypted_pdf_with_password() -> None:
    doc = MockPdfDocument(page_count=2)
    doc.extract.return_value = {"text": "secret decrypted text", "images": []}
    engine = MockPdfEngine(doc)
    extractor = create_pdf_document_extractor(engine=engine)

    result = await extractor.extract(make_request(password="secret"))
    engine.open.assert_awaited_once_with(b"%PDF-1.4", password="secret")
    assert result.text == "secret decrypted text"
    doc.destroy.assert_called_once()


@pytest.mark.asyncio
async def test_normalizes_password_errors() -> None:
    doc = MockPdfDocument(page_count=2)
    engine = MockPdfEngine(doc)
    engine.open.side_effect = PdfPasswordError("wrong password")
    extractor = create_pdf_document_extractor(engine=engine)

    with pytest.raises(RuntimeError, match="PDF requires a password or password is incorrect."):
        await extractor.extract(make_request(password="wrong"))


@pytest.mark.asyncio
async def test_filters_selected_pages_and_renders_each() -> None:
    doc = MockPdfDocument(page_count=2)
    doc.extract.side_effect = [
        {"text": "", "images": []},
        {"text": "", "images": []},
        {"text": "", "images": []},
    ]
    engine = MockPdfEngine(doc)
    extractor = create_pdf_document_extractor(engine=engine)

    result = await extractor.extract(make_request(page_numbers=[3, 2, 0, 1], max_pages=2))
    assert result.text == ""
    assert doc.extract.await_count == 3
    # Check page calls: 1st text extraction with pages=[2, 1], 2nd images page 2, 3rd images page 1
    assert doc.extract.await_args_list[0].kwargs.get("pages") == [2, 1]
    assert doc.extract.await_args_list[1].kwargs.get("pages") == [2]
    assert doc.extract.await_args_list[2].kwargs.get("pages") == [1]


@pytest.mark.asyncio
async def test_rejects_selected_pages_outside_page_count() -> None:
    doc = MockPdfDocument(page_count=1)
    engine = MockPdfEngine(doc)
    extractor = create_pdf_document_extractor(engine=engine)

    with pytest.raises(RuntimeError, match="No requested PDF pages exist in this 1-page document."):
        await extractor.extract(make_request(page_numbers=[2]))


@pytest.mark.asyncio
async def test_reports_image_fallback_failures_and_returns_text() -> None:
    error_cb = MagicMock()
    doc = MockPdfDocument(page_count=2)
    doc.extract.side_effect = [
        {"text": "short", "images": []},
        RuntimeError("render failed"),
    ]
    engine = MockPdfEngine(doc)
    extractor = create_pdf_document_extractor(engine=engine)

    result = await extractor.extract(make_request(on_image_extraction_error=error_cb))
    assert result.text == "short"
    assert len(result.images) == 0
    error_cb.assert_called_once()
    doc.destroy.assert_called_once()


@pytest.mark.asyncio
async def test_surfaces_image_fallback_failures_when_empty_text() -> None:
    error_cb = MagicMock()
    doc = MockPdfDocument(page_count=2)
    failure = RuntimeError("render fatal error")
    doc.extract.side_effect = [
        {"text": "", "images": []},
        failure,
    ]
    engine = MockPdfEngine(doc)
    extractor = create_pdf_document_extractor(engine=engine)

    with pytest.raises(RuntimeError, match="PDF image extraction failed with no extractable text."):
        await extractor.extract(make_request(on_image_extraction_error=error_cb))
    error_cb.assert_called_once_with(failure)
    doc.destroy.assert_called_once()
