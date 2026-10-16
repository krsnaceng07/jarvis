"""
PDF Analysis Runtime Core
"""

from typing import Any, Callable, List, Optional
from .types import PdfAnalysisRequest, PdfAnalysisResult
from .extraction import extract_pdf_fallback
import logging

logger = logging.getLogger("jarvis_media.pdf_analysis.runtime")


def resolve_pdf_model_candidates(
    cfg: Any,
    pdf_model_config: Any,
    image_model_config: Any,
    session_model_ref: Optional[dict[str, str]],
    model_override: Optional[str],
    parse_model_ref: Callable[[Optional[str]], Optional[dict[str, str]]],
    list_providers: Callable[[], List[Any]],
    auto_provider_fallback: Optional[bool] = None,
) -> List[dict[str, str]]:
    """Resolve which models to try for PDF analysis."""
    candidates: List[dict[str, str]] = []

    # 1. Override
    if model_override:
        ref = parse_model_ref(model_override)
        if ref:
            candidates.append(ref)
            if not auto_provider_fallback:
                return candidates

    # 2. pdfModel config
    if pdf_model_config:
        if getattr(pdf_model_config, "primary", None):
            ref = parse_model_ref(pdf_model_config.primary)
            if ref and ref not in candidates:
                candidates.append(ref)
        if getattr(pdf_model_config, "fallbacks", None):
            for fallback in pdf_model_config.fallbacks:
                ref = parse_model_ref(fallback)
                if ref and ref not in candidates:
                    candidates.append(ref)

    # 3. imageModel config
    if image_model_config:
        if getattr(image_model_config, "primary", None):
            ref = parse_model_ref(image_model_config.primary)
            if ref and ref not in candidates:
                candidates.append(ref)
        if getattr(image_model_config, "fallbacks", None):
            for fallback in image_model_config.fallbacks:
                ref = parse_model_ref(fallback)
                if ref and ref not in candidates:
                    candidates.append(ref)

    # 4. Session default model
    if session_model_ref and session_model_ref not in candidates:
        # In a full implementation, we'd check if the session model supports vision or native pdf.
        # OpenClaw handles this by checking provider capabilities later.
        candidates.append(session_model_ref)

    # 5. Auto provider fallback
    if auto_provider_fallback is not False:
        for provider in list_providers():
            if getattr(provider, "default_model", None):
                ref = {"provider": provider.id, "model": provider.default_model}
                if ref not in candidates:
                    # Prefer native-PDF providers (anthropic, google) first.
                    # We can prepend if native, append if not.
                    if provider.id in ("anthropic", "google"):
                        candidates.insert(0, ref)  # Highly naive, but matches spec preference
                    else:
                        candidates.append(ref)

    return candidates


async def analyze_pdf(
    request: PdfAnalysisRequest,
    model_resolver: Callable[[dict[str, str]], Any],  # returns a loaded model instance
    call_model: Callable[[Any, List[Any], str], Any],  # model, contents, prompt
) -> PdfAnalysisResult:
    """Core runtime logic for pdf tool."""

    if not request.pdfs:
        raise ValueError("pdf required: provide a path or URL to a PDF document")

    if len(request.pdfs) > 10:
        return PdfAnalysisResult("", {"error": "too_many_pdfs"})

    candidates = resolve_pdf_model_candidates(
        request.cfg,
        getattr(request.cfg, "pdfModel", None) if request.cfg else None,
        getattr(request.cfg, "imageModel", None) if request.cfg else None,
        None,  # session_model_ref, omitted for simplicity
        request.model_override,
        lambda m: (
            {"provider": m.split("/")[0], "model": m.split("/")[1]} if m and "/" in m else None
        ),
        lambda: [],  # list_providers
        True,
    )

    # We pretend to resolve and pick the first
    # In full OpenClaw, we loop over candidates and try them.
    # We will just pick the first valid one here.
    if not candidates:
        raise RuntimeError("No PDF capable model found.")

    selected_ref = candidates[0]
    provider_id = selected_ref.get("provider")

    is_native = provider_id in ("anthropic", "google")

    if is_native:
        if request.pages:
            raise ValueError("pages is not supported with native PDF providers")
        if request.password:
            raise ValueError("password is not supported with native PDF providers")

        # Format native PDF request
        contents = []
        from .extraction import _resolve_pdf_bytes
        import base64

        max_bytes = int(request.max_bytes_mb * 1024 * 1024)
        for pdf_ref in request.pdfs:
            try:
                pdf_bytes = _resolve_pdf_bytes(pdf_ref, max_bytes)
                b64 = base64.b64encode(pdf_bytes).decode("utf-8")
                contents.append(
                    {"type": "document", "document": {"url": f"data:application/pdf;base64,{b64}"}}
                )
            except Exception as e:
                if str(e) == "unsupported_pdf_reference":
                    return PdfAnalysisResult("", {"error": "unsupported_pdf_reference"})
                raise

        # Call model
        response_text = await call_model(selected_ref, contents, request.prompt)

        details = {
            "model": f"{provider_id}/{selected_ref.get('model')}",
            "native": True,
            "attempts": 0,
            "pdf": request.pdfs[0] if len(request.pdfs) == 1 else None,
            "pdfs": [{"pdf": p} for p in request.pdfs] if len(request.pdfs) > 1 else None,
        }
        return PdfAnalysisResult(response_text, details)

    else:
        # Fallback
        try:
            text, images, fb_details = extract_pdf_fallback(request)
        except ValueError as e:
            if str(e) == "unsupported_pdf_reference":
                return PdfAnalysisResult("", {"error": "unsupported_pdf_reference"})
            raise

        contents = []
        if text:
            contents.append({"type": "text", "text": text})
        for img in images:
            contents.append(img)

        response_text = await call_model(selected_ref, contents, request.prompt)

        fb_details.update(
            {
                "model": f"{provider_id}/{selected_ref.get('model')}",
                "attempts": 0,
            }
        )
        return PdfAnalysisResult(response_text, fb_details)
