"""FastMCP server for PostgreSQL natural language query interface.

This module implements the MCP server using FastMCP, exposing the query
functionality as an MCP tool. It includes complete lifespan management for
initializing and cleaning up all components.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from asyncpg import Pool
from mcp.server.fastmcp import FastMCP

from pg_mcp.cache.schema_cache import SchemaCache
from pg_mcp.config.settings import Settings
from pg_mcp.db.pool import close_pools, create_pool
from pg_mcp.models.query import QueryRequest, QueryResponse, ReturnType
from pg_mcp.observability.logging import configure_logging, get_logger
from pg_mcp.observability.metrics import MetricsCollector
from pg_mcp.resilience.circuit_breaker import CircuitBreaker
from pg_mcp.resilience.rate_limiter import MultiRateLimiter
from pg_mcp.services.executor_registry import ExecutorRegistry
from pg_mcp.services.orchestrator import (
    OrchestratorConfig,
    OrchestratorDependencies,
    QueryOrchestrator,
)
from pg_mcp.services.result_validator import ResultValidator
from pg_mcp.services.sql_generator import SQLGenerator
from pg_mcp.services.sql_validator import SQLValidator

logger = get_logger(__name__)

# Global state for lifespan management
_settings: Settings | None = None
_pools: dict[str, Pool] | None = None
_schema_cache: SchemaCache | None = None
_orchestrator: QueryOrchestrator | None = None
_metrics: MetricsCollector | None = None
_circuit_breaker: CircuitBreaker | None = None
_rate_limiter: MultiRateLimiter | None = None


async def _initialize_settings() -> Settings:
    """Load and configure application settings.

    Returns:
        Settings: Loaded application settings.
    """
    logger.info("Loading configuration...")
    settings = Settings()

    # Configure logging
    logger.info("Configuring logging...")
    configure_logging(
        level=settings.observability.log_level,
        log_format=settings.observability.log_format,
        enable_sensitive_filter=True,
    )

    logger.info(
        "Configuration loaded",
        extra={
            "environment": settings.environment,
            "log_level": settings.observability.log_level,
        },
    )
    return settings


async def _initialize_database_pools(settings: Settings) -> dict[str, Pool]:
    """Create database connection pools.

    Args:
        settings: Application settings.

    Returns:
        dict: Mapping of database names to connection pools.
    """
    logger.info("Creating database connection pools...")
    pools = {}
    pool = await create_pool(settings.database)
    pools[settings.database.name] = pool
    logger.info(
        f"Created connection pool for database '{settings.database.name}'",
        extra={
            "min_size": settings.database.min_pool_size,
            "max_size": settings.database.max_pool_size,
        },
    )
    return pools


async def _initialize_schema_cache(
    settings: Settings,
    pools: dict[str, Pool],
) -> SchemaCache:
    """Initialize and populate schema cache.

    Args:
        settings: Application settings.
        pools: Database connection pools.

    Returns:
        SchemaCache: Initialized schema cache.
    """
    logger.info("Initializing schema cache...")
    schema_cache = SchemaCache(settings.cache)

    for db_name, pool in pools.items():
        logger.info(f"Loading schema for database '{db_name}'...")
        schema = await schema_cache.load(db_name, pool)
        logger.info(
            f"Schema loaded for '{db_name}'",
            extra={"tables": len(schema.tables)},
        )

    return schema_cache


async def _initialize_metrics(settings: Settings) -> MetricsCollector:
    """Initialize metrics collector and HTTP server.

    Args:
        settings: Application settings.

    Returns:
        MetricsCollector: Initialized metrics collector.
    """
    logger.info("Initializing metrics collector...")
    metrics = MetricsCollector()

    if settings.observability.metrics_enabled:
        from prometheus_client import start_http_server

        start_http_server(settings.observability.metrics_port)
        logger.info(f"Metrics server started on port {settings.observability.metrics_port}")

    return metrics


async def _initialize_services(
    settings: Settings,
    pools: dict[str, Pool],
) -> dict[str, Any]:
    """Initialize all service components.

    Args:
        settings: Application settings.
        pools: Database connection pools.

    Returns:
        dict: Dictionary containing all initialized services.
    """
    logger.info("Initializing service components...")

    # SQL Generator
    sql_generator = SQLGenerator(settings.gemini)

    # SQL Validator
    sql_validator = SQLValidator(
        config=settings.security,
        blocked_tables=None,
        blocked_columns=None,
        allow_explain=False,
        database=settings.database.name,
    )

    # Executor Registry
    executor_registry = ExecutorRegistry(
        security_config=settings.security,
        db_config=settings.database,
        resilience_config=settings.resilience,
    )

    # Register all database pools
    for db_name, pool in pools.items():
        executor_registry.register_pool(db_name, pool)
        logger.info(f"Registered executor for database '{db_name}'")

    # Result Validator
    result_validator = ResultValidator(
        gemini_config=settings.gemini,
        validation_config=settings.validation,
    )

    return {
        "sql_generator": sql_generator,
        "sql_validator": sql_validator,
        "executor_registry": executor_registry,
        "result_validator": result_validator,
    }


async def _initialize_resilience_components(
    settings: Settings,
) -> tuple[CircuitBreaker, MultiRateLimiter]:
    """Initialize resilience components.

    Args:
        settings: Application settings.

    Returns:
        tuple: (CircuitBreaker, MultiRateLimiter)
    """
    logger.info("Initializing resilience components...")

    circuit_breaker = CircuitBreaker(
        failure_threshold=settings.resilience.circuit_breaker_threshold,
        recovery_timeout=settings.resilience.circuit_breaker_timeout,
    )

    rate_limiter = MultiRateLimiter(
        query_limit=10,  # Can be made configurable
        llm_limit=5,  # Can be made configurable
    )

    return circuit_breaker, rate_limiter


async def _initialize_orchestrator(
    settings: Settings,
    services: dict[str, Any],
    schema_cache: SchemaCache,
    pools: dict[str, Pool],
) -> QueryOrchestrator:
    """Create and configure query orchestrator.

    Args:
        settings: Application settings.
        services: Dictionary of initialized services.
        schema_cache: Schema cache instance.
        pools: Database connection pools.

    Returns:
        QueryOrchestrator: Configured orchestrator.
    """
    logger.info("Creating query orchestrator...")

    dependencies = OrchestratorDependencies(
        sql_generator=services["sql_generator"],
        sql_validator=services["sql_validator"],
        executor_registry=services["executor_registry"],
        result_validator=services["result_validator"],
        schema_cache=schema_cache,
        pools=pools,
    )
    config = OrchestratorConfig(
        resilience=settings.resilience,
        validation=settings.validation,
    )

    return QueryOrchestrator(dependencies=dependencies, config=config)


async def _shutdown_server(
    schema_cache: SchemaCache | None,
    pools: dict[str, Pool] | None,
) -> None:
    """Gracefully shutdown server components.

    Args:
        schema_cache: Schema cache to stop.
        pools: Database pools to close.
    """
    logger.info("Starting PostgreSQL MCP Server shutdown...")

    # Stop schema auto-refresh
    if schema_cache is not None:
        try:
            import asyncio

            await asyncio.wait_for(schema_cache.stop_auto_refresh(), timeout=3.0)
            logger.info("Schema auto-refresh stopped")
        except asyncio.TimeoutError:
            logger.warning("Schema auto-refresh stop timed out")
        except Exception as e:
            logger.warning(f"Error stopping schema auto-refresh: {e!s}")

    # Close database pools
    if pools is not None:
        try:
            await close_pools(pools, timeout=5.0)
            logger.info("Database connection pools closed")
        except Exception as e:
            logger.error(f"Error closing connection pools: {e!s}")

    logger.info("PostgreSQL MCP Server shutdown complete")


@asynccontextmanager
async def lifespan(_app: FastMCP) -> AsyncIterator[None]:
    """Lifespan context manager for server initialization and cleanup.

    This function manages the complete lifecycle of the MCP server:

    Startup:
        1. Load configuration from Settings
        2. Configure logging
        3. Create database connection pools
        4. Load schema cache for all databases
        5. Initialize metrics collector
        6. Create service components (generators, validators, executors)
        7. Initialize resilience components (circuit breaker, rate limiter)
        8. Create query orchestrator
        9. Start metrics HTTP server (optional)

    Shutdown:
        1. Stop schema auto-refresh (if enabled)
        2. Close all database connection pools
        3. Stop metrics HTTP server (if running)

    Yields:
        None

    Example:
        >>> async with lifespan():
        ...     # Server is running with all components initialized
        ...     pass
    """
    global _settings, _pools, _schema_cache, _orchestrator, _metrics
    global _circuit_breaker, _rate_limiter

    logger.info("Starting PostgreSQL MCP Server initialization...")

    try:
        # Initialize all components
        _settings = await _initialize_settings()
        _pools = await _initialize_database_pools(_settings)
        _schema_cache = await _initialize_schema_cache(_settings, _pools)
        _metrics = await _initialize_metrics(_settings)
        services = await _initialize_services(_settings, _pools)
        _circuit_breaker, _rate_limiter = await _initialize_resilience_components(_settings)
        _orchestrator = await _initialize_orchestrator(_settings, services, _schema_cache, _pools)

        logger.info("PostgreSQL MCP Server initialization complete!")
        logger.info(
            "Server ready to accept requests",
            extra={
                "databases": list(_pools.keys()),
                "cache_enabled": _settings.cache.enabled,
                "metrics_enabled": _settings.observability.metrics_enabled,
            },
        )

        yield

    finally:
        await _shutdown_server(_schema_cache, _pools)


# Create FastMCP server instance with lifespan
mcp = FastMCP("pg-mcp", lifespan=lifespan)


@mcp.tool()
async def query(
    question: str,
    database: str | None = None,
    return_type: str = "result",
) -> dict[str, Any]:
    """Execute a natural language query against PostgreSQL database.

    This tool converts natural language questions into SQL queries and executes
    them against the specified PostgreSQL database. It includes comprehensive
    security validation, result verification, and error handling.

    Args:
        question: Natural language description of the query.
            Examples:
                - "How many users registered in the last 30 days?"
                - "Show me the top 10 products by revenue"
                - "What is the average order value by country?"

        database: Target database name (optional if only one database is configured).
            If not specified and only one database is available, it will be
            automatically selected.

        return_type: Type of result to return.
            Options:
                - "sql": Return only the generated SQL query without executing it
                - "result": Execute the query and return results (default)

    Returns:
        dict: Query response containing:
            - success (bool): Whether the query succeeded
            - generated_sql (str): The generated SQL query
            - data (dict): Query results if executed (columns, rows, row_count, etc.)
            - error (dict): Error information if query failed
            - confidence (int): Confidence score (0-100) for result quality
            - tokens_used (int): Number of LLM tokens consumed

    Examples:
        >>> # Get query results
        >>> result = await query(
        ...     question="How many active users are there?",
        ...     return_type="result"
        ... )
        >>> print(result["data"]["rows"])

        >>> # Get SQL only
        >>> result = await query(
        ...     question="Count all products",
        ...     return_type="sql"
        ... )
        >>> print(result["generated_sql"])

    Raises:
        This function does not raise exceptions. All errors are captured and
        returned in the response with success=False and error details.

    Security:
        - Only SELECT queries are allowed (no INSERT, UPDATE, DELETE, DROP, etc.)
        - Dangerous PostgreSQL functions are blocked (pg_sleep, file operations, etc.)
        - Query execution timeout is enforced
        - Row count limits prevent memory exhaustion
        - All queries run in read-only transactions
    """
    global _orchestrator

    if _orchestrator is None:
        return {
            "success": False,
            "error": {
                "code": "SERVER_NOT_INITIALIZED",
                "message": "Server not initialized properly",
                "details": None,
            },
        }

    # Validate return_type
    if return_type not in ("sql", "result"):
        return {
            "success": False,
            "error": {
                "code": "INVALID_PARAMETER",
                "message": f"Invalid return_type: '{return_type}'. Must be 'sql' or 'result'.",
                "details": {"return_type": return_type},
            },
        }

    # Build request
    try:
        request = QueryRequest(
            question=question,
            database=database,
            return_type=ReturnType(return_type),
        )
    except Exception as e:
        return {
            "success": False,
            "error": {
                "code": "INVALID_REQUEST",
                "message": f"Invalid request parameters: {e!s}",
                "details": {"error": str(e)},
            },
        }

    # Execute query through orchestrator with rate limiting
    global _rate_limiter

    if _rate_limiter is None:
        return {
            "success": False,
            "error": {
                "code": "SERVER_NOT_INITIALIZED",
                "message": "Rate limiter not initialized",
                "details": None,
            },
        }

    try:
        # Apply rate limiting
        rate_limit_timeout = (
            _settings.resilience.rate_limit_timeout if _settings else 30.0
        )
        async with _rate_limiter.for_queries(timeout=rate_limit_timeout):
            response: QueryResponse = await _orchestrator.execute_query(request)
            result = response.to_dict()
            # Ensure tokens_used is always present
            if "tokens_used" not in result:
                result["tokens_used"] = 0
        return result
    except TimeoutError:
        # Rate limiter timeout
        logger.warning("Rate limiter timeout exceeded")
        max_concurrent = (
            _settings.resilience.max_concurrent if _settings else 10
        )
        return {
            "success": False,
            "error": {
                "code": "RATE_LIMIT_TIMEOUT",
                "message": (
                    "Too many concurrent requests. Please try again later."
                ),
                "details": {"max_concurrent": max_concurrent},
            },
            "tokens_used": 0,
        }
    except Exception as e:
        logger.exception("Unexpected error in query tool")
        return {
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": f"Internal server error: {e!s}",
                "details": {"error_type": type(e).__name__},
            },
            "tokens_used": 0,
        }


if __name__ == "__main__":
    """Run the server when executed directly."""
    import anyio

    anyio.run(mcp.run_stdio_async)
