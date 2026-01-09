# Feature Specification: Fix Security, Observability, and Testing Gaps

**Feature Name**: Security, Observability, and Testing Enhancement
**Status**: Draft
**Created**: 2026-01-09
**Last Updated**: 2026-01-09

---

## Executive Summary

The PostgreSQL MCP Server currently has critical gaps between its design promises and actual implementation. While the codebase includes well-designed modules for multi-database security controls, resilience mechanisms, and observability features, these components are not fully integrated into the request processing pipeline. This specification addresses three major categories of issues:

1. **Multi-database & Security Control**: Database-specific executors and access restrictions are not enforced
2. **Resilience & Observability**: Rate limiting, retry mechanisms, and metrics/tracing are not integrated into request flow
3. **Code Quality & Testing**: Duplicate methods, unused configuration fields, and insufficient test coverage

---

## Problem Statement

### Current State

The system has the following architectural gaps:

**Security & Access Control**:
- Server always uses a single executor instance regardless of database selection
- Table/column-level access restrictions are not enforced
- EXPLAIN policy enforcement is not implemented
- Security configuration exists but is not fully utilized during query execution

**Resilience & Observability**:
- Rate limiting module (`RateLimiter`) exists but is not applied to incoming requests
- Retry/backoff mechanisms only apply to SQL generation, not database operations
- Circuit breaker only protects LLM calls, not database connections
- Metrics and tracing modules are defined but not integrated into the request pipeline

**Code Quality**:
- Duplicate `to_dict()` methods in `QueryResponse` (lines 160 and 214 in `models/query.py`)
- Duplicate `to_dict()` method in `QueryResult` (line 130)
- Configuration fields defined but not actively used in request processing
- Test coverage exists (235 test files) but may not validate actual system behavior against design specifications

### Impact

These gaps create the following risks:

- **Security Risk**: Users may access databases, tables, or columns they shouldn't have permission to access
- **Reliability Risk**: System lacks protection against request floods, database connection exhaustion, and cascading failures
- **Operational Risk**: Lack of metrics and tracing makes it difficult to diagnose issues and monitor system health
- **Maintenance Risk**: Code duplication and unused configuration increase technical debt and confusion

---

## Goals and Success Criteria

### Goals

1. **Enforce Multi-Database Security**: Ensure each database request uses the correct executor with appropriate access controls
2. **Integrate Resilience Mechanisms**: Apply rate limiting, retry logic, and circuit breakers throughout the request pipeline
3. **Enable Observability**: Integrate metrics collection and tracing into all critical operations
4. **Improve Code Quality**: Remove duplications, activate unused configurations, and enhance test coverage

### Success Criteria

1. **Security Enforcement**:
   - Each database query uses a database-specific executor with configured security policies
   - Table/column access restrictions are validated before query execution
   - EXPLAIN policies are enforced for complex queries
   - Security violations are logged and blocked with appropriate error messages

2. **Resilience Integration**:
   - Rate limiting is applied to all incoming query requests
   - Concurrent request limits are enforced per database
   - Retry logic with exponential backoff is applied to transient database failures
   - Circuit breakers protect both LLM and database operations

3. **Observability Activation**:
   - Request metrics (count, latency, errors) are collected and exposed
   - Database operation metrics (query time, connection pool status) are tracked
   - Distributed tracing spans cover the entire request lifecycle
   - Metrics endpoint is accessible for monitoring systems

4. **Code Quality**:
   - No duplicate method definitions exist in response models
   - All configuration fields are either used or removed
   - Test coverage validates actual system behavior matches design specifications
   - Integration tests verify security, resilience, and observability features work end-to-end

---

## User Scenarios

### Scenario 1: Multi-Database Query with Access Control

**Actor**: Data Analyst using Claude Desktop with MCP

**Flow**:
1. Analyst asks: "Show me user data from the production database"
2. System validates analyst has access to production database
3. System checks table-level permissions for `users` table
4. System validates column-level access (e.g., cannot access `password_hash` column)
5. System generates SQL excluding restricted columns
6. System executes query using production-specific executor with read-only role
7. System returns results with only permitted columns

**Expected Outcome**: Query succeeds with only authorized data returned, or fails with clear permission error

### Scenario 2: Request Flood Protection

**Actor**: Multiple concurrent users or automated scripts

