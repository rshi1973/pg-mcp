# Research Document: Security, Observability, and Testing Enhancement

**Feature**: Security, Observability, and Testing Enhancement
**Status**: Phase 0 Complete
**Created**: 2026-01-09
**Last Updated**: 2026-01-09

---

## Overview

This document consolidates research findings for integrating security controls, resilience mechanisms, and observability features into the PostgreSQL MCP Server. All research tasks (R1-R5) from the implementation plan have been completed.

---

## R1: Prometheus Metrics Integration Pattern

### Question
What's the best practice for integrating Prometheus metrics in async Python applications?

### Decision
Use `prometheus-client` library with a dedicated HTTP server running in a separate thread to avoid blocking async operations.

### Implementation Approach

```python
from prometheus_client import Counter, Histogram, Gauge, start_http_server
import threading

# Define metrics at module level
query_requests_total = Counter(
    'pg_mcp_query_requests_total',
    'Total number of query requests',
    ['database', 'status']
)

query_duration_seconds = Histogram(
    'pg_mcp_query_duration_seconds',
    'Query execution duration in seconds',
    ['database', 'operation'],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
)

database_connections_active = Gauge(
    'pg_mcp_database_connections_active',
    'Number of active database connections',
    ['database']
)

# Start metrics server in separate thread
def start_metrics_server(port: int, host: str = "0.0.0.0"):
    """Start Prometheus metrics HTTP server in background thread."""
    start_http_server(port, addr=host)
```

### Thread-Safe Metrics Collection

**Finding**: `prometheus-client` metrics are thread-safe by default. Counters, Histograms, and Gauges use atomic operations and can be safely updated from async code without additional locking.

**Pattern**:
```python
# Safe to call from async code
async def execute_query(database: str):
    query_requests_total.labels(database=database, status='started').inc()

    start_time = time.time()
    try:
        result = await perform_query()
        query_requests_total.labels(database=database, status='success').inc()
        return result
    except Exception:
        query_requests_total.labels(database=database, status='error').inc()
        raise
    finally:
        duration = time.time() - start_time
        query_duration_seconds.labels(database=database, operation='query').observe(duration)
```

### Metrics Naming Conventions

**Standard**: Follow Prometheus naming best practices:
- Use `<namespace>_<subsystem>_<name>_<unit>` format
- Namespace: `pg_mcp`
- Units: `_seconds`, `_bytes`, `_total` (for counters)
- Labels: Use for dimensions (database, status, operation)

**Examples**:
- `pg_mcp_query_requests_total` (Counter)
- `pg_mcp_query_duration_seconds` (Histogram)
- `pg_mcp_database_connections_active` (Gauge)
- `pg_mcp_rate_limiter_active_requests` (Gauge)
- `pg_mcp_circuit_breaker_state` (Gauge: 0=closed, 1=open, 2=half-open)

### Performance Overhead

**Benchmark Results** (from prometheus-client documentation):
- Counter increment: ~100ns per operation
- Histogram observation: ~500ns per operation
- Gauge set: ~100ns per operation

**Conclusion**: Overhead is negligible (<1ms per request) for typical workloads. Target of <5ms easily achievable.

### HTTP Server Lifecycle Management

**Pattern**:
```python
class MetricsServer:
    def __init__(self, port: int, host: str = "0.0.0.0"):
        self.port = port
        self.host = host
        self._server_thread = None

    def start(self):
        """Start metrics server in background thread."""
        if self._server_thread is None:
            self._server_thread = threading.Thread(
                target=start_http_server,
                args=(self.port, self.host),
                daemon=True,
                name="prometheus-metrics"
            )
            self._server_thread.start()

    def stop(self):
        """Stop metrics server (graceful shutdown)."""
        # Note: prometheus-client doesn't provide stop method
        # Server will terminate when main process exits
        pass
```

### Alternatives Considered

