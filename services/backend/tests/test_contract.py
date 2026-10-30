"""The frontend's hand-written contract (services/frontend/src/api/types.ts) matches the API schemas.

Catches drift in both directions: a field or a status added, renamed or made nullable on one side only.
"""

from __future__ import annotations

import re
import typing
from enum import StrEnum
from pathlib import Path

import pytest
from pydantic import BaseModel

from app.domain import enums
from app.schemas import v2
from app.xliff.qa import QaFinding

TYPES_TS = Path(__file__).resolve().parents[2] / "frontend" / "src" / "api" / "types.ts"

# TS interface → API model.  Responses must match exactly; requests may have server defaults.
RESPONSES = {
    "Ref": v2.Ref,
    "OrderProgress": v2.OrderProgress,
    "OrderSummary": v2.OrderSummary,
    "OrderDetail": v2.OrderDetail,
    "QaFinding": QaFinding,
    "Task": v2.TaskOut,
    "Position": v2.PositionOut,
    "PositionDetail": v2.PositionDetail,
    "EventItem": v2.EventOut,
    "Segment": v2.SegmentOut,
    "Template": v2.TemplateOut,
    "Language": v2.LanguageOut,
    "SourcePost": v2.SourcePostOut,
    "AnalyticsRow": v2.AnalyticsRow,
    "AnalyticsSummary": v2.AnalyticsSummary,
}
REQUESTS = {
    "CreateOrderRequest": v2.CreateOrderRequest,
    "WorkflowAction": v2.WorkflowActionRequest,
}
UNIONS = {
    "OrderKind": enums.OrderKind,
    "OrderStatus": enums.OrderStatus,
    "WorkflowStatus": enums.WorkflowStatus,
    "TaskType": enums.TaskType,
    "TaskStatus": enums.TaskStatus,
    "Overlay": enums.Overlay,
    "Destination": enums.Destination,
    "EventKind": enums.EventKind,
    "EventLevel": enums.EventLevel,
    "WorkflowActionName": v2.WorkflowActionName,
    "OrderActionName": v2.OrderActionName,
}

_INTERFACE = re.compile(r"export interface (\w+)(?: extends (\w+))? \{\n(.*?)\n\}", re.S)
_FIELD = re.compile(r"^  (\w+)(\?)?: (.+);$", re.M)
_UNION = re.compile(r"export type (\w+) =([^;]+);", re.S)


def _ts() -> tuple[dict[str, dict[str, tuple[bool, bool]]], dict[str, set[str]]]:
    """Interfaces as {name: {field: (optional, nullable)}} and string unions as {name: values}."""
    source = re.sub(r"/\*\*.*?\*/", "", TYPES_TS.read_text(), flags=re.S)
    nullable_aliases = {name for name, body in _UNION.findall(source) if re.search(r"\|\s*null\b", body)}
    interfaces: dict[str, dict[str, tuple[bool, bool]]] = {}
    for name, parent, body in _INTERFACE.findall(source):
        fields = dict(interfaces.get(parent, {}))
        for field, optional, ts_type in _FIELD.findall(body):
            ts_type = ts_type.strip()
            fields[field] = (bool(optional), ts_type.endswith("| null") or ts_type in nullable_aliases)
        interfaces[name] = fields
    unions = {
        name: set(re.findall(r"'([^']+)'", body))
        for name, body in _UNION.findall(source)
        if "'" in body and "{" not in body
    }
    return interfaces, unions


INTERFACES, TS_UNIONS = _ts()


def _nullable(annotation) -> bool:
    return type(None) in typing.get_args(annotation) or annotation is type(None)


def _py(model: type[BaseModel]) -> dict[str, tuple[bool, bool]]:
    """{field: (has_default, nullable)}"""
    return {
        name: (not info.is_required(), _nullable(info.annotation))
        for name, info in model.model_fields.items()
    }


@pytest.mark.parametrize("name", sorted(RESPONSES))
def test_response_shapes_match(name):
    ts, py = INTERFACES[name], _py(RESPONSES[name])
    assert set(ts) == set(py), f"{name}: only in TS {set(ts) - set(py)}, only in API {set(py) - set(ts)}"
    for field, (optional, ts_null) in ts.items():
        assert not optional, f"{name}.{field} is optional in TS but always sent by the API"
        assert ts_null == py[field][1], f"{name}.{field}: nullable in TS={ts_null}, API={py[field][1]}"


@pytest.mark.parametrize("name", sorted(REQUESTS))
def test_request_shapes_match(name):
    ts, py = INTERFACES[name], _py(REQUESTS[name])
    assert set(ts) == set(py), f"{name}: only in TS {set(ts) - set(py)}, only in API {set(py) - set(ts)}"
    for field, (optional, ts_null) in ts.items():
        has_default, py_null = py[field]
        if optional:
            assert has_default, f"{name}.{field} may be left out by the UI but the API requires it"
        if ts_null:
            assert py_null, f"{name}.{field} may be null from the UI but the API refuses null"


@pytest.mark.parametrize("name", sorted(UNIONS))
def test_status_lists_match(name):
    source = UNIONS[name]
    if isinstance(source, type) and issubclass(source, StrEnum):
        values = {m.value for m in source}
    else:
        values = set(typing.get_args(source))
    assert TS_UNIONS[name] == values, f"{name}: only in TS {TS_UNIONS[name] - values}, only in API {values - TS_UNIONS[name]}"


def test_every_ts_interface_is_checked():
    """A new interface in types.ts needs a decision here (response, request or UI-only)."""
    ui_only = {"OrderFilters", "EventScope", "Api"}
    assert set(INTERFACES) - set(RESPONSES) - set(REQUESTS) - ui_only == set()

