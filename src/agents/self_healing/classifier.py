"""src.agents.self_healing.classifier — Error classification engine.

OpenClaw parity: mirrors
- packages/ai/src/utils/retryable-network-errors.ts
- packages/gateway-protocol/src/failover-reasons.ts
- packages/agent-core/src/errors.ts
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from .failure_event import ErrorCategory, FailureEvent

#: Transient network error patterns matching OpenClaw's TRANSIENT_NETWORK_CODES
TRANSIENT_NETWORK_PATTERNS = re.compile(
    r"econnreset|econnrefused|enotfound|etimedout|eai_again|epipe|ehostunreach|"
    r"connection reset|connection refused|socket hang up|broken pipe|"
    r"network unreachable|und_err_connect_timeout|und_err_headers_timeout|"
    r"und_err_socket|err_stream_premature_close|ssl.*handshake|"
    r"remoteprotocolerror|connection error|temporary failure in name resolution",
    re.IGNORECASE,
)

#: Rate limit patterns matching HTTP 429 and provider messages
RATE_LIMIT_PATTERNS = re.compile(
    r"429|rate[- ]?limit|too many requests|resource_exhausted|quota exceeded|"
    r"throughput limit|exceeded your current quota",
    re.IGNORECASE,
)

#: Auth expiration vs permanent rejection patterns
AUTH_EXPIRED_PATTERNS = re.compile(
    r"401|unauthorized|token expired|invalid_grant|jwt expired|"
    r"auth.*expired|token.*expired|refresh.*token",
    re.IGNORECASE,
)

AUTH_PERMANENT_PATTERNS = re.compile(
    r"403|forbidden|account suspended|invalid api key|invalid_api_key|"
    r"billing.*disabled|access denied|permission denied|unregistered project",
    re.IGNORECASE,
)

#: Model overload patterns matching 503 and capacity drops
MODEL_OVERLOADED_PATTERNS = re.compile(
    r"503|service unavailable|model.*overloaded|server temporarily unavailable|"
    r"upstream server.*overloaded|capacity exceeded|bad gateway|502|504",
    re.IGNORECASE,
)

#: Context overflow patterns matching token limit errors
CONTEXT_OVERFLOW_PATTERNS = re.compile(
    r"context length|maximum context|token limit|string too long|prompt.*too long|"
    r"exceeds.*maximum context length|context_overflow|reduce the length",
    re.IGNORECASE,
)

#: Tool schema validation error patterns
TOOL_VALIDATION_PATTERNS = re.compile(
    r"tool validation|schema mismatch|missing required argument|invalid type|"
    r"expected (string|number|boolean|array|object)|validation error|"
    r"tool argument validation failed",
    re.IGNORECASE,
)

#: System I/O and Windows filesystem error patterns
SYSTEM_IO_PATTERNS = re.compile(
    r"winerror 32|winerror 5|winerror 3|sharing violation|access is denied|"
    r"file not found|no such file or directory|device or resource busy|"
    r"cannot find the drive|is a directory|not a directory|permission denied",
    re.IGNORECASE,
)

#: TLS certificate error patterns matching OpenClaw's tls_certificate
TLS_CERT_PATTERNS = re.compile(
    r"certificate_verify_failed|self[- ]?signed certificate|unable to get local issuer certificate|"
    r"certificate has expired|ssl.*certificate|tls.*handshake.*failed",
    re.IGNORECASE,
)

#: Billing exhausted patterns matching OpenClaw's billing failover reason and HTTP 402
BILLING_PATTERNS = re.compile(
    r"402|payment required|insufficient_quota|credit balance too low|insufficient credits|"
    r"billing.*disabled|billing.*account|current quota|exceeded your.*quota",
    re.IGNORECASE,
)

#: Model not found patterns matching OpenClaw's model_not_found
MODEL_NOT_FOUND_PATTERNS = re.compile(
    r"model not found|model.*does not exist|unknown model|model_not_found|"
    r"the model `.*` does not exist",
    re.IGNORECASE,
)

#: Format error patterns matching OpenClaw's format failover reason
FORMAT_ERROR_PATTERNS = re.compile(
    r"jsondecodeerror|failed to parse|invalid json|malformed response|"
    r"expecting value|unterminated string",
    re.IGNORECASE,
)

#: Session expired patterns matching OpenClaw's session_expired
SESSION_EXPIRED_PATTERNS = re.compile(
    r"session expired|session terminated|session not found|session closed|"
    r"session_expired",
    re.IGNORECASE,
)


class ErrorClassifier:
    """Classifies runtime failures into deterministic ErrorCategory instances."""

    @classmethod
    def classify_exception(
        cls,
        exc: BaseException,
        context: dict[str, Any] | None = None,
    ) -> FailureEvent:
        """Classify an arbitrary exception into a structured FailureEvent."""
        ctx = dict(context or {})
        err_msg = str(exc)
        exc_type = type(exc).__name__

        # 1. Timeout detection
        if isinstance(exc, (asyncio.TimeoutError, TimeoutError)) or "timeout" in err_msg.lower():
            is_tool = "tool_name" in ctx
            return FailureEvent(
                category=ErrorCategory.TOOL_TIMEOUT if is_tool else ErrorCategory.NETWORK_TRANSIENT,
                severity="recoverable",
                error_message=err_msg or "Operation timed out",
                exception_type=exc_type,
                context=ctx,
            )

        # 2. Tool validation error
        if "validation" in exc_type.lower() or TOOL_VALIDATION_PATTERNS.search(err_msg):
            return FailureEvent(
                category=ErrorCategory.TOOL_VALIDATION_ERROR,
                severity="recoverable",
                error_message=err_msg,
                exception_type=exc_type,
                context=ctx,
            )

        # 3. Billing & Quota exhaustion (OpenClaw parity: distinct from transient rate limit)
        if BILLING_PATTERNS.search(err_msg):
            return FailureEvent(
                category=ErrorCategory.BILLING_EXHAUSTED,
                severity="fatal",
                error_message=err_msg,
                exception_type=exc_type,
                context=ctx,
            )

        # 4. Rate limit detection (transient 429 / resource exhausted)
        if RATE_LIMIT_PATTERNS.search(err_msg):
            return FailureEvent(
                category=ErrorCategory.RATE_LIMIT,
                severity="transient",
                error_message=err_msg,
                exception_type=exc_type,
                context=ctx,
            )

        # 5. Auth checks
        if AUTH_PERMANENT_PATTERNS.search(err_msg):
            return FailureEvent(
                category=ErrorCategory.AUTH_PERMANENT,
                severity="fatal",
                error_message=err_msg,
                exception_type=exc_type,
                context=ctx,
            )
        if AUTH_EXPIRED_PATTERNS.search(err_msg):
            return FailureEvent(
                category=ErrorCategory.AUTH_EXPIRED,
                severity="recoverable",
                error_message=err_msg,
                exception_type=exc_type,
                context=ctx,
            )

        # 5. Model overload / capacity
        if MODEL_OVERLOADED_PATTERNS.search(err_msg):
            return FailureEvent(
                category=ErrorCategory.MODEL_OVERLOADED,
                severity="transient",
                error_message=err_msg,
                exception_type=exc_type,
                context=ctx,
            )

        # 6. Context window overflow
        if CONTEXT_OVERFLOW_PATTERNS.search(err_msg):
            return FailureEvent(
                category=ErrorCategory.CONTEXT_OVERFLOW,
                severity="recoverable",
                error_message=err_msg,
                exception_type=exc_type,
                context=ctx,
            )

        # 7. Empty response or reasoning deadlock
        if (
            "empty response" in err_msg.lower()
            or "0 tokens" in err_msg.lower()
            or "no content returned" in err_msg.lower()
        ):
            return FailureEvent(
                category=ErrorCategory.EMPTY_RESPONSE,
                severity="recoverable",
                error_message=err_msg,
                exception_type=exc_type,
                context=ctx,
            )

        # 8. TLS Certificate Error (check before general network transient)
        if TLS_CERT_PATTERNS.search(err_msg):
            return FailureEvent(
                category=ErrorCategory.TLS_CERTIFICATE_ERROR,
                severity="recoverable",
                error_message=err_msg,
                exception_type=exc_type,
                context=ctx,
            )

        # 9. Model not found
        if MODEL_NOT_FOUND_PATTERNS.search(err_msg):
            return FailureEvent(
                category=ErrorCategory.MODEL_NOT_FOUND,
                severity="recoverable",
                error_message=err_msg,
                exception_type=exc_type,
                context=ctx,
            )

        # 11. Format error
        if FORMAT_ERROR_PATTERNS.search(err_msg):
            return FailureEvent(
                category=ErrorCategory.FORMAT_ERROR,
                severity="recoverable",
                error_message=err_msg,
                exception_type=exc_type,
                context=ctx,
            )

        # 12. Session expired
        if SESSION_EXPIRED_PATTERNS.search(err_msg):
            return FailureEvent(
                category=ErrorCategory.SESSION_EXPIRED,
                severity="recoverable",
                error_message=err_msg,
                exception_type=exc_type,
                context=ctx,
            )

        # 13. Transient network errors
        if TRANSIENT_NETWORK_PATTERNS.search(err_msg):
            return FailureEvent(
                category=ErrorCategory.NETWORK_TRANSIENT,
                severity="transient",
                error_message=err_msg,
                exception_type=exc_type,
                context=ctx,
            )

        # 8. Filesystem & System I/O
        if isinstance(
            exc,
            (
                FileNotFoundError,
                PermissionError,
                IsADirectoryError,
                NotADirectoryError,
                FileExistsError,
            ),
        ) or SYSTEM_IO_PATTERNS.search(err_msg):
            return FailureEvent(
                category=ErrorCategory.SYSTEM_IO_ERROR,
                severity="recoverable",
                error_message=err_msg,
                exception_type=exc_type,
                context=ctx,
            )

        # 9. Tool execution error fallback
        if "tool_name" in ctx:
            return FailureEvent(
                category=ErrorCategory.TOOL_EXECUTION_ERROR,
                severity="recoverable",
                error_message=err_msg,
                exception_type=exc_type,
                context=ctx,
            )

        # 10. Default unknown
        return FailureEvent(
            category=ErrorCategory.UNKNOWN,
            severity="recoverable",
            error_message=err_msg,
            exception_type=exc_type,
            context=ctx,
        )

    @classmethod
    def classify_tool_error(
        cls,
        tool_name: str,
        args: dict[str, Any],
        error: Any,
    ) -> FailureEvent:
        """Classify a tool execution failure or validation error."""
        ctx = {"tool_name": tool_name, "args": args}
        if "path" in args:
            ctx["path"] = str(args["path"])
        elif "target" in args:
            ctx["target"] = str(args["target"])

        if isinstance(error, BaseException):
            return cls.classify_exception(error, context=ctx)

        err_str = str(error)
        if TOOL_VALIDATION_PATTERNS.search(err_str):
            return FailureEvent(
                category=ErrorCategory.TOOL_VALIDATION_ERROR,
                severity="recoverable",
                error_message=err_str,
                exception_type="ToolValidationError",
                context=ctx,
            )
        if "timeout" in err_str.lower() or "timed out" in err_str.lower():
            return FailureEvent(
                category=ErrorCategory.TOOL_TIMEOUT,
                severity="recoverable",
                error_message=err_str,
                exception_type="TimeoutError",
                context=ctx,
            )
        if SYSTEM_IO_PATTERNS.search(err_str):
            return FailureEvent(
                category=ErrorCategory.SYSTEM_IO_ERROR,
                severity="recoverable",
                error_message=err_str,
                exception_type="SystemIOError",
                context=ctx,
            )

        return FailureEvent(
            category=ErrorCategory.TOOL_EXECUTION_ERROR,
            severity="recoverable",
            error_message=err_str,
            exception_type="ToolExecutionError",
            context=ctx,
        )

    @classmethod
    def classify_http_status(
        cls,
        status_code: int,
        response_body: str = "",
        context: dict[str, Any] | None = None,
    ) -> FailureEvent:
        """Classify an HTTP status code into a FailureEvent."""
        ctx = dict(context or {})
        ctx["status_code"] = status_code
        err_msg = f"HTTP {status_code}: {response_body[:200]}"

        if status_code == 429:
            return FailureEvent(
                category=ErrorCategory.RATE_LIMIT,
                severity="transient",
                error_message=err_msg,
                exception_type="HttpRateLimitError",
                context=ctx,
            )
        if status_code == 401:
            return FailureEvent(
                category=ErrorCategory.AUTH_EXPIRED,
                severity="recoverable",
                error_message=err_msg,
                exception_type="HttpAuthExpiredError",
                context=ctx,
            )
        if status_code == 403:
            return FailureEvent(
                category=ErrorCategory.AUTH_PERMANENT,
                severity="fatal",
                error_message=err_msg,
                exception_type="HttpForbiddenError",
                context=ctx,
            )
        if status_code in (500, 502, 503, 504):
            return FailureEvent(
                category=ErrorCategory.MODEL_OVERLOADED,
                severity="transient",
                error_message=err_msg,
                exception_type="HttpServerError",
                context=ctx,
            )
        if status_code == 408:
            return FailureEvent(
                category=ErrorCategory.NETWORK_TRANSIENT,
                severity="transient",
                error_message=err_msg,
                exception_type="HttpRequestTimeout",
                context=ctx,
            )
        if status_code == 402:
            return FailureEvent(
                category=ErrorCategory.BILLING_EXHAUSTED,
                severity="fatal",
                error_message=err_msg,
                exception_type="HttpPaymentRequiredError",
                context=ctx,
            )
        if status_code == 404 and ("model" in response_body.lower() or "model" in ctx):
            return FailureEvent(
                category=ErrorCategory.MODEL_NOT_FOUND,
                severity="recoverable",
                error_message=err_msg,
                exception_type="HttpModelNotFoundError",
                context=ctx,
            )

        return FailureEvent(
            category=ErrorCategory.UNKNOWN,
            severity="recoverable",
            error_message=err_msg,
            exception_type="HttpError",
            context=ctx,
        )

    @classmethod
    def classify_model_turn(
        cls,
        content: str | None,
        has_tool_calls: bool,
        is_reasoning_only: bool = False,
        context: dict[str, Any] | None = None,
    ) -> FailureEvent | None:
        """Inspect model turn output to detect empty responses or reasoning-only deadlocks.

        Matches OpenClaw qa/scenarios/runtime/empty-response-recovery-replay-safe-read.yaml
        and qa/scenarios/runtime/reasoning-only-recovery-replay-safe-read.yaml.
        """
        ctx = dict(context or {})
        clean_text = (content or "").strip()

        if is_reasoning_only and not clean_text and not has_tool_calls:
            return FailureEvent(
                category=ErrorCategory.REASONING_ONLY,
                severity="recoverable",
                error_message="Model returned reasoning tokens only without response text or tool calls.",
                exception_type="ReasoningOnlyResponse",
                context=ctx,
            )

        if not clean_text and not has_tool_calls:
            return FailureEvent(
                category=ErrorCategory.EMPTY_RESPONSE,
                severity="recoverable",
                error_message="Model returned empty response (0 tokens, no tool calls).",
                exception_type="EmptyModelResponse",
                context=ctx,
            )

    @classmethod
    def is_transient(cls, category: ErrorCategory) -> bool:
        """Return True if the error category is transient and safe for automatic backoff retry."""
        return category in (
            ErrorCategory.NETWORK_TRANSIENT,
            ErrorCategory.RATE_LIMIT,
            ErrorCategory.MODEL_OVERLOADED,
        )


__all__ = [
    "ErrorClassifier",
]
