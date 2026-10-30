from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.domain.enums import TaskStatus
from app.domain.plunet_status import task_status_from_plunet
from app.integrations.errors import BusinessError, TechnicalError
from app.integrations.plunet import (
    ItemStatus,
    JobStatus,
    PlunetAuthError,
    PlunetBusinessError,
    PlunetTechnicalError,
    ProjectType,
    QuoteStatus,
    SoapPlunetGateway,
)
from app.integrations.plunet.gateway import resolve_language
from app.integrations.plunet.models import ItemDraft, ProjectDraft
from tests.plunet_fakes import ScriptedSoap, failed, ok

DRAFT = ProjectDraft(
    project_name="Spring product pages",
    customer_id=1,
    project_manager_id=11,
    deadline=datetime(2026, 11, 4, 17, tzinfo=UTC),
    reference="FOX-101",
)


LANGUAGES = ok([
    SimpleNamespace(id=327, name="English", folderName="en", active=True, isoCode=None, favorite=False),
    SimpleNamespace(id=93, name="English (USA)", folderName="en-US", active=True, isoCode="ENG", favorite=False),
    SimpleNamespace(id=326, name="French", folderName="fr-FR", active=True, isoCode=None, favorite=False),
    SimpleNamespace(id=423, name="French (Canada)", folderName="fr-CA", active=True, isoCode=None, favorite=True),
    SimpleNamespace(id=323, name="German", folderName="de-DE", active=True, isoCode=None, favorite=False),
    SimpleNamespace(id=999, name="Klingon", folderName="tlh", active=False, isoCode=None, favorite=False),
])


def gateway(script=None) -> tuple[SoapPlunetGateway, ScriptedSoap]:
    soap = ScriptedSoap({("DataAdmin30", "getAvailableLanguages"): LANGUAGES, **(script or {})})
    return SoapPlunetGateway(soap, "api-user", "secret"), soap


def job_row(**overrides):
    row = dict(
        jobID=88213, itemID=5105, projectID=414, projectType=3, jobTypeShort="TRA", jobTypeFull="Translation",
        status=7, resourceID=21, startDate=None, dueDate=None, countSourceFiles=1,
    )
    return SimpleNamespace(**{**row, **overrides})


def test_create_order_logs_in_once_and_returns_display_number():
    gw, soap = gateway({
        ("DataOrder30", "insert2"): ok(414),
        ("DataOrder30", "getOrderNo_for_View"): ok("O-2026-0414"),
    })
    created = gw.create_order(DRAFT)
    assert (created.id, created.number, created.project_type) == (414, "O-2026-0414", ProjectType.ORDER)
    assert soap.ops() == ["PlunetAPI.login", "DataOrder30.insert2", "DataOrder30.getOrderNo_for_View"]
    order_in = soap.kwargs("DataOrder30", "insert2")["OrderIN"]
    assert order_in["customerID"] == 1 and order_in["projectManagerID"] == 11
    assert order_in["referenceNumber"] == "FOX-101"
    assert soap.kwargs("DataOrder30", "insert2")["UUID"] == "uuid-1"


def test_create_quote_sets_project_manager_separately():
    gw, soap = gateway({("DataQuote30", "insert2"): ok(77), ("DataQuote30", "getQuoteNo_for_View"): ok("Q-77")})
    created = gw.create_quote(DRAFT)
    assert created.project_type == ProjectType.QUOTE and created.number == "Q-77"
    assert soap.kwargs("DataQuote30", "setProjectmanagerID") == {"UUID": "uuid-1", "resourceID": 11, "quoteID": 77}
    assert soap.kwargs("DataQuote30", "insert2")["QuoteIN"]["status"] == QuoteStatus.IN_PREPARATION
    assert "DataQuote30.setStatus" not in soap.ops()  # released by the caller once items are added


def test_half_created_quote_is_deleted():
    gw, soap = gateway({
        ("DataQuote30", "insert2"): ok(77),
        ("DataQuote30", "setProjectmanagerID"): failed(9002, "The quote status is not NEW"),
    })
    with pytest.raises(PlunetBusinessError):
        gw.create_quote(DRAFT)
    assert soap.kwargs("DataQuote30", "delete") == {"UUID": "uuid-1", "quoteID": 77}


