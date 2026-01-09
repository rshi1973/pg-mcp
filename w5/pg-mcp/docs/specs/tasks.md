# Implementation Tasks: Security, Observability, and Testing Enhancement

**Feature**: Security, Observability, and Testing Enhancement
**Status**: Ready for Implementation
**Created**: 2026-01-09
**Last Updated**: 2026-01-09

---

## Overview

This document provides a complete task breakdown for implementing security controls, resilience mechanisms, and observability features in the PostgreSQL MCP Server. Tasks are organized by functional area and include clear dependencies, file paths, and acceptance criteria.

**Total Tasks**: 68
**Estimated Duration**: 4 weeks
**Parallel Opportunities**: 45 parallelizable tasks

---

## Task Organization

Tasks are organized into phases:
- **Phase 1**: Setup & Dependencies (5 tasks)
- **Phase 2**: Security Enhancements (18 tasks)
- **Phase 3**: Resilience Integration (15 tasks)
- **Phase 4**: Observability Activation (18 tasks)
- **Phase 5**: Code Quality & Testing (12 tasks)

---

## Phase 1: Setup & Dependencies

**Goal**: Install required dependencies and prepare project structure.

**Duration**: 0.5 days

### Tasks

- [X] T001 Add prometheus-client to pyproject.toml dependencies
- [X] T002 Add opentelemetry-api to pyproject.toml dependencies
- [X] T003 Add opentelemetry-sdk to pyproject.toml dependencies
- [X] T004 Add opentelemetry-exporter-otlp to pyproject.toml dependencies
- [X] T005 Run uv sync to install new dependencies

**Acceptance Criteria**:
- All new dependencies installed successfully
- No version conflicts with existing packages
- `uv sync` completes without errors

---

## Phase 2: Security Enhancements

**Goal**: Implement multi-database executor management, table/column access control, and EXPLAIN policy enforcement.

**Duration**: 5 days

**User Stories Addressed**:
- FR1: Database-Specific Executor Management
- FR2: Table and Column Access Control
- FR3: EXPLAIN Policy Enforcement

### 2.1: Configuration Extensions

- [ ] T006 [P] Add allowed_tables field to SecurityConfig in src/pg_mcp/config/settings.py
- [ ] T007 [P] Add blocked_tables field to SecurityConfig in src/pg_mcp/config/settings.py
- [ ] T008 [P] Add column_restrictions field to SecurityConfig in src/pg_mcp/config/settings.py
- [ ] T009 [P] Add explain_threshold field to SecurityConfig in src/pg_mcp/config/settings.py
- [ ] T010 [P] Add max_query_cost field to SecurityConfig in src/pg_mcp/config/settings.py
- [ ] T011 [P] Add explain_enabled field to SecurityConfig in src/pg_mcp/config/settings.py
- [ ] T012 [P] Add max_concurrent field to ResilienceConfig in src/pg_mcp/config/settings.py
- [ ] T013 [P] Add rate_limit_timeout field to ResilienceConfig in src/pg_mcp/config/settings.py

**Acceptance Criteria**:
- All new config fields have type annotations
- All fields have sensible defaults
- All fields have docstrings
- Configuration validates correctly with Pydantic

### 2.2: Executor Registry

- [ ] T014 Create ExecutorRegistry class in src/pg_mcp/services/executor_registry.py
- [ ] T015 Implement get_executor() method in ExecutorRegistry
- [ ] T016 Implement get_circuit_breaker() method in ExecutorRegistry
- [ ] T017 Implement register_pool() method in ExecutorRegistry
- [ ] T018 Implement list_databases() method in ExecutorRegistry

**Acceptance Criteria**:
- ExecutorRegistry manages per-database executors
- Executors are created lazily on first access
- Circuit breakers are created per database
- Registry validates database names

### 2.3: Access Control