**Flow**:
1. System receives 50 concurrent query requests
2. Rate limiter allows only 10 concurrent requests (configured limit)
3. Remaining 40 requests wait in queue with timeout
4. As requests complete, queued requests are processed
5. Requests exceeding timeout receive rate limit error

**Expected Outcome**: System remains stable, database connections don't exhaust, and users receive appropriate feedback

### Scenario 3: Database Connection Failure Recovery

**Actor**: System Administrator monitoring production

**Flow**:
1. Database connection pool experiences transient network issue
2. Query execution fails with connection error
3. Circuit breaker detects failure pattern
4. System retries query with exponential backoff (1s, 2s, 4s)
5. Connection recovers on second retry
6. Query succeeds and circuit breaker records success
7. Metrics show retry count and recovery time

**Expected Outcome**: Transient failures are automatically recovered without user intervention

### Scenario 4: Performance Monitoring

**Actor**: DevOps Engineer monitoring system health

**Flow**:
1. Engineer accesses metrics endpoint at `/metrics`
2. Metrics show:
   - Request rate: 45 requests/minute
   - Average query latency: 250ms
   - Database connection pool: 8/20 connections active
   - Circuit breaker state: CLOSED (healthy)
   - Rate limiter: 3 requests queued
3. Engineer sets up alerts for latency > 1s or circuit breaker OPEN state

**Expected Outcome**: Complete visibility into system health and performance

---

## Functional Requirements

### FR1: Database-Specific Executor Management

**Priority**: High
**Category**: Security

1. System SHALL maintain a separate `SQLExecutor` instance for each configured database
2. System SHALL select the correct executor based on the `database` field in `QueryRequest`
3. Each executor SHALL be initialized with database-specific security configuration
4. System SHALL validate database access permissions before query execution

**Acceptance Criteria**:
- `QueryOrchestrator` maintains a `dict[str, SQLExecutor]` mapping database names to executors
- Executor selection logic validates database name and retrieves correct instance
- Each executor uses database-specific `SecurityConfig` and `DatabaseConfig`
- Attempting to access unauthorized database returns `DatabaseError` with code `ACCESS_DENIED`

### FR2: Table and Column Access Control

**Priority**: High
**Category**: Security

1. System SHALL support configuration of allowed/blocked tables per database
2. System SHALL support configuration of allowed/blocked columns per table
3. System SHALL validate generated SQL against access control rules before execution
4. System SHALL reject queries accessing restricted tables or columns with `SecurityViolationError`

**Acceptance Criteria**:
- `SecurityConfig` includes `allowed_tables: list[str]` and `blocked_tables: list[str]`
- `SecurityConfig` includes `column_restrictions: dict[str, list[str]]` mapping tables to blocked columns
- `SQLValidator` parses SQL to extract referenced tables and columns
- Validation fails if SQL references blocked tables or columns
- Error message clearly indicates which table/column caused the violation

### FR3: EXPLAIN Policy Enforcement

**Priority**: Medium
**Category**: Security

1. System SHALL support configuration of query complexity thresholds
2. System SHALL run EXPLAIN on queries exceeding complexity threshold
3. System SHALL reject queries with estimated cost above configured limit
4. System SHALL log EXPLAIN results for audit purposes

**Acceptance Criteria**:
- `SecurityConfig` includes `explain_threshold: int` (default: 10000) and `max_query_cost: int`
- `SQLExecutor` runs `EXPLAIN` before executing queries with multiple JOINs or subqueries
- Queries with estimated cost > `max_query_cost` are rejected with `QueryTooExpensiveError`
- EXPLAIN results are logged at DEBUG level with request_id for tracing

### FR4: Request Rate Limiting

**Priority**: High
**Category**: Resilience

1. System SHALL limit concurrent requests using the existing `RateLimiter` class
2. System SHALL apply rate limiting at the MCP tool entry point
3. System SHALL return appropriate error when rate limit is exceeded
4. System SHALL expose rate limiter statistics via metrics

**Acceptance Criteria**:
- MCP tool handler wraps query execution with `async with rate_limiter(timeout=30.0)`
- Rate limit is configurable via `RESILIENCE_MAX_CONCURRENT` environment variable
- Requests exceeding limit receive `RateLimitExceededError` with retry-after information
- Metrics include `rate_limiter_active_requests` and `rate_limiter_rejections_total`

### FR5: Database Operation Retry Logic

**Priority**: High
**Category**: Resilience

