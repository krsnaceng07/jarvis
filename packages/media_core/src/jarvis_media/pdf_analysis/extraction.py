"""
Fallback extraction for PDF analysis using PyMuPDF (fitz).
"""

import base64
import logging
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
from urllib.parse import urlparse
import urllib.request

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

from .types import PdfAnalysisRequest

logger = logging.getLogger("jarvis_media.pdf_analysis.extraction")


def _resolve_pdf_bytes(pdf_ref: str, max_bytes: int) -> bytes:
    """Fetch or read PDF bytes."""
    parsed = urlparse(pdf_ref)
    scheme = parsed.scheme.lower()

    if scheme in ("http", "https"):
        req = urllib.request.Request(pdf_ref, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req) as response:
            content = response.read(max_bytes + 1)
            if len(content) > max_bytes:
                raise ValueError(f"PDF exceeds size limit of {max_bytes} bytes.")
            return content
    elif scheme == "file" or not scheme:
        path = Path(parsed.path if scheme else pdf_ref).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {path}")
        size = path.stat().st_size
        if size > max_bytes:
            raise ValueError(f"PDF exceeds size limit of {max_bytes} bytes.")
        return path.read_bytes()
    else:
        raise ValueError("unsupported_pdf_reference")


def _parse_pages(pages_str: Optional[str], max_pages: int, doc_page_count: int) -> List[int]:
    """Parse a pages string like '1-5,7' into 0-indexed page numbers."""
    if not pages_str:
        return list(range(min(max_pages, doc_page_count)))

    pages = set()
    parts = pages_str.split(",")
    for part in parts:
        part = part.strip()
        if "-" in part:
            start_str, end_str = part.split("-", 1)
            try:
                start = int(start_str)
                end = int(end_str)
                for p in range(start, end + 1):
                    pages.add(p)
            except ValueError:
                pass
        else:
            try:
                pages.add(int(part))
            except ValueError:
                pass

    valid_pages = sorted([p - 1 for p in pages if 1 <= p <= doc_page_count])
    if not valid_pages:
        raise ValueError("No valid pages found in range.")

    return valid_pages[:max_pages]


def extract_pdf_fallback(
    request: PdfAnalysisRequest,
) -> Tuple[str, List[Dict[str, str]], Dict[str, Any]]:
    """
    Extract text and optionally images from PDFs using PyMuPDF.
    Returns (extracted_text, images, details)
    """
    if fitz is None:
        raise RuntimeError("pymupdf is not installed. Run `uv add pymupdf`.")

    max_bytes = int(request.max_bytes_mb * 1024 * 1024)
    all_text = []
    all_images = []

    total_pixel_budget = 4_000_000

    for pdf_ref in request.pdfs:
        try:
            pdf_bytes = _resolve_pdf_bytes(pdf_ref, max_bytes)
        except Exception as e:
            if str(e) == "unsupported_pdf_reference":
                raise ValueError("unsupported_pdf_reference")
            logger.warning(f"Failed to read PDF {pdf_ref}: {e}")
            continue

        try:
            doc = fitz.open("pdf", pdf_bytes)
        except Exception as e:
            logger.warning(f"Failed to open PDF {pdf_ref}: {e}")
            continue

        if doc.needs_pass:
            if request.password:
                if not doc.authenticate(request.password):
                    raise ValueError(f"Incorrect password for {pdf_ref}")
            else:
                raise ValueError(f"Password required for encrypted PDF {pdf_ref}")

        try:
            pages_to_process = _parse_pages(request.pages, request.max_pages, len(doc))
        except ValueError as e:
            if "No valid pages" in str(e):
                raise ValueError("No valid pages found in range.")
            pages_to_process = list(range(min(request.max_pages, len(doc))))

        doc_text = []
        for p in pages_to_process:
            page = doc[p]
            doc_text.append(page.get_text())

        full_doc_text = "\\n".join(doc_text).strip()
        all_text.append(full_doc_text)

        # If text is too short, fallback to rendering images
        if len(full_doc_text) < 200:
            remaining_pages = len(pages_to_process)
            for p in pages_to_process:
                page = doc[p]
                budget_for_page = total_pixel_budget // remaining_pages

                # Default 72 DPI (scale=1)
                # Area = width * height
                rect = page.rect
                area = rect.width * rect.height

                scale = 1.0
                if area > budget_for_page and area > 0:
                    scale = (budget_for_page / area) ** 0.5

                total_pixel_budget -= int(area * scale * scale)
                remaining_pages -= 1

                try:
                    matrix = fitz.Matrix(scale, scale)
                    pix = page.get_pixmap(matrix=matrix)
                    png_bytes = pix.tobytes("png")
                    b64 = base64.b64encode(png_bytes).decode("utf-8")
                    all_images.append(
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
                    )
                except Exception as e:
                    logger.warning(f"Failed to render page {p} of {pdf_ref}: {e}")

        doc.close()

    combined_text = "\\n\\n".join(all_text)

    details = {
        "native": False,
        "pdf": request.pdfs[0] if len(request.pdfs) == 1 else None,
        "pdfs": [{"pdf": p} for p in request.pdfs] if len(request.pdfs) > 1 else None,
    }

    return combined_text, all_images, details