- [ ] T019 Create AccessControlPolicy class in src/pg_mcp/security/access_control.py
- [ ] T020 Implement validate_table_access() method in AccessControlPolicy
- [ ] T021 Implement validate_column_access() method in AccessControlPolicy
- [ ] T022 Implement get_violations() method in AccessControlPolicy
- [ ] T023 Implement from_config() class method in AccessControlPolicy
- [ ] T024 Create AccessControlValidator class in src/pg_mcp/security/access_control.py
- [ ] T025 Implement extract_tables() method using pglast in AccessControlValidator
- [ ] T026 Implement extract_columns() method using pglast in AccessControlValidator
- [ ] T027 Implement validate() method in AccessControlValidator
- [ ] T028 Integrate AccessControlValidator into SQLValidator.validate() in src/pg_mcp/services/sql_validator.py

**Acceptance Criteria**:
- Table whitelist/blacklist validation works
- Column restrictions are enforced
- SQL parsing handles JOINs, subqueries, and CTEs
- Clear error messages for violations

### 2.4: EXPLAIN Policy

- [ ] T029 Create ExplainPolicy class in src/pg_mcp/security/explain_policy.py
- [ ] T030 Implement should_explain() method with complexity heuristics in ExplainPolicy
- [ ] T031 Implement validate_cost() async method in ExplainPolicy
- [ ] T032 Implement from_config() class method in ExplainPolicy
- [ ] T033 Integrate ExplainPolicy into SQLExecutor.execute() in src/pg_mcp/services/sql_executor.py

**Acceptance Criteria**:
- EXPLAIN runs for complex queries (JOINs, subqueries, CTEs)
- Cost validation rejects expensive queries
- EXPLAIN failures are handled gracefully
- Cost estimates are logged for audit

### 2.5: Orchestrator Integration

- [ ] T034 Change self.sql_executor to self.executor_registry in QueryOrchestrator.__init__() in src/pg_mcp/services/orchestrator.py
- [ ] T035 Update execute_query() to use executor_registry.get_executor(database) in src/pg_mcp/services/orchestrator.py
- [ ] T036 Update _resolve_database() to validate against executor_registry in src/pg_mcp/services/orchestrator.py

**Acceptance Criteria**:
- Orchestrator uses correct executor per database
- Database validation works correctly
- Backward compatibility maintained

### 2.6: Security Tests

- [ ] T037 [P] Create test_access_control_validator.py in tests/security/
- [ ] T038 [P] Create test_explain_policy.py in tests/security/
- [ ] T039 [P] Create test_executor_registry.py in tests/security/
- [ ] T040 [P] Create test_multi_database_executor_selection.py in tests/integration/
- [ ] T041 [P] Create test_table_column_access_control.py in tests/integration/

**Acceptance Criteria**:
- Unit tests cover all security modules (>95% coverage)
- Integration tests validate end-to-end security flows
- Tests include edge cases and error scenarios
- All tests pass

---

## Phase 3: Resilience Integration

**Goal**: Integrate rate limiting, retry logic, and circuit breakers into the request pipeline.

**Duration**: 4 days

**User Stories Addressed**:
- FR4: Request Rate Limiting
- FR5: Database Operation Retry Logic
- FR6: Circuit Breaker for Database Operations

### 3.1: Rate Limiting Integration

- [ ] T042 Initialize RateLimiter in main.py with max_concurrent from config
- [ ] T043 Wrap query_database() tool with rate_limiter context manager in main.py
- [ ] T044 Add rate limit timeout error handling in main.py
- [ ] T045 Add rate limiter statistics logging in main.py

**Acceptance Criteria**:
- Rate limiting applied to all MCP tool invocations
- Concurrent requests limited to configured maximum
- Timeout errors return clear error messages
- Rate limiter stats are logged

### 3.2: Retry Logic

- [ ] T046 Create RetryStrategy class in src/pg_mcp/resilience/retry.py
- [ ] T047 Implement execute() method with exponential backoff in RetryStrategy
- [ ] T048 Implement calculate_delay() method in RetryStrategy
- [ ] T049 Implement is_transient_error() function in src/pg_mcp/resilience/retry.py
- [ ] T050 Wrap SQLExecutor.execute() with retry logic in src/pg_mcp/services/sql_executor.py

