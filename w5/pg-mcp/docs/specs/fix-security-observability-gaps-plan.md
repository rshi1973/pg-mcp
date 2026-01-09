# Implementation Plan: Fix Security, Observability, and Testing Gaps

**Feature**: Security, Observability, and Testing Enhancement
**Spec Document**: [fix-security-observability-gaps.md](./fix-security-observability-gaps.md)
**Status**: Planning
**Created**: 2026-01-09
**Last Updated**: 2026-01-09

---

## Executive Summary

This implementation plan addresses critical gaps between the PostgreSQL MCP Server's design promises and actual implementation. The plan is structured in four phases to systematically integrate security controls, resilience mechanisms, observability features, and improve code quality while maintaining backward compatibility.

---

## Technical Context

### Current Architecture

```
MCP Tool Handler (main.py)
    ↓
QueryOrchestrator (services/orchestrator.py)
    ↓
Single SQLExecutor instance
    ↓
Database Connection Pool
```

**Key Observations**:
- `QueryOrchestrator` currently uses a single `SQLExecutor` instance (line 91 in orchestrator.py)
- Database selection is handled via `_resolve_database()` method (line 280)
- Circuit breaker only protects LLM calls (line 99-102)
- Rate limiting module exists (`resilience/rate_limiter.py`) but not integrated
- Metrics and tracing modules exist but not integrated into request pipeline

### Target Architecture

```
MCP Tool Handler
    ↓
RateLimiter (concurrent request control)
    ↓
QueryOrchestrator
    ↓
Database-Specific SQLExecutor (per database)
    ↓
CircuitBreaker (per database)
    ↓
Retry Logic (transient failure handling)
    ↓
Database Connection Pool

[Metrics Collection] ← All layers
[Distributed Tracing] ← All layers
```

### Technology Stack

**Existing Dependencies**:
- `asyncpg` - PostgreSQL async driver
- `pglast` - SQL parsing and validation
- `google-genai` - LLM for SQL generation (migrated from OpenAI)
- `pydantic` - Configuration and data validation
- `structlog` - Structured logging
- `fastmcp` - MCP protocol implementation

**New Dependencies Required**:
- `prometheus-client` - Metrics collection and exposition
- `opentelemetry-api` - Distributed tracing API
- `opentelemetry-sdk` - Trace processing
- `opentelemetry-exporter-otlp` - Trace export (optional)

### Configuration Changes

**SecurityConfig** (config/settings.py:81-117):
- ADD: `allowed_tables: list[str] = []` - Whitelist of allowed tables
- ADD: `blocked_tables: list[str] = []` - Blacklist of blocked tables
- ADD: `column_restrictions: dict[str, list[str]] = {}` - Table → blocked columns mapping
- ADD: `explain_threshold: int = 10000` - Query complexity threshold for EXPLAIN
- ADD: `max_query_cost: int = 100000` - Maximum allowed query cost

**ResilienceConfig** (config/settings.py:156-173):
- ADD: `max_concurrent: int = 10` - Maximum concurrent requests
- ADD: `rate_limit_timeout: float = 30.0` - Rate limiter timeout

**ObservabilityConfig** (config/settings.py:176-189):
- ADD: `tracing_enabled: bool = False` - Enable distributed tracing
- ADD: `tracing_endpoint: str = ""` - OTLP endpoint for traces
- ADD: `metrics_host: str = "0.0.0.0"` - Metrics server bind address

### Key Files to Modify

1. **main.py** - MCP tool handler
   - Initialize rate limiter
   - Initialize metrics server
   - Wrap query execution with rate limiting

2. **services/orchestrator.py** - Query orchestration
   - Change `self.sql_executor` to `self.executors: dict[str, SQLExecutor]`
   - Add executor selection logic
   - Add tracing span creation
   - Add metrics collection

3. **services/sql_executor.py** - SQL execution
   - Add retry logic with exponential backoff
   - Add circuit breaker integration
   - Add metrics collection
   - Add tracing spans

4. **services/sql_validator.py** - SQL validation
   - Add table/column access control validation
   - Add EXPLAIN policy enforcement
   - Parse SQL to extract table/column references

5. **config/settings.py** - Configuration
   - Add new configuration fields as listed above

6. **observability/metrics.py** - Metrics collection
   - Implement Prometheus metrics
   - Add HTTP server for /metrics endpoint

7. **observability/tracing.py** - Distributed tracing
   - Implement OpenTelemetry tracing
   - Add span creation helpers

8. **models/query.py** - Data models
   - Remove duplicate `to_dict()` methods (lines 160, 214, 130)

