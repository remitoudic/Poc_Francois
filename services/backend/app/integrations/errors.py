"""Error taxonomy shared by all integrations (architecture §5.3, "two kinds of failure").

- `TechnicalError`: network, timeout, 5xx, SOAP fault. Temporal retries the activity.
- `BusinessError`: the remote system rejected the input. No automatic retry; the task fails
  and waits for a user decision. Activities list it in `non_retryable_error_types`.
"""


class IntegrationError(Exception):
    """Base class for errors raised by a gateway."""


class TechnicalError(IntegrationError):
    """Transient failure; safe to retry."""


class BusinessError(IntegrationError):
    """The remote system refused the request; retrying will not help."""
