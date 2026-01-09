# Internal API Contracts

**Feature**: Security, Observability, and Testing Enhancement
**Status**: Phase 1 Design
**Created**: 2026-01-09
**Last Updated**: 2026-01-09

---

## Overview

This document defines the internal service contracts (interfaces) for new components being added to the PostgreSQL MCP Server. All contracts use Python's `Protocol` for structural typing.

---

## 1. Rate Limiter Contract

**Purpose**: Control concurrent request rate to prevent resource exhaustion.

**Location**: `src/pg_mcp/resilience/rate_limiter.py`

```python
from typing import Protocol
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

class RateLimiter(Protocol):
    """Protocol for rate limiting concurrent operations."""

    @property
    def max_concurrent(self) -> int:
        """Maximum number of concurrent operations allowed."""
        ...

    @property
    def active_count(self) -> int:
        """Current number of active operations."""
        ...

    @property
    def available(self) -> int:
        """Number of available slots."""
        ...

    async def acquire(self, *, timeout: float | None = None) -> bool:
        """Acquire a slot for concurrent operation.

        Args:
            timeout: Optional timeout in seconds. If None, waits indefinitely.

        Returns:
            True if slot was acquired, False if timeout occurred.

        Raises:
            asyncio.TimeoutError: If timeout is exceeded.
        """
        ...

    def release(self) -> None:
        """Release a slot after operation completes."""
        ...

    @asynccontextmanager
    async def __call__(
        self,
        *,
        timeout: float | None = None,
    ) -> AsyncIterator[None]:
        """Context manager for rate-limited operations.

        Args:
            timeout: Optional timeout in seconds.

        Yields:
            None

        Raises:
            asyncio.TimeoutError: If timeout is exceeded.

        Example:
            >>> async with rate_limiter(timeout=10.0):
            ...     await perform_operation()
        """
        ...

    def get_stats(self) -> dict[str, int]:
        """Get rate limiter statistics.

        Returns:
            Dictionary containing:
                - max_concurrent: Maximum concurrent operations
                - active_count: Current active operations
                - available: Available slots
                - total_requests: Total requests processed
                - total_rejections: Total requests rejected
        """
        ...
```

**Usage Example**:
```python
rate_limiter = RateLimiter(max_concurrent=10)

@mcp.tool()
async def query_database(question: str) -> dict:
    try:
        async with rate_limiter(timeout=30.0):
            response = await orchestrator.execute_query(request)
            return response.model_dump()
    except TimeoutError:
        return {"error": "Rate limit timeout"}
```

---

## 2. Executor Registry Contract

**Purpose**: Manage database-specific executor instances.

**Location**: `src/pg_mcp/services/executor_registry.py`

```python
from typing import Protocol
from asyncpg import Pool
from pg_mcp.services.sql_executor import SQLExecutor
from pg_mcp.resilience.circuit_breaker import CircuitBreaker

class ExecutorRegistry(Protocol):
    """Protocol for managing database-specific executors."""

    def get_executor(self, database: str) -> SQLExecutor:
        """Get executor for database.

        Args:
            database: Database name

        Returns:
            SQLExecutor instance for the database

        Raises:
            DatabaseError: If database not found

        Note:
            Executors are created lazily on first access and cached.
        """
        ...

    def get_circuit_breaker(self, database: str) -> CircuitBreaker:
        """Get circuit breaker for database.

        Args:
            database: Database name

        Returns:
            CircuitBreaker instance for the database

        Raises:
            DatabaseError: If database not found
        """
        ...

    def register_pool(self, database: str, pool: Pool) -> None:
        """Register a connection pool for a database.

        Args:
            database: Database name
            pool: asyncpg connection pool

        Note:
            Must be called before get_executor() for the database.
        """
        ...

    def list_databases(self) -> list[str]:
        """Get list of registered database names.

        Returns:
            List of database names
        """
        ...
```

**Usage Example**:
```python
registry = ExecutorRegistry(security_config, db_config, resilience_config)

# Register pools
for db_name, pool in pools.items():
    registry.register_pool(db_name, pool)

# Get executor for specific database
executor = registry.get_executor("mydb")
results, count = await executor.execute(sql)

# Get circuit breaker for monitoring
cb = registry.get_circuit_breaker("mydb")
print(f"Circuit breaker state: {cb.state}")
```

---

## 3. Access Control Validator Contract

**Purpose**: Validate SQL against access control policies.

**Location**: `src/pg_mcp/security/access_control.py`

