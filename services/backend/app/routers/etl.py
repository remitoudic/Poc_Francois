from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.job import DestinationDelivery, ETLJob, XLIFFSegment
from app.schemas.job import (
    DestinationPayload,
    ETLJobDetailResponse,
    ETLJobSummaryResponse,
    ETLRunRequest,
)
from app.services.dispatcher import DestinationDispatcher
from app.services.plunet_service import PlunetService
from app.services.xliff_processor import XLIFFProcessor

router = APIRouter(prefix="/etl", tags=["ETL Pipeline"])
settings = get_settings()


def find_fixtures_dir() -> Path:
    """Locate fixtures directory across docker container and local workspaces."""
    possible_paths = [
        Path("/app/fixtures/XLIFF"),
        Path(__file__).resolve().parent.parent.parent.parent.parent / "fixtures" / "XLIFF",
        Path(__file__).resolve().parent.parent.parent.parent / "fixtures" / "XLIFF",
        Path.cwd() / "fixtures" / "XLIFF",
        Path.cwd().parent / "fixtures" / "XLIFF",
        Path.cwd().parent.parent / "fixtures" / "XLIFF",
    ]
    for p in possible_paths:
        if p.exists():
            return p
    return possible_paths[0]


@router.post("/run", response_model=ETLJobDetailResponse)
async def run_etl_pipeline(req: ETLRunRequest, db: Session = Depends(get_db)):
    """
    Execute full ETL Pipeline:
    1. EXTRACT: Fetch XLIFF data from chosen source (fixture, external API, or direct upload).
    2. TRANSFORM: Parse XML, count words/segments, validate placeholders, enrich translations.
    3. PLUNET LOAD: Connect to Plunet SOAP server and register/sync project.
    4. DESTINATION LOAD: Transport the processed XLIFF to the target destination server.
    """
    raw_content = ""
    source_ref = ""

    # Step 1: EXTRACT
    if req.source_type == "fixture":
        fixture_dir = find_fixtures_dir()
        file_path = fixture_dir / (req.fixture_name or "example.fr.xlf")
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"Fixture file not found: {file_path}")
        raw_content = file_path.read_text(encoding="utf-8")
        source_ref = req.fixture_name or "example.fr.xlf"

    elif req.source_type == "api":
        if not req.api_url:
            raise HTTPException(
                status_code=400, detail="api_url is required when source_type is 'api'"
            )
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.get(req.api_url)
                res.raise_for_status()
                raw_content = res.text
                source_ref = req.api_url
        except Exception as e:
            raise HTTPException(
                status_code=502, detail=f"Failed to fetch XLIFF from remote API: {e}"
            )

    elif req.source_type == "upload":
        if not req.raw_content:
            raise HTTPException(status_code=400, detail="raw_content is required for upload")
        raw_content = req.raw_content
        source_ref = req.job_name or "Uploaded XLIFF"

    else:
        raise HTTPException(status_code=400, detail=f"Invalid source_type: {req.source_type}")

    # Step 2: TRANSFORM / PARSE
    try:
        parsed = XLIFFProcessor.parse_xliff(raw_content)
        transformed_xml, transform_meta = XLIFFProcessor.transform_xliff(raw_content)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid XLIFF XML structure: {e}")

    job_title = req.job_name or f"ETL-{parsed['original_file']}-{parsed['target_language']}"

    # Create ETL Job record
    job = ETLJob(
        job_name=job_title,
        source_type=req.source_type,
        source_reference=source_ref,
        status="PARSED",
        source_language=parsed["source_language"],
        target_language=parsed["target_language"],
        segment_count=parsed["segment_count"],
        word_count=parsed["word_count"],
        destination_url=req.destination_url or settings.DEFAULT_DESTINATION_URL,
        raw_xliff=raw_content,
        processed_xliff=transformed_xml,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Save segments
    for s in parsed["segments"]:
        seg = XLIFFSegment(
            job_id=job.id,
            unit_id=s["unit_id"],
            resname=s["resname"],
            source_text=s["source_text"],
            target_text=s["target_text"],
            notes=s["notes"],
            status=s["status"],
        )
        db.add(seg)
    db.commit()

    # Step 3: SYNC TO PLUNET
    if req.sync_with_plunet:
        plunet_svc = PlunetService()
        plunet_result = plunet_svc.register_xliff_order(
            job_name=job.job_name,
            source_lang=job.source_language,
            target_lang=job.target_language,
            word_count=job.word_count,
            segment_count=job.segment_count,
        )
        if plunet_result.get("synced"):
            job.plunet_synced = "SYNCED"
            job.plunet_order_id = plunet_result.get("plunet_order_id")
            job.plunet_status_message = plunet_result.get("message")
        else:
            job.plunet_synced = "FAILED"
            job.plunet_status_message = plunet_result.get("error")
        db.commit()

    # Step 4: TRANSPORT TO DESTINATION SERVER
    dest_url = job.destination_url or settings.DEFAULT_DESTINATION_URL
    dispatch_result = await DestinationDispatcher.dispatch(
        destination_url=dest_url,
        job_id=job.id,
        job_name=job.job_name,
        source_lang=job.source_language,
        target_lang=job.target_language,
        segment_count=job.segment_count,
        word_count=job.word_count,
        xliff_content=transformed_xml,
        db=db,
    )

    job.destination_status_code = dispatch_result.get("status_code")
    job.destination_response = dispatch_result.get("response_body")

    if dispatch_result.get("success"):
        job.status = "COMPLETED"
    else:
        job.status = "DISPATCH_FAILED"
        job.error_message = dispatch_result.get("response_body")

    db.commit()
    db.refresh(job)
    return job


@router.get("/jobs", response_model=list[ETLJobSummaryResponse])
def list_etl_jobs(limit: int = 50, db: Session = Depends(get_db)):
    """List all ETL execution jobs."""
    return db.query(ETLJob).order_by(ETLJob.created_at.desc()).limit(limit).all()


@router.get("/jobs/{job_id}", response_model=ETLJobDetailResponse)
def get_etl_job(job_id: int, db: Session = Depends(get_db)):
    """Retrieve detailed information for a specific ETL job."""
    job = db.query(ETLJob).filter(ETLJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/simulate-destination")
def simulate_destination_endpoint(payload: DestinationPayload, db: Session = Depends(get_db)):
    """
    Mock Destination Server endpoint.
    Receives transported XLIFF from Python ETL and logs delivery in database.
    """
    delivery = DestinationDelivery(
        job_id=payload.job_id,
        source_filename=payload.job_name or "Delivered Payload",
        source_language=payload.source_language,
        target_language=payload.target_language,
        segment_count=payload.segment_count,
        word_count=payload.word_count,
        payload_size=len(payload.xliff_content.encode("utf-8")),
    )
    db.add(delivery)
    db.commit()
    db.refresh(delivery)

    return {
        "status": "RECEIVED",
        "delivery_id": delivery.id,
        "message": f"Successfully received XLIFF delivery for job '{payload.job_name}'",
        "segment_count": payload.segment_count,
        "word_count": payload.word_count,
        "received_at": delivery.received_at,
    }


@router.get("/destination-deliveries")
def list_destination_deliveries(limit: int = 20, db: Session = Depends(get_db)):
    """List received deliveries on the destination server."""
    return (
        db.query(DestinationDelivery)
        .order_by(DestinationDelivery.received_at.desc())
        .limit(limit)
        .all()
    )
