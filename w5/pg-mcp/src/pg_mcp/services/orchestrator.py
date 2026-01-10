"""Query orchestrator for coordinating the complete query flow.

This module provides the QueryOrchestrator class that coordinates all components
of the query processing pipeline: SQL generation, validation, execution, and result
validation. It implements retry logic, error handling, and request tracking.
"""

import logging
import uuid
from typing import TYPE_CHECKING, Any

from asyncpg import Pool

from dataclasses import dataclass

from pg_mcp.cache.schema_cache import SchemaCache
from pg_mcp.config.settings import ResilienceConfig, ValidationConfig
from pg_mcp.models.errors import (
    DatabaseError,
    ErrorCode,
    LLMError,
    PgMcpError,
    SchemaLoadError,
    SecurityViolationError,
    SQLParseError,
)
from pg_mcp.models.query import (
    ErrorDetail,
    QueryRequest,
    QueryResponse,
    QueryResult,
    ReturnType,
    ValidationResult,
)
from pg_mcp.resilience.circuit_breaker import CircuitBreaker
from pg_mcp.services.executor_registry import ExecutorRegistry
from pg_mcp.services.result_validator import ResultValidator
from pg_mcp.services.sql_executor import SQLExecutor
from pg_mcp.services.sql_generator import SQLGenerator
from pg_mcp.services.sql_validator import SQLValidator

if TYPE_CHECKING:
    from pg_mcp.models.schema import DatabaseSchema

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OrchestratorDependencies:
    """Container for QueryOrchestrator dependencies to reduce parameter count.

    This dataclass groups all service dependencies required by QueryOrchestrator,
    reducing the constructor parameter count from 9 to 2.

    Example:
        >>> dependencies = OrchestratorDependencies(
        ...     sql_generator=generator,
        ...     sql_validator=validator,
        ...     executor_registry=registry,
        ...     result_validator=result_validator,
        ...     schema_cache=cache,
        ...     pools=pools,
        ... )
        >>> orchestrator = QueryOrchestrator(
        ...     dependencies=dependencies,
        ...     config=config,
        ... )
    """

    sql_generator: "SQLGenerator"
    sql_validator: "SQLValidator"
    executor_registry: "ExecutorRegistry"
    result_validator: "ResultValidator"
    schema_cache: SchemaCache
    pools: dict[str, Pool]


@dataclass(frozen=True)
class OrchestratorConfig:
    """Container for QueryOrchestrator configuration to reduce parameter count.

    This dataclass groups all configuration objects required by QueryOrchestrator.

    Example:
        >>> config = OrchestratorConfig(
        ...     resilience=resilience_config,
        ...     validation=validation_config,
        ... )
        >>> orchestrator = QueryOrchestrator(
        ...     dependencies=dependencies,
        ...     config=config,
        ... )
    """

    resilience: ResilienceConfig
    validation: ValidationConfig


