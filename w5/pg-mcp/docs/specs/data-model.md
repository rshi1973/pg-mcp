# Data Model Design: Security, Observability, and Testing Enhancement

**Feature**: Security, Observability, and Testing Enhancement
**Status**: Phase 1 Design
**Created**: 2026-01-09
**Last Updated**: 2026-01-09

---

## Overview

This document defines the data models and entities required for implementing security controls, resilience mechanisms, and observability features in the PostgreSQL MCP Server.

---

## Entity Definitions

### 1. ExecutorRegistry

**Purpose**: Manage database-specific executor instances with per-database circuit breakers.

**Location**: `src/pg_mcp/services/executor_registry.py`

**Fields**:
```python
class ExecutorRegistry:
    """Registry for managing database-specific SQL executors."""

    _executors: dict[str, SQLExecutor]
    """Mapping of database name to executor instance."""

    _circuit_breakers: dict[str, CircuitBreaker]
    """Mapping of database name to circuit breaker instance."""

    _pools: dict[str, Pool]
    """Mapping of database name to connection pool."""

    _security_config: SecurityConfig
    """Security configuration shared across executors."""

    _db_config: DatabaseConfig
    """Database configuration shared across executors."""

    _resilience_config: ResilienceConfig
    """Resilience configuration for circuit breakers."""
```

**Operations**:
```python
def get_executor(self, database: str) -> SQLExecutor:
    """Get or create executor for database.

    Args:
        database: Database name

    Returns:
        SQLExecutor instance for the database

    Raises:
        DatabaseError: If database not found in pools
    """

def get_circuit_breaker(self, database: str) -> CircuitBreaker:
    """Get circuit breaker for database.

    Args:
        database: Database name

    Returns:
        CircuitBreaker instance for the database
    """

def register_pool(self, database: str, pool: Pool) -> None:
    """Register a connection pool for a database.

    Args:
        database: Database name
        pool: asyncpg connection pool
    """

def list_databases(self) -> list[str]:
    """Get list of registered database names.

    Returns:
        List of database names
    """
```

**Relationships**:
- Has many `SQLExecutor` instances (one per database)
- Has many `CircuitBreaker` instances (one per database)
- References `SecurityConfig`, `DatabaseConfig`, `ResilienceConfig`

**State Transitions**:
1. **Initialization**: Empty registry
2. **Pool Registration**: Pools added via `register_pool()`
3. **Lazy Executor Creation**: Executors created on first `get_executor()` call
4. **Steady State**: Executors cached and reused

---

### 2. AccessControlPolicy

**Purpose**: Define and enforce table/column access restrictions.

**Location**: `src/pg_mcp/security/access_control.py`

**Fields**:
```python
class AccessControlPolicy:
    """Policy for table and column access control."""

    database: str
    """Database name this policy applies to."""

    allowed_tables: set[str]
    """Whitelist of allowed tables. Empty set means all tables allowed."""

    blocked_tables: set[str]
    """Blacklist of blocked tables. Takes precedence over allowed_tables."""

    column_restrictions: dict[str, set[str]]
    """Mapping of table name to set of blocked column names."""
```

**Operations**:
```python
def validate_table_access(self, table: str) -> bool:
    """Check if access to table is allowed.

    Args:
        table: Table name to check

    Returns:
        True if access allowed, False otherwise

    Logic:
        1. If table in blocked_tables: return False
        2. If allowed_tables is empty: return True (allow all)
        3. If table in allowed_tables: return True
        4. Otherwise: return False
    """

def validate_column_access(self, table: str, column: str) -> bool:
    """Check if access to column is allowed.

    Args:
        table: Table name
        column: Column name

    Returns:
        True if access allowed, False otherwise

    Logic:
        1. If table not in column_restrictions: return True
        2. If column in column_restrictions[table]: return False
        3. Otherwise: return True
    """

def get_violations(self, tables: set[str], columns: dict[str, set[str]]) -> list[str]:
    """Get list of access control violations.

    Args:
        tables: Set of table names referenced in SQL
        columns: Dict mapping table names to column sets

    Returns:
        List of violation messages (empty if no violations)

    Example:
        >>> policy.get_violations(
        ...     tables={"users", "passwords"},
        ...     columns={"users": {"id", "email", "password_hash"}}
        ... )
        ["Access denied to table: passwords",
         "Access denied to column: users.password_hash"]
    """

@classmethod
def from_config(cls, database: str, config: SecurityConfig) -> "AccessControlPolicy":
    """Create policy from security configuration.

    Args:
        database: Database name
        config: Security configuration

    Returns:
        AccessControlPolicy instance
    """
```

