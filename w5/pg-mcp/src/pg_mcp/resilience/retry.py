"""Retry strategy for handling transient failures.

This module provides retry logic with exponential backoff for handling
transient database failures.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

import asyncpg

T = TypeVar("T")


def is_transient_error(error: Exception) -> bool:
    """Determine if error is transient and should be retried.

    Args:
        error: Exception to check.

    Returns:
        True if error is transient, False otherwise.

    Transient errors include:
        - Connection errors
        - Too many connections
        - Temporary unavailability
        - Network timeouts
    """
    # asyncpg transient errors
    if isinstance(
        error,
        (
            asyncpg.ConnectionDoesNotExistError,
            asyncpg.ConnectionFailureError,
            asyncpg.TooManyConnectionsError,
            asyncpg.CannotConnectNowError,
        ),
    ):
        return True

    # Check for specific PostgreSQL error codes
    if isinstance(error, asyncpg.PostgresError):
        # 08000: connection_exception
        # 08003: connection_does_not_exist
        # 08006: connection_failure
        # 53300: too_many_connections
        # 57P03: cannot_connect_now
        if hasattr(error, "sqlstate") and error.sqlstate in {
            "08000",
            "08003",
            "08006",
            "53300",
            "57P03",
        }:
            return True

    return False


class RetryStrategy:
    """Retry strategy with exponential backoff.

    This class implements retry logic for handling transient failures
    with configurable backoff parameters.

    Example:
        >>> retry = RetryStrategy(max_retries=3, initial_delay=1.0)
        >>> result = await retry.execute(
        ...     lambda: conn.fetch(sql),
        ...     is_transient=is_transient_error
        ... )
    """

    def __init__(
        self,
        max_retries: int,
        initial_delay: float,
        backoff_factor: float,
    ) -> None:
        """Initialize retry strategy.

        Args:
            max_retries: Maximum number of retry attempts.
            initial_delay: Initial retry delay in seconds.
            backoff_factor: Exponential backoff factor.
        """
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.backoff_factor = backoff_factor

    async def execute(
        self,
        func: Callable[[], Awaitable[T]],
        *,
        is_transient: Callable[[Exception], bool] | None = None,
    ) -> T:
        """Execute function with retry logic.

        Args:
            func: Async function to execute.
            is_transient: Optional function to determine if error is transient.
                         Defaults to is_transient_error.

        Returns:
            Result of successful execution.

        Raises:
            Exception: Last exception if all retries exhausted.

        Example:
            >>> retry = RetryStrategy(max_retries=3, initial_delay=1.0)
            >>> result = await retry.execute(
            ...     lambda: conn.fetch(sql),
            ...     is_transient=lambda e: isinstance(e, asyncpg.ConnectionError)
            ... )
        """
        if is_transient is None:
            is_transient = is_transient_error

        last_exception: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                return await func()
            except Exception as e:
                last_exception = e

                # Check if error is transient
                if not is_transient(e):
                    # Non-transient error, don't retry
                    raise

                # Check if we have retries left
                if attempt >= self.max_retries:
                    # Out of retries
                    raise

                # Calculate delay for this attempt
                delay = self.calculate_delay(attempt)

                # Wait before retrying
                await asyncio.sleep(delay)

        # Should not reach here, but just in case
        if last_exception:
            raise last_exception
        raise RuntimeError("Retry logic failed unexpectedly")

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number.

        Args:
            attempt: Attempt number (0-indexed).

        Returns:
            Delay in seconds.

        Formula:
            delay = initial_delay * (backoff_factor ** attempt)

        Example:
            >>> retry = RetryStrategy(max_retries=3, initial_delay=1.0, backoff_factor=2.0)
            >>> retry.calculate_delay(0)  # 1.0
            >>> retry.calculate_delay(1)  # 2.0
            >>> retry.calculate_delay(2)  # 4.0
        """
        return self.initial_delay * (self.backoff_factor**attempt)