class QueryOrchestrator:
    """Orchestrates the complete query processing pipeline.

    This class coordinates SQL generation, validation, execution, and result
    validation. It implements retry logic with error feedback, circuit breaker
    pattern for fault tolerance, and comprehensive error handling.

    Example:
        >>> orchestrator = QueryOrchestrator(
        ...     sql_generator=generator,
        ...     sql_validator=validator,
        ...     sql_executor=executor,
        ...     result_validator=result_validator,
        ...     schema_cache=cache,
        ...     pools={"mydb": pool},
        ...     resilience_config=resilience_config,
        ...     validation_config=validation_config,
        ... )
        >>> response = await orchestrator.execute_query(QueryRequest(
        ...     question="How many users?",
        ...     database="mydb"
        ... ))
    """

    def __init__(
        self,
        dependencies: OrchestratorDependencies,
        config: OrchestratorConfig,
    ) -> None:
        """Initialize query orchestrator.

        Args:
            dependencies: Container with all service dependencies.
            config: Container with all configuration settings.
        """
        self.sql_generator = dependencies.sql_generator
        self.sql_validator = dependencies.sql_validator
        self.executor_registry = dependencies.executor_registry
        self.result_validator = dependencies.result_validator
        self.schema_cache = dependencies.schema_cache
        self.pools = dependencies.pools
        self.resilience_config = config.resilience
        self.validation_config = config.validation

        # Create circuit breaker for LLM calls
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=config.resilience.circuit_breaker_threshold,
            recovery_timeout=config.resilience.circuit_breaker_timeout,
        )

    async def execute_query(self, request: QueryRequest) -> QueryResponse:
        """Execute complete query flow from question to results.

        This method orchestrates the entire pipeline:
        1. Generate request_id for tracking
        2. Resolve and validate database name
        3. Load schema from cache
        4. Generate and validate SQL with retry logic
        5. Execute SQL (if return_type == RESULT)
        6. Validate results (optional)
        7. Return structured response

        Args:
            request: Query request containing question and parameters.

        Returns:
            QueryResponse: Complete response with SQL, results, or error information.
                Note: The response.data.row_count represents the number of rows
                actually returned, which may be less than the total number of rows
                in the database if SECURITY_MAX_ROWS limit is applied. The total
                number of rows in the database (before limiting) is logged but
                not included in the response.

        Example:
            >>> response = await orchestrator.execute_query(
            ...     QueryRequest(question="Count all users", return_type="result")
            ... )
            >>> if response.success:
            ...     print(f"Found {response.data.row_count} rows")
        """
        request_id = str(uuid.uuid4())
        logger.info(
            "Starting query execution",
            extra={"request_id": request_id, "question": request.question[:100]},
        )

        try:
            # Step 1: Load schema
            database_name = self._resolve_database(request.database)
            schema = await self._load_schema(database_name, request_id)

            # Step 2: Generate and validate SQL
            generated_sql, validation_result, tokens_used = await self._generate_sql_with_retry(
                question=request.question,
                schema=schema,
                request_id=request_id,
            )

            # Step 3: Handle SQL-only requests
            if request.return_type == ReturnType.SQL:
                return self._build_sql_only_response(
                    generated_sql, validation_result, tokens_used, request_id
                )

            # Step 4: Execute and validate
            query_result, confidence = await self._execute_and_validate(
                database_name, generated_sql, request.question, request_id
            )

            # Step 5: Build success response
            return self._build_success_response(
                generated_sql, validation_result, query_result, confidence, tokens_used
            )

        except PgMcpError as e:
            return self._build_error_response(e, request_id)
        except Exception as e:
            return self._build_unexpected_error_response(e, request_id)

    async def _load_schema(self, database_name: str, request_id: str) -> "DatabaseSchema":
        """Load schema from cache or database.

        Args:
            database_name: Name of the database.
            request_id: Request ID for tracking.

        Returns:
            DatabaseSchema: Loaded schema with table and column information.

        Raises:
            DatabaseError: If pool is not available.
            SchemaLoadError: If schema loading fails.
        """
        logger.debug(
            "Resolved database",
            extra={"request_id": request_id, "database": database_name},
        )

        schema = await self.schema_cache.get(database_name)
        if schema is None:
            # Schema not in cache, load it
            pool = self.pools.get(database_name)
            if pool is None:
                raise DatabaseError(
                    message=f"No connection pool available for database '{database_name}'",
                    details={"database": database_name},
                )
            try:
                schema = await self.schema_cache.load(database_name, pool)
            except Exception as e:
                raise SchemaLoadError(
                    message=f"Failed to load schema for database '{database_name}': {e!s}",
                    details={"database": database_name, "error": str(e)},
                ) from e

        logger.debug(
            "Schema loaded",
            extra={
                "request_id": request_id,
                "database": database_name,
                "tables": len(schema.tables),
            },
        )
        return schema

    def _build_sql_only_response(
        self,
        generated_sql: str,
        validation_result: ValidationResult,
        tokens_used: int | None,
        request_id: str,
    ) -> QueryResponse:
        """Build response for SQL-only requests.

        Args:
            generated_sql: Generated SQL query.
            validation_result: Validation result.
            tokens_used: Number of tokens used.
            request_id: Request ID for tracking.

        Returns:
            QueryResponse: Response with SQL only.
        """
        logger.info(
            "Returning SQL only",
            extra={"request_id": request_id, "sql_length": len(generated_sql)},
        )
        return QueryResponse(
            success=True,
            generated_sql=generated_sql,
            validation=validation_result,
            data=None,
            error=None,
            confidence=100,
            tokens_used=tokens_used,
        )

    async def _execute_and_validate(
        self,
        database_name: str,
        generated_sql: str,
        question: str,
        request_id: str,
    ) -> tuple[QueryResult, int]:
        """Execute SQL and validate results.

        Args:
            database_name: Name of the database.
            generated_sql: Generated SQL query.
            question: Original user question.
            request_id: Request ID for tracking.

        Returns:
            tuple: (QueryResult, confidence_score)
        """
        logger.debug("Executing SQL", extra={"request_id": request_id})
        start_time = self._get_current_time_ms()

        # Execute with circuit breaker protection
        results, total_count = await self.executor_registry.execute_with_circuit_breaker(
            database=database_name,
            sql=generated_sql,
        )

        execution_time_ms = self._get_current_time_ms() - start_time
        
        # Log execution results with clear distinction between returned and total rows
        returned_rows = len(results)
        rows_truncated = total_count > returned_rows
        logger.info(
            "SQL executed successfully",
            extra={
                "request_id": request_id,
                "returned_rows": returned_rows,  # Number of rows actually returned
                "total_rows_in_db": total_count,  # Total rows in database (before limiting)
                "rows_truncated": rows_truncated,  # Whether results were limited
                "execution_time_ms": execution_time_ms,
            },
        )

        # Validate results (non-blocking)
        confidence = await self._validate_results_safely(
            question=question,
            sql=generated_sql,
            results=results,
            row_count=total_count,
            request_id=request_id,
        )

        # Build query result
        query_result = QueryResult(
            columns=list(results[0].keys()) if results else [],
            rows=results,
            row_count=len(results),
            execution_time_ms=execution_time_ms,
        )

        return query_result, confidence

    def _build_success_response(
        self,
        generated_sql: str,
        validation_result: ValidationResult,
        query_result: QueryResult,
        confidence: int,
        tokens_used: int | None,
    ) -> QueryResponse:
        """Build successful query response.

        Args:
            generated_sql: Generated SQL query.
            validation_result: Validation result.
            query_result: Query execution result.
            confidence: Result confidence score.
            tokens_used: Number of tokens used.

        Returns:
            QueryResponse: Successful response.
        """
        return QueryResponse(
            success=True,
            generated_sql=generated_sql,
            validation=validation_result,
            data=query_result,
            error=None,
            confidence=confidence,
            tokens_used=tokens_used,
        )

    def _build_error_response(self, error: PgMcpError, request_id: str) -> QueryResponse:
        """Build error response for known application errors.

        Args:
            error: Application error.
            request_id: Request ID for tracking.

        Returns:
            QueryResponse: Error response.
        """
        logger.warning(
            "Query execution failed with known error",
            extra={
                "request_id": request_id,
                "error_code": error.code,
                "error_message": str(error),
            },
        )
        return QueryResponse(
            success=False,
            generated_sql=None,
            validation=None,
            data=None,
            error=ErrorDetail(
                code=error.code.value,
                message=error.message,
                details=error.details,
            ),
            confidence=0,
            tokens_used=None,
        )

    def _build_unexpected_error_response(
        self, error: Exception, request_id: str
    ) -> QueryResponse:
        """Build error response for unexpected errors.

        Args:
            error: Unexpected error.
            request_id: Request ID for tracking.

        Returns:
            QueryResponse: Error response.
        """
        logger.exception(
            "Query execution failed with unexpected error",
            extra={"request_id": request_id},
        )
        return QueryResponse(
            success=False,
            generated_sql=None,
            validation=None,
            data=None,
            error=ErrorDetail(
                code=ErrorCode.INTERNAL_ERROR.value,
                message=f"Internal server error: {error!s}",
                details={"error_type": type(error).__name__},
            ),
            confidence=0,
            tokens_used=None,
        )

    def _resolve_database(self, database: str | None) -> str:
        """Resolve database name from request or auto-select.

        If database is specified, validate it exists.
        If not specified and only one database available, auto-select it.

        Args:
            database: Database name from request (optional).

        Returns:
            str: Resolved database name.

        Raises:
            DatabaseError: If database is invalid or cannot be auto-selected.

        Example:
            >>> name = orchestrator._resolve_database("mydb")  # Validates "mydb" exists
            >>> name = orchestrator._resolve_database(None)  # Auto-selects if only one DB
        """
        if database is not None:
            # Validate specified database exists
            if database not in self.pools:
                raise DatabaseError(
                    message=f"Database '{database}' not found",
                    details={
                        "requested_database": database,
                        "available_databases": list(self.pools.keys()),
                    },
                )
            return database

        # Auto-select if only one database available
        available_dbs = list(self.pools.keys())
        if len(available_dbs) == 0:
            raise DatabaseError(
                message="No databases configured",
                details={},
            )
        if len(available_dbs) == 1:
            return available_dbs[0]

        # Multiple databases, must specify
        raise DatabaseError(
            message="Multiple databases available, please specify which to query",
            details={"available_databases": available_dbs},
        )

    async def _generate_sql_with_retry(
        self,
        question: str,
        schema: "DatabaseSchema",
        request_id: str,
    ) -> tuple[str, ValidationResult, int | None]:
        """Generate and validate SQL with retry logic on validation failures.

        This method implements a retry loop that:
        1. Checks circuit breaker state
        2. Generates SQL using LLM
        3. Validates the generated SQL
        4. On validation failure, retries with error feedback
        5. Records success/failure to circuit breaker

        Args:
            question: User's natural language question.
            schema: Database schema for context.
            request_id: Request ID for tracking.

        Returns:
            tuple: (generated_sql, validation_result, tokens_used)

        Raises:
            LLMError: If circuit breaker is open or generation fails.
            SecurityViolationError: If SQL fails validation after all retries.
            SQLParseError: If SQL cannot be parsed.

        Example:
            >>> sql, validation, tokens = await orchestrator._generate_sql_with_retry(
            ...     question="Count users",
            ...     schema=db_schema,
            ...     request_id="123",
            ... )
        """
        self._check_circuit_breaker()

        previous_sql: str | None = None
        error_feedback: str | None = None
        max_retries = self.resilience_config.max_retries
        generated_sql: str | None = None

        for attempt in range(max_retries + 1):
            try:
                # Generate SQL
                generated_sql = await self._generate_sql(
                    question=question,
                    schema=schema,
                    previous_sql=previous_sql,
                    error_feedback=error_feedback,
                    attempt=attempt,
                    request_id=request_id,
                )

                # Validate SQL (raises on failure)
                self.sql_validator.validate_or_raise(generated_sql)

                # Validation successful
                return self._build_successful_generation_result(
                    generated_sql, attempt, request_id
                )

            except (SecurityViolationError, SQLParseError) as validation_error:
                if attempt < max_retries:
                    # Capture the failed SQL for next retry (only if generation succeeded)
                    if generated_sql is not None:
                        previous_sql = generated_sql
                    error_feedback = self._handle_validation_retry(
                        validation_error, attempt, request_id
                    )
                    continue
                else:
                    self._handle_validation_failure(validation_error, attempt, request_id)
                    raise
            except (LLMError, SecurityViolationError, SQLParseError):
                raise
            except Exception as e:
                self._handle_unexpected_error(e, request_id)
                raise

        # Should not reach here, but just in case
        self.circuit_breaker.record_failure()
        raise LLMError(
            message="SQL generation failed after all retry attempts",
            details={"max_retries": max_retries},
        )

    def _check_circuit_breaker(self) -> None:
        """Check if circuit breaker allows requests.

        Raises:
            LLMError: If circuit breaker is open.
        """
        if not self.circuit_breaker.allow_request():
            raise LLMError(
                message="SQL generation service is temporarily unavailable (circuit breaker open)",
                details={
                    "circuit_state": self.circuit_breaker.state,
                    "failure_count": self.circuit_breaker.failure_count,
                },
            )

    async def _attempt_sql_generation_internal(
        self,
        question: str,
        schema: "DatabaseSchema",
        previous_sql: str | None,
        error_feedback: str | None,
        attempt: int,
        request_id: str,
    ) -> tuple[str, tuple[str, ValidationResult, int | None]]:
        """Deprecated: Use _generate_sql and _build_successful_generation_result instead."""
        # This method is no longer used but kept for reference
        raise NotImplementedError("Use _generate_sql instead")

    async def _generate_sql(
        self,
        question: str,
        schema: "DatabaseSchema",
        previous_sql: str | None,
        error_feedback: str | None,
        attempt: int,
        request_id: str,
    ) -> str:
        """Generate SQL from natural language question.

        Args:
            question: User's natural language question.
            schema: Database schema for context.
            previous_sql: Previously generated SQL that failed (for retry).
            error_feedback: Error message from previous attempt.
            attempt: Current attempt number (0-indexed).
            request_id: Request ID for tracking.

        Returns:
            str: Generated SQL query.

        Raises:
            LLMError: If SQL generation fails.
        """
        logger.debug(
            "Generating SQL",
            extra={
                "request_id": request_id,
                "attempt": attempt + 1,
                "max_retries": self.resilience_config.max_retries + 1,
            },
        )

        # Generate SQL
        generated_sql = await self.sql_generator.generate(
            question=question,
            schema=schema,
            previous_attempt=previous_sql,
            error_feedback=error_feedback,
        )

        logger.debug(
            "SQL generated",
            extra={
                "request_id": request_id,
                "sql_length": len(generated_sql),
            },
        )

        return generated_sql

    def _build_successful_generation_result(
        self, generated_sql: str, attempt: int, request_id: str
    ) -> tuple[str, ValidationResult, int | None]:
        """Build result for successful SQL generation and validation.

        Args:
            generated_sql: The validated SQL query.
            attempt: Current attempt number (0-indexed).
            request_id: Request ID for tracking.

        Returns:
            tuple: (generated_sql, validation_result, tokens_used)
        """
        self.circuit_breaker.record_success()
        logger.info(
            "SQL generated and validated successfully",
            extra={
                "request_id": request_id,
                "attempts": attempt + 1,
            },
        )

        # Build validation result
        validation_result = ValidationResult(
            is_valid=True,
            is_select=True,
            allows_data_modification=False,
            uses_blocked_functions=[],
            error_message=None,
        )

        # Note: tokens_used would come from LLM response metadata if available
        tokens_used: int | None = None

        return generated_sql, validation_result, tokens_used

    def _handle_validation_retry(
        self,
        validation_error: SecurityViolationError | SQLParseError,
        attempt: int,
        request_id: str,
    ) -> str:
        """Handle validation failure and prepare for retry.

        Args:
            validation_error: The validation error that occurred.
            attempt: Current attempt number (0-indexed).
            request_id: Request ID for tracking.

        Returns:
            str: Error feedback for next retry.
        """
        logger.warning(
            "SQL validation failed, retrying with feedback",
            extra={
                "request_id": request_id,
                "attempt": attempt + 1,
                "error": str(validation_error),
            },
        )
        return str(validation_error)

    def _handle_validation_failure(
        self,
        validation_error: SecurityViolationError | SQLParseError,
        attempt: int,
        request_id: str,
    ) -> None:
        """Handle final validation failure after all retries.

        Args:
            validation_error: The validation error that occurred.
            attempt: Current attempt number (0-indexed).
            request_id: Request ID for tracking.
        """
        self.circuit_breaker.record_failure()
        logger.error(
            "SQL validation failed after all retries",
            extra={
                "request_id": request_id,
                "attempts": attempt + 1,
                "error": str(validation_error),
            },
        )

    def _handle_unexpected_error(self, error: Exception, request_id: str) -> None:
        """Handle unexpected error during SQL generation.

        Args:
            error: The unexpected error that occurred.
            request_id: Request ID for tracking.

        Raises:
            LLMError: Wrapped unexpected error.
        """
        self.circuit_breaker.record_failure()
        logger.exception(
            "Unexpected error during SQL generation",
            extra={"request_id": request_id},
        )
        raise LLMError(
            message=f"SQL generation failed unexpectedly: {error!s}",
            details={"error_type": type(error).__name__},
        ) from error

    async def _validate_results_safely(
        self,
        question: str,
        sql: str,
        results: list[dict[str, Any]],
        row_count: int,
        request_id: str,
    ) -> int:
        """Validate query results with error handling (non-blocking).

        This method attempts to validate results using LLM, but failures
        don't cause the overall query to fail. Returns a confidence score.

        Args:
            question: User's original question.
            sql: Generated SQL query.
            results: Query results.
            row_count: Total row count.
            request_id: Request ID for tracking.

        Returns:
            int: Confidence score (0-100). Returns 100 if validation disabled/fails.

        Example:
            >>> confidence = await orchestrator._validate_results_safely(
            ...     question="Count users",
            ...     sql="SELECT COUNT(*) FROM users",
            ...     results=[{"count": 42}],
            ...     row_count=1,
            ...     request_id="123",
            ... )
        """
        if not self.validation_config.enabled:
            return 100

        try:
            logger.debug(
                "Validating results",
                extra={"request_id": request_id},
            )

            validation_result = await self.result_validator.validate(
                question=question,
                sql=sql,
                results=results,
                row_count=row_count,
            )

            logger.info(
                "Result validation completed",
                extra={
                    "request_id": request_id,
                    "confidence": validation_result.confidence,
                    "is_acceptable": validation_result.is_acceptable,
                },
            )

            return validation_result.confidence

        except Exception as e:
            # Log but don't fail the query
            logger.warning(
                "Result validation failed, continuing with default confidence",
                extra={
                    "request_id": request_id,
                    "error": str(e),
                },
            )
            return 100  # Default to high confidence if validation fails

    @staticmethod
    def _get_current_time_ms() -> float:
        """Get current time in milliseconds.

        Returns:
            float: Current time in milliseconds since epoch.
        """
        import time

        return time.time() * 1000