def test_create_item_sets_language_combination():
    gw, soap = gateway({("DataItem30", "insert2"): ok(5105)})
    item_id = gw.create_item(ItemDraft(
        project_type=ProjectType.ORDER, project_id=414, description="P05 · Behind the atelier",
        source_lang="en", target_lang="fr",
    ))
    assert item_id == 5105
    lang = soap.kwargs("DataItem30", "addLanguageCombination")
    assert (lang["sourceLanguage"], lang["targetLanguage"], lang["itemID"], lang["projectID"]) == ("English", "French", 5105, 414)


@pytest.mark.parametrize(
    ("code", "name"),
    [("en", "English"), ("en-US", "English (USA)"), ("en_us", "English (USA)"), ("fr", "French"),
     ("fr_CA", "French (Canada)"), ("de-at", "German"), ("tlh", None), ("ja", None)],
)
def test_language_resolution(code, name):
    gw, _ = gateway()
    found = resolve_language(code, gw.list_languages())
    assert (found.name if found else None) == name


def test_unknown_language_is_a_business_error_and_languages_are_cached():
    gw, soap = gateway({("DataItem30", "insert2"): ok(5105)})
    with pytest.raises(PlunetBusinessError):
        gw.create_item(ItemDraft(project_type=ProjectType.ORDER, project_id=414, description="x", source_lang="en", target_lang="ja"))
    assert "DataItem30.insert2" not in soap.ops()
    gw.list_languages()
    assert soap.ops().count("DataAdmin30.getAvailableLanguages") == 1


def test_upload_document_targets_item_source_folder():
    gw, soap = gateway()
    gw.upload_document(ProjectType.ORDER, 5105, "p433.fr.xlf", b"<xliff/>")
    call = soap.kwargs("DataDocument30", "upload_Document")
    assert (call["MainID"], call["FolderType"], call["FileSize"]) == (5105, 16, 8)
    gw.upload_document(ProjectType.QUOTE, 5105, "p433.fr.xlf", b"<xliff/>")
    assert soap.calls[-1][2]["FolderType"] == 14


def test_get_job_returns_raw_plunet_status():
    gw, _ = gateway({("DataJob30", "getJob_ForView"): ok(job_row(status=7))})
    job = gw.get_job(ProjectType.ORDER, 88213)
    assert (job.status, job.job_type, job.resource_id, job.item_id) == ("ASSIGNED_WAITING", "TRA", 21, 5105)
    assert task_status_from_plunet(job.status) == TaskStatus.WAITING


def test_job_cost_sums_price_lines_in_project_currency():
    gw, soap = gateway({
        ("DataJob30", "getPriceLine_ListByCurrencyType"): ok([SimpleNamespace(amount=120.5), SimpleNamespace(amount=85.2)]),
        ("DataJob30", "getCurrency"): ok("EUR"),
    })
    cost = gw.get_job_cost(ProjectType.ORDER, 88213)
    assert (cost.amount, cost.currency) == (205.7, "EUR")
    assert soap.kwargs("DataJob30", "getPriceLine_ListByCurrencyType")["currencyType"] == 1


def test_order_id_for_unconverted_quote_is_none():
    gw, soap = gateway({("DataQuote30", "getQuoteObject"): [
        ok(SimpleNamespace(quoteID=77, orderID=None)),
        ok(SimpleNamespace(quoteID=77, orderID=[0])),
        ok(SimpleNamespace(quoteID=77, orderID=[414])),
    ]})
    assert gw.get_order_id_for_quote(77) is None
    assert gw.get_order_id_for_quote(77) is None
    assert gw.get_order_id_for_quote(77) == 414
    assert "DataQuote30.getOrderIDFirstItem" not in soap.ops()


def test_reference_lists_are_mapped_and_sorted():
    gw, soap = gateway({
        ("DataCustomer30", "getAllCustomerObjects"): ok([
            SimpleNamespace(customerID=2, fullName="Nordwind AG", name1=None, name2=None, currency="EUR"),
            SimpleNamespace(customerID=1, fullName="", name1="Alpentech", name2="GmbH", currency=None),
        ]),
        ("DataResource30", "getAllResourceObjects"): ok([
            SimpleNamespace(resourceID=11, fullName=None, name1="Dubois", name2="Claire", email="c@x.ch"),
        ]),
    })
    assert [c.name for c in gw.list_customers()] == ["Alpentech GmbH", "Nordwind AG"]
    assert gw.list_project_managers()[0].name == "Claire Dubois"
    assert soap.kwargs("DataResource30", "getAllResourceObjects")["WorkingStatus"] == 1