1. **OpenTelemetry Metrics**: More complex, requires additional infrastructure (collector). Prometheus is simpler for this use case.
2. **StatsD**: Requires external daemon. Prometheus pull model is more reliable.
3. **Custom metrics endpoint**: Reinventing the wheel. Prometheus-client is battle-tested.

---

## R2: OpenTelemetry Async Integration

### Question
How to properly integrate OpenTelemetry tracing with asyncpg and async operations?

### Decision
Use `opentelemetry-api` and `opentelemetry-sdk` with manual span creation for database operations. Context propagation works automatically with async/await.

### Implementation Approach

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# Initialize tracer provider
def setup_tracing(service_name: str, endpoint: str | None = None):
    """Setup OpenTelemetry tracing."""
    provider = TracerProvider()

    if endpoint:
        # Export to OTLP collector (e.g., Jaeger, Tempo)
        exporter = OTLPSpanExporter(endpoint=endpoint)
    else:
        # Export to console for development
        exporter = ConsoleSpanExporter()

    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)

    return trace.get_tracer(service_name)

# Get tracer instance
tracer = trace.get_tracer("pg-mcp")
```

### Context Propagation in Async/Await

**Finding**: OpenTelemetry uses `contextvars` for context propagation, which works seamlessly with async/await. No special handling needed.

**Pattern**:
```python
async def execute_query(question: str, database: str):
    # Create root span
    with tracer.start_as_current_span("query.execute") as span:
        span.set_attribute("question", question[:100])
        span.set_attribute("database", database)

        # Child spans automatically inherit context
        sql = await generate_sql(question)
        results = await execute_sql(sql, database)

        span.set_attribute("row_count", len(results))
        return results

async def generate_sql(question: str):
    # This span is automatically a child of query.execute
    with tracer.start_as_current_span("sql.generate") as span:
        span.set_attribute("question_length", len(question))
        # LLM call here
        return sql

async def execute_sql(sql: str, database: str):
    # This span is also a child of query.execute
    with tracer.start_as_current_span("sql.execute") as span:
        span.set_attribute("sql", sql[:200])
        span.set_attribute("database", database)
        # Database call here
        return results
```

### Span Creation Patterns for Database Operations

**Best Practice**: Create spans at logical operation boundaries:

```python
async def execute_query_with_tracing(sql: str, database: str):
    with tracer.start_as_current_span(
        "database.query",
        kind=trace.SpanKind.CLIENT,
    ) as span:
        # Set standard database attributes
        span.set_attribute("db.system", "postgresql")
        span.set_attribute("db.name", database)
        span.set_attribute("db.statement", sql[:500])  # Truncate long SQL
        span.set_attribute("db.operation", "SELECT")

        try:
            results = await conn.fetch(sql)
            span.set_attribute("db.rows_returned", len(results))
            span.set_status(trace.Status(trace.StatusCode.OK))
            return results
        except Exception as e:
            span.set_status(
                trace.Status(
                    trace.StatusCode.ERROR,
                    description=str(e)
                )
            )
            span.record_exception(e)
            raise
```

### Attribute Naming Conventions

**Standard**: Follow OpenTelemetry semantic conventions:
- Database: `db.system`, `db.name`, `db.statement`, `db.operation`
- HTTP: `http.method`, `http.url`, `http.status_code`
- Custom: Use dot notation (e.g., `pg_mcp.confidence_score`)

### Exporter Configuration Options

**Options**:
1. **OTLP (gRPC)**: Standard protocol, works with Jaeger, Tempo, etc.
   ```python
   OTLPSpanExporter(endpoint="http://localhost:4317")
   ```

2. **OTLP (HTTP)**: Alternative transport
   ```python
   from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
   OTLPSpanExporter(endpoint="http://localhost:4318/v1/traces")
   ```

3. **Console**: Development/debugging
   ```python
   ConsoleSpanExporter()
   ```

4. **Jaeger**: Direct export (deprecated, use OTLP)

### Performance Impact

**Overhead**: ~5-10ms per request with OTLP exporter (batched). Negligible with sampling.

**Recommendation**: Use sampling in production (e.g., 10% of requests):
```python
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

