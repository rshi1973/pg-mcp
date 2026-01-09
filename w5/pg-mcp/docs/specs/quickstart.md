# Quickstart Guide: Security, Observability, and Testing Features

**Feature**: Security, Observability, and Testing Enhancement
**Status**: Phase 1 Design
**Created**: 2026-01-09
**Last Updated**: 2026-01-09

---

## Overview

This guide provides quick-start instructions for using the new security, resilience, and observability features in the PostgreSQL MCP Server.

---

## Table of Contents

1. [Configuration](#configuration)
2. [Security Features](#security-features)
3. [Resilience Features](#resilience-features)
4. [Observability Features](#observability-features)
5. [Monitoring](#monitoring)
6. [Troubleshooting](#troubleshooting)

---

## Configuration

### Environment Variables

All features are configured via environment variables with sensible defaults.

#### Security Configuration

```bash
# Access Control
SECURITY_ALLOWED_TABLES=users,orders,products
SECURITY_BLOCKED_TABLES=passwords,secrets,api_keys
SECURITY_COLUMN_RESTRICTIONS='{"users": ["password_hash", "ssn"], "orders": ["credit_card"]}'

# EXPLAIN Policy
SECURITY_EXPLAIN_THRESHOLD=10000
SECURITY_MAX_QUERY_COST=100000
SECURITY_EXPLAIN_ENABLED=true

# Existing Security Settings
SECURITY_ALLOW_WRITE_OPERATIONS=false
SECURITY_BLOCKED_FUNCTIONS=pg_sleep,pg_read_file,pg_write_file
SECURITY_MAX_ROWS=10000
SECURITY_MAX_EXECUTION_TIME=30.0
```

#### Resilience Configuration

```bash
# Rate Limiting
RESILIENCE_MAX_CONCURRENT=10
RESILIENCE_RATE_LIMIT_TIMEOUT=30.0

# Retry Logic
RESILIENCE_MAX_RETRIES=3
RESILIENCE_RETRY_DELAY=1.0
RESILIENCE_BACKOFF_FACTOR=2.0

# Circuit Breaker
RESILIENCE_CIRCUIT_BREAKER_THRESHOLD=5
RESILIENCE_CIRCUIT_BREAKER_TIMEOUT=60.0
```

#### Observability Configuration

```bash
# Metrics
OBSERVABILITY_METRICS_ENABLED=true
OBSERVABILITY_METRICS_PORT=9090
OBSERVABILITY_METRICS_HOST=0.0.0.0

# Tracing
OBSERVABILITY_TRACING_ENABLED=false
OBSERVABILITY_TRACING_ENDPOINT=http://localhost:4317
OBSERVABILITY_TRACING_SAMPLE_RATE=1.0

# Logging
OBSERVABILITY_LOG_LEVEL=INFO
OBSERVABILITY_LOG_FORMAT=json
```

### Configuration File Example

Create a `.env` file in your project root:

```env
# Database
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=mydb
DATABASE_USER=postgres
DATABASE_PASSWORD=secret

# Gemini API
GEMINI_API_KEY=your-api-key-here
GEMINI_MODEL=gemini-2.0-flash-exp

# Security
SECURITY_ALLOWED_TABLES=users,orders,products
SECURITY_BLOCKED_TABLES=passwords,secrets
SECURITY_EXPLAIN_ENABLED=true
SECURITY_MAX_QUERY_COST=100000

# Resilience
RESILIENCE_MAX_CONCURRENT=10
RESILIENCE_MAX_RETRIES=3

# Observability
OBSERVABILITY_METRICS_ENABLED=true
OBSERVABILITY_METRICS_PORT=9090
OBSERVABILITY_TRACING_ENABLED=false
```

---

## Security Features

### 1. Table Access Control

**Purpose**: Restrict access to specific tables.

**Configuration**:
```bash
# Whitelist approach (only allow specific tables)
SECURITY_ALLOWED_TABLES=users,orders,products

# Blacklist approach (block specific tables)
SECURITY_BLOCKED_TABLES=passwords,secrets,api_keys

# Combined approach (whitelist + blacklist)
SECURITY_ALLOWED_TABLES=users,orders,products
SECURITY_BLOCKED_TABLES=users_backup,orders_archive
```

**Behavior**:
- If `ALLOWED_TABLES` is empty: All tables allowed (except blocked)
- If `ALLOWED_TABLES` is set: Only listed tables allowed
- `BLOCKED_TABLES` always takes precedence

**Example**:
```python
# This query will be blocked if "passwords" is in BLOCKED_TABLES
"SELECT * FROM passwords"

# This query will be allowed if "users" is in ALLOWED_TABLES
"SELECT id, name FROM users"
```

### 2. Column Access Control

**Purpose**: Restrict access to sensitive columns within allowed tables.

**Configuration**:
```bash
# JSON format: {"table": ["column1", "column2"]}
SECURITY_COLUMN_RESTRICTIONS='{"users": ["password_hash", "ssn"], "orders": ["credit_card"]}'
```

**Example**:
```python
# This query will be blocked (password_hash is restricted)
"SELECT id, name, password_hash FROM users"

# This query will be allowed
"SELECT id, name, email FROM users"
```

### 3. Query Cost Validation (EXPLAIN Policy)

**Purpose**: Prevent expensive queries from consuming excessive resources.

**Configuration**:
```bash
# Enable EXPLAIN policy
SECURITY_EXPLAIN_ENABLED=true

# Complexity threshold (queries above this are checked)
SECURITY_EXPLAIN_THRESHOLD=10000

# Maximum allowed cost
SECURITY_MAX_QUERY_COST=100000
```

**How It Works**:
1. Query complexity is evaluated using heuristics (JOINs, subqueries, etc.)
2. If complexity exceeds threshold, `EXPLAIN` is run
3. If estimated cost exceeds `MAX_QUERY_COST`, query is rejected

**Example**:
```python
# Simple query - no EXPLAIN check
"SELECT * FROM users WHERE id = 1"

# Complex query - EXPLAIN check performed
"SELECT u.*, o.* FROM users u JOIN orders o ON u.id = o.user_id"
```

---

## Resilience Features

### 1. Rate Limiting

**Purpose**: Limit concurrent requests to prevent resource exhaustion.

**Configuration**:
```bash
# Maximum concurrent requests
RESILIENCE_MAX_CONCURRENT=10

# Timeout waiting for slot (seconds)
RESILIENCE_RATE_LIMIT_TIMEOUT=30.0
```

**Behavior**:
- Requests beyond `MAX_CONCURRENT` wait for available slot
- If wait exceeds `RATE_LIMIT_TIMEOUT`, request is rejected
- Metrics track active requests and rejections

**Error Response**:
```json
{
  "success": false,
  "error": {
    "code": "RATE_LIMIT_TIMEOUT",
    "message": "Too many concurrent requests, please try again"
  }
}
```

### 2. Retry Logic

**Purpose**: Automatically retry transient database failures.

**Configuration**:
```bash
# Maximum retry attempts
RESILIENCE_MAX_RETRIES=3

# Initial retry delay (seconds)
RESILIENCE_RETRY_DELAY=1.0

# Exponential backoff factor
RESILIENCE_BACKOFF_FACTOR=2.0
```

**Retry Schedule**:
- Attempt 1: Immediate
- Attempt 2: After 1.0s
- Attempt 3: After 2.0s (1.0 * 2^1)
- Attempt 4: After 4.0s (1.0 * 2^2)

**Transient Errors** (automatically retried):
- Connection errors
- Too many connections
- Temporary unavailability

**Non-Transient Errors** (not retried):
- SQL syntax errors
- Security violations
- Permission errors

### 3. Circuit Breaker

**Purpose**: Prevent cascading failures by temporarily blocking requests to failing services.

**Configuration**:
```bash
# Failures before circuit opens
RESILIENCE_CIRCUIT_BREAKER_THRESHOLD=5

# Time before attempting recovery (seconds)
RESILIENCE_CIRCUIT_BREAKER_TIMEOUT=60.0
```

**States**:
- **CLOSED**: Normal operation, requests allowed
- **OPEN**: Too many failures, requests blocked
- **HALF_OPEN**: Testing recovery, limited requests allowed

**Behavior**:
- After `THRESHOLD` consecutive failures, circuit opens
- Requests blocked for `TIMEOUT` seconds
- After timeout, circuit enters HALF_OPEN state
- One successful request closes circuit

---

## Observability Features

### 1. Prometheus Metrics

**Purpose**: Expose operational metrics for monitoring.

**Configuration**:
```bash
# Enable metrics
OBSERVABILITY_METRICS_ENABLED=true

# HTTP server port
OBSERVABILITY_METRICS_PORT=9090

# Bind address
OBSERVABILITY_METRICS_HOST=0.0.0.0
```

**Accessing Metrics**:
```bash
# View metrics in browser
open http://localhost:9090/metrics

# Scrape with curl
curl http://localhost:9090/metrics
```

**Available Metrics**:

| Metric | Type | Description | Labels |
|--------|------|-------------|--------|
| `pg_mcp_query_requests_total` | Counter | Total query requests | database, status |
| `pg_mcp_query_duration_seconds` | Histogram | Query duration | database, operation |
| `pg_mcp_database_connections_active` | Gauge | Active connections | database |
| `pg_mcp_rate_limiter_active_requests` | Gauge | Active rate-limited requests | - |
| `pg_mcp_rate_limiter_rejections_total` | Counter | Rate limiter rejections | - |
| `pg_mcp_circuit_breaker_state` | Gauge | Circuit breaker state | database, resource |
| `pg_mcp_llm_generation_duration_seconds` | Histogram | LLM generation time | model |
| `pg_mcp_llm_tokens_used_total` | Counter | LLM tokens used | model, type |

**Example Queries** (PromQL):
```promql
# Request rate per database
rate(pg_mcp_query_requests_total{status="success"}[5m])

# 95th percentile query duration
histogram_quantile(0.95, pg_mcp_query_duration_seconds_bucket)

# Circuit breaker open count
sum(pg_mcp_circuit_breaker_state == 1)
```

### 2. Distributed Tracing

**Purpose**: Track requests across components for debugging and performance analysis.

**Configuration**:
```bash
# Enable tracing
OBSERVABILITY_TRACING_ENABLED=true

# OTLP endpoint (Jaeger, Tempo, etc.)
OBSERVABILITY_TRACING_ENDPOINT=http://localhost:4317

# Sampling rate (0.0-1.0)
OBSERVABILITY_TRACING_SAMPLE_RATE=0.1
```

**Setup with Jaeger** (local development):
```bash
# Start Jaeger all-in-one
docker run -d --name jaeger \
  -p 16686:16686 \
  -p 4317:4317 \
  jaegertracing/all-in-one:latest

# Configure tracing
export OBSERVABILITY_TRACING_ENABLED=true
export OBSERVABILITY_TRACING_ENDPOINT=http://localhost:4317

# View traces
open http://localhost:16686
```

**Trace Hierarchy**:
```
query.execute (root span)
├── sql.generate
│   └── llm.call
├── sql.validate
│   └── sql.parse
├── sql.execute
│   └── database.query
└── result.validate
    └── llm.call
```

**Span Attributes**:
- `db.system`: "postgresql"
- `db.name`: Database name
- `db.statement`: SQL query (truncated)
- `db.operation`: "SELECT", "INSERT", etc.
- `llm.model`: Model name
- `pg_mcp.request_id`: Request ID
- `pg_mcp.confidence_score`: Result confidence

### 3. Structured Logging

**Purpose**: Consistent, parseable log output.

**Configuration**:
```bash
# Log level
OBSERVABILITY_LOG_LEVEL=INFO

# Log format (json or text)
OBSERVABILITY_LOG_FORMAT=json
```

**Log Levels**:
- `DEBUG`: Detailed debugging information
- `INFO`: General informational messages
- `WARNING`: Warning messages (non-critical issues)
- `ERROR`: Error messages (failures)
- `CRITICAL`: Critical errors (system failures)

**JSON Log Example**:
```json
{
  "timestamp": "2026-01-09T10:30:45.123Z",
  "level": "INFO",
  "message": "Query executed successfully",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "database": "mydb",
  "row_count": 42,
  "execution_time_ms": 123.45
}
```

---

## Monitoring

### Prometheus + Grafana Setup

**1. Start Prometheus**:
```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'pg-mcp'
    static_configs:
      - targets: ['localhost:9090']
```

```bash
docker run -d --name prometheus \
  -p 9091:9090 \
  -v $(pwd)/prometheus.yml:/etc/prometheus/prometheus.yml \
  prom/prometheus
```

**2. Start Grafana**:
```bash
docker run -d --name grafana \
  -p 3000:3000 \
  grafana/grafana
```

**3. Add Prometheus Data Source**:
- URL: `http://localhost:9091`
- Access: Browser

**4. Import Dashboard**:
- Use dashboard ID: 1860 (Node Exporter Full)
- Customize for pg-mcp metrics

### Key Metrics to Monitor

**Performance**:
- Query duration (p50, p95, p99)
- Request rate
- Error rate

**Resilience**:
- Rate limiter active requests
- Rate limiter rejections
- Circuit breaker state

**Resources**:
- Active database connections
- LLM token usage
- Memory usage

### Alerting Rules

**Example Prometheus Alerts**:
```yaml
groups:
  - name: pg-mcp
    rules:
      - alert: HighErrorRate
        expr: rate(pg_mcp_query_requests_total{status="error"}[5m]) > 0.05
        for: 5m
        annotations:
          summary: "High error rate detected"

      - alert: CircuitBreakerOpen
        expr: pg_mcp_circuit_breaker_state == 1
        for: 2m
        annotations:
          summary: "Circuit breaker is open"

      - alert: RateLimiterSaturated
        expr: pg_mcp_rate_limiter_active_requests >= pg_mcp_rate_limiter_max_concurrent
        for: 5m
        annotations:
          summary: "Rate limiter is saturated"
```

---

## Troubleshooting

### Common Issues

#### 1. Rate Limiter Timeout

**Symptom**: Requests fail with "Rate limit timeout" error.

**Cause**: Too many concurrent requests.

**Solutions**:
- Increase `RESILIENCE_MAX_CONCURRENT`
- Increase `RESILIENCE_RATE_LIMIT_TIMEOUT`
- Reduce request rate from clients

**Check Metrics**:
```promql
pg_mcp_rate_limiter_active_requests
pg_mcp_rate_limiter_rejections_total
```

#### 2. Circuit Breaker Open

**Symptom**: Requests fail with "Service temporarily unavailable (circuit breaker open)".

**Cause**: Too many consecutive failures.

**Solutions**:
- Check database connectivity
- Check LLM API availability
- Wait for circuit breaker timeout
- Manually reset circuit breaker (if implemented)

**Check Metrics**:
```promql
pg_mcp_circuit_breaker_state{database="mydb"}
```

#### 3. Access Control Violations

**Symptom**: Queries fail with "Access denied to table/column" error.

**Cause**: Query accesses restricted tables or columns.

**Solutions**:
- Review `SECURITY_ALLOWED_TABLES` and `SECURITY_BLOCKED_TABLES`
- Review `SECURITY_COLUMN_RESTRICTIONS`
- Adjust access control policy
- Modify query to avoid restricted resources

**Check Logs**:
```bash
# Search for security violations
grep "SecurityViolationError" logs/*.log
```

#### 4. Query Cost Exceeded

**Symptom**: Queries fail with "Query cost exceeds maximum" error.

**Cause**: Query is too expensive.

**Solutions**:
- Optimize query (add indexes, reduce JOINs)
- Increase `SECURITY_MAX_QUERY_COST`
- Disable EXPLAIN policy (`SECURITY_EXPLAIN_ENABLED=false`)

**Check Logs**:
```bash
# Find expensive queries
grep "Query cost" logs/*.log
```

#### 5. Metrics Not Available

**Symptom**: Cannot access `http://localhost:9090/metrics`.

**Cause**: Metrics server not started or wrong port.

**Solutions**:
- Check `OBSERVABILITY_METRICS_ENABLED=true`
- Check `OBSERVABILITY_METRICS_PORT` matches URL
- Check firewall rules
- Check server logs for startup errors

**Verify**:
```bash
# Check if port is listening
lsof -i :9090

# Check server logs
tail -f logs/pg-mcp.log | grep "metrics"
```

#### 6. Traces Not Appearing

**Symptom**: No traces in Jaeger/Tempo.

**Cause**: Tracing not enabled or wrong endpoint.

**Solutions**:
- Check `OBSERVABILITY_TRACING_ENABLED=true`
- Check `OBSERVABILITY_TRACING_ENDPOINT` is correct
- Check OTLP collector is running
- Check sampling rate (`OBSERVABILITY_TRACING_SAMPLE_RATE`)

**Verify**:
```bash
# Test OTLP endpoint
curl http://localhost:4317

# Check tracing logs
tail -f logs/pg-mcp.log | grep "tracing"
```

### Debug Mode

Enable debug logging for detailed troubleshooting:

```bash
OBSERVABILITY_LOG_LEVEL=DEBUG
OBSERVABILITY_LOG_FORMAT=text
```

### Health Check Endpoints

**Metrics Endpoint**:
```bash
curl http://localhost:9090/metrics
```

**Expected Response**:
```
# HELP pg_mcp_query_requests_total Total number of query requests
# TYPE pg_mcp_query_requests_total counter
pg_mcp_query_requests_total{database="mydb",status="success"} 42.0
...
```

---

## Best Practices

### Security

1. **Start Restrictive**: Begin with strict access control, relax as needed
2. **Monitor Violations**: Track security violations in logs and metrics
3. **Regular Audits**: Review access control policies regularly
4. **Cost Limits**: Set conservative `MAX_QUERY_COST` initially

### Resilience

1. **Tune Rate Limits**: Adjust `MAX_CONCURRENT` based on load testing
2. **Monitor Circuit Breakers**: Alert on circuit breaker state changes
3. **Retry Budgets**: Balance retries vs. latency (3 retries is reasonable)
4. **Graceful Degradation**: Handle rate limit errors gracefully in clients

### Observability

1. **Enable Metrics**: Always enable metrics in production
2. **Selective Tracing**: Use sampling (10-20%) in production
3. **Structured Logs**: Use JSON format for production
4. **Dashboard First**: Create dashboards before issues arise

### Performance

1. **Baseline Metrics**: Establish performance baselines
2. **Monitor Overhead**: Track metrics collection overhead
3. **Optimize Queries**: Use EXPLAIN to identify expensive queries
4. **Connection Pooling**: Ensure proper pool sizing

---

## Next Steps

1. **Configure**: Set environment variables for your environment
2. **Test**: Verify features work as expected
3. **Monitor**: Set up Prometheus and Grafana
4. **Alert**: Configure alerting rules
5. **Iterate**: Adjust configuration based on monitoring data

---

## Support

For issues or questions:
- Check logs: `logs/pg-mcp.log`
- Check metrics: `http://localhost:9090/metrics`
- Review documentation: `docs/specs/`
- File issue: GitHub repository

---

**Document Version**: 1.0
**Status**: Complete
**Next**: Agent Context Update