---

## Constitution Check

### Project Principles (from CLAUDE.md)

**Alignment Check**:

✅ **SOLID Principles**:
- Single Responsibility: Each component (rate limiter, circuit breaker, metrics) has one job
- Open/Closed: Using Protocol interfaces for extensibility
- Dependency Inversion: Components depend on abstractions

✅ **Python Best Practices**:
- Type annotations on all new code
- Pydantic for configuration validation
- Context managers for resource management
- Async/await for I/O operations

✅ **Security First**:
- Access control validation before SQL execution
- No SQL string concatenation
- Sensitive data not logged
- Security violations logged with context

✅ **Testing Requirements**:
- Unit tests for each new component
- Integration tests for end-to-end flows
- Security tests for access control
- Target: 80% overall, 95% for security modules

✅ **Performance**:
- Async operations throughout
- Connection pooling maintained
- Caching strategy preserved
- Overhead targets: <5ms for rate limiting, <5ms for metrics

### Gate Evaluation

**Gate 1: Backward Compatibility**
- ✅ PASS: All new configuration fields have defaults
- ✅ PASS: MCP tool interface unchanged
- ✅ PASS: No database schema changes

**Gate 2: Security**
- ✅ PASS: Access control validation before execution
- ✅ PASS: Security violations logged
- ✅ PASS: No sensitive data in logs/metrics

**Gate 3: Performance**
- ⚠️ NEEDS VALIDATION: Overhead targets must be benchmarked
- ✅ PASS: Async operations maintained
- ✅ PASS: Connection pooling preserved

**Gate 4: Testing**
- ✅ PASS: Comprehensive test plan included
- ✅ PASS: Security test coverage planned
- ✅ PASS: Integration tests planned

---

## Phase 0: Research & Design Validation

### Objectives
- Resolve all technical unknowns
- Validate technology choices
- Document design decisions

### Research Tasks

#### R1: Prometheus Metrics Integration Pattern
**Question**: What's the best practice for integrating Prometheus metrics in async Python applications?

**Research Areas**:
- Thread-safe metrics collection in async context
- HTTP server lifecycle management (startup/shutdown)
- Metrics naming conventions for database operations
- Performance overhead of metrics collection

**Deliverable**: Document recommended patterns in `research.md`

#### R2: OpenTelemetry Async Integration
**Question**: How to properly integrate OpenTelemetry tracing with asyncpg and async operations?

**Research Areas**:
- Context propagation in async/await chains
- Span creation patterns for database operations
- Attribute naming conventions
- Exporter configuration options

**Deliverable**: Document integration approach in `research.md`

#### R3: SQL Parsing for Access Control
**Question**: How to reliably extract table and column references from SQL using pglast?

**Research Areas**:
- Parsing SELECT statements for table references
- Extracting column references from SELECT lists and WHERE clauses
- Handling JOINs, subqueries, and CTEs
- Error handling for complex queries

**Deliverable**: Code examples and patterns in `research.md`

#### R4: EXPLAIN Policy Implementation
**Question**: How to run EXPLAIN and parse cost estimates in PostgreSQL?

**Research Areas**:
- EXPLAIN output format and parsing
- Cost estimation accuracy
- Performance impact of EXPLAIN
- Handling EXPLAIN failures

**Deliverable**: Implementation approach in `research.md`

#### R5: Rate Limiter Integration Point
**Question**: Where should rate limiting be applied in the MCP tool handler?

**Research Areas**:
- FastMCP tool decorator patterns
- Async context manager usage
- Error handling and timeout behavior
- Metrics integration

**Deliverable**: Integration pattern in `research.md`

### Output
- `docs/specs/research.md` - Consolidated research findings

---

## Phase 1: Design Artifacts

### Prerequisites
- Phase 0 research complete
- All NEEDS CLARIFICATION resolved

### D1: Data Model Design

**File**: `docs/specs/data-model.md`

**Entities**:

1. **ExecutorRegistry**
   - Purpose: Manage database-specific executor instances
   - Fields:
     - `executors: dict[str, SQLExecutor]` - Database name → executor mapping
     - `circuit_breakers: dict[str, CircuitBreaker]` - Database name → circuit breaker
   - Operations:
     - `get_executor(database: str) -> SQLExecutor`
     - `register_executor(database: str, executor: SQLExecutor)`

