"""Shared activity plumbing: error classification and retry policy (architecture §5.3)."""

import functools
import inspect
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError

from app.integrations.errors import BusinessError

BUSINESS_ERROR = "BusinessError"

# Technical errors: 5 attempts, exponential backoff up to 5 minutes. Business errors: never.
RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=5),
    maximum_attempts=5,
    non_retryable_error_types=[BUSINESS_ERROR],
)


def _as_application_error(exc: BusinessError) -> ApplicationError:
    return ApplicationError(str(exc), type=BUSINESS_ERROR, non_retryable=True)


def business_errors[F: Callable[..., Any]](fn: F) -> F:
    """Turn BusinessError (Plunet refusal, unknown post, malformed XLIFF…) into a non-retryable
    ApplicationError, so Temporal fails the activity at once and the task becomes FAILED."""
    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await fn(*args, **kwargs)
            except BusinessError as exc:
                raise _as_application_error(exc) from exc

        return async_wrapper  # type: ignore[return-value]

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except BusinessError as exc:
            raise _as_application_error(exc) from exc

    return wrapper  # type: ignore[return-value]
