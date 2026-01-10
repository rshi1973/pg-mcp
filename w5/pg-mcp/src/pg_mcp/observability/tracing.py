"""Request tracing and context propagation for PostgreSQL MCP Server.

This module provides request ID generation and context propagation throughout
the query processing pipeline, enabling end-to-end tracing of requests.
"""

import contextvars
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from pydantic import BaseModel

# Context variable for current request ID
_request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)

# Type variables for decorators
P = ParamSpec("P")
R = TypeVar("R")


class TraceContext(BaseModel):
    """Trace context containing request tracking information.

    Attributes:
        request_id: Unique identifier for the request.
        parent_id: Optional parent request ID for nested operations.
        operation: Name of the operation being traced.
        metadata: Additional metadata about the request.
    """

    request_id: str
    parent_id: str | None = None
    operation: str | None = None
    metadata: dict[str, Any] | None = None


def generate_request_id() -> str:
    """Generate a unique request ID.

    Returns:
        UUID4-based request ID as a string.

    Example:
        >>> req_id = generate_request_id()
        >>> print(req_id)
        'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
    """
    return str(uuid.uuid4())


def get_request_id() -> str | None:
    """Get the current request ID from context.

    Returns:
        Current request ID or None if not set.

    Example:
        >>> with request_context():
        ...     print(get_request_id())
        'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
    """
    return _request_id_var.get()


def set_request_id(request_id: str) -> None:
    """Set the current request ID in context.

    Args:
        request_id: Request ID to set.

    Example:
        >>> set_request_id("custom-request-id")
        >>> assert get_request_id() == "custom-request-id"
    """
    _request_id_var.set(request_id)


def clear_request_id() -> None:
    """Clear the current request ID from context.

    Example:
        >>> clear_request_id()
        >>> assert get_request_id() is None
    """
    _request_id_var.set(None)


@asynccontextmanager
async def request_context(request_id: str | None = None) -> AsyncIterator[str]:
    """Context manager for request tracing.

    Creates a new request context with a unique (or provided) request ID
    that will be propagated through all async operations.

    Args:
        request_id: Optional request ID. If not provided, a new one is generated.

    Yields:
        The request ID for this context.

    Example:
        >>> async with request_context() as req_id:
        ...     logger.info("Processing request", extra={"request_id": req_id})
        ...     await some_operation()
    """
    if request_id is None:
        request_id = generate_request_id()

    token = _request_id_var.set(request_id)
    try:
        yield request_id
    finally:
        _request_id_var.reset(token)


