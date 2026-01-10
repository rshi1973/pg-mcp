"""Executor registry for managing database-specific SQL executors.

This module provides the ExecutorRegistry class that manages per-database
SQL executor instances with associated circuit breakers for fault tolerance.
"""

from typing import Any

from asyncpg import Pool

from pg_mcp.config.settings import DatabaseConfig, ResilienceConfig, SecurityConfig
from pg_mcp.models.errors import DatabaseError
from pg_mcp.resilience.circuit_breaker import CircuitBreaker
from pg_mcp.services.sql_executor import SQLExecutor


class ExecutorRegistry:
    """Registry for managing database-specific SQL executors.

    This class maintains separate SQLExecutor instances for each database,
    along with associated circuit breakers for fault tolerance. Executors
    are created lazily on first access and cached for reuse.

    Example:
        >>> registry = ExecutorRegistry(security_config, db_config, resilience_config)
        >>> registry.register_pool("mydb", pool)
        >>> executor = registry.get_executor("mydb")
        >>> results, count = await executor.execute(sql)
    """

    def __init__(
        self,
        security_config: SecurityConfig,
        db_config: DatabaseConfig,
        resilience_config: ResilienceConfig,
    ) -> None:
        """Initialize executor registry.

        Args:
            security_config: Security configuration shared across executors.
            db_config: Database configuration shared across executors.
            resilience_config: Resilience configuration for circuit breakers.
        """
        self._security_config = security_config
        self._db_config = db_config
        self._resilience_config = resilience_config

        self._pools: dict[str, Pool] = {}
        self._executors: dict[str, SQLExecutor] = {}
        self._circuit_breakers: dict[str, CircuitBreaker] = {}

    def register_pool(self, database: str, pool: Pool) -> None:
        """Register a connection pool for a database.

        Args:
            database: Database name.
            pool: asyncpg connection pool.

        Note:
            Must be called before get_executor() for the database.
        """
        self._pools[database] = pool

    def get_executor(self, database: str) -> SQLExecutor:
        """Get or create executor for database.

        Args:
            database: Database name.

        Returns:
            SQLExecutor instance for the database.

        Raises:
            DatabaseError: If database not found in pools.

        Note:
            Executors are created lazily on first access and cached.
        """
        if database not in self._pools:
            raise DatabaseError(
                message=f"Database '{database}' not found",
                details={
                    "requested_database": database,
                    "available_databases": list(self._pools.keys()),
                },
            )

        # Create executor if not already cached
        if database not in self._executors:
            pool = self._pools[database]
            executor = SQLExecutor(
                pool=pool,
                security_config=self._security_config,
                db_config=self._db_config,
                resilience_config=self._resilience_config,
            )
            self._executors[database] = executor

            # Create circuit breaker for this database
            circuit_breaker = CircuitBreaker(
                failure_threshold=self._resilience_config.circuit_breaker_threshold,
                recovery_timeout=self._resilience_config.circuit_breaker_timeout,
            )
            self._circuit_breakers[database] = circuit_breaker

        return self._executors[database]

    def get_circuit_breaker(self, database: str) -> CircuitBreaker:
        """Get circuit breaker for database.

        Args:
            database: Database name.

        Returns:
            CircuitBreaker instance for the database.

        Raises:
            DatabaseError: If database not found.

        Note:
            Circuit breaker is created when executor is first accessed.
        """
        if database not in self._circuit_breakers:
            # Trigger executor creation which also creates circuit breaker
            self.get_executor(database)

        return self._circuit_breakers[database]

    def list_databases(self) -> list[str]:
        """Get list of registered database names.

        Returns:
            List of database names.
        """
        return list(self._pools.keys())

    async def execute_with_circuit_breaker(
        self, database: str, sql: str, timeout: float | None = None, max_rows: int | None = None
    ) -> tuple[list[dict[str, Any]], int]:
        """Execute SQL with circuit breaker protection.

        Args:
            database: Database name.
            sql: SQL query to execute.
            timeout: Query timeout in seconds.
            max_rows: Maximum rows to return.

        Returns:
            tuple: (results, total_row_count)

        Raises:
            DatabaseError: If circuit breaker is open or execution fails.
        """
        circuit_breaker = self.get_circuit_breaker(database)

        # Check if circuit breaker allows request
        if not circuit_breaker.allow_request():
            raise DatabaseError(
                message=f"Circuit breaker is open for database '{database}'",
                details={
                    "database": database,
                    "circuit_state": circuit_breaker.state,
                    "failure_count": circuit_breaker.failure_count,
                },
            )

        executor = self.get_executor(database)

        try:
            results, count = await executor.execute(sql, timeout=timeout, max_rows=max_rows)
            circuit_breaker.record_success()
            return results, count
        except Exception as e:
            circuit_breaker.record_failure()
            raise