2. **AccessControlPolicy**
   - Purpose: Define table/column access restrictions
   - Fields:
     - `database: str` - Database name
     - `allowed_tables: set[str]` - Whitelist (empty = all allowed)
     - `blocked_tables: set[str]` - Blacklist
     - `column_restrictions: dict[str, set[str]]` - Table → blocked columns
   - Operations:
     - `validate_table_access(table: str) -> bool`
     - `validate_column_access(table: str, columns: list[str]) -> bool`
     - `get_violations(sql: str) -> list[str]`

3. **ExplainPolicy**
   - Purpose: Query cost validation
   - Fields:
     - `threshold: int` - Complexity threshold
     - `max_cost: int` - Maximum allowed cost
   - Operations:
     - `should_explain(sql: str) -> bool`
     - `validate_cost(explain_result: dict) -> bool`

4. **MetricsCollector**
   - Purpose: Centralized metrics collection
   - Metrics:
     - `query_requests_total` - Counter with labels: database, status
     - `query_duration_seconds` - Histogram with labels: database, operation
     - `database_connections_active` - Gauge with label: database
     - `rate_limiter_active_requests` - Gauge
     - `circuit_breaker_state` - Gauge with label: database

5. **TracingContext**
   - Purpose: Distributed tracing context
   - Fields:
     - `request_id: str` - Unique request identifier
     - `root_span: Span` - Root span for request
     - `current_span: Span | None` - Current active span
   - Operations:
     - `create_span(name: str, attributes: dict) -> Span`
     - `end_span()`

### D2: API Contracts

**File**: `docs/specs/contracts/internal-apis.md`

**Internal Service Contracts**:

```python
# Rate Limiter Contract
class RateLimiter(Protocol):
    async def __aenter__(self) -> None:
        """Acquire rate limit slot or wait."""
        ...

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Release rate limit slot."""
        ...

    def get_stats(self) -> dict[str, int]:
        """Return current rate limiter statistics."""
        ...

# Executor Registry Contract
class ExecutorRegistry(Protocol):
    def get_executor(self, database: str) -> SQLExecutor:
        """Get executor for database, raise if not found."""
        ...

    def get_circuit_breaker(self, database: str) -> CircuitBreaker:
        """Get circuit breaker for database."""
        ...

# Access Control Validator Contract
class AccessControlValidator(Protocol):
    def validate(self, sql: str, policy: AccessControlPolicy) -> ValidationResult:
        """Validate SQL against access control policy."""
        ...

    def extract_tables(self, sql: str) -> set[str]:
        """Extract table references from SQL."""
        ...

    def extract_columns(self, sql: str) -> dict[str, set[str]]:
        """Extract column references per table."""
        ...

# Metrics Contract
class MetricsCollector(Protocol):
    def increment_counter(self, name: str, labels: dict[str, str]) -> None:
        """Increment counter metric."""
        ...

    def observe_histogram(self, name: str, value: float, labels: dict[str, str]) -> None:
        """Record histogram observation."""
        ...

    def set_gauge(self, name: str, value: float, labels: dict[str, str]) -> None:
        """Set gauge value."""
        ...
```

### D3: Quickstart Guide

**File**: `docs/specs/quickstart.md`

**Content**:
1. Configuration examples for new features
2. How to enable/disable observability features
3. How to configure access control policies
4. How to monitor metrics endpoint
5. How to troubleshoot common issues

---

## Phase 2: Implementation Plan

### Implementation Phases

#### Phase 2.1: Security Enhancements (Week 1)

**Tasks**:

1. **Multi-Database Executor Management**
   - Modify `QueryOrchestrator.__init__()` to create executor per database
   - Change `self.sql_executor` to `self.executors: dict[str, SQLExecutor]`
   - Update `execute_query()` to select correct executor
   - Add tests: `test_multi_database_executor_selection()`

2. **Table/Column Access Control**
   - Add new fields to `SecurityConfig`
   - Create `AccessControlValidator` class
   - Integrate into `SQLValidator.validate()`
   - Add SQL parsing logic using pglast
   - Add tests: `test_table_access_control()`, `test_column_access_control()`

3. **EXPLAIN Policy Enforcement**
   - Add EXPLAIN fields to `SecurityConfig`
   - Create `ExplainPolicy` class
   - Integrate into `SQLExecutor.execute()`
   - Add cost validation logic
   - Add tests: `test_explain_policy_enforcement()`

**Deliverables**:
- Modified `services/orchestrator.py`
- Modified `services/sql_validator.py`
- Modified `services/sql_executor.py`
- New `security/access_control.py`
- Modified `config/settings.py`
- Test files in `tests/security/`

#### Phase 2.2: Resilience Integration (Week 2)

**Tasks**:

1. **Rate Limiting Integration**
   - Add `max_concurrent` to `ResilienceConfig`
   - Initialize `RateLimiter` in `main.py`
   - Wrap query execution with rate limiter
   - Add metrics for rate limiter
   - Add tests: `test_rate_limiting_enforcement()`

2. **Database Retry Logic**
   - Add retry wrapper to `SQLExecutor.execute()`
   - Implement transient error detection
   - Add exponential backoff
   - Add retry metrics
   - Add tests: `test_database_retry_logic()`

3. **Circuit Breaker for Databases**
   - Create circuit breaker per database
   - Integrate into `SQLExecutor.execute()`
   - Add circuit breaker state metrics
   - Add tests: `test_circuit_breaker_protection()`

**Deliverables**:
- Modified `main.py`
- Modified `services/sql_executor.py`
- Modified `resilience/rate_limiter.py` (if needed)
- Test files in `tests/resilience/`

#### Phase 2.3: Observability Activation (Week 3)

**Tasks**:

1. **Metrics Collection**
   - Install `prometheus-client`
   - Create `observability/metrics.py`
   - Define all required metrics
   - Integrate metrics into orchestrator, executor
   - Add tests: `test_metrics_collection()`

2. **Metrics HTTP Server**
   - Implement HTTP server in `observability/metrics.py`
   - Add startup/shutdown lifecycle
   - Expose `/metrics` endpoint
   - Add tests: `test_metrics_endpoint()`

3. **Distributed Tracing**
   - Install OpenTelemetry packages
   - Create `observability/tracing.py`
   - Add span creation helpers
   - Integrate tracing into orchestrator, executor
   - Add tests: `test_tracing_spans()`

**Deliverables**:
- New `observability/metrics.py`
- New `observability/tracing.py`
- Modified `services/orchestrator.py`
- Modified `services/sql_executor.py`
- Modified `main.py`
- Test files in `tests/observability/`

#### Phase 2.4: Code Quality & Testing (Week 4)

**Tasks**:

1. **Remove Code Duplications**
   - Remove duplicate `to_dict()` in `QueryResponse` (line 214)
   - Remove duplicate `to_dict()` in `QueryResult` (line 130)
   - Verify single implementation using `model_dump()`

2. **Configuration Cleanup**
   - Audit all config fields for usage
   - Remove unused fields or document why kept
   - Update configuration documentation

3. **Enhanced Test Coverage**
   - Write integration tests for all new features
   - Achieve 90% coverage for security/resilience/observability
   - Add end-to-end tests
   - Run tests in CI/CD

4. **Documentation Updates**
   - Update README with new features
   - Update configuration guide
   - Add troubleshooting guide
   - Update CLAUDE.md if needed

**Deliverables**:
- Modified `models/query.py`
- Modified `config/settings.py`
- Comprehensive test suite
- Updated documentation

---

## Testing Strategy

### Unit Tests

**Security Module** (target: 95% coverage):
- `test_access_control_validator.py`
  - Table whitelist/blacklist validation
  - Column restriction validation
  - SQL parsing edge cases
- `test_explain_policy.py`
  - Cost threshold validation
  - EXPLAIN parsing
  - Error handling

**Resilience Module** (target: 90% coverage):
- `test_rate_limiter_integration.py`
  - Concurrent request limiting
  - Timeout behavior
  - Metrics collection
- `test_retry_logic.py`
  - Transient error detection
  - Exponential backoff
  - Max retries
- `test_circuit_breaker_database.py`
  - Failure threshold
  - Recovery timeout
  - State transitions

**Observability Module** (target: 85% coverage):
- `test_metrics_collector.py`
  - Counter increments
  - Histogram observations
  - Gauge updates
- `test_tracing_context.py`
  - Span creation
  - Context propagation
  - Attribute setting

### Integration Tests

**End-to-End Flows**:
- `test_multi_database_query_flow.py`
  - Query routing to correct executor
  - Access control enforcement
  - Metrics collection
- `test_resilience_flow.py`
  - Rate limiting under load
  - Retry on transient failures
  - Circuit breaker activation
- `test_observability_flow.py`
  - Metrics endpoint accessibility
  - Trace span creation
  - Log correlation

### Performance Tests

**Benchmarks**:
- Rate limiting overhead: < 5ms
- Metrics collection overhead: < 5ms
- Tracing overhead: < 10ms
- Circuit breaker check: < 1ms

---

## Deployment Strategy

### Phase Rollout

**Phase 1: Development Environment**
- Deploy to dev environment
- Enable all observability features
- Run integration tests
- Validate metrics and traces

**Phase 2: Staging Environment**
- Deploy to staging
- Run load tests
- Validate performance overhead
- Test circuit breaker behavior

