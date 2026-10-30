"""API v2 against a migrated Postgres test database, the Polylang mock app and the fake Plunet.

Temporal is replaced by a recording fake: the workflows themselves are tested in test_workflows.py.
"""

from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select, update

from app.api import deps
from app.config import get_settings
from app.database import SessionLocal, async_engine
from app.domain.enums import EventLevel, OrderStatus, TaskStatus, WorkflowStatus
from app.integrations.plunet.fake import FakePlunetGateway
from app.integrations.polylang import PolylangConnector
from app.main import api_v1, app
from app.models.job import XLIFFSegment
from app.models.orchestration import Event, Order, Position, Task
from app.routers import reference
from tests.api_fakes import FakeTemporal, prepare_database, truncate

MOCK_MAIN = Path(__file__).resolve().parents[2] / "polylang-mock" / "app" / "main.py"
SITE = "shop.test"


def _load_mock():
    spec = importlib.util.spec_from_file_location("polylang_mock_api", MOCK_MAIN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


polylang_mock = _load_mock()


@pytest.fixture(scope="module", autouse=True)
def database():
    prepare_database()


@pytest.fixture
async def client():
    truncate()
    polylang_mock.reset_store()
    reference._cache.clear()
    get_settings().POLYLANG_SITE = SITE
    temporal = FakeTemporal()
    plunet = FakePlunetGateway()

    async def source():
        async with PolylangConnector("http://polylang", transport=httpx.ASGITransport(app=polylang_mock.app)) as c:
            yield c

    async def get_temporal():
        return temporal

    api_v1.dependency_overrides = {deps.get_source: source, deps.get_temporal: get_temporal, deps.get_plunet: lambda: plunet}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test/api/v1") as http:
        http.temporal = temporal
        yield http
    api_v1.dependency_overrides = {}
    get_settings().POLYLANG_SITE = ""
    await async_engine.dispose()  # connections belong to this test's event loop


async def refs(http) -> tuple[dict, dict]:
    customers = {c["name"]: c["id"] for c in (await http.get("/plunet/customers")).json()}
    pms = {r["name"]: r["id"] for r in (await http.get("/plunet/resources")).json()}
    return customers, pms


async def create(http, **overrides) -> httpx.Response:
    customers, pms = await refs(http)
    body = {
        "kind": "ORDER", "title": "Spring launch", "customer_id": customers["Maison Lumière SA"],
        "pm_resource_id": pms["Claire Dubois"], "deadline": None, "source_site": SITE, "source_lang": "en",
        "post_ids": [412, 421], "target_langs": ["fr", "it"], "template_code": "standard",
        "destination": "POLYLANG", "destination_url": None,
    }
    return await http.post("/orders", json=body | overrides, headers={"X-Fox-Actor": "Claire"})


def db_set(model, where, **values) -> None:
    with SessionLocal() as session, session.begin():
        session.execute(update(model).where(where).values(**values))


def add_event(**fields) -> None:
    with SessionLocal() as session, session.begin():
        session.add(Event(kind=fields.pop("kind", "STATE"), level=fields.pop("level", "INFO"), **fields))


# --- reference data ----------------------------------------------------------------------------


async def test_reference_data(client):
    customers = (await client.get("/plunet/customers")).json()
    assert [c["name"] for c in customers] == ["Alpentech GmbH", "Maison Lumière SA"]
    again = (await client.get("/plunet/customers")).json()
    assert again == customers  # same local ids, served from the cache
    assert [r["name"] for r in (await client.get("/plunet/resources")).json()] == ["Claire Dubois", "Jonas Weber"]
    templates = (await client.get("/templates")).json()
    assert templates[0] == {"code": "standard", "name": "Standard", "tasks": ["IMPORT", "PM", "TRA", "REV", "QA", "DELIVER"]}
    assert (await client.get("/sources/polylang/sites")).json() == [SITE]
    languages = (await client.get("/sources/polylang/languages", params={"site": SITE})).json()
    assert {"slug": "fr", "name": "Français", "locale": "fr_FR"} in languages
    posts = (await client.get("/sources/polylang/posts", params={"site": SITE, "lang": "en"})).json()
    spring = next(p for p in posts if p["id"] == 412)
    assert spring["type"] == "page" and spring["translations"]["fr"] == 512 and spring["words"] > 20
    assert (await client.get("/sources/polylang/posts", params={"site": "other", "lang": "en"})).status_code == 404


# --- create ------------------------------------------------------------------------------------


async def test_create_order_saves_positions_and_starts_the_workflow(client):
    res = await create(client)
    assert res.status_code == 201, res.text
    order = res.json()
    assert order["status"] == "DRAFT" and order["kind"] == "ORDER" and order["template"]["code"] == "standard"
    assert order["customer"]["name"] == "Maison Lumière SA" and order["pm"]["name"] == "Claire Dubois"
    positions = order["positions"]
    assert [(p["no"], p["polylang_post_id"], p["target_lang"]) for p in positions] == [
        (1, 412, "fr"), (2, 412, "it"), (3, 421, "fr"), (4, 421, "it")
    ]
    assert positions[0]["title"] == "Spring collection — overview" and positions[0]["file_name"] == "p412.fr.xlf"
    assert [t["type"] for t in positions[0]["tasks"]] == ["IMPORT", "PM", "TRA", "REV", "QA", "DELIVER"]
    assert order["progress"] == {"total": 4, "statuses": ["NOT_STARTED"] * 4}
    assert order["last_activity"]["message"].startswith("Order created with 4 position(s)")
    wf_id, workflow, arg = client.temporal.started[0]
    assert wf_id == f"order-{order['id']}" and workflow == "OrderWorkflow.run" and arg.order_id == order["id"]
    events = (await client.get("/events", params={"order_id": order["id"]})).json()
    assert events[0]["actor"] == "Claire" and events[0]["kind"] == "ACTION"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"post_ids": []}, "at least one post"),
        ({"target_langs": ["en"]}, "differ from the source"),
        ({"template_code": "nope"}, "Unknown template"),
        ({"customer_id": 999}, "Unknown customer"),
        ({"source_site": "other.test"}, "Unknown site"),
        ({"target_langs": ["xx"]}, "Unknown language"),
        ({"post_ids": [512]}, "not in en"),
        ({"post_ids": [99999]}, "Polylang"),
    ],
)
async def test_create_order_validation(client, overrides, message):
    res = await create(client, **overrides)
    assert res.status_code == 422 and message in res.json()["detail"], res.text
    assert client.temporal.started == []


