"""Manual smoke test against the REAL Plunet portal (PLUNET_BASE_URL, PLUNET_USERNAME, PLUNET_PASSWORD).

It writes to Plunet: creates a test order with one item, uploads a small XLIFF, creates one job,
reads its status and cost, cancels it, then deletes the order (unless --keep).
Optionally checks quote creation and the quote → order lookup (--quote).

    cd services/backend
    uv run python scripts/plunet_smoke.py --customer-id 123 --pm-id 45 [--job-type TRA] [--quote] [--keep]
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.domain.plunet_status import task_status_from_plunet  # noqa: E402
from app.integrations.plunet import (  # noqa: E402
    ItemStatus,
    JobStatus,
    ProjectType,
    QuoteStatus,
    SoapPlunetGateway,
    zeep_service_factory,
)
from app.integrations.plunet.models import ItemDraft, ProjectDraft  # noqa: E402

XLIFF = b"""<?xml version="1.0" encoding="UTF-8"?>
<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">
  <file original="fox-mlo-smoke" source-language="en" target-language="fr" datatype="plaintext">
    <body><trans-unit id="u-001"><source>FOX MLO smoke test</source><target/></trans-unit></body>
  </file>
</xliff>
"""


def step(label: str, value: object = "") -> None:
    print(f"  ✓ {label} {value}".rstrip())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--customer-id", type=int, help="Plunet customer (default: first active one)")
    parser.add_argument("--pm-id", type=int, help="Plunet resource as PM (default: first internal one)")
    parser.add_argument("--job-type", default="TRA", help="Job type short name (default TRA)")
    parser.add_argument("--quote", action="store_true", help="also create a quote and check the order lookup")
    parser.add_argument("--keep", action="store_true", help="do not delete what was created")
    args = parser.parse_args()

    s = get_settings()
    gw = SoapPlunetGateway(zeep_service_factory(s.PLUNET_BASE_URL), s.PLUNET_USERNAME, s.PLUNET_PASSWORD)
    print(f"Plunet {s.PLUNET_BASE_URL} as {s.PLUNET_USERNAME}")
    created: list[tuple[str, int]] = []
    try:
        step("version", gw.version())
        customers = gw.list_customers()
        pms = gw.list_project_managers()
        step(f"{len(customers)} active customers, {len(pms)} internal resources")
        customer_id = args.customer_id or customers[0].id
        pm_id = args.pm_id or (pms[0].id if pms else None)

        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        draft = ProjectDraft(
            project_name=f"FOX MLO smoke {stamp}",
            customer_id=customer_id,
            project_manager_id=pm_id,
            deadline=datetime.now(UTC) + timedelta(days=7),
            reference=f"FOX-SMOKE-{stamp}",
            memo="Created by services/backend/scripts/plunet_smoke.py; safe to delete.",
        )
        order = gw.create_order(draft)
        created.append(("order", order.id))
        step("order", f"{order.number} (id {order.id})")

        item_id = gw.create_item(ItemDraft(
            project_type=ProjectType.ORDER, project_id=order.id, description="P01 · smoke",
            source_lang="en", target_lang="fr", deadline=draft.deadline, reference=f"FOX-SMOKE-P1-{stamp}",
        ))
        step("item", item_id)
        gw.upload_document(ProjectType.ORDER, item_id, "fox-mlo-smoke.en-fr.xlf", XLIFF)
        step("document uploaded to item source folder", gw.list_item_files(ProjectType.ORDER, item_id))
        items = gw.list_items(ProjectType.ORDER, order.id)
        step("items of order", [(i.id, i.reference, i.source_lang, i.target_lang) for i in items])
        step("order number", gw.get_order_number(order.id))

        job_id = gw.create_job(
            ProjectType.ORDER, order.id, item_id, args.job_type,
            start_date=datetime.now(UTC), due_date=draft.deadline,
        )
        job = gw.get_job(ProjectType.ORDER, job_id)
        step("job", f"{job_id} {job.job_type} {job.status} → {task_status_from_plunet(job.status)}")
        step("job dates", f"start {job.start_date} due {job.due_date}")
        step("job cost", gw.get_job_cost(ProjectType.ORDER, job_id))
        step("job output files", gw.list_job_output(ProjectType.ORDER, job_id))

        gw.set_job_status(ProjectType.ORDER, job_id, JobStatus.CANCELED)
        job = gw.get_job(ProjectType.ORDER, job_id)
        assert job.status == "CANCELED", job.status
        step("job cancelled", job.status)
        gw.set_item_status(ProjectType.ORDER, item_id, ItemStatus.CANCELED)
        step("item cancelled")

        if args.quote:
            quote = gw.create_quote(draft.model_copy(update={"project_name": f"FOX MLO smoke quote {stamp}"}))
            created.append(("quote", quote.id))
            step("quote", f"{quote.number} status {gw.get_quote_status(quote.id).name}")
            quote_item = gw.create_item(ItemDraft(
                project_type=ProjectType.QUOTE, project_id=quote.id, description="P01 · smoke",
                source_lang="en", target_lang="de-at", deadline=draft.deadline,
            ))
            step("quote item (de-at → German)", quote_item)
            gw.upload_document(ProjectType.QUOTE, quote_item, "fox-mlo-smoke.en-de.xlf", XLIFF)
            step("quote document uploaded")
            gw.set_quote_status(quote.id, QuoteStatus.PENDING)
            step("quote released", gw.get_quote_status(quote.id).name)
            step("order for quote (None until converted in Plunet)", gw.get_order_id_for_quote(quote.id))
        print("OK")
        return 0
    except Exception as exc:
        print(f"  ✗ {type(exc).__name__}: {exc}")
        return 1
    finally:
        if not args.keep:
            for kind, obj_id in reversed(created):
                try:
                    (gw.delete_order if kind == "order" else gw.delete_quote)(obj_id)
                    print(f"  · deleted {kind} {obj_id}")
                except Exception as exc:
                    print(f"  ! could not delete {kind} {obj_id}: {exc}")
        gw.close()


if __name__ == "__main__":
    sys.exit(main())