```python
from typing import Protocol
from dataclasses import dataclass

@dataclass
class ValidationResult:
    """Result of access control validation."""
    is_valid: bool
    violations: list[str]
    tables_accessed: set[str]
    columns_accessed: dict[str, set[str]]

class AccessControlValidator(Protocol):
    """Protocol for SQL access control validation."""

    def validate(
        self,
        sql: str,
        policy: "AccessControlPolicy"
    ) -> ValidationResult:
        """Validate SQL against access control policy.

        Args:
            sql: SQL query to validate
            policy: Access control policy to enforce

        Returns:
            ValidationResult with validation outcome

        Raises:
            SQLParseError: If SQL cannot be parsed

        Note:
            This method does not raise on validation failures,
            it returns them in ValidationResult.violations.
        """
        ...

    def extract_tables(self, sql: str) -> set[str]:
        """Extract table references from SQL.

        Args:
            sql: SQL query to parse

        Returns:
            Set of table names referenced in the query

        Raises:
            SQLParseError: If SQL cannot be parsed

        Note:
            Includes tables from FROM, JOIN, and CTE clauses.
        """
        ...

    def extract_columns(self, sql: str) -> dict[str, set[str]]:
        """Extract column references per table.

        Args:
            sql: SQL query to parse

        Returns:
            Dictionary mapping table names to sets of column names

        Raises:
            SQLParseError: If SQL cannot be parsed

        Note:
            Includes columns from SELECT list, WHERE, JOIN ON, etc.
        """
        ...
```

**Usage Example**:
```python
validator = AccessControlValidator()
policy = AccessControlPolicy.from_config("mydb", security_config)

# Validate SQL
result = validator.validate(sql, policy)

if not result.is_valid:
    raise SecurityViolationError(
        f"Access control violations: {', '.join(result.violations)}"
    )

# Or extract references for logging
tables = validator.extract_tables(sql)
columns = validator.extract_columns(sql)
logger.info("Query accesses tables", extra={"tables": list(tables)})
```

---

## 4. EXPLAIN Policy Contract

**Purpose**: Validate query cost using PostgreSQL EXPLAIN.

**Location**: `src/pg_mcp/security/explain_policy.py`

```python
from typing import Protocol
from asyncpg import Connection

class ExplainPolicy(Protocol):
    """Protocol for query cost validation using EXPLAIN."""

    @property
    def threshold(self) -> int:
        """Complexity threshold to trigger EXPLAIN check."""
        ...

    @property
    def max_cost(self) -> int:
        """Maximum allowed query cost."""
        ...

    @property
    def enabled(self) -> bool:
        """Whether EXPLAIN policy is enabled."""
        ...

    def should_explain(self, sql: str) -> bool:
        """Determine if query should be explained based on complexity.

        Args:
            sql: SQL query to check

        Returns:
            True if query should be explained, False otherwise

        Heuristics:
            - Contains JOIN: True
            - Contains UNION: True
            - Contains WITH (CTE): True
            - Contains GROUP BY: True
            - Multiple SELECT statements: True
            - Otherwise: False
        """
        ...

    async def validate_cost(
        self,
        conn: Connection,
        sql: str
    ) -> tuple[bool, float]:
        """Validate query cost using EXPLAIN.

        Args:
            conn: Database connection
            sql: SQL query to validate

        Returns:
            tuple: (is_acceptable, actual_cost) where:
                - is_acceptable: True if cost <= max_cost
                - actual_cost: Estimated query cost from EXPLAIN

        Raises:
            DatabaseError: If EXPLAIN fails

        Note:
            Uses EXPLAIN (FORMAT JSON) for structured output.
        """
        ...
```

**Usage Example**:
```python
policy = ExplainPolicy.from_config(security_config)

# Check if EXPLAIN needed
if policy.enabled and policy.should_explain(sql):
    async with pool.acquire() as conn:
        is_acceptable, cost = await policy.validate_cost(conn, sql)

        if not is_acceptable:
            raise SecurityViolationError(
                f"Query cost ({cost}) exceeds maximum ({policy.max_cost})"
            )
```

---

## 5. Metrics Collector Contract

**Purpose**: Collect and expose Prometheus metrics.

**Location**: `src/pg_mcp/observability/metrics.py`