async def test_create_order_when_temporal_is_down_keeps_the_draft(client):
    client.temporal.down = True
    res = await create(client)
    assert res.status_code == 503 and "is saved" in res.json()["detail"]
    orders = (await client.get("/orders")).json()
    assert len(orders) == 1 and orders[0]["status"] == "DRAFT"


# --- list and detail ---------------------------------------------------------------------------


async def test_list_filters(client):
    a = (await create(client, title="Spring launch")).json()
    b = (await create(client, title="Care guide", kind="QUOTE")).json()
    c = (await create(client, title="Late one", deadline=(datetime.utcnow() - timedelta(days=1)).isoformat() + "Z")).json()
    db_set(Order, Order.id == a["id"], status=OrderStatus.NEEDS_ATTENTION)
    db_set(Order, Order.id == c["id"], status=OrderStatus.RUNNING)

    ids = lambda res: [o["id"] for o in res.json()]  # noqa: E731
    assert ids(await client.get("/orders")) == [c["id"], b["id"], a["id"]]
    assert ids(await client.get("/orders", params={"kind": "QUOTE"})) == [b["id"]]
    assert ids(await client.get("/orders", params={"attention": True})) == [c["id"], a["id"]]
    assert ids(await client.get("/orders", params={"q": "care"})) == [b["id"]]
    assert ids(await client.get("/orders", params={"q": "lumière"})) == [c["id"], b["id"], a["id"]]
    assert ids(await client.get("/orders", params={"limit": 1, "offset": 1})) == [b["id"]]
    late = (await client.get(f"/orders/{c['id']}")).json()
    assert late["overdue"] is True and datetime.fromisoformat(late["deadline"]).utcoffset() == timedelta(0)
    assert (await client.get("/orders/999")).status_code == 404