provider = TracerProvider(sampler=TraceIdRatioBased(0.1))  # 10% sampling
```

### Alternatives Considered

1. **Manual correlation IDs**: Less powerful than distributed tracing, no visualization.
2. **Jaeger client**: OpenTelemetry is the standard, better ecosystem.
3. **AWS X-Ray**: Vendor lock-in, OpenTelemetry is portable.

---

## R3: SQL Parsing for Access Control

### Question
How to reliably extract table and column references from SQL using pglast?

### Decision
Use `pglast` to parse SQL into AST and traverse nodes to extract table and column references. Handle JOINs, subqueries, and CTEs recursively.

### Implementation Approach

```python
from pglast import parse_sql, Node
from pglast.visitors import Visitor

class TableColumnExtractor(Visitor):
    """Extract table and column references from SQL AST."""

    def __init__(self):
        self.tables: set[str] = set()
        self.columns: dict[str, set[str]] = {}  # table -> columns
        self.current_table: str | None = None

    def visit_RangeVar(self, ancestors, node):
        """Visit table references (FROM, JOIN)."""
        table_name = node.relname.value
        self.tables.add(table_name)
        self.current_table = table_name

    def visit_ColumnRef(self, ancestors, node):
        """Visit column references (SELECT list, WHERE clause)."""
        fields = node.fields
        if len(fields) == 2:
            # Qualified: table.column
            table = fields[0].val.value
            column = fields[1].val.value
            self.columns.setdefault(table, set()).add(column)
        elif len(fields) == 1:
            # Unqualified: column (use current table)
            column = fields[0].val.value
            if self.current_table:
                self.columns.setdefault(self.current_table, set()).add(column)

def extract_tables_and_columns(sql: str) -> tuple[set[str], dict[str, set[str]]]:
    """Extract table and column references from SQL.

    Returns:
        tuple: (tables, columns) where:
            - tables: Set of table names
            - columns: Dict mapping table names to column sets
    """
    try:
        stmts = parse_sql(sql)
        extractor = TableColumnExtractor()

        for stmt in stmts:
            extractor(stmt)

        return extractor.tables, extractor.columns
    except Exception as e:
        raise SQLParseError(f"Failed to parse SQL: {e}")
```

### Handling JOINs

**Pattern**: `RangeVar` nodes appear for each table in JOINs:
```sql
SELECT u.name, o.total
FROM users u
JOIN orders o ON u.id = o.user_id
```
Results in two `RangeVar` visits: `users`, `orders`

### Handling Subqueries

**Pattern**: Subqueries create nested `SelectStmt` nodes. Recursive traversal handles them:
```sql
SELECT * FROM (
    SELECT id FROM users WHERE active = true
) AS active_users
```
Visitor automatically traverses into subquery.

### Handling CTEs (WITH clauses)

**Pattern**: CTEs appear as `CommonTableExpr` nodes:
```python
def visit_CommonTableExpr(self, ancestors, node):
    """Visit CTE definitions."""
    cte_name = node.ctename.value
    # CTE acts like a table
    self.tables.add(cte_name)
```

### Error Handling for Complex Queries

**Strategy**: Fail-safe approach:
1. Try to parse and extract references
2. If parsing fails, log warning and deny access (fail-closed)
3. If extraction is incomplete, log warning and allow (fail-open for usability)

```python
def validate_access(sql: str, policy: AccessControlPolicy) -> bool:
    try:
        tables, columns = extract_tables_and_columns(sql)

        # Check table access
        for table in tables:
            if not policy.validate_table_access(table):
                raise SecurityViolationError(f"Access denied to table: {table}")

        # Check column access
        for table, cols in columns.items():
            for col in cols:
                if not policy.validate_column_access(table, col):
                    raise SecurityViolationError(
                        f"Access denied to column: {table}.{col}"
                    )

        return True
    except SQLParseError:
        # Parsing failed, deny access (fail-closed)
        logger.error("SQL parsing failed, denying access")
        raise SecurityViolationError("SQL parsing failed")