**Acceptance Criteria**:
- Transient errors trigger retry (connection errors, timeouts)
- Permanent errors do not trigger retry (syntax errors, permissions)
- Exponential backoff follows configured pattern
- Maximum retries are respected

### 3.3: Circuit Breaker Integration

- [ ] T051 Add circuit breaker creation to ExecutorRegistry in src/pg_mcp/services/executor_registry.py
- [ ] T052 Integrate circuit breaker checks into SQLExecutor.execute() in src/pg_mcp/services/sql_executor.py
- [ ] T053 Add circuit breaker state logging in src/pg_mcp/services/sql_executor.py
- [ ] T054 Add circuit breaker recovery logic in src/pg_mcp/services/sql_executor.py

**Acceptance Criteria**:
- Circuit breaker created per database
- Circuit opens after threshold failures
- Circuit attempts recovery after timeout
- Circuit state changes are logged

### 3.4: Resilience Tests

- [ ] T055 [P] Create test_rate_limiter_integration.py in tests/resilience/
- [ ] T056 [P] Create test_retry_logic.py in tests/resilience/
- [ ] T057 [P] Create test_circuit_breaker_database.py in tests/resilience/
- [ ] T058 [P] Create test_resilience_flow.py in tests/integration/

**Acceptance Criteria**:
- Unit tests cover all resilience modules (>90% coverage)
- Integration tests validate end-to-end resilience flows
- Tests simulate failures and recovery
- All tests pass

---

## Phase 4: Observability Activation

**Goal**: Implement metrics collection, metrics HTTP server, and distributed tracing.

**Duration**: 5 days

**User Stories Addressed**:
- FR7: Metrics Collection and Exposure
- FR8: Distributed Tracing Integration

### 4.1: Metrics Collection

- [ ] T059 Create MetricsCollector class in src/pg_mcp/observability/metrics.py
- [ ] T060 Define query_requests_total counter metric in MetricsCollector
- [ ] T061 Define query_duration_seconds histogram metric in MetricsCollector
- [ ] T062 Define database_connections_active gauge metric in MetricsCollector
- [ ] T063 Define rate_limiter_active_requests gauge metric in MetricsCollector
- [ ] T064 Define rate_limiter_rejections_total counter metric in MetricsCollector
- [ ] T065 Define circuit_breaker_state gauge metric in MetricsCollector
- [ ] T066 Define llm_generation_duration_seconds histogram metric in MetricsCollector
- [ ] T067 Define llm_tokens_used_total counter metric in MetricsCollector
- [ ] T068 Implement increment_counter() method in MetricsCollector
- [ ] T069 Implement observe_histogram() method in MetricsCollector
- [ ] T070 Implement set_gauge() method in MetricsCollector
- [ ] T071 Implement start_timer() method in MetricsCollector

**Acceptance Criteria**:
- All metrics follow Prometheus naming conventions
- Metrics have appropriate labels
- Metrics are thread-safe
- Metrics collection overhead < 5ms

### 4.2: Metrics HTTP Server

- [ ] T072 Create MetricsServer class in src/pg_mcp/observability/metrics.py
- [ ] T073 Implement start() method using prometheus-client HTTP server in MetricsServer
- [ ] T074 Implement stop() method in MetricsServer
- [ ] T075 Implement is_running() method in MetricsServer
- [ ] T076 Initialize MetricsServer in main.py with config port and host
- [ ] T077 Start metrics server on application startup in main.py

**Acceptance Criteria**:
- Metrics server runs in background thread
- /metrics endpoint is accessible
- Server starts/stops cleanly
- Server configuration is validated

### 4.3: Metrics Integration

- [ ] T078 Add metrics collection to QueryOrchestrator.execute_query() in src/pg_mcp/services/orchestrator.py
- [ ] T079 Add metrics collection to SQLExecutor.execute() in src/pg_mcp/services/sql_executor.py
- [ ] T080 Add metrics collection to SQLGenerator.generate() in src/pg_mcp/services/sql_generator.py
- [ ] T081 Add metrics collection to RateLimiter in src/pg_mcp/resilience/rate_limiter.py
- [ ] T082 Add metrics collection to CircuitBreaker in src/pg_mcp/resilience/circuit_breaker.py

