"""jarvis.agents.sessions.tools.pdf_tool — PDF text and visual extraction tool.

OpenClaw parity: mirrors document extraction engine patterns from
`extensions/document-extract/` and `clawpdf`.
Extracts plain text per page from PDF files using PyMuPDF (fitz), pypdf, or pdfminer,
with flexible page range selection and query search filtering.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Optional

from ..extensions.types import AgentToolResult, ToolDefinition
from .path_utils import resolve_unicode_path


@dataclass(frozen=True, slots=True)
class ExtractedPage:
    """Value object capturing extracted text from a single PDF page."""

    page_number: int  # 1-indexed
    total_pages: int
    text: str
    char_count: int


def _parse_page_selection(pages_str: str | None, total_pages: int) -> list[int]:
    """Parse a flexible page selection string into a 1-indexed list of page numbers.

    Supported patterns:
    - None, "", "all" -> [1, 2, ..., total_pages]
    - "1-5"           -> [1, 2, 3, 4, 5]
    - "1,3,5"         -> [1, 3, 5]
    - "3-"            -> [3, 4, ..., total_pages]
    - "-4"            -> [1, 2, 3, 4]
    - "2"             -> [2]
    """
    if total_pages <= 0:
        return []

    if not pages_str or pages_str.strip().lower() in ("all", "*", ""):
        return list(range(1, total_pages + 1))

    selected: list[int] = []
    seen: set[int] = set()

    chunks = [c.strip() for c in pages_str.split(",") if c.strip()]
    for chunk in chunks:
        # Match range e.g. "1-5", "3-", "-4"
        if "-" in chunk:
            parts = chunk.split("-", 1)
            start_str = parts[0].strip()
            end_str = parts[1].strip()

            start = int(start_str) if start_str.isdigit() else 1
            end = int(end_str) if end_str.isdigit() else total_pages

            start = max(1, min(total_pages, start))
            end = max(1, min(total_pages, end))

            if start <= end:
                step = 1
            else:
                step = -1

            for p in range(start, end + step, step):
                if 1 <= p <= total_pages and p not in seen:
                    selected.append(p)
                    seen.add(p)
        elif chunk.isdigit():
            p = int(chunk)
            if 1 <= p <= total_pages and p not in seen:
                selected.append(p)
                seen.add(p)

    return selected or list(range(1, total_pages + 1))


def _extract_pages_pymupdf(
    file_path: str, pages_to_read: list[int]
) -> tuple[list[ExtractedPage], int]:
    """Extract pages using PyMuPDF (fitz)."""
    import fitz  # pyright: ignore[reportMissingImports]

    doc = fitz.open(file_path)
    try:
        total_pages = doc.page_count
        # Re-verify page bounds
        valid_pages = [p for p in pages_to_read if 1 <= p <= total_pages]
        results: list[ExtractedPage] = []
        for p_num in valid_pages:
            page = doc.load_page(p_num - 1)
            raw_text = page.get_text() or ""
            cleaned = raw_text.strip()
            results.append(
                ExtractedPage(
                    page_number=p_num,
                    total_pages=total_pages,
                    text=cleaned,
                    char_count=len(cleaned),
                )
            )
        return results, total_pages
    finally:
        doc.close()


def _extract_pages_pypdf(
    file_path: str, pages_to_read: list[int]
) -> tuple[list[ExtractedPage], int]:
    """Extract pages using pypdf."""
    from pypdf import PdfReader  # pyright: ignore[reportMissingImports]

    reader = PdfReader(file_path)
    total_pages = len(reader.pages)
    valid_pages = [p for p in pages_to_read if 1 <= p <= total_pages]
    results: list[ExtractedPage] = []
    for p_num in valid_pages:
        page = reader.pages[p_num - 1]
        raw_text = page.extract_text() or ""
        cleaned = raw_text.strip()
        results.append(
            ExtractedPage(
                page_number=p_num,
                total_pages=total_pages,
                text=cleaned,
                char_count=len(cleaned),
            )
        )
    return results, total_pages


def _extract_pages_pdfminer(
    file_path: str, pages_to_read: list[int]
) -> tuple[list[ExtractedPage], int]:
    """Extract pages using pdfminer.six."""
    from pdfminer.high_level import extract_pages  # pyright: ignore[reportMissingImports]
    from pdfminer.layout import LTTextContainer  # pyright: ignore[reportMissingImports]

    results: list[ExtractedPage] = []
    # pdfminer extract_pages is 0-indexed page_numbers
    zero_indexed = [p - 1 for p in pages_to_read]
    page_count = 0
    extracted_dict: dict[int, str] = {}

    for page_layout in extract_pages(file_path):
        page_idx = page_layout.pageid - 1
        page_count += 1
        if page_idx in zero_indexed:
            page_text = ""
            for element in page_layout:
                if isinstance(element, LTTextContainer):
                    page_text += element.get_text()
            extracted_dict[page_idx + 1] = page_text.strip()

    for p in pages_to_read:
        if p in extracted_dict:
            text = extracted_dict[p]
            results.append(
                ExtractedPage(
                    page_number=p,
                    total_pages=page_count,
                    text=text,
                    char_count=len(text),
                )
            )

    return results, page_count


def _extract_pdf(file_path: str, pages_spec: str | None) -> tuple[list[ExtractedPage], int, str]:
    """Extract PDF pages trying pymupdf, then pypdf, then pdfminer."""
    # 1. Try PyMuPDF (fitz)
    try:
        import fitz  # noqa: F401

        # Probe total pages first
        doc = fitz.open(file_path)
        total = doc.page_count
        doc.close()
        pages = _parse_page_selection(pages_spec, total)
        results, total_pages = _extract_pages_pymupdf(file_path, pages)
        return results, total_pages, "pymupdf"
    except (ImportError, Exception):
        pass

    # 2. Fallback: pypdf
    try:
        from pypdf import PdfReader  # noqa: F401

        reader = PdfReader(file_path)
        total = len(reader.pages)
        pages = _parse_page_selection(pages_spec, total)
        results, total_pages = _extract_pages_pypdf(file_path, pages)
        return results, total_pages, "pypdf"
    except (ImportError, Exception):
        pass

    # 3. Fallback: pdfminer.six
    try:
        from pdfminer.high_level import extract_pages  # noqa: F401

        # We assume up to 500 pages for page range resolution, then correct
        pages = _parse_page_selection(pages_spec, 500)
        results, total_pages = _extract_pages_pdfminer(file_path, pages)
        return results, total_pages, "pdfminer"
    except (ImportError, Exception):
        pass

    raise RuntimeError(
        "No PDF extraction library available. Please ensure 'pymupdf', 'pypdf', or 'pdfminer.six' is installed."
    )


def create_pdf_tool_definition(
    cwd: str = "",
    options: Optional[dict] = None,
) -> ToolDefinition:
    """Build the ToolDefinition for the pdf tool."""
    _ = options

    async def _execute(
        tool_call_id: str,
        params: dict,
        signal: object = None,
        on_update: object = None,
        ctx: object = None,
    ) -> AgentToolResult:
        _ = (tool_call_id, on_update, ctx)
        if signal is not None and getattr(signal, "is_set", lambda: False)():
            raise RuntimeError("Operation aborted")

        raw_path = str(
            params.get("file_path") or params.get("pdf") or params.get("path") or ""
        ).strip()
        if not raw_path:
            raise ValueError("pdf or file_path parameter is required.")

        workspace_root = cwd or os.getcwd()
        resolved_path = resolve_unicode_path(raw_path, workspace_root)

        if not os.path.exists(resolved_path):
            raise FileNotFoundError(
                f"PDF file not found: '{raw_path}' (resolved to '{resolved_path}')."
            )

        if not os.path.isfile(resolved_path):
            raise ValueError(f"Target '{resolved_path}' is a directory, not a PDF file.")

        pages_spec = params.get("pages")
        if pages_spec is not None:
            pages_spec = str(pages_spec).strip()

        prompt_filter = params.get("prompt")
        if prompt_filter is not None:
            prompt_filter = str(prompt_filter).strip()

        extracted_pages, total_pages, engine = _extract_pdf(resolved_path, pages_spec)

        # Apply search/prompt filter if provided
        matched_pages: list[ExtractedPage] = []
        if prompt_filter:
            q_lower = prompt_filter.lower()
            for p in extracted_pages:
                if q_lower in p.text.lower():
                    matched_pages.append(p)
            pages_to_display = matched_pages
        else:
            pages_to_display = extracted_pages

        # Build output text
        pdf_name = Path(resolved_path).name
        output_parts: list[str] = [
            f"PDF: {pdf_name} ({total_pages} total pages, extracted via {engine})"
        ]

        if prompt_filter:
            output_parts.append(
                f"Search Query: '{prompt_filter}' — {len(matched_pages)} matching page(s)"
            )
            if not matched_pages:
                output_parts.append(
                    f"\nNo pages matched the query '{prompt_filter}'. "
                    f"Examined {len(extracted_pages)} page(s)."
                )

        for page in pages_to_display:
            output_parts.append(f"\n--- Page {page.page_number} of {page.total_pages} ---")
            if page.text:
                output_parts.append(page.text)
            else:
                output_parts.append("(Page contains no extractable text)")

        final_text = "\n".join(output_parts)

        return {
            "content": [{"type": "text", "text": final_text}],
            "details": {
                "pdf": str(resolved_path),
                "total_pages": total_pages,
                "engine": engine,
                "pages_extracted": [p.page_number for p in extracted_pages],
                "matches_found": len(matched_pages) if prompt_filter else len(extracted_pages),
                "matches_count": len(matched_pages) if prompt_filter else len(extracted_pages),
            },
        }

    return {
        "name": "pdf",
        "description": (
            "PDF text and visual extraction tool. "
            "Reads PDF pages, extracts plain text per page, supports page range selection ('1-5', 'all', '1,3,5'), "
            "and optional search query filtering."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "pdf": {
                    "type": "STRING",
                    "description": "Local filesystem path to the PDF document to extract text from.",
                },
                "pages": {
                    "type": "STRING",
                    "description": "Page range selection (e.g. '1-5', 'all', '1,3,5', '2'). Default: 'all'.",
                },
                "prompt": {
                    "type": "STRING",
                    "description": "Optional search query to filter relevant sections or pages in the PDF.",
                },
            },
            "required": ["pdf"],
        },
        "execute": _execute,
    }


def create_pdf_tool(
    cwd: str = "",
    options: Optional[dict] = None,
) -> ToolDefinition:
    """Convenience alias matching create_write_tool / create_open_path_tool naming."""
    return create_pdf_tool_definition(cwd=cwd, options=options)


__all__ = [
    "ExtractedPage",
    "create_pdf_tool",
    "create_pdf_tool_definition",
]