```python
from typing import Protocol, Callable

class MetricsCollector(Protocol):
    """Protocol for Prometheus metrics collection."""

    def increment_counter(
        self,
        name: str,
        labels: dict[str, str],
        value: float = 1.0
    ) -> None:
        """Increment counter metric.

        Args:
            name: Metric name (without namespace prefix)
            labels: Label key-value pairs
            value: Increment value (default 1.0)

        Example:
            >>> metrics.increment_counter(
            ...     "query_requests_total",
            ...     labels={"database": "mydb", "status": "success"}
            ... )
        """
        ...

    def observe_histogram(
        self,
        name: str,
        value: float,
        labels: dict[str, str]
    ) -> None:
        """Record histogram observation.

        Args:
            name: Metric name (without namespace prefix)
            value: Observed value
            labels: Label key-value pairs

        Example:
            >>> metrics.observe_histogram(
            ...     "query_duration_seconds",
            ...     value=1.234,
            ...     labels={"database": "mydb", "operation": "execute"}
            ... )
        """
        ...

    def set_gauge(
        self,
        name: str,
        value: float,
        labels: dict[str, str]
    ) -> None:
        """Set gauge value.

        Args:
            name: Metric name (without namespace prefix)
            value: Gauge value
            labels: Label key-value pairs

        Example:
            >>> metrics.set_gauge(
            ...     "database_connections_active",
            ...     value=15,
            ...     labels={"database": "mydb"}
            ... )
        """
        ...

    def start_timer(
        self,
        name: str,
        labels: dict[str, str]
    ) -> Callable[[], None]:
        """Start timer for histogram metric.

        Args:
            name: Metric name (without namespace prefix)
            labels: Label key-value pairs

        Returns:
            Callable that stops timer and records duration

        Example:
            >>> stop_timer = metrics.start_timer(
            ...     "query_duration_seconds",
            ...     labels={"database": "mydb", "operation": "execute"}
            ... )
            >>> # ... perform operation ...
            >>> stop_timer()  # Records duration
        """
        ...
```

**Usage Example**:
```python
metrics = MetricsCollector()

# Increment counter
metrics.increment_counter(
    "query_requests_total",
    labels={"database": "mydb", "status": "started"}
)

# Use timer
stop_timer = metrics.start_timer(
    "query_duration_seconds",
    labels={"database": "mydb", "operation": "execute"}
)
try:
    results = await execute_query(sql)
    metrics.increment_counter(
        "query_requests_total",
        labels={"database": "mydb", "status": "success"}
    )
finally:
    stop_timer()
```

---

## 6. Metrics Server Contract

**Purpose**: HTTP server for exposing Prometheus metrics.

**Location**: `src/pg_mcp/observability/metrics.py`

```python
from typing import Protocol

class MetricsServer(Protocol):
    """Protocol for Prometheus metrics HTTP server."""

    @property
    def port(self) -> int:
        """HTTP server port."""
        ...

    @property
    def host(self) -> str:
        """HTTP server bind address."""
        ...

    def start(self) -> None:
        """Start metrics server in background thread.

        Note:
            Server runs in daemon thread and terminates with main process.
        """
        ...

    def stop(self) -> None:
        """Stop metrics server (graceful shutdown).

        Note:
            prometheus-client doesn't provide stop method,
            server terminates when main process exits.
        """
        ...

    def is_running(self) -> bool:
        """Check if server is running.

        Returns:
            True if server thread is alive, False otherwise
        """
        ...
```

**Usage Example**:
```python
metrics_server = MetricsServer(port=9090, host="0.0.0.0")

# Start server
metrics_server.start()
logger.info(f"Metrics server started on {metrics_server.host}:{metrics_server.port}")

# Metrics available at http://localhost:9090/metrics

# Shutdown (optional, happens automatically on exit)
metrics_server.stop()
```

---

## 7. Tracing Context Contract

**Purpose**: Distributed tracing context management.

**Location**: `src/pg_mcp/observability/tracing.py`