**Acceptance Criteria**:
- Metrics collected at all critical points
- Metrics include appropriate labels
- Metrics are updated in real-time
- No performance degradation

### 4.4: Distributed Tracing

- [ ] T083 Create TracingContext class in src/pg_mcp/observability/tracing.py
- [ ] T084 Implement create_span() method in TracingContext
- [ ] T085 Implement end_span() method in TracingContext
- [ ] T086 Implement set_attribute() method in TracingContext
- [ ] T087 Implement record_exception() method in TracingContext
- [ ] T088 Implement set_status() method in TracingContext
- [ ] T089 Implement span() context manager in TracingContext
- [ ] T090 Create setup_tracing() function in src/pg_mcp/observability/tracing.py
- [ ] T091 Initialize tracing in main.py with config endpoint
- [ ] T092 Add tracing spans to QueryOrchestrator.execute_query() in src/pg_mcp/services/orchestrator.py
- [ ] T093 Add tracing spans to SQLGenerator.generate() in src/pg_mcp/services/sql_generator.py
- [ ] T094 Add tracing spans to SQLExecutor.execute() in src/pg_mcp/services/sql_executor.py

**Acceptance Criteria**:
- Tracing context propagates through async operations
- Spans include standard attributes (db.system, db.statement, etc.)
- Tracing can be enabled/disabled via config
- Tracing overhead < 10ms when enabled

### 4.5: Observability Configuration

- [ ] T095 [P] Add tracing_enabled field to ObservabilityConfig in src/pg_mcp/config/settings.py
- [ ] T096 [P] Add tracing_endpoint field to ObservabilityConfig in src/pg_mcp/config/settings.py
- [ ] T097 [P] Add tracing_sample_rate field to ObservabilityConfig in src/pg_mcp/config/settings.py
- [ ] T098 [P] Add metrics_host field to ObservabilityConfig in src/pg_mcp/config/settings.py

**Acceptance Criteria**:
- All observability features are configurable
- Configuration has sensible defaults
- Configuration is validated

### 4.6: Observability Tests

- [ ] T099 [P] Create test_metrics_collector.py in tests/observability/
- [ ] T100 [P] Create test_metrics_server.py in tests/observability/
- [ ] T101 [P] Create test_tracing_context.py in tests/observability/
- [ ] T102 [P] Create test_observability_flow.py in tests/integration/

**Acceptance Criteria**:
- Unit tests cover all observability modules (>85% coverage)
- Integration tests validate end-to-end observability flows
- Tests verify metrics endpoint accessibility
- Tests verify trace span creation
- All tests pass

---

## Phase 5: Code Quality & Testing

**Goal**: Remove code duplications, clean up configuration, enhance test coverage, and update documentation.

**Duration**: 3 days

**User Stories Addressed**:
- FR9: Code Quality Improvements
- FR10: Enhanced Test Coverage

### 5.1: Code Duplications

- [ ] T103 Remove duplicate to_dict() method at line 214 in src/pg_mcp/models/query.py (QueryResponse)
- [ ] T104 Remove duplicate to_dict() method at line 130 in src/pg_mcp/models/query.py (QueryResult)
- [ ] T105 Verify single to_dict() implementation uses model_dump() in src/pg_mcp/models/query.py
- [ ] T106 Run tests to ensure no regressions after removing duplicates

**Acceptance Criteria**:
- Only one to_dict() method per class
- All tests pass after removal
- No functionality is broken

### 5.2: Configuration Cleanup

- [ ] T107 Audit all SecurityConfig fields for usage in src/pg_mcp/config/settings.py
- [ ] T108 Audit all ResilienceConfig fields for usage in src/pg_mcp/config/settings.py
- [ ] T109 Audit all ObservabilityConfig fields for usage in src/pg_mcp/config/settings.py
- [ ] T110 Remove or document unused configuration fields
- [ ] T111 Update configuration documentation in docs/