1. System SHALL retry database operations on transient failures
2. System SHALL use exponential backoff between retry attempts
3. System SHALL respect configured maximum retry attempts
4. System SHALL distinguish between transient and permanent failures

**Acceptance Criteria**:
- `SQLExecutor.execute()` wraps database calls with retry logic
- Transient errors (connection timeout, connection reset) trigger retry
- Permanent errors (syntax error, permission denied) do not trigger retry
- Retry delays follow pattern: `retry_delay * (backoff_factor ** attempt)`
- Maximum retries controlled by `ResilienceConfig.max_retries`

### FR6: Circuit Breaker for Database Operations

**Priority**: Medium
**Category**: Resilience

1. System SHALL apply circuit breaker pattern to database connection pools
2. System SHALL track failure rates per database
3. System SHALL open circuit after threshold failures
4. System SHALL attempt recovery after timeout period

**Acceptance Criteria**:
- Each database pool has an associated `CircuitBreaker` instance
- Circuit breaker tracks failures in `SQLExecutor.execute()`
- Circuit opens after `circuit_breaker_threshold` consecutive failures
- Circuit remains open for `circuit_breaker_timeout` seconds
- Circuit state is exposed via metrics: `circuit_breaker_state{database="name"}`

### FR7: Metrics Collection and Exposure

**Priority**: High
**Category**: Observability

1. System SHALL collect metrics for all critical operations
2. System SHALL expose metrics in Prometheus format
3. System SHALL include request, database, and LLM metrics
4. System SHALL serve metrics on configured HTTP port

**Acceptance Criteria**:
- Metrics include:
  - `query_requests_total{database, status}` - Counter
  - `query_duration_seconds{database, operation}` - Histogram
  - `database_connections_active{database}` - Gauge
  - `llm_requests_total{model, status}` - Counter
  - `rate_limiter_active_requests` - Gauge
  - `circuit_breaker_state{database}` - Gauge (0=closed, 1=open, 2=half-open)
- Metrics endpoint accessible at `http://localhost:{metrics_port}/metrics`
- Metrics collection has minimal performance overhead (< 5ms per request)

### FR8: Distributed Tracing Integration

**Priority**: Medium
**Category**: Observability

1. System SHALL create trace spans for each request phase
2. System SHALL propagate trace context through async operations
3. System SHALL include relevant attributes in spans
4. System SHALL support OpenTelemetry-compatible tracing

**Acceptance Criteria**:
- Root span created for each MCP tool invocation with `request_id`
- Child spans created for: schema loading, SQL generation, SQL validation, SQL execution, result validation
- Spans include attributes: `database`, `question_length`, `sql_length`, `row_count`, `error_code`
- Tracing can be enabled/disabled via `OBSERVABILITY_TRACING_ENABLED` config
- Trace exporter is configurable (OTLP, Jaeger, etc.)

### FR9: Code Quality Improvements

**Priority**: Medium
**Category**: Maintenance

1. System SHALL remove duplicate `to_dict()` method definitions
2. System SHALL activate or remove unused configuration fields
3. System SHALL ensure all public methods have type annotations
4. System SHALL maintain consistent error handling patterns

**Acceptance Criteria**:
- Only one `to_dict()` method exists in `QueryResponse` class
- Only one `to_dict()` method exists in `QueryResult` class
- All configuration fields in `SecurityConfig`, `ResilienceConfig`, and `ObservabilityConfig` are actively used
- Unused fields are removed with deprecation notice in changelog
- All public methods have complete type hints
- All custom exceptions inherit from `PgMcpError` base class

### FR10: Enhanced Test Coverage

**Priority**: High
**Category**: Quality Assurance

1. System SHALL include integration tests for security features
2. System SHALL include integration tests for resilience features
3. System SHALL include integration tests for observability features
4. System SHALL validate actual behavior matches design specifications

**Acceptance Criteria**:
- Test suite includes:
  - `test_multi_database_executor_selection()` - Validates correct executor is used
  - `test_table_column_access_control()` - Validates access restrictions work
  - `test_rate_limiting_enforcement()` - Validates concurrent request limits
  - `test_database_retry_logic()` - Validates retry on transient failures
  - `test_circuit_breaker_protection()` - Validates circuit breaker opens/closes
  - `test_metrics_collection()` - Validates metrics are collected and exposed
  - `test_tracing_spans()` - Validates trace spans are created correctly