**Validation Rules**:
1. **Table Blacklist**: Always enforced, takes precedence
2. **Table Whitelist**: Only enforced if non-empty
3. **Column Restrictions**: Per-table blocked columns
4. **Default Behavior**: Allow all if no restrictions configured

**Example Usage**:
```python
# Configuration
config = SecurityConfig(
    allowed_tables=["users", "orders"],
    blocked_tables=["passwords", "secrets"],
    column_restrictions={
        "users": ["password_hash", "ssn"],
        "orders": ["credit_card"]
    }
)

policy = AccessControlPolicy.from_config("mydb", config)

# Validation
policy.validate_table_access("users")      # True
policy.validate_table_access("passwords")  # False
policy.validate_column_access("users", "email")         # True
policy.validate_column_access("users", "password_hash") # False
```

---

### 3. ExplainPolicy

**Purpose**: Query cost validation using PostgreSQL EXPLAIN.

**Location**: `src/pg_mcp/security/explain_policy.py`

**Fields**:
```python
class ExplainPolicy:
    """Policy for query cost validation using EXPLAIN."""

    threshold: int
    """Complexity threshold to trigger EXPLAIN check."""

    max_cost: int
    """Maximum allowed query cost."""

    enabled: bool
    """Whether EXPLAIN policy is enabled."""
```

**Operations**:
```python
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
        tuple: (is_acceptable, actual_cost)

    Raises:
        DatabaseError: If EXPLAIN fails

    Process:
        1. Run EXPLAIN (FORMAT JSON) {sql}
        2. Parse JSON output
        3. Extract Total Cost from Plan
        4. Compare against max_cost
        5. Return result
    """

@classmethod
def from_config(cls, config: SecurityConfig) -> "ExplainPolicy":
    """Create policy from security configuration.

    Args:
        config: Security configuration

    Returns:
        ExplainPolicy instance
    """
```

**Cost Interpretation**:
- PostgreSQL costs are relative, not absolute
- Typical ranges:
  - Simple index lookup: 0-100
  - Small table scan: 100-1,000
  - Medium table scan: 1,000-10,000
  - Large table scan: 10,000-100,000
  - Complex joins: 100,000+

**Example Usage**:
```python
policy = ExplainPolicy(
    threshold=10000,
    max_cost=100000,
    enabled=True
)

# Check if EXPLAIN needed
if policy.should_explain(sql):
    is_acceptable, cost = await policy.validate_cost(conn, sql)
    if not is_acceptable:
        raise SecurityViolationError(
            f"Query cost ({cost}) exceeds maximum ({policy.max_cost})"
        )
```

---

### 4. MetricsCollector

**Purpose**: Centralized Prometheus metrics collection.

**Location**: `src/pg_mcp/observability/metrics.py`

**Metrics Definitions**:
```python
class MetricsCollector:
    """Centralized Prometheus metrics collector."""

    # Counter: Total query requests
    query_requests_total: Counter
    """
    Name: pg_mcp_query_requests_total
    Labels: database, status (started|success|error)
    Description: Total number of query requests
    """

    # Histogram: Query duration
    query_duration_seconds: Histogram
    """
    Name: pg_mcp_query_duration_seconds
    Labels: database, operation (generate|validate|execute)
    Buckets: (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
    Description: Query execution duration in seconds
    """

    # Gauge: Active database connections
    database_connections_active: Gauge
    """
    Name: pg_mcp_database_connections_active
    Labels: database
    Description: Number of active database connections
    """

    # Gauge: Rate limiter active requests
    rate_limiter_active_requests: Gauge
    """
    Name: pg_mcp_rate_limiter_active_requests
    Labels: none
    Description: Number of active requests in rate limiter
    """

    # Counter: Rate limiter rejections
    rate_limiter_rejections_total: Counter
    """
    Name: pg_mcp_rate_limiter_rejections_total
    Labels: none
    Description: Total number of rate limiter rejections
    """

    # Gauge: Circuit breaker state
    circuit_breaker_state: Gauge
    """
    Name: pg_mcp_circuit_breaker_state
    Labels: database, resource (database|llm)
    Values: 0=closed, 1=open, 2=half-open
    Description: Circuit breaker state
    """

    # Counter: Circuit breaker state changes
    circuit_breaker_state_changes_total: Counter
    """
    Name: pg_mcp_circuit_breaker_state_changes_total
    Labels: database, resource, from_state, to_state
    Description: Total number of circuit breaker state changes
    """

    # Histogram: LLM generation duration
    llm_generation_duration_seconds: Histogram
    """
    Name: pg_mcp_llm_generation_duration_seconds
    Labels: model
    Buckets: (0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0)
    Description: LLM SQL generation duration in seconds
    """

    # Counter: LLM tokens used
    llm_tokens_used_total: Counter
    """
    Name: pg_mcp_llm_tokens_used_total
    Labels: model, type (prompt|completion)
    Description: Total number of LLM tokens used
    """
```

