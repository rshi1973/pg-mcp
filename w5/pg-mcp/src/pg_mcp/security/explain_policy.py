"""EXPLAIN policy for query cost validation.

This module provides query cost validation using PostgreSQL EXPLAIN to
prevent expensive queries from consuming excessive resources.
"""

import json

from asyncpg import Connection

from pg_mcp.config.settings import SecurityConfig
from pg_mcp.models.errors import DatabaseError


class ExplainPolicy:
    """Policy for query cost validation using EXPLAIN.

    This class determines whether queries should be explained based on
    complexity heuristics and validates query cost against configured limits.

    Example:
        >>> policy = ExplainPolicy.from_config(security_config)
        >>> if policy.should_explain(sql):
        ...     is_acceptable, cost = await policy.validate_cost(conn, sql)
        ...     if not is_acceptable:
        ...         raise QueryTooExpensiveError(f"Cost {cost} exceeds limit")
    """

    def __init__(
        self,
        threshold: int,
        max_cost: int,
        enabled: bool,
    ) -> None:
        """Initialize EXPLAIN policy.

        Args:
            threshold: Complexity threshold to trigger EXPLAIN check.
            max_cost: Maximum allowed query cost.
            enabled: Whether EXPLAIN policy is enabled.
        """
        self.threshold = threshold
        self.max_cost = max_cost
        self.enabled = enabled

    def should_explain(self, sql: str) -> bool:
        """Determine if query should be explained based on complexity.

        Args:
            sql: SQL query to check.

        Returns:
            True if query should be explained, False otherwise.

        Heuristics:
            - Contains JOIN: True
            - Contains UNION: True
            - Contains WITH (CTE): True
            - Contains GROUP BY: True
            - Multiple SELECT statements: True
            - Otherwise: False
        """
        if not self.enabled:
            return False

        sql_upper = sql.upper()

        # Check for complex operations
        if any(keyword in sql_upper for keyword in ["JOIN", "UNION", "WITH"]):
            return True

        if "GROUP BY" in sql_upper or "HAVING" in sql_upper:
            return True

        # Check for subqueries (multiple SELECT statements)
        if sql_upper.count("SELECT") > 1:
            return True

        return False

    async def validate_cost(
        self,
        conn: Connection,
        sql: str,
    ) -> tuple[bool, float]:
        """Validate query cost using EXPLAIN.

        Args:
            conn: Database connection.
            sql: SQL query to validate.

        Returns:
            tuple: (is_acceptable, actual_cost) where:
                - is_acceptable: True if cost <= max_cost
                - actual_cost: Estimated query cost from EXPLAIN

        Raises:
            DatabaseError: If EXPLAIN fails.

        Note:
            Uses EXPLAIN (FORMAT JSON) for structured output.
        """
        try:
            # Run EXPLAIN with JSON format for structured output
            # Note: SQL is already validated by SQLValidator, so string interpolation is safe.
            # EXPLAIN is read-only and only analyzes query plans, never executes queries.
            explain_sql = f"EXPLAIN (FORMAT JSON) {sql}"
            result = await conn.fetchval(explain_sql)

            # Parse JSON output
            if isinstance(result, str):
                plan_data = json.loads(result)
            else:
                plan_data = result

            # Extract total cost from plan
            if isinstance(plan_data, list) and len(plan_data) > 0:
                plan = plan_data[0].get("Plan", {})
                total_cost = plan.get("Total Cost", 0.0)
            else:
                total_cost = 0.0

            is_acceptable = total_cost <= self.max_cost

            return is_acceptable, total_cost

        except Exception as e:
            raise DatabaseError(
                message=f"EXPLAIN failed: {e!s}",
                details={
                    "sql": sql[:200],
                    "error": str(e),
                },
            ) from e

    @classmethod
    def from_config(cls, config: SecurityConfig) -> "ExplainPolicy":
        """Create policy from security configuration.

        Args:
            config: Security configuration.

        Returns:
            ExplainPolicy instance.
        """
        return cls(
            threshold=config.explain_threshold,
            max_cost=config.max_query_cost,
            enabled=config.explain_enabled,
        )
