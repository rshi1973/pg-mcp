"""Access control for table and column restrictions.

This module provides access control validation for SQL queries, enforcing
table and column restrictions based on security policies.
"""

from dataclasses import dataclass
from typing import Any

from pglast import parse_sql
from pglast.visitors import Visitor

from pg_mcp.config.settings import SecurityConfig
from pg_mcp.models.errors import SQLParseError


@dataclass
class ValidationResult:
    """Result of access control validation."""

    is_valid: bool
    violations: list[str]
    tables_accessed: set[str]
    columns_accessed: dict[str, set[str]]


class AccessControlPolicy:
    """Policy for table and column access control.

    This class defines and enforces access restrictions for database tables
    and columns based on whitelist/blacklist rules.

    Example:
        >>> policy = AccessControlPolicy.from_config("mydb", security_config)
        >>> if not policy.validate_table_access("passwords"):
        ...     raise SecurityViolationError("Access denied")
    """

    def __init__(
        self,
        database: str,
        allowed_tables: set[str],
        blocked_tables: set[str],
        column_restrictions: dict[str, set[str]],
    ) -> None:
        """Initialize access control policy.

        Args:
            database: Database name this policy applies to.
            allowed_tables: Whitelist of allowed tables (empty = all allowed).
            blocked_tables: Blacklist of blocked tables.
            column_restrictions: Mapping of table name to blocked column names.
        """
        self.database = database
        self.allowed_tables = allowed_tables
        self.blocked_tables = blocked_tables
        self.column_restrictions = column_restrictions

    def validate_table_access(self, table: str) -> bool:
        """Check if access to table is allowed.

        Args:
            table: Table name to check.

        Returns:
            True if access allowed, False otherwise.

        Logic:
            1. If table in blocked_tables: return False
            2. If allowed_tables is empty: return True (allow all)
            3. If table in allowed_tables: return True
            4. Otherwise: return False
        """
        # Blocked tables always take precedence
        if table in self.blocked_tables:
            return False

        # If no whitelist, allow all (except blocked)
        if not self.allowed_tables:
            return True

        # Check whitelist
        return table in self.allowed_tables

    def validate_column_access(self, table: str, column: str) -> bool:
        """Check if access to column is allowed.

        Args:
            table: Table name.
            column: Column name.

        Returns:
            True if access allowed, False otherwise.

        Logic:
            1. If table not in column_restrictions: return True
            2. If column in column_restrictions[table]: return False
            3. Otherwise: return True
        """
        if table not in self.column_restrictions:
            return True

        return column not in self.column_restrictions[table]

    def get_violations(
        self, tables: set[str], columns: dict[str, set[str]]
    ) -> list[str]:
        """Get list of access control violations.

        Args:
            tables: Set of table names referenced in SQL.
            columns: Dict mapping table names to column sets.

        Returns:
            List of violation messages (empty if no violations).

        Example:
            >>> violations = policy.get_violations(
            ...     tables={"users", "passwords"},
            ...     columns={"users": {"id", "password_hash"}}
            ... )
            >>> # ["Access denied to table: passwords",
            >>> #  "Access denied to column: users.password_hash"]
        """
        violations: list[str] = []

        # Check table access
        for table in tables:
            if not self.validate_table_access(table):
                violations.append(f"Access denied to table: {table}")

        # Check column access
        for table, cols in columns.items():
            for col in cols:
                if not self.validate_column_access(table, col):
                    violations.append(f"Access denied to column: {table}.{col}")

        return violations

    @classmethod
    def from_config(cls, database: str, config: SecurityConfig) -> "AccessControlPolicy":
        """Create policy from security configuration.

        Args:
            database: Database name.
            config: Security configuration.

        Returns:
            AccessControlPolicy instance.
        """
        return cls(
            database=database,
            allowed_tables=set(config.allowed_tables),
            blocked_tables=set(config.blocked_tables),
            column_restrictions={
                table: set(cols) for table, cols in config.column_restrictions.items()
            },
        )