async def test_detail_notes_overlays_and_totals(client):
    order = (await create(client, post_ids=[412], target_langs=["fr", "it"])).json()
    p1, p2 = (p["id"] for p in order["positions"])
    started = datetime.utcnow() - timedelta(hours=2)
    db_set(Order, Order.id == order["id"], status=OrderStatus.NEEDS_ATTENTION)
    db_set(Position, Position.id == p1, status=WorkflowStatus.FAILED, words=34)
    db_set(Task, (Task.position_id == p1) & (Task.seq < 4), status=TaskStatus.DONE, started_at=started,
           finished_at=started + timedelta(minutes=30), cost=40, currency="EUR")
    db_set(Task, (Task.position_id == p1) & (Task.seq == 4), status=TaskStatus.FAILED, started_at=started,
           error="QA failed: 1 blocking finding(s) (u-002)")
    db_set(Position, Position.id == p2, status=WorkflowStatus.PAUSED)
    db_set(Task, (Task.position_id == p2) & (Task.seq == 0), status=TaskStatus.DONE)
    db_set(Task, (Task.position_id == p2) & (Task.seq == 1), status=TaskStatus.WAITING, plunet_job_id=88)
    add_event(order_id=order["id"], position_id=p1, level=EventLevel.ERROR, message="P01 · QA failed")

    detail = (await client.get(f"/orders/{order['id']}")).json()
    first, second = detail["positions"]
    assert first["note"].startswith("QA failed") and first["tasks"][4]["overlay"] == "FAILED"
    assert first["tasks"][1]["duration_seconds"] == 1800
    assert datetime.fromisoformat(first["tasks"][1]["started_at"]).utcoffset() == timedelta(0)
    assert second["note"].startswith("Paused") and second["tasks"][1]["overlay"] == "PAUSED"
    assert second["tasks"][2]["overlay"] is None
    assert detail["totals"]["cost"] == 160.0 and detail["totals"]["currency"] == "EUR"
    assert detail["totals"]["errors"] == 1 and detail["totals"]["words"] == 34
    assert detail["totals"]["elapsed_seconds"] >= 7200
    assert detail["progress"]["statuses"] == ["FAILED", "PAUSED"]

    position = (await client.get(f"/positions/{p2}")).json()
    assert position["order"] == {"id": order["id"], "number": None, "title": "Spring launch", "kind": "ORDER",
                                 "template": {"code": "standard", "name": "Standard"}}

    db_set(Position, Position.id == p2, status=WorkflowStatus.WAITING)
    waiting = (await client.get(f"/positions/{p2}")).json()["position"]
    assert waiting["note"] == "PM waiting in Plunet (job J-88 · new)" and waiting["tasks"][1]["overlay"] is None


async def test_completed_position_note_comes_from_the_delivery(client):
    order = (await create(client, post_ids=[412], target_langs=["fr"])).json()
    position = order["positions"][0]
    deliver = position["tasks"][-1]["id"]
    db_set(Position, Position.id == position["id"], status=WorkflowStatus.COMPLETED)
    db_set(Task, Task.position_id == position["id"], status=TaskStatus.DONE)
    add_event(order_id=order["id"], position_id=position["id"], task_id=deliver,
              message="P01 · DELIVER · Delivered to Polylang as post #512")
    note = (await client.get(f"/positions/{position['id']}")).json()["position"]["note"]
    assert note == "Delivered to Polylang as post #512"


# --- quotes --------------------------------------------------------------------------------------


async def test_accept_and_reject_quotes(client):
    quote = (await create(client, kind="QUOTE")).json()
    order = (await create(client)).json()
    res = await client.post(f"/orders/{quote['id']}/accept", headers={"X-Fox-Actor": "Jonas"})
    assert res.status_code == 202
    wf_id, signal, decision = client.temporal.signals[0]
    assert (wf_id, signal, decision.actor, decision.in_plunet) == (f"order-{quote['id']}", "quote_accepted", "Jonas", False)
    assert (await client.post(f"/orders/{order['id']}/accept")).status_code == 409

    res = await client.post(f"/orders/{quote['id']}/reject", json={"reason": "Too expensive"})
    assert res.status_code == 202 and client.temporal.signals[-1][2].reason == "Too expensive"
    db_set(Order, Order.id == quote["id"], status=OrderStatus.REJECTED)
    assert (await client.post(f"/orders/{quote['id']}/reject")).status_code == 409

    client.temporal.missing.add(f"order-{order['id']}")
    db_set(Order, Order.id == order["id"], kind="QUOTE")
    assert (await client.post(f"/orders/{order['id']}/accept")).status_code == 409  # finished workflow