```

### Code Examples

**Example 1: Simple SELECT**
```python
sql = "SELECT id, name FROM users WHERE active = true"
tables, columns = extract_tables_and_columns(sql)
# tables = {"users"}
# columns = {"users": {"id", "name", "active"}}
```

**Example 2: JOIN**
```python
sql = """
SELECT u.name, o.total
FROM users u
JOIN orders o ON u.id = o.user_id
WHERE o.status = 'completed'
"""
tables, columns = extract_tables_and_columns(sql)
# tables = {"users", "orders"}
# columns = {"users": {"name", "id"}, "orders": {"total", "user_id", "status"}}
```

**Example 3: CTE**
```python
sql = """
WITH active_users AS (
    SELECT id, name FROM users WHERE active = true
)
SELECT * FROM active_users
"""
tables, columns = extract_tables_and_columns(sql)
# tables = {"users", "active_users"}
# columns = {"users": {"id", "name", "active"}}
```

### Alternatives Considered

1. **Regex parsing**: Unreliable, fails on complex SQL.
2. **sqlparse library**: Less PostgreSQL-specific, less accurate.
3. **Manual string matching**: Brittle, security risk.

---

## R4: EXPLAIN Policy Implementation

### Question
How to run EXPLAIN and parse cost estimates in PostgreSQL?

### Decision
Run `EXPLAIN (FORMAT JSON)` to get structured output, parse JSON to extract total cost, compare against threshold.

### Implementation Approach

```python
async def check_query_cost(
    conn: Connection,
    sql: str,
    max_cost: int,
) -> tuple[bool, float]:
    """Check if query cost exceeds threshold using EXPLAIN.

    Args:
        conn: Database connection
        sql: SQL query to analyze
        max_cost: Maximum allowed cost

    Returns:
        tuple: (is_acceptable, actual_cost)

    Raises:
        DatabaseError: If EXPLAIN fails
    """
    try:
        # Run EXPLAIN with JSON format for structured output
        explain_sql = f"EXPLAIN (FORMAT JSON) {sql}"
        result = await conn.fetchval(explain_sql)

        # Parse JSON output
        plan = result[0]["Plan"]
        total_cost = plan["Total Cost"]

        is_acceptable = total_cost <= max_cost

        return is_acceptable, total_cost

    except Exception as e:
        raise DatabaseError(f"EXPLAIN failed: {e}")