class TableColumnExtractor(Visitor):
    """Extract table and column references from SQL AST.

    This visitor traverses the SQL parse tree and collects all table
    and column references.
    """

    def __init__(self) -> None:
        """Initialize extractor."""
        self.tables: set[str] = set()
        self.columns: dict[str, set[str]] = {}
        self.current_table: str | None = None

    def visit_RangeVar(self, ancestors: tuple[Any, ...], node: Any) -> None:
        """Visit table references (FROM, JOIN).

        Args:
            ancestors: Ancestor nodes in the parse tree.
            node: Current RangeVar node.
        """
        if hasattr(node, "relname") and node.relname:
            table_name = node.relname.value if hasattr(node.relname, "value") else str(node.relname)
            self.tables.add(table_name)
            self.current_table = table_name

    def visit_ColumnRef(self, ancestors: tuple[Any, ...], node: Any) -> None:
        """Visit column references (SELECT list, WHERE clause).

        Args:
            ancestors: Ancestor nodes in the parse tree.
            node: Current ColumnRef node.
        """
        if not hasattr(node, "fields") or not node.fields:
            return

        fields = node.fields

        if len(fields) == 2:
            # Qualified: table.column
            table_node = fields[0]
            column_node = fields[1]

            if hasattr(table_node, "val") and hasattr(column_node, "val"):
                table = table_node.val.value if hasattr(table_node.val, "value") else str(table_node.val)
                column = column_node.val.value if hasattr(column_node.val, "value") else str(column_node.val)
                self.columns.setdefault(table, set()).add(column)

        elif len(fields) == 1:
            # Unqualified: column (use current table)
            column_node = fields[0]
            if hasattr(column_node, "val"):
                column = column_node.val.value if hasattr(column_node.val, "value") else str(column_node.val)
                if self.current_table and column != "*":
                    self.columns.setdefault(self.current_table, set()).add(column)

    def visit_CommonTableExpr(self, ancestors: tuple[Any, ...], node: Any) -> None:
        """Visit CTE definitions.

        Args:
            ancestors: Ancestor nodes in the parse tree.
            node: Current CommonTableExpr node.
        """
        if hasattr(node, "ctename") and node.ctename:
            cte_name = node.ctename.value if hasattr(node.ctename, "value") else str(node.ctename)
            self.tables.add(cte_name)


class AccessControlValidator:
    """Validator for SQL access control.

    This class validates SQL queries against access control policies by
    parsing the SQL and extracting table and column references.

    Example:
        >>> validator = AccessControlValidator()
        >>> result = validator.validate(sql, policy)
        >>> if not result.is_valid:
        ...     raise SecurityViolationError(result.violations[0])
    """

    def validate(self, sql: str, policy: AccessControlPolicy) -> ValidationResult:
        """Validate SQL against access control policy.

        Args:
            sql: SQL query to validate.
            policy: Access control policy to enforce.

        Returns:
            ValidationResult with validation outcome.

        Raises:
            SQLParseError: If SQL cannot be parsed.

        Note:
            This method does not raise on validation failures,
            it returns them in ValidationResult.violations.
        """
        try:
            tables = self.extract_tables(sql)
            columns = self.extract_columns(sql)
            violations = policy.get_violations(tables, columns)

            return ValidationResult(
                is_valid=len(violations) == 0,
                violations=violations,
                tables_accessed=tables,
                columns_accessed=columns,
            )
        except Exception as e:
            raise SQLParseError(
                message=f"Failed to parse SQL for access control validation: {e!s}",
                details={"sql": sql[:200]},
            ) from e

    def extract_tables(self, sql: str) -> set[str]:
        """Extract table references from SQL.

        Args:
            sql: SQL query to parse.

        Returns:
            Set of table names referenced in the query.

        Raises:
            SQLParseError: If SQL cannot be parsed.

        Note:
            Includes tables from FROM, JOIN, and CTE clauses.
        """
        try:
            stmts = parse_sql(sql)
            extractor = TableColumnExtractor()

            for stmt in stmts:
                extractor(stmt)

            return extractor.tables
        except Exception as e:
            raise SQLParseError(
                message=f"Failed to extract tables from SQL: {e!s}",
                details={"sql": sql[:200]},
            ) from e

    def extract_columns(self, sql: str) -> dict[str, set[str]]:
        """Extract column references per table.

        Args:
            sql: SQL query to parse.

        Returns:
            Dictionary mapping table names to sets of column names.

        Raises:
            SQLParseError: If SQL cannot be parsed.

        Note:
            Includes columns from SELECT list, WHERE, JOIN ON, etc.
        """
        try:
            stmts = parse_sql(sql)
            extractor = TableColumnExtractor()

            for stmt in stmts:
                extractor(stmt)

            return extractor.columns
        except Exception as e:
            raise SQLParseError(
                message=f"Failed to extract columns from SQL: {e!s}",
                details={"sql": sql[:200]},
            ) from e