**Operations**:
```python
def increment_counter(self, name: str, labels: dict[str, str], value: float = 1.0) -> None:
    """Increment counter metric."""

def observe_histogram(self, name: str, value: float, labels: dict[str, str]) -> None:
    """Record histogram observation."""

def set_gauge(self, name: str, value: float, labels: dict[str, str]) -> None:
    """Set gauge value."""

def start_timer(self, name: str, labels: dict[str, str]) -> Callable[[], None]:
    """Start timer for histogram metric.

    Returns:
        Callable that stops timer and records duration
    """
```

**Example Usage**:
```python
metrics = MetricsCollector()

# Increment counter
metrics.increment_counter(
    "query_requests_total",
    labels={"database": "mydb", "status": "started"}
)

# Observe histogram
metrics.observe_histogram(
    "query_duration_seconds",
    value=1.234,
    labels={"database": "mydb", "operation": "execute"}
)

# Set gauge
metrics.set_gauge(
    "database_connections_active",
    value=15,
    labels={"database": "mydb"}
)

# Use timer
stop_timer = metrics.start_timer(
    "query_duration_seconds",
    labels={"database": "mydb", "operation": "execute"}
)
# ... perform operation ...
stop_timer()  # Records duration
```

---

### 5. TracingContext

**Purpose**: Distributed tracing context management.

**Location**: `src/pg_mcp/observability/tracing.py`

**Fields**:
```python
class TracingContext:
    """Distributed tracing context for request tracking."""

    request_id: str
    """Unique request identifier (UUID)."""

    tracer: Tracer
    """OpenTelemetry tracer instance."""

    root_span: Span | None
    """Root span for the request."""

    _span_stack: list[Span]
    """Stack of active spans for nested operations."""
```

**Operations**:
```python
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

def end_span(self) -> None:
    """End the current span and pop from stack."""

def set_attribute(self, key: str, value: Any) -> None:
    """Set attribute on current span.

    Args:
        key: Attribute key (use dot notation, e.g., "db.statement")
        value: Attribute value
    """

def record_exception(self, exception: Exception) -> None:
    """Record exception on current span.

    Args:
        exception: Exception to record
    """

def set_status(self, status_code: StatusCode, description: str | None = None) -> None:
    """Set status on current span.

    Args:
        status_code: Status code (OK, ERROR)
        description: Optional status description
    """

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
```

**Span Hierarchy**:
```
query.execute (root)
├── sql.generate
│   └── llm.call
├── sql.validate
│   └── sql.parse
├── sql.execute
│   └── database.query
└── result.validate
    └── llm.call
```

**Standard Attributes**:
- Database operations: `db.system`, `db.name`, `db.statement`, `db.operation`
- LLM operations: `llm.model`, `llm.prompt_tokens`, `llm.completion_tokens`
- Custom: `pg_mcp.request_id`, `pg_mcp.confidence_score`, `pg_mcp.row_count`