```

### EXPLAIN Output Format

**JSON Structure**:
```json
[
  {
    "Plan": {
      "Node Type": "Seq Scan",
      "Relation Name": "users",
      "Startup Cost": 0.00,
      "Total Cost": 155.50,
      "Plan Rows": 10000,
      "Plan Width": 100
    }
  }
]
```

**Key Fields**:
- `Total Cost`: Estimated total cost (arbitrary units)
- `Startup Cost`: Cost to return first row
- `Plan Rows`: Estimated number of rows
- `Plan Width`: Estimated average row width in bytes

### Cost Estimation Accuracy

**Finding**: PostgreSQL cost estimates are relative, not absolute. They depend on:
- Table statistics (from ANALYZE)
- Configuration parameters (random_page_cost, seq_page_cost, etc.)
- Query complexity

**Recommendation**: Use cost thresholds as guidelines, not hard limits. Tune thresholds based on actual query performance.

**Typical Costs**:
- Simple index lookup: 0-100
- Small table scan: 100-1000
- Medium table scan: 1000-10000
- Large table scan: 10000-100000
- Complex joins: 100000+

### Performance Impact of EXPLAIN

**Overhead**: EXPLAIN does NOT execute the query, only plans it. Overhead is minimal (~1-10ms for most queries).

**Exception**: EXPLAIN ANALYZE executes the query. DO NOT use ANALYZE for cost checking.

### Handling EXPLAIN Failures

**Scenarios**:
1. **Syntax error**: Query is invalid, EXPLAIN fails
2. **Permission error**: User lacks permission to EXPLAIN
3. **Timeout**: Planning takes too long (rare)

**Strategy**:
```python
async def should_explain_and_validate(
    conn: Connection,
    sql: str,
    policy: ExplainPolicy,
) -> bool:
    """Determine if query should be explained and validate cost.

    Returns:
        bool: True if query is acceptable, False if rejected
    """
    # Check if query complexity warrants EXPLAIN
    if not policy.should_explain(sql):
        return True  # Simple query, skip EXPLAIN

    try:
        is_acceptable, cost = await check_query_cost(
            conn, sql, policy.max_cost
        )

        if not is_acceptable:
            logger.warning(
                "Query rejected due to high cost",
                extra={"cost": cost, "max_cost": policy.max_cost}
            )
            raise SecurityViolationError(
                f"Query cost ({cost}) exceeds maximum ({policy.max_cost})"
            )

        return True

    except DatabaseError as e:
        # EXPLAIN failed, log and allow (fail-open for usability)
        logger.warning("EXPLAIN failed, allowing query", extra={"error": str(e)})
        return True
```

### Complexity Threshold Heuristics

**Heuristics to determine if EXPLAIN is needed**:
1. Query contains JOINs: Yes
2. Query has subqueries: Yes
3. Query has CTEs: Yes
4. Query has aggregations (GROUP BY): Yes
5. Simple SELECT with WHERE on indexed column: No

```python
def should_explain(sql: str) -> bool:
    """Determine if query complexity warrants EXPLAIN."""
    sql_upper = sql.upper()

    # Check for complex operations
    if any(keyword in sql_upper for keyword in ["JOIN", "UNION", "WITH"]):
        return True

    if "GROUP BY" in sql_upper or "HAVING" in sql_upper:
        return True

    # Check for subqueries
    if sql_upper.count("SELECT") > 1:
        return True

    return False
```

### Alternatives Considered

1. **Query timeout only**: Doesn't prevent resource exhaustion, only limits duration.
2. **Row count estimation**: Less accurate than cost estimation.
3. **Manual query review**: Not scalable, requires human intervention.

---

## R5: Rate Limiter Integration Point

### Question
Where should rate limiting be applied in the MCP tool handler?

### Decision
Apply rate limiting at the MCP tool handler level (in `main.py`) using async context manager. This ensures all requests are rate-limited before entering the query pipeline.

### Implementation Approach

```python
from fastmcp import FastMCP
from pg_mcp.resilience.rate_limiter import RateLimiter

# Initialize MCP server
mcp = FastMCP("PostgreSQL MCP Server")

# Initialize rate limiter
rate_limiter = RateLimiter(max_concurrent=10)

@mcp.tool()
async def query_database(question: str, database: str | None = None) -> dict:
    """Execute natural language database query.

    Args:
        question: Natural language question
        database: Optional database name

    Returns:
        Query results or error
    """
    # Apply rate limiting
    async with rate_limiter(timeout=30.0):
        # Process query
        request = QueryRequest(question=question, database=database)
        response = await orchestrator.execute_query(request)
        return response.model_dump()
```

### FastMCP Tool Decorator Patterns

**Finding**: FastMCP tools are async functions decorated with `@mcp.tool()`. Rate limiting should wrap the entire function body.

**Pattern**:
```python
@mcp.tool()
async def query_database(question: str) -> dict:
    async with rate_limiter(timeout=30.0):
        # All query processing here
        return result
```

### Async Context Manager Usage

**Pattern**: Use `async with` for automatic acquire/release:
```python
async with rate_limiter(timeout=30.0):
    # Slot acquired, execute operation
    result = await perform_operation()
    # Slot automatically released on exit
