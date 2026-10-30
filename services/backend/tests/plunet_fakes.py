"""SOAP test double: validates every call against the recorded Plunet WSDLs, then answers from a script."""

from __future__ import annotations

from collections.abc import Callable
from functools import cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from zeep import Client

WSDL_DIR = Path(__file__).parent / "fixtures" / "plunet_wsdl"


@cache
def wsdl_client(name: str) -> Client:
    return Client(str(WSDL_DIR / f"{name}.wsdl"))


def ok(data: Any = None) -> SimpleNamespace:
    return SimpleNamespace(statusCode=0, statusMessage="OK", data=data)


def failed(code: int, message: str) -> SimpleNamespace:
    return SimpleNamespace(statusCode=code, statusMessage=message, data=None)


Answer = Any | Callable[..., Any]


class ScriptedSoap:
    """Service factory for SoapPlunetGateway.

    `script[(service, operation)]` is a value, a callable(**kwargs), or a list consumed one
    answer per call. Unscripted operations answer ok(None).
    """

    def __init__(self, script: dict[tuple[str, str], Answer] | None = None, token: str = "uuid-1"):
        self.script: dict[tuple[str, str], Answer] = {("PlunetAPI", "login"): token, **(script or {})}
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def __call__(self, service: str) -> Any:
        soap = self

        class Proxy:
            def __getattr__(self, operation: str) -> Callable[..., Any]:
                def call(**kwargs: Any) -> Any:
                    client = wsdl_client(service)
                    # Raises on an unknown operation, unknown argument, wrong type or missing required field.
                    client.create_message(client.service, operation, **kwargs)
                    soap.calls.append((service, operation, kwargs))
                    answer = soap.script.get((service, operation), ok())
                    if isinstance(answer, list):
                        answer = answer.pop(0)
                    if isinstance(answer, BaseException):
                        raise answer
                    return answer(**kwargs) if callable(answer) else answer

                return call

        return Proxy()

    def ops(self) -> list[str]:
        return [f"{s}.{o}" for s, o, _ in self.calls]

    def kwargs(self, service: str, operation: str) -> dict[str, Any]:
        return next(k for s, o, k in self.calls if (s, o) == (service, operation))