**Acceptance Criteria**:
- All config fields are either used or documented as reserved
- Configuration documentation is up-to-date
- No unused fields remain

### 5.3: Enhanced Test Coverage

- [ ] T112 [P] Write integration test for multi-database query flow in tests/integration/
- [ ] T113 [P] Write integration test for access control enforcement in tests/integration/
- [ ] T114 [P] Write integration test for rate limiting under load in tests/integration/
- [ ] T115 [P] Write integration test for retry on transient failures in tests/integration/
- [ ] T116 [P] Write integration test for circuit breaker activation in tests/integration/
- [ ] T117 [P] Write integration test for metrics collection in tests/integration/
- [ ] T118 [P] Write integration test for tracing spans in tests/integration/
- [ ] T119 Run pytest with coverage report
- [ ] T120 Verify coverage >= 80% overall, >= 90% for security modules

**Acceptance Criteria**:
- Integration tests cover all major features
- Test coverage meets targets
- All tests pass in CI/CD
- Tests are maintainable and well-documented

### 5.4: Documentation Updates

- [ ] T121 [P] Update README.md with new features overview
- [ ] T122 [P] Update configuration guide with new config fields
- [ ] T123 [P] Create troubleshooting guide in docs/
- [ ] T124 [P] Update CLAUDE.md with new architectural patterns
- [ ] T125 [P] Create migration guide for existing deployments in docs/

**Acceptance Criteria**:
- README includes all new features
- Configuration guide is complete and accurate
- Troubleshooting guide covers common issues
- Migration guide helps users upgrade
- All documentation is clear and concise

---

## Dependencies

### Phase Dependencies

```
Phase 1 (Setup)
    ↓
Phase 2 (Security) ←─┐
    ↓                 │
Phase 3 (Resilience) ←┤ (Can run in parallel after Phase 1)
    ↓                 │
Phase 4 (Observability) ←┘
    ↓
Phase 5 (Quality & Testing)
```

### Task Dependencies

**Critical Path**:
1. T001-T005: Install dependencies (blocking all other phases)
2. T006-T013: Configuration extensions (blocking implementation tasks)
3. T014-T018: Executor registry (blocking orchestrator integration)
4. T034-T036: Orchestrator integration (blocking end-to-end flows)
5. T042-T045: Rate limiting integration (blocking resilience tests)
6. T059-T077: Metrics implementation (blocking observability tests)
7. T112-T120: Integration tests (blocking final validation)

**Parallel Opportunities**:
- Configuration fields (T006-T013) can be added in parallel
- Security modules (T019-T033) can be developed in parallel after config
- Resilience modules (T046-T054) can be developed in parallel with security
- Observability modules (T059-T098) can be developed in parallel with resilience
- Tests (T037-T041, T055-T058, T099-T102, T112-T118) can be written in parallel
- Documentation (T121-T125) can be written in parallel

---

## Parallel Execution Examples

### Phase 2: Security (Parallel Groups)

**Group 1** (Configuration):
- T006, T007, T008, T009, T010, T011, T012, T013

**Group 2** (After Group 1):
- T014-T018 (Executor Registry)
- T019-T028 (Access Control)
- T029-T033 (EXPLAIN Policy)

**Group 3** (After Group 2):
- T034-T036 (Orchestrator Integration)

**Group 4** (After Group 3):
- T037, T038, T039, T040, T041 (Tests)

### Phase 3: Resilience (Parallel Groups)

**Group 1**:
- T042-T045 (Rate Limiting)
- T046-T050 (Retry Logic)
- T051-T054 (Circuit Breaker)

**Group 2** (After Group 1):
- T055, T056, T057, T058 (Tests)

### Phase 4: Observability (Parallel Groups)

**Group 1**:
- T059-T071 (Metrics Collection)
- T083-T089 (Tracing Context)
- T095-T098 (Configuration)