**Phase 3: Production Rollout**
- Deploy with observability disabled by default
- Enable metrics only
- Monitor for issues
- Gradually enable tracing if needed

### Configuration Migration

**Backward Compatibility**:
- All new config fields have defaults
- Existing configurations work without changes
- Optional features disabled by default

**Migration Guide**:
1. Update dependencies: `uv sync`
2. Review new configuration options
3. Enable features incrementally
4. Monitor metrics endpoint
5. Adjust thresholds based on load

### Rollback Plan

**If Issues Occur**:
1. Disable observability features via config
2. Revert to previous version if needed
3. All features have feature flags
4. No database schema changes to revert

---

## Risk Mitigation

### Identified Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Performance degradation | Medium | Low | Benchmark overhead, make features optional, optimize collection code |
| Breaking config changes | High | Low | Provide defaults, maintain backward compatibility, document migration |
| Complexity increase | Medium | Medium | Keep logic modular, comprehensive tests, clear documentation |
| False positive access control | High | Medium | Clear error messages, admin override, log all violations |
| Circuit breaker blocks valid requests | Medium | Low | Tune thresholds, manual reset capability, monitor false positives |
| Metrics memory overhead | Medium | Low | Limit metric cardinality, use TTL for time series, monitor memory |

### Monitoring Plan

**Key Metrics to Watch**:
- Request latency (p50, p95, p99)
- Error rate by type
- Circuit breaker state changes
- Rate limiter rejections
- Memory usage
- CPU usage

**Alerts**:
- Latency > 1s for 5 minutes
- Error rate > 5% for 5 minutes
- Circuit breaker open for > 2 minutes
- Memory usage > 80%

---

## Success Criteria

### Functional Requirements Met

✅ **Security**:
- [ ] Multi-database executor selection works
- [ ] Table/column access control enforced
- [ ] EXPLAIN policy validates query cost
- [ ] Security violations logged and blocked

✅ **Resilience**:
- [ ] Rate limiting applied to all requests
- [ ] Retry logic handles transient failures
- [ ] Circuit breakers protect database operations
- [ ] System remains stable under load

✅ **Observability**:
- [ ] Metrics collected and exposed
- [ ] Metrics endpoint accessible
- [ ] Distributed tracing works (if enabled)
- [ ] Logs include request_id for correlation

✅ **Code Quality**:
- [ ] No duplicate methods
- [ ] All config fields used or removed
- [ ] Test coverage >= 80% overall, >= 90% for security
- [ ] All tests pass in CI/CD

### Performance Targets

- [ ] Rate limiting overhead < 5ms
- [ ] Metrics collection overhead < 5ms
- [ ] Tracing overhead < 10ms (when enabled)
- [ ] Circuit breaker check < 1ms
- [ ] No memory leaks
- [ ] No connection pool exhaustion

### Documentation Complete

- [ ] README updated with new features
- [ ] Configuration guide updated
- [ ] Quickstart guide created
- [ ] Troubleshooting guide created
- [ ] API documentation updated

---

## Next Steps

1. **Immediate**: Begin Phase 0 research tasks
2. **Week 1**: Complete research, start Phase 1 design artifacts
3. **Week 2**: Begin Phase 2.1 implementation (Security)
4. **Week 3**: Continue with Phase 2.2 (Resilience)
5. **Week 4**: Complete Phase 2.3 (Observability) and Phase 2.4 (Quality)

---

## Appendix

### References

- **Feature Spec**: `docs/specs/fix-security-observability-gaps.md`
- **Project Guidelines**: `CLAUDE.md`
- **Current Config**: `src/pg_mcp/config/settings.py`
- **Orchestrator**: `src/pg_mcp/services/orchestrator.py`
- **SQL Executor**: `src/pg_mcp/services/sql_executor.py`
- **Rate Limiter**: `src/pg_mcp/resilience/rate_limiter.py`
- **Circuit Breaker**: `src/pg_mcp/resilience/circuit_breaker.py`

### Glossary

- **Circuit Breaker**: Pattern that prevents cascading failures by temporarily blocking requests
- **EXPLAIN**: PostgreSQL command showing query execution plan and cost
- **MCP**: Model Context Protocol for AI assistant integration
- **Observability**: Understanding system state from external outputs (logs, metrics, traces)
- **Rate Limiting**: Controlling request rate to prevent resource exhaustion
- **Transient Failure**: Temporary failure that may succeed if retried

---

**Document Version**: 1.0
**Status**: Ready for Phase 0 Research
**Next Review**: After Phase 0 completion
