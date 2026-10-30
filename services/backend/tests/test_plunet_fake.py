import pytest

from app.domain.enums import TaskStatus
from app.domain.plunet_status import task_status_from_plunet
from app.integrations.plunet import (
    FakePlunetGateway,
    JobStatus,
    PlunetBusinessError,
    ProjectType,
    QuoteStatus,
)
from app.integrations.plunet.models import ItemDraft, ProjectDraft


def test_order_item_job_lifecycle():
    gw = FakePlunetGateway()
    order = gw.create_order(ProjectDraft(project_name="Spring", customer_id=1, project_manager_id=11))
    item = gw.create_item(ItemDraft(project_type=ProjectType.ORDER, project_id=order.id, description="P01", source_lang="en", target_lang="fr"))
    job = gw.create_job(ProjectType.ORDER, order.id, item, "TRA")
    assert task_status_from_plunet(gw.get_job(ProjectType.ORDER, job).status) == TaskStatus.PENDING
    gw.assign_resource(ProjectType.ORDER, job, 21)
    assert gw.get_job(ProjectType.ORDER, job).status == "ASSIGNED_WAITING"
    gw.set_job_status(ProjectType.ORDER, job, JobStatus.DELIVERED)
    gw.set_job_price(job, 148.8)
    assert gw.get_job_cost(ProjectType.ORDER, job).amount == 148.8
    assert [j.id for j in gw.list_item_jobs(ProjectType.ORDER, item)] == [job]
    gw.delete_order(order.id)
    assert not gw.items and not gw.jobs


def test_quote_conversion_is_detected():
    gw = FakePlunetGateway()
    quote = gw.create_quote(ProjectDraft(project_name="Careers", customer_id=2))
    draft = ItemDraft(project_type=ProjectType.QUOTE, project_id=quote.id, description="P01", source_lang="en", target_lang="fr")
    gw.create_item(draft)
    gw.set_quote_status(quote.id, QuoteStatus.PENDING)
    with pytest.raises(PlunetBusinessError):  # Plunet refuses items on a released quote
        gw.create_item(draft)
    gw.set_quote_status(quote.id, QuoteStatus.ACCEPTED)
    assert gw.get_order_id_for_quote(quote.id) is None
    order_id = gw.convert_quote(quote.id)
    assert gw.get_order_id_for_quote(quote.id) == order_id
    assert gw.get_quote_status(quote.id) == QuoteStatus.CHANGE_INTO_ORDER


def test_rejects_unknown_references():
    gw = FakePlunetGateway()
    with pytest.raises(PlunetBusinessError):
        gw.create_order(ProjectDraft(project_name="x", customer_id=999))
    order = gw.create_order(ProjectDraft(project_name="x", customer_id=1))
    item = gw.create_item(ItemDraft(project_type=ProjectType.ORDER, project_id=order.id, description="x", source_lang="en", target_lang="fr"))
    with pytest.raises(PlunetBusinessError):
        gw.create_job(ProjectType.ORDER, order.id, item, "XYZ")