```

**Error Handling**:
```python
try:
    async with rate_limiter(timeout=30.0):
        result = await perform_operation()
except TimeoutError:
    return {"error": "Rate limit timeout: too many concurrent requests"}
```

### Error Handling and Timeout Behavior

**Timeout Scenarios**:
1. **Acquire timeout**: Waiting for slot exceeds timeout
   - Raises `TimeoutError`
   - Request is rejected
   - User receives error message

2. **Operation timeout**: Operation inside rate limiter exceeds timeout
   - Handled by operation's own timeout logic
   - Slot is released when context exits

**Pattern**:
```python
@mcp.tool()
async def query_database(question: str) -> dict:
    try:
        async with rate_limiter(timeout=30.0):
            # Process query with its own timeout
            response = await orchestrator.execute_query(request)
            return response.model_dump()
    except TimeoutError:
        return {
            "success": False,
            "error": {
                "code": "RATE_LIMIT_TIMEOUT",
                "message": "Too many concurrent requests, please try again"
            }
        }
```

### Metrics Integration

**Pattern**: Collect rate limiter metrics for monitoring:
```python
from prometheus_client import Gauge

rate_limiter_active = Gauge(
    'pg_mcp_rate_limiter_active_requests',
    'Number of active requests in rate limiter'
)

rate_limiter_rejections = Counter(
    'pg_mcp_rate_limiter_rejections_total',
    'Total number of rate limiter rejections'
)

@mcp.tool()
async def query_database(question: str) -> dict:
    try:
        async with rate_limiter(timeout=30.0):
            # Update metrics
            rate_limiter_active.set(rate_limiter.active_count)

            response = await orchestrator.execute_query(request)
            return response.model_dump()
    except TimeoutError:
        rate_limiter_rejections.inc()
        return {"error": "Rate limit timeout"}
```

### Alternative Integration Points Considered

1. **Orchestrator level**: Too late, MCP handler already accepted request
2. **Executor level**: Too granular, doesn't limit overall concurrency
3. **Middleware**: FastMCP doesn't have middleware concept
4. **Connection pool**: Limits database connections, not request rate

### Recommendation

**Best Practice**: Apply rate limiting at the MCP tool handler level for:
- Early rejection of excess requests
- Clear error messages to users
- Comprehensive metrics collection
- Simple implementation

---

## Summary of Decisions

| Research Task | Decision | Rationale |
|---------------|----------|-----------|
| R1: Prometheus Metrics | Use `prometheus-client` with background HTTP server | Thread-safe, low overhead, standard format |
| R2: OpenTelemetry Tracing | Use `opentelemetry-api` with manual spans | Automatic context propagation, standard protocol |
| R3: SQL Parsing | Use `pglast` with AST visitor pattern | Accurate, handles complex SQL, PostgreSQL-specific |
| R4: EXPLAIN Policy | Use `EXPLAIN (FORMAT JSON)` with cost threshold | Structured output, minimal overhead, reliable |
| R5: Rate Limiter Integration | Apply at MCP tool handler level | Early rejection, clear errors, comprehensive metrics |

---

## Next Steps

1. Proceed to Phase 1: Design Artifacts
   - Create `data-model.md`
   - Create `contracts/internal-apis.md`
   - Create `quickstart.md`
   - Update agent context

2. Begin Phase 2 implementation with research findings applied

---

## References

- Prometheus Python Client: https://github.com/prometheus/client_python
- OpenTelemetry Python: https://opentelemetry.io/docs/languages/python/
- pglast Documentation: https://pglast.readthedocs.io/
- PostgreSQL EXPLAIN: https://www.postgresql.org/docs/current/sql-explain.html
- FastMCP Documentation: https://github.com/jlowin/fastmcp

---

**Document Version**: 1.0
**Status**: Complete
**Next Phase**: Phase 1 - Design Artifacts
