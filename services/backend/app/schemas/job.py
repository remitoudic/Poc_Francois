from datetime import datetime

from pydantic import BaseModel, Field


class XLIFFSegmentSchema(BaseModel):
    id: int | None = None
    unit_id: str
    resname: str | None = None
    source_text: str
    target_text: str | None = None
    status: str | None = "translated"
    notes: str | None = None

    class Config:
        from_attributes = True


class ETLRunRequest(BaseModel):
    source_type: str = Field(..., description="'fixture', 'api', or 'upload'")
    fixture_name: str | None = Field(
        "example.fr.xlf", description="Fixture file name if source_type is fixture"
    )
    api_url: str | None = Field(
        None, description="External API URL to fetch XLIFF from if source_type is api"
    )
    raw_content: str | None = Field(None, description="Raw XLIFF string if source_type is upload")
    destination_url: str | None = Field(
        None, description="Destination server to push processed XLIFF to"
    )
    workflow_type: str | None = Field(
        "type 1", description="Workflow type preset (type 1, type 2, type 3)"
    )
    sync_with_plunet: bool = Field(
        True, description="Whether to register/sync with Plunet BusinessManager"
    )
    job_name: str | None = Field(None, description="Optional custom name for this ETL job")


class ETLJobSummaryResponse(BaseModel):
    id: int
    job_name: str
    source_type: str
    source_reference: str | None
    status: str
    source_language: str
    target_language: str
    segment_count: int
    word_count: int
    plunet_synced: str
    plunet_order_id: int | None
    destination_url: str | None
    destination_status_code: int | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ETLJobDetailResponse(ETLJobSummaryResponse):
    raw_xliff: str | None = None
    processed_xliff: str | None = None
    segments: list[XLIFFSegmentSchema] = []


class DestinationPayload(BaseModel):
    job_id: int | None = None
    job_name: str | None = None
    source_language: str
    target_language: str
    segment_count: int
    word_count: int
    xliff_content: str