def trace_async(
    operation: str | None = None,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Decorator to trace async functions with request ID.

    Automatically injects request_id into log records and ensures
    context propagation through async calls.

    Args:
        operation: Optional operation name. If not provided, uses function name.

    Returns:
        Decorated function that maintains request context.

    Example:
        >>> @trace_async(operation="generate_sql")
        ... async def generate_sql(question: str) -> str:
        ...     logger.info("Generating SQL", extra={"question": question})
        ...     return "SELECT 1"
    """

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        op_name = operation or func.__name__

        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            request_id = get_request_id()

            if request_id:
                # Create a log adapter that adds request_id to all log records
                old_factory = logging.getLogRecordFactory()

                def record_factory(*factory_args: Any, **factory_kwargs: Any) -> logging.LogRecord:
                    record = old_factory(*factory_args, **factory_kwargs)
                    record.request_id = request_id
                    record.operation = op_name
                    return record

                logging.setLogRecordFactory(record_factory)

                try:
                    result = await func(*args, **kwargs)
                    return result
                finally:
                    logging.setLogRecordFactory(old_factory)
            else:
                # No request context, just execute
                return await func(*args, **kwargs)

        return wrapper

    return decorator


def trace_sync(
    operation: str | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator to trace synchronous functions with request ID.

    Similar to trace_async but for synchronous functions.

    Args:
        operation: Optional operation name. If not provided, uses function name.

    Returns:
        Decorated function that maintains request context.

    Example:
        >>> @trace_sync(operation="validate_sql")
        ... def validate_sql(sql: str) -> bool:
        ...     logger.info("Validating SQL", extra={"sql": sql})
        ...     return True
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        op_name = operation or func.__name__

        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            request_id = get_request_id()

            if request_id:
                old_factory = logging.getLogRecordFactory()

                def record_factory(*factory_args: Any, **factory_kwargs: Any) -> logging.LogRecord:
                    record = old_factory(*factory_args, **factory_kwargs)
                    record.request_id = request_id
                    record.operation = op_name
                    return record

                logging.setLogRecordFactory(record_factory)

                try:
                    result = func(*args, **kwargs)
                    return result
                finally:
                    logging.setLogRecordFactory(old_factory)
            else:
                return func(*args, **kwargs)

        return wrapper

    return decorator


class TracingLogger:
    """Logger wrapper that automatically includes request context.

    This class wraps the standard logger to automatically include
    request_id and operation name in all log messages.

    Example:
        >>> logger = TracingLogger(__name__)
        >>> async with request_context():
        ...     logger.info("Processing query", database="mydb")
    """

    def __init__(self, name: str):
        """Initialize tracing logger.

        Args:
            name: Logger name (typically module name).
        """
        self._logger = logging.getLogger(name)

    def _log(self, level: int, msg: str, *args: Any, **kwargs: Any) -> None:
        """Internal log method that adds request context.

        Args:
            level: Log level.
            msg: Log message.
            *args: Positional arguments for message formatting.
            **kwargs: Keyword arguments including 'extra' for additional fields.
        """
        extra = kwargs.pop("extra", {})
        request_id = get_request_id()

        # Only add request_id if not already present
        if request_id and "request_id" not in extra:
            extra["request_id"] = request_id

        kwargs["extra"] = extra
        self._logger.log(level, msg, *args, **kwargs)

    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log a debug message."""
        self._log(logging.DEBUG, msg, *args, **kwargs)

    def info(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log an info message."""
        self._log(logging.INFO, msg, *args, **kwargs)

    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log a warning message."""
        self._log(logging.WARNING, msg, *args, **kwargs)

    def error(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log an error message."""
        self._log(logging.ERROR, msg, *args, **kwargs)

    def critical(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log a critical message."""
        self._log(logging.CRITICAL, msg, *args, **kwargs)

    def exception(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log an exception message with traceback."""
        kwargs["exc_info"] = True
        self._log(logging.ERROR, msg, *args, **kwargs)


def get_tracing_logger(name: str) -> TracingLogger:
    """Get a tracing logger instance.

    Args:
        name: Logger name (typically __name__).

    Returns:
        TracingLogger instance.

    Example:
        >>> logger = get_tracing_logger(__name__)
        >>> logger.info("Operation started")
    """
    return TracingLogger(name)


# OpenTelemetry Integration
try:
    from contextlib import contextmanager
    from typing import Iterator

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
    from opentelemetry.trace import Span, SpanKind, Status, StatusCode, Tracer

    _OPENTELEMETRY_AVAILABLE = True
except ImportError:
    _OPENTELEMETRY_AVAILABLE = False
    Tracer = Any  # type: ignore[misc,assignment]
    Span = Any  # type: ignore[misc,assignment]
    SpanKind = Any  # type: ignore[misc,assignment]
    StatusCode = Any  # type: ignore[misc,assignment]


def setup_opentelemetry_tracing(
    service_name: str,
    endpoint: str | None = None,
    sample_rate: float = 1.0,
) -> Tracer | None:
    """Setup OpenTelemetry distributed tracing.

    Args:
        service_name: Service name for traces.
        endpoint: OTLP endpoint URL (e.g., http://localhost:4317).
                 If None, exports to console.
        sample_rate: Sampling rate (0.0-1.0). Default 1.0 (100%).

    Returns:
        Tracer instance if OpenTelemetry is available, None otherwise.

    Example:
        >>> tracer = setup_opentelemetry_tracing("pg-mcp", "http://localhost:4317", 0.1)
    """
    if not _OPENTELEMETRY_AVAILABLE:
        return None

    # Create tracer provider with sampling
    sampler = TraceIdRatioBased(sample_rate)
    provider = TracerProvider(sampler=sampler)

    # Configure exporter
    if endpoint:
        # Export to OTLP collector (Jaeger, Tempo, etc.)
        exporter: OTLPSpanExporter | ConsoleSpanExporter = OTLPSpanExporter(endpoint=endpoint)
    else:
        # Export to console for development
        exporter = ConsoleSpanExporter()

    # Add batch span processor
    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)

    # Set as global tracer provider
    trace.set_tracer_provider(provider)

    # Return tracer for this service
    return trace.get_tracer(service_name)


class OpenTelemetryContext:
    """OpenTelemetry tracing context for request tracking.

    This class manages trace spans for a single request, providing
    context propagation and span lifecycle management.

    Example:
        >>> tracer = trace.get_tracer("pg-mcp")
        >>> ctx = OpenTelemetryContext(request_id="123", tracer=tracer)
        >>> with ctx.span("query.execute") as span:
        ...     span.set_attribute("question", question)
        ...     result = await process_query()
    """

    def __init__(self, request_id: str, tracer: Tracer) -> None:
        """Initialize tracing context.

        Args:
            request_id: Unique request identifier.
            tracer: OpenTelemetry tracer instance.
        """
        self.request_id = request_id
        self.tracer = tracer
        self.root_span: Span | None = None
        self._span_stack: list[Span] = []

    def create_span(
        self,
        name: str,
        attributes: dict[str, Any] | None = None,
        kind: Any = None,
    ) -> Span:
        """Create and start a new span.

        Args:
            name: Span name (e.g., "sql.generate", "database.query").
            attributes: Optional span attributes.
            kind: Span kind (INTERNAL, CLIENT, SERVER, etc.).

        Returns:
            Started span instance.
        """
        if not _OPENTELEMETRY_AVAILABLE:
            return None  # type: ignore[return-value]

        if kind is None:
            kind = SpanKind.INTERNAL

        span = self.tracer.start_span(name, kind=kind)

        # Set request ID attribute
        span.set_attribute("pg_mcp.request_id", self.request_id)

        # Set additional attributes
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, value)

        # Track root span
        if self.root_span is None:
            self.root_span = span

        # Add to stack
        self._span_stack.append(span)

        return span

    def end_span(self) -> None:
        """End the current span and pop from stack."""
        if self._span_stack:
            span = self._span_stack.pop()
            span.end()

    def set_attribute(self, key: str, value: Any) -> None:
        """Set attribute on current span."""
        if self._span_stack:
            self._span_stack[-1].set_attribute(key, value)

    def record_exception(self, exception: Exception) -> None:
        """Record exception on current span."""
        if self._span_stack:
            self._span_stack[-1].record_exception(exception)

    def set_status(self, status_code: Any, description: str | None = None) -> None:
        """Set status on current span."""
        if self._span_stack and _OPENTELEMETRY_AVAILABLE:
            status = Status(status_code, description)
            self._span_stack[-1].set_status(status)

    @contextmanager
    def span(
        self,
        name: str,
        attributes: dict[str, Any] | None = None,
        kind: Any = None,
    ) -> Iterator[Span | None]:
        """Context manager for span lifecycle."""
        if not _OPENTELEMETRY_AVAILABLE:
            yield None
            return

        span = self.create_span(name, attributes, kind)
        try:
            yield span
        except Exception as e:
            span.record_exception(e)
            if _OPENTELEMETRY_AVAILABLE:
                span.set_status(Status(StatusCode.ERROR, str(e)))
            raise
        finally:
            self.end_span()
