"""
PDF Analysis Types
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class PdfAnalysisRequest:
    """The normalized request for PDF analysis."""

    prompt: str
    pdfs: List[str]
    pages: Optional[str] = None
    password: Optional[str] = None
    model_override: Optional[str] = None
    max_bytes_mb: float = 10.0
    max_pages: int = 20
    agent_id: Optional[str] = None
    cfg: Optional[Any] = None


@dataclass
class PdfAnalysisResult:
    """The result of PDF analysis."""

    text: str
    details: Dict[str, Any]


@dataclass
class PdfAnalysisProvider:
    """A provider configuration for PDF analysis capabilities."""

    id: str
    default_model: Optional[str] = None
    models: List[str] = field(default_factory=list)