# --- workflow actions ----------------------------------------------------------------------------


async def test_position_actions_map_to_updates(client):
    order = (await create(client, post_ids=[412], target_langs=["fr"])).json()
    pid = order["positions"][0]["id"]
    wf = f"position-{pid}"
    assert (await client.post(f"/positions/{pid}/actions", json={"action": "pause"})).status_code == 409  # not started
    db_set(Position, Position.id == pid, status=WorkflowStatus.RUNNING)

    res = await client.post(f"/positions/{pid}/actions", json={"action": "pause"}, headers={"X-Fox-Actor": "Claire"})
    assert res.status_code == 202 and res.json()["position"]["id"] == pid
    assert client.temporal.updates[-1][:2] == (wf, "pause") and client.temporal.updates[-1][2].actor == "Claire"

    client.temporal.reject[(wf, "resume")] = "Not paused"
    res = await client.post(f"/positions/{pid}/actions", json={"action": "resume"})
    assert res.status_code == 409 and res.json()["detail"] == "Not paused"

    assert (await client.post(f"/positions/{pid}/actions", json={"action": "cancel"})).status_code == 422
    assert (await client.post(f"/positions/{pid}/actions", json={"action": "restart_from", "task_seq": 9})).status_code == 422
    res = await client.post(f"/positions/{pid}/actions", json={"action": "restart_from", "task_seq": 3, "reason": "Redo"})
    assert res.status_code == 202 and client.temporal.updates[-1][2].seq == 3
    res = await client.post(f"/positions/{pid}/actions", json={"action": "cancel", "reason": "Withdrawn"})
    assert res.status_code == 202 and client.temporal.updates[-1][2].reason == "Withdrawn"

    client.temporal.missing.add(wf)
    assert (await client.post(f"/positions/{pid}/actions", json={"action": "pause"})).status_code == 409
    assert (await client.post("/positions/999/actions", json={"action": "pause"})).status_code == 404


async def test_restart_of_a_completed_position_starts_a_new_run(client):
    order = (await create(client, post_ids=[412], target_langs=["fr"])).json()
    pid = order["positions"][0]["id"]
    db_set(Position, Position.id == pid, status=WorkflowStatus.COMPLETED)
    res = await client.post(f"/positions/{pid}/actions", json={"action": "restart_from", "task_seq": 2},
                            headers={"X-Fox-Actor": "Claire"})
    assert res.status_code == 202, res.text
    wf_id, workflow, arg = client.temporal.started[-1]
    assert (wf_id, workflow, arg.start_from) == (f"position-{pid}", "PositionWorkflow.run", 2)
    events = (await client.get(f"/positions/{pid}/events")).json()
    assert "Restart from TRA by Claire" in events[-1]["message"]


async def test_order_actions_apply_to_matching_positions(client):
    order = (await create(client, post_ids=[412], target_langs=["fr", "it"])).json()
    p1, p2 = (p["id"] for p in order["positions"])
    db_set(Position, Position.id == p1, status=WorkflowStatus.FAILED)
    db_set(Position, Position.id == p2, status=WorkflowStatus.WAITING)
    res = await client.post(f"/orders/{order['id']}/actions", json={"action": "retry_failed"})
    assert res.status_code == 202 and [u[:2] for u in client.temporal.updates] == [(f"position-{p1}", "retry")]
    await client.post(f"/orders/{order['id']}/actions", json={"action": "pause"})
    assert client.temporal.updates[-1][:2] == (f"position-{p2}", "pause")
    assert (await client.post(f"/orders/{order['id']}/actions", json={"action": "resume"})).status_code == 409


# --- events, segments, xliff ---------------------------------------------------------------------