```python
from typing import Protocol, Any, Iterator
from contextlib import contextmanager
from opentelemetry.trace import Span, SpanKind, StatusCode

class TracingContext(Protocol):
    """Protocol for distributed tracing context."""

    @property
    def request_id(self) -> str:
        """Unique request identifier."""
        ...

    def create_span(
        self,
        name: str,
        attributes: dict[str, Any] | None = None,
        kind: SpanKind = SpanKind.INTERNAL
    ) -> Span:
        """Create and start a new span.

        Args:
            name: Span name (e.g., "sql.generate", "database.query")
            attributes: Optional span attributes
            kind: Span kind (INTERNAL, CLIENT, SERVER, etc.)

        Returns:
            Started span instance

        Note:
            Span is automatically added to span stack and set as current.
        """
        ...

    def end_span(self) -> None:
        """End the current span and pop from stack."""
        ...

    def set_attribute(self, key: str, value: Any) -> None:
        """Set attribute on current span.

        Args:
            key: Attribute key (use dot notation, e.g., "db.statement")
            value: Attribute value
        """
        ...

    def record_exception(self, exception: Exception) -> None:
        """Record exception on current span.

        Args:
            exception: Exception to record
        """
        ...

    def set_status(
        self,
        status_code: StatusCode,
        description: str | None = None
    ) -> None:
        """Set status on current span.

        Args:
            status_code: Status code (OK, ERROR)
            description: Optional status description
        """
        ...

    @contextmanager
    def span(
        self,
        name: str,
        attributes: dict[str, Any] | None = None,
        kind: SpanKind = SpanKind.INTERNAL
    ) -> Iterator[Span]:
        """Context manager for span lifecycle.

        Args:
            name: Span name
            attributes: Optional span attributes
            kind: Span kind

        Yields:
            Span instance

        Example:
            >>> with tracing_ctx.span("sql.generate") as span:
            ...     span.set_attribute("question", question)
            ...     sql = await generate_sql(question)
        """
        ...
```

**Usage Example**:
```python
tracing_ctx = TracingContext(request_id="123", tracer=tracer)

# Using context manager
with tracing_ctx.span("query.execute") as span:
    span.set_attribute("question", question)
    span.set_attribute("database", database)

    with tracing_ctx.span("sql.generate", kind=SpanKind.CLIENT) as gen_span:
        gen_span.set_attribute("llm.model", "gemini-2.0-flash-exp")
        try:
            sql = await generate_sql(question)
            gen_span.set_attribute("sql_length", len(sql))
        except Exception as e:
            gen_span.record_exception(e)
            gen_span.set_status(StatusCode.ERROR, str(e))
            raise
```

---

## 8. Retry Strategy Contract

**Purpose**: Retry logic for transient failures.

**Location**: `src/pg_mcp/resilience/retry.py`

```python
from typing import Protocol, TypeVar, Callable, Awaitable

T = TypeVar("T")

class RetryStrategy(Protocol):
    """Protocol for retry logic with exponential backoff."""

    @property
    def max_retries(self) -> int:
        """Maximum number of retry attempts."""
        ...

    @property
    def initial_delay(self) -> float:
        """Initial retry delay in seconds."""
        ...

    @property
    def backoff_factor(self) -> float:
        """Exponential backoff factor."""
        ...

    async def execute(
        self,
        func: Callable[[], Awaitable[T]],
        *,
        is_transient: Callable[[Exception], bool] | None = None
    ) -> T:
        """Execute function with retry logic.

        Args:
            func: Async function to execute
            is_transient: Optional function to determine if error is transient

        Returns:
            Result of successful execution

        Raises:
            Exception: Last exception if all retries exhausted

        Example:
            >>> retry = RetryStrategy(max_retries=3, initial_delay=1.0)
            >>> result = await retry.execute(
            ...     lambda: conn.fetch(sql),
            ...     is_transient=lambda e: isinstance(e, asyncpg.ConnectionError)
            ... )
        """
        ...

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number.

        Args:
            attempt: Attempt number (0-indexed)

        Returns:
            Delay in seconds

        Formula:
            delay = initial_delay * (backoff_factor ** attempt)
        """
        ...
```

**Usage Example**:
```python
retry = RetryStrategy(
    max_retries=3,
    initial_delay=1.0,
    backoff_factor=2.0
)

def is_transient_error(e: Exception) -> bool:
    """Determine if error is transient and should be retried."""
    return isinstance(e, (
        asyncpg.ConnectionError,
        asyncpg.TooManyConnectionsError,
        asyncpg.CannotConnectNowError
    ))

# Execute with retry
results = await retry.execute(
    lambda: conn.fetch(sql),
    is_transient=is_transient_error
)
```

---

## Summary

This document defines 8 internal service contracts:

1. **RateLimiter**: Concurrent request control
2. **ExecutorRegistry**: Database-specific executor management
3. **AccessControlValidator**: SQL access control validation
4. **ExplainPolicy**: Query cost validation
5. **MetricsCollector**: Prometheus metrics collection
6. **MetricsServer**: Metrics HTTP server
7. **TracingContext**: Distributed tracing context
8. **RetryStrategy**: Retry logic with exponential backoff

All contracts use Python's `Protocol` for structural typing, enabling flexible implementations while maintaining type safety.

---

**Document Version**: 1.0
**Status**: Complete
**Next**: Quickstart Guide