def test_expired_session_logs_in_again_once():
    gw, soap = gateway({
        ("PlunetAPI", "login"): ["uuid-1", "uuid-2"],
        ("DataJob30", "setJobStatus"): [failed(-1, "The UUID is invalid"), ok()],
    })
    gw.set_job_status(ProjectType.ORDER, 88213, JobStatus.CANCELED)
    assert soap.ops().count("PlunetAPI.login") == 2
    assert soap.calls[-1][2] == {"UUID": "uuid-2", "projectType": 3, "jobID": 88213, "status": 4}


def test_refusal_is_a_business_error_and_not_retried():
    gw, soap = gateway({("DataJob30", "insert2"): failed(-14, "Job type XYZ does not exist")})
    with pytest.raises(PlunetBusinessError) as err:
        gw.create_job(ProjectType.ORDER, 414, 5105, "XYZ")
    assert isinstance(err.value, BusinessError) and err.value.status_code == -14
    assert soap.ops().count("DataJob30.insert2") == 1


def test_transport_failure_is_a_technical_error():
    gw, _ = gateway({("DataItem30", "setStatus"): ConnectionError("connection reset")})
    with pytest.raises(PlunetTechnicalError) as err:
        gw.set_item_status(ProjectType.ORDER, 5105, ItemStatus.DELIVERED)
    assert isinstance(err.value, TechnicalError)


def test_login_refused():
    gw, _ = gateway({("PlunetAPI", "login"): "refused"})
    with pytest.raises(PlunetAuthError):
        gw.list_customers()


def test_missing_credentials():
    with pytest.raises(PlunetAuthError):
        SoapPlunetGateway(ScriptedSoap(), "", "").list_customers()


# Every gateway method, replayed against the recorded WSDLs.
CALLS = [
    ("version", ()),
    ("list_customers", ()),
    ("list_project_managers", ()),
    ("list_languages", ()),
    ("create_order", (DRAFT,)),
    ("create_order", (ProjectDraft(project_name="Minimal", customer_id=1),)),
    ("create_quote", (DRAFT,)),
    ("get_quote_status", (77,)),
    ("set_quote_status", (77, QuoteStatus.ACCEPTED)),
    ("get_order_id_for_quote", (77,)),
    ("delete_order", (414,)),
    ("delete_quote", (77,)),
    ("create_item", (ItemDraft(project_type=ProjectType.QUOTE, project_id=77, description="x", source_lang="en", target_lang="de-AT", deadline=DRAFT.deadline),)),
    ("set_item_status", (ProjectType.ORDER, 5105, ItemStatus.DELIVERED)),
    ("upload_document", (ProjectType.ORDER, 5105, "a.xlf", b"<xliff/>")),
    ("create_job", (ProjectType.ORDER, 414, 5105, "TRA")),
    ("get_job", (ProjectType.ORDER, 88213)),
    ("list_item_jobs", (ProjectType.ORDER, 5105)),
    ("set_job_status", (ProjectType.ORDER, 88213, JobStatus.CANCELED)),
    ("assign_resource", (ProjectType.ORDER, 88213, 21)),
    ("get_job_cost", (ProjectType.ORDER, 88213)),
]


@pytest.mark.parametrize(("method", "args"), CALLS, ids=[c[0] for c in CALLS])
def test_every_call_matches_the_wsdl(method, args):
    gw, soap = gateway({
        ("PlunetAPI", "getPlunetVersion"): ok("10.26.2"),
        ("DataOrder30", "insert2"): ok(414),
        ("DataQuote30", "insert2"): ok(77),
        ("DataQuote30", "getStatus"): ok(7),
        ("DataQuote30", "getQuoteObject"): ok(SimpleNamespace(quoteID=77, orderID=[])),
        ("DataItem30", "insert2"): ok(5105),
        ("DataJob30", "insert2"): ok(88213),
        ("DataJob30", "getJob_ForView"): ok(job_row()),
        ("DataJob30", "getJobListOfItem_ForView"): ok([job_row()]),
    })
    getattr(gw, method)(*args)  # ScriptedSoap raises if a call does not match the WSDL
    assert soap.calls