async def test_events_latest_first_page_and_filters(client):
    order = (await create(client, post_ids=[412], target_langs=["fr"])).json()
    pid = order["positions"][0]["id"]
    for i in range(5):
        add_event(order_id=order["id"], position_id=pid, message=f"e{i}", level="WARN" if i == 3 else "INFO")
    latest = (await client.get("/events", params={"order_id": order["id"], "limit": 2})).json()
    assert [e["message"] for e in latest] == ["e3", "e4"]  # the latest ones, oldest first
    after = (await client.get("/events", params={"order_id": order["id"], "after_id": latest[0]["id"]})).json()
    assert [e["message"] for e in after] == ["e4"]
    warn = (await client.get(f"/positions/{pid}/events", params={"level": "WARN"})).json()
    assert [e["message"] for e in warn] == ["e3"]


async def test_segments_and_xliff(client):
    order = (await create(client, post_ids=[412], target_langs=["fr"])).json()
    pid = order["positions"][0]["id"]
    assert (await client.get(f"/positions/{pid}/xliff")).status_code == 404
    with SessionLocal() as session, session.begin():
        session.add_all([
            XLIFFSegment(position_id=pid, unit_id="u-001", source_text="Hello", target_text="Bonjour"),
            XLIFFSegment(position_id=pid, unit_id="u-002", source_text="{0} items", target_text="articles"),
        ])
        qa = session.scalar(select(Task).where(Task.position_id == pid, Task.type == "QA"))
        qa.findings = [{"code": "PLACEHOLDER_MISMATCH", "level": "BLOCKING", "unit_id": "u-002", "message": "Missing {0}"}]
        session.get(Position, pid).xliff_raw = "<xliff/>"
    segments = (await client.get(f"/positions/{pid}/segments")).json()
    assert [s["unit_id"] for s in segments] == ["u-001", "u-002"]
    assert segments[0]["findings"] == [] and segments[1]["findings"][0]["code"] == "PLACEHOLDER_MISMATCH"
    res = await client.get(f"/positions/{pid}/xliff", params={"variant": "raw"})
    assert res.status_code == 200 and res.text == "<xliff/>"
    assert 'filename="p412.fr.source.xlf"' in res.headers["content-disposition"]


# --- analytics -----------------------------------------------------------------------------------


async def test_analytics_by_pm_and_customer(client):
    a = (await create(client, post_ids=[412], target_langs=["fr", "it"])).json()
    customers, pms = await refs(client)
    b = (await create(client, post_ids=[421], target_langs=["fr"], pm_resource_id=pms["Jonas Weber"],
                      customer_id=customers["Alpentech GmbH"])).json()
    await create(client, kind="QUOTE")  # quotes are not counted
    start = datetime.utcnow() - timedelta(hours=10)
    first = a["positions"][0]["id"]
    db_set(Position, Position.id == first, status=WorkflowStatus.COMPLETED)
    db_set(Task, Task.position_id == first, status=TaskStatus.DONE, started_at=start, finished_at=start + timedelta(hours=4))
    db_set(Task, (Task.position_id == first) & Task.seq.in_([1, 2]), cost=50, currency="EUR")
    db_set(Task, (Task.position_id == b["positions"][0]["id"]) & (Task.seq == 2), cost=500, currency="CAD")
    add_event(order_id=a["id"], level=EventLevel.ERROR, message="boom")

    summary = (await client.get("/analytics/summary", params={"group_by": "pm"})).json()
    assert summary["currency"] == "EUR"
    rows = {r["label"]: r for r in summary["rows"]}
    claire = rows["Claire Dubois"]
    assert (claire["orders"], claire["positions"], claire["completed"]) == (1, 2, 1)
    assert claire["avg_duration_hours"] == 4.0 and claire["cost"] == 100.0 and claire["errors"] == 1
    assert rows["Jonas Weber"]["cost"] == 0.0  # CAD is not the reporting currency here

    by_customer = (await client.get("/analytics/summary", params={"group_by": "customer"})).json()
    assert {r["label"] for r in by_customer["rows"]} == {"Maison Lumière SA", "Alpentech GmbH"}
    future = (datetime.utcnow() + timedelta(days=1)).isoformat() + "Z"
    assert (await client.get("/analytics/summary", params={"from": future})).json()["rows"] == []