**Example Usage**:
```python
tracing_ctx = TracingContext(request_id="123", tracer=tracer)

with tracing_ctx.span("query.execute") as span:
    span.set_attribute("question", question)
    span.set_attribute("database", database)

    with tracing_ctx.span("sql.generate", kind=SpanKind.CLIENT) as gen_span:
        gen_span.set_attribute("llm.model", "gemini-2.0-flash-exp")
        sql = await generate_sql(question)
        gen_span.set_attribute("sql_length", len(sql))

    with tracing_ctx.span("database.query", kind=SpanKind.CLIENT) as db_span:
        db_span.set_attribute("db.system", "postgresql")
        db_span.set_attribute("db.statement", sql)
        results = await execute_sql(sql)
        db_span.set_attribute("db.rows_returned", len(results))
```

---

## Configuration Extensions

### SecurityConfig Extensions

**New Fields** (to be added to `src/pg_mcp/config/settings.py`):
```python
class SecurityConfig(BaseSettings):
    # ... existing fields ...

    # Access Control
    allowed_tables: list[str] = Field(
        default_factory=list,
        description="Whitelist of allowed tables (empty = all allowed)"
    )

    blocked_tables: list[str] = Field(
        default_factory=list,
        description="Blacklist of blocked tables"
    )

    column_restrictions: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Table -> blocked columns mapping"
    )

    # EXPLAIN Policy
    explain_threshold: int = Field(
        default=10000,
        ge=0,
        le=1000000,
        description="Query complexity threshold for EXPLAIN"
    )

    max_query_cost: int = Field(
        default=100000,
        ge=0,
        le=10000000,
        description="Maximum allowed query cost"
    )

    explain_enabled: bool = Field(
        default=True,
        description="Enable EXPLAIN policy enforcement"
    )
```

### ResilienceConfig Extensions

**New Fields**:
```python
class ResilienceConfig(BaseSettings):
    # ... existing fields ...

    # Rate Limiting
    max_concurrent: int = Field(
        default=10,
        ge=1,
        le=1000,
        description="Maximum concurrent requests"
    )

    rate_limit_timeout: float = Field(
        default=30.0,
        ge=1.0,
        le=300.0,
        description="Rate limiter timeout in seconds"
    )
```

### ObservabilityConfig Extensions

**New Fields**:
```python
class ObservabilityConfig(BaseSettings):
    # ... existing fields ...

    # Tracing
    tracing_enabled: bool = Field(
        default=False,
        description="Enable distributed tracing"
    )

    tracing_endpoint: str = Field(
        default="",
        description="OTLP endpoint for traces (e.g., http://localhost:4317)"
    )

    tracing_sample_rate: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Trace sampling rate (0.0-1.0)"
    )

    # Metrics
    metrics_host: str = Field(
        default="0.0.0.0",
        description="Metrics server bind address"
    )
```

---

## Data Flow Diagrams

### Query Execution Flow with New Components

```
┌─────────────────┐
│  MCP Tool       │
│  Handler        │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Rate Limiter   │ ◄─── Metrics: active_requests
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Tracing        │ ◄─── Create root span
│  Context        │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Query          │
│  Orchestrator   │
└────────┬────────┘
         │
         ├─────────────────────┐
         │                     │
         ▼                     ▼
┌─────────────────┐   ┌─────────────────┐
│  SQL Generator  │   │  Executor       │
│  (with CB)      │   │  Registry       │
└────────┬────────┘   └────────┬────────┘
         │                     │
         ▼                     ▼
┌─────────────────┐   ┌─────────────────┐
│  SQL Validator  │   │  SQL Executor   │
│  + Access       │   │  (per DB)       │
│  Control        │   │  + Retry        │
│  + EXPLAIN      │   │  + CB           │
└─────────────────┘   └────────┬────────┘
                               │
                               ▼
                      ┌─────────────────┐
                      │  Database       │
                      │  Connection     │
                      │  Pool           │
                      └─────────────────┘

[Metrics Collection] ◄─── All components
[Distributed Tracing] ◄─── All components
```

---

## Summary

This data model design provides:

1. **ExecutorRegistry**: Per-database executor management with circuit breakers
2. **AccessControlPolicy**: Table/column access control enforcement
3. **ExplainPolicy**: Query cost validation using EXPLAIN
4. **MetricsCollector**: Centralized Prometheus metrics
5. **TracingContext**: Distributed tracing with OpenTelemetry

All entities are designed to integrate seamlessly with existing code while maintaining backward compatibility.

---

**Document Version**: 1.0
**Status**: Complete
**Next**: API Contracts Document
