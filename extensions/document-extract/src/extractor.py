"""Document Extract plugin module implements PDF extraction behavior.

OpenClaw parity: mirrors OpenClaw's PDF document extractor with
text extraction priority, per-page pixel budget fallback, password
handling, and page range filtering.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
import io
import math
from typing import Any, Callable, Protocol


MAX_EXTRACTED_TEXT_CHARS = 200_000
MAX_RENDER_DIMENSION = 10_000


@dataclass(frozen=True, slots=True)
class DocumentExtractedImage:
    """Represents an extracted page image."""

    data: str  # Base64 encoded
    mime_type: str = "image/png"
    type: str = "image"


@dataclass(frozen=True, slots=True)
class DocumentExtractionRequest:
    """Request parameters for document extraction."""

    buffer: bytes
    mime_type: str = "application/pdf"
    max_pages: int = 10
    max_pixels: int = 10_000_000
    min_text_chars: int = 100
    password: str | None = None
    page_numbers: list[int] | None = None
    on_image_extraction_error: Callable[[Exception], None] | None = None


@dataclass(frozen=True, slots=True)
class DocumentExtractionResult:
    """Result of document extraction."""

    text: str
    images: list[DocumentExtractedImage] = field(default_factory=list)


class PdfPasswordError(Exception):
    """Raised when PDF decryption fails due to password."""

    code = "password"


class PdfDocumentProtocol(Protocol):
    """Protocol for open PDF document."""

    page_count: int

    async def extract(self, **kwargs: Any) -> dict[str, Any]: ...

    def destroy(self) -> None: ...


class PdfEngineProtocol(Protocol):
    """Protocol for PDF engine."""

    async def open(
        self, input_bytes: bytes, password: str | None = None
    ) -> PdfDocumentProtocol: ...


class DefaultPypdfDocument:
    """Default lightweight PDF document adapter using pypdf if available."""

    def __init__(self, reader: Any) -> None:
        self._reader = reader
        self.page_count = len(reader.pages)

    async def extract(self, **kwargs: Any) -> dict[str, Any]:
        mode = kwargs.get("mode", "text")
        if mode == "text":
            pages = kwargs.get("pages")
            max_pages = kwargs.get("max_pages", self.page_count)
            max_text_chars = kwargs.get("max_text_chars", MAX_EXTRACTED_TEXT_CHARS)

            if pages is not None:
                selected_pages = [
                    self._reader.pages[p - 1] for p in pages if 1 <= p <= self.page_count
                ]
            else:
                selected_pages = self._reader.pages[:max_pages]

            text_parts = []
            for page in selected_pages:
                try:
                    text_parts.append(page.extract_text() or "")
                except Exception:
                    continue
            full_text = "\n".join(text_parts)[:max_text_chars]
            return {"text": full_text, "images": []}

        # Fallback image rendering mode
        return {"text": "", "images": []}

    def destroy(self) -> None:
        self._reader = None


class DefaultPypdfEngine:
    """Default PDF engine using pypdf."""

    async def open(self, input_bytes: bytes, password: str | None = None) -> PdfDocumentProtocol:
        try:
            import pypdf

            stream = io.BytesIO(input_bytes)
            reader = pypdf.PdfReader(stream)
            if reader.is_encrypted:
                if not password or reader.decrypt(password) == 0:
                    raise PdfPasswordError("PDF requires a password or password is incorrect.")
            return DefaultPypdfDocument(reader)
        except PdfPasswordError:
            raise
        except Exception as err:
            if "password" in str(err).lower() or "decrypt" in str(err).lower():
                raise PdfPasswordError("PDF requires a password or password is incorrect.") from err
            raise


_default_engine: PdfEngineProtocol | None = None


def get_default_pdf_engine() -> PdfEngineProtocol:
    global _default_engine
    if _default_engine is None:
        _default_engine = DefaultPypdfEngine()
    return _default_engine


def set_default_pdf_engine(engine: PdfEngineProtocol | None) -> None:
    global _default_engine
    _default_engine = engine


def _to_document_image(img_dict: dict[str, Any]) -> DocumentExtractedImage:
    data = img_dict.get("data")
    if data is None:
        raw_bytes = img_dict.get("bytes", b"")
        data = base64.b64encode(raw_bytes).decode("ascii")
    mime_type = img_dict.get("mimeType") or img_dict.get("mime_type") or "image/png"
    return DocumentExtractedImage(data=data, mime_type=mime_type)


class PdfDocumentExtractor:
    """Extracts text and fallback page images from PDF files."""

    id: str = "pdf"
    label: str = "PDF"
    mime_types: list[str] = ["application/pdf"]
    auto_detect_order: int = 10

    def __init__(self, engine: PdfEngineProtocol | None = None) -> None:
        self._engine = engine

    async def extract(self, request: DocumentExtractionRequest) -> DocumentExtractionResult:
        """Extract text or render fallback images from PDF buffer."""
        engine = self._engine or get_default_pdf_engine()

        try:
            pdf = await engine.open(request.buffer, password=request.password)
        except Exception as err:
            if getattr(err, "code", None) == "password" or "password" in str(err).lower():
                raise RuntimeError("PDF requires a password or password is incorrect.") from err
            raise

        try:
            pages: list[int] | None = None
            if request.page_numbers is not None:
                pages = [
                    p
                    for p in request.page_numbers
                    if isinstance(p, int) and 1 <= p <= pdf.page_count
                ][: request.max_pages]

            if (
                request.page_numbers is not None
                and len(request.page_numbers) > 0
                and (pages is None or len(pages) == 0)
            ):
                raise RuntimeError(
                    f"No requested PDF pages exist in this {pdf.page_count}-page document."
                )

            page_selection = (
                {"pages": pages} if pages is not None else {"maxPages": request.max_pages}
            )

            text_result = await pdf.extract(
                mode="text",
                maxTextChars=MAX_EXTRACTED_TEXT_CHARS,
                **page_selection,
            )
            text = text_result.get("text", "")

            if len(text.strip()) >= request.min_text_chars:
                return DocumentExtractionResult(text=text, images=[])

            image_pages = (
                pages
                if pages is not None
                else list(range(1, min(pdf.page_count, request.max_pages) + 1))
            )

            try:
                images: list[DocumentExtractedImage] = []
                remaining_pixels = request.max_pixels

                for index, page_number in enumerate(image_pages):
                    if remaining_pixels <= 0:
                        break
                    pages_remaining = len(image_pages) - index
                    max_pixels_per_page = max(1, math.ceil(remaining_pixels / pages_remaining))

                    image_result = await pdf.extract(
                        mode="images",
                        pages=[page_number],
                        image={
                            "maxDimension": MAX_RENDER_DIMENSION,
                            "maxPixels": max_pixels_per_page,
                            "forms": True,
                        },
                    )

                    for raw_img in image_result.get("images", []):
                        img_obj = _to_document_image(raw_img)
                        images.append(img_obj)
                        w = raw_img.get("width", 1)
                        h = raw_img.get("height", 1)
                        remaining_pixels -= w * h

                return DocumentExtractionResult(text=text, images=images)
            except Exception as err:
                if request.on_image_extraction_error:
                    request.on_image_extraction_error(err)
                if not text.strip():
                    raise RuntimeError(
                        "PDF image extraction failed with no extractable text."
                    ) from err
                return DocumentExtractionResult(text=text, images=[])
        finally:
            pdf.destroy()


def create_pdf_document_extractor(
    engine: PdfEngineProtocol | None = None,
) -> PdfDocumentExtractor:
    """Factory creating a PdfDocumentExtractor instance."""
    return PdfDocumentExtractor(engine=engine)