- Test coverage for security, resilience, and observability modules >= 90%
- Integration tests run against real PostgreSQL instance (using testcontainers or similar)
- All tests pass in CI/CD pipeline

---

## Non-Functional Requirements

### Performance

1. Rate limiting overhead SHALL NOT exceed 5ms per request
2. Metrics collection overhead SHALL NOT exceed 5ms per request
3. Tracing overhead (when enabled) SHALL NOT exceed 10ms per request
4. Circuit breaker state check SHALL complete in < 1ms

### Scalability

1. System SHALL support at least 5 concurrent databases
2. System SHALL handle at least 100 concurrent requests (with rate limiting)
3. Metrics storage SHALL NOT exceed 100MB memory footprint
4. Schema cache SHALL support at least 100 database schemas

### Reliability

1. System SHALL recover from transient database failures within 10 seconds
2. Circuit breaker SHALL prevent cascading failures
3. Rate limiting SHALL prevent resource exhaustion
4. System SHALL maintain 99.9% uptime for non-database-related failures

### Security

1. Access control validation SHALL occur before SQL execution
2. Security violations SHALL be logged with full context
3. Sensitive data (passwords, API keys) SHALL NOT appear in logs or metrics
4. Database credentials SHALL be stored securely (environment variables or secrets manager)

### Observability

1. All errors SHALL be logged with structured context (request_id, database, error_code)
2. Metrics SHALL be updated in real-time (< 1 second delay)
3. Trace spans SHALL include all relevant attributes for debugging
4. Logs SHALL use consistent format (JSON in production, text in development)

---

## Technical Considerations

### Architecture Changes

**Current Architecture**:
```
MCP Tool → QueryOrchestrator → Single SQLExecutor → Database
```

**Proposed Architecture**:
```
MCP Tool → RateLimiter → QueryOrchestrator → Database-Specific SQLExecutor → CircuitBreaker → Database
                ↓                    ↓                      ↓
            Metrics            Tracing Spans          Retry Logic
```

### Key Components to Modify

1. **`main.py`** (MCP Tool Handler):
   - Add rate limiter initialization
   - Wrap query execution with rate limiting
   - Initialize metrics server

2. **`services/orchestrator.py`**:
   - Change `self.sql_executor` to `self.executors: dict[str, SQLExecutor]`
   - Add executor selection logic in `execute_query()`
   - Add tracing span creation
   - Add metrics collection

3. **`services/sql_executor.py`**:
   - Add retry logic with exponential backoff
   - Add circuit breaker integration
   - Add metrics collection for database operations
   - Add tracing spans for query execution

4. **`services/sql_validator.py`**:
   - Add table/column access control validation
   - Add EXPLAIN policy enforcement
   - Parse SQL to extract table and column references

5. **`config/settings.py`**:
   - Add `allowed_tables`, `blocked_tables`, `column_restrictions` to `SecurityConfig`
   - Add `explain_threshold`, `max_query_cost` to `SecurityConfig`
   - Add `max_concurrent` to `ResilienceConfig`
   - Ensure all config fields are documented and used

6. **`observability/metrics.py`**:
   - Implement Prometheus metrics collection
   - Add HTTP server for metrics endpoint
   - Define all required metrics (counters, gauges, histograms)

7. **`observability/tracing.py`**:
   - Implement OpenTelemetry tracing
   - Add span creation helpers
   - Configure trace exporter

8. **`models/query.py`**:
   - Remove duplicate `to_dict()` methods
   - Keep single implementation using `model_dump()`

### Dependencies

**New Dependencies** (if not already present):
- `prometheus-client` - For metrics collection and exposition
- `opentelemetry-api` - For distributed tracing
- `opentelemetry-sdk` - For trace processing
- `opentelemetry-exporter-otlp` - For exporting traces

**Existing Dependencies** (already in use):
- `asyncpg` - Database driver
- `pglast` - SQL parsing
- `pydantic` - Configuration and validation
- `structlog` - Structured logging

### Backward Compatibility

1. **Configuration**: New configuration fields have sensible defaults, existing configs continue to work
2. **API**: MCP tool interface remains unchanged, only internal behavior improves
3. **Database**: No database schema changes required
4. **Metrics**: Metrics endpoint is optional, disabled by default in development

### Migration Strategy

**Phase 1: Security Enhancements** (Week 1)
- Implement multi-database executor management
- Add table/column access control
- Add EXPLAIN policy enforcement
- Add security integration tests