**Group 2** (After Group 1):
- T072-T077 (Metrics Server)
- T090-T094 (Tracing Integration)

**Group 3** (After Group 2):
- T078-T082 (Metrics Integration)

**Group 4** (After Group 3):
- T099, T100, T101, T102 (Tests)

### Phase 5: Quality (Parallel Groups)

**Group 1**:
- T103-T106 (Code Duplications)
- T107-T111 (Configuration Cleanup)

**Group 2** (After Group 1):
- T112, T113, T114, T115, T116, T117, T118 (Integration Tests)
- T121, T122, T123, T124, T125 (Documentation)

**Group 3** (After Group 2):
- T119-T120 (Coverage Validation)

---

## Implementation Strategy

### MVP Scope (Week 1)

**Minimum Viable Product** includes:
- Phase 1: Setup & Dependencies (T001-T005)
- Phase 2.1-2.3: Core security features (T006-T033)
- Phase 2.5: Orchestrator integration (T034-T036)
- Basic tests (T037-T041)

**MVP Delivers**:
- Multi-database executor management
- Table/column access control
- EXPLAIN policy enforcement
- Basic test coverage

### Incremental Delivery

**Week 1**: Security (MVP)
- Deliverable: Multi-database security controls working
- Validation: Security integration tests pass

**Week 2**: Resilience
- Deliverable: Rate limiting, retry, circuit breaker integrated
- Validation: Resilience integration tests pass

**Week 3**: Observability
- Deliverable: Metrics and tracing operational
- Validation: Metrics endpoint accessible, traces visible

**Week 4**: Quality & Polish
- Deliverable: Code cleaned up, full test coverage, documentation complete
- Validation: All tests pass, coverage targets met

---

## Testing Strategy

### Unit Tests (Per Module)

**Security** (Target: 95% coverage):
- AccessControlValidator: Table/column validation, SQL parsing
- ExplainPolicy: Cost validation, EXPLAIN parsing
- ExecutorRegistry: Executor management, circuit breaker creation

**Resilience** (Target: 90% coverage):
- RetryStrategy: Exponential backoff, transient error detection
- RateLimiter: Concurrent request limiting, timeout behavior
- CircuitBreaker: State transitions, failure threshold

**Observability** (Target: 85% coverage):
- MetricsCollector: Counter/histogram/gauge operations
- MetricsServer: HTTP server lifecycle
- TracingContext: Span creation, context propagation

### Integration Tests (End-to-End)

**Security Flow**:
- Multi-database query routing
- Access control enforcement
- EXPLAIN policy validation

**Resilience Flow**:
- Rate limiting under load
- Retry on transient failures
- Circuit breaker activation/recovery

**Observability Flow**:
- Metrics collection and exposure
- Trace span creation and propagation
- Log correlation with request_id

### Performance Tests

**Benchmarks**:
- Rate limiting overhead: < 5ms
- Metrics collection overhead: < 5ms
- Tracing overhead: < 10ms (when enabled)
- Circuit breaker check: < 1ms

---

## Success Criteria

### Functional Requirements

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
- [ ] Migration guide created

---

## Task Summary

**Total Tasks**: 125
**Parallelizable Tasks**: 45 (36%)

**By Phase**:
- Phase 1 (Setup): 5 tasks
- Phase 2 (Security): 36 tasks
- Phase 3 (Resilience): 17 tasks
- Phase 4 (Observability): 44 tasks
- Phase 5 (Quality): 23 tasks

**By Type**:
- Configuration: 17 tasks
- Implementation: 68 tasks
- Testing: 28 tasks
- Documentation: 12 tasks

---

## Format Validation

✅ All tasks follow checklist format: `- [ ] TXXX [P] Description with file path`
✅ Task IDs are sequential (T001-T125)
✅ Parallelizable tasks marked with [P]
✅ File paths included in all implementation tasks
✅ Dependencies clearly documented
✅ Acceptance criteria defined for each phase

---

**Document Version**: 1.0
**Status**: Ready for Implementation
**Next Action**: Begin Phase 1 (Setup & Dependencies)