**Phase 2: Resilience Integration** (Week 2)
- Integrate rate limiting at MCP tool level
- Add retry logic to database operations
- Add circuit breaker for database pools
- Add resilience integration tests

**Phase 3: Observability Activation** (Week 3)
- Implement metrics collection
- Add metrics HTTP server
- Implement distributed tracing
- Add observability integration tests

**Phase 4: Code Quality & Testing** (Week 4)
- Remove code duplications
- Clean up unused configuration
- Enhance test coverage
- Perform end-to-end validation

---

## Assumptions and Dependencies

### Assumptions

1. PostgreSQL databases are already configured and accessible
2. Database users have appropriate permissions for read-only operations
3. Network connectivity between MCP server and databases is reliable
4. LLM API (Google Gemini) is available and responsive
5. Monitoring infrastructure (Prometheus, Grafana) is available for metrics collection

### Dependencies

**Internal Dependencies**:
- Existing `RateLimiter` class in `resilience/rate_limiter.py`
- Existing `CircuitBreaker` class in `resilience/circuit_breaker.py`
- Existing `SQLValidator` class in `services/sql_validator.py`
- Existing configuration system in `config/settings.py`

**External Dependencies**:
- PostgreSQL 12+ (for EXPLAIN support)
- Python 3.12+ (for modern async features)
- Google Gemini API (for SQL generation)
- Prometheus-compatible monitoring system (optional, for metrics)
- OpenTelemetry collector (optional, for tracing)

### Risks and Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Performance degradation from metrics/tracing | Medium | Low | Make observability features optional, optimize collection code, benchmark overhead |
| Breaking changes in configuration | High | Low | Provide sensible defaults, maintain backward compatibility, document migration |
| Complexity increase in orchestrator | Medium | Medium | Keep logic modular, add comprehensive tests, document architecture |
| False positives in access control | High | Medium | Provide clear error messages, add override mechanism for admins, log all violations |
| Circuit breaker prevents legitimate requests | Medium | Low | Tune thresholds carefully, add manual reset capability, monitor false positives |

---

## Out of Scope

The following items are explicitly **not** included in this specification:

1. **Write Operations**: This spec focuses on read-only query improvements, not enabling INSERT/UPDATE/DELETE
2. **Authentication/Authorization**: User identity management is handled by Claude Desktop/MCP, not this server
3. **Query Result Caching**: Result caching is a separate feature for future consideration
4. **Multi-Tenancy**: Supporting multiple isolated tenants with separate databases
5. **Query Optimization**: Automatic query rewriting or optimization beyond EXPLAIN validation
6. **Real-Time Alerting**: Alert generation and notification (handled by external monitoring systems)
7. **Database Schema Migration**: Managing database schema changes
8. **Backup and Recovery**: Database backup/restore procedures

---

## Glossary

- **Circuit Breaker**: A resilience pattern that prevents cascading failures by temporarily blocking requests to a failing service
- **EXPLAIN**: PostgreSQL command that shows the execution plan and estimated cost of a query
- **MCP (Model Context Protocol)**: Protocol for connecting AI assistants to external tools and data sources
- **Observability**: The ability to understand system internal state from external outputs (logs, metrics, traces)
- **Rate Limiting**: Controlling the rate of requests to prevent resource exhaustion
- **Resilience**: System's ability to handle and recover from failures
- **Transient Failure**: Temporary failure that may succeed if retried (e.g., network timeout)

---

## References

- **Project Documentation**: `pg-mcp/CLAUDE.md` - Development guidelines and best practices
- **Configuration**: `pg-mcp/src/pg_mcp/config/settings.py` - Current configuration structure
- **Orchestrator**: `pg-mcp/src/pg_mcp/services/orchestrator.py` - Main query processing logic
- **SQL Executor**: `pg-mcp/src/pg_mcp/services/sql_executor.py` - Database query execution
- **Rate Limiter**: `pg-mcp/src/pg_mcp/resilience/rate_limiter.py` - Existing rate limiting implementation
- **Circuit Breaker**: `pg-mcp/src/pg_mcp/resilience/circuit_breaker.py` - Existing circuit breaker implementation

---

## Approval and Sign-off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Product Owner | TBD | | |
| Technical Lead | TBD | | |
| Security Reviewer | TBD | | |
| QA Lead | TBD | | |

---

**Document Version**: 1.0
**Last Review Date**: 2026-01-09
**Next Review Date**: TBD
