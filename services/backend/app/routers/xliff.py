from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.routers.etl import find_fixtures_dir
from app.services.xliff_processor import XLIFFProcessor

router = APIRouter(prefix="/xliff", tags=["XLIFF Inspection & Tools"])


@router.get("/fixtures")
def list_fixtures() -> list[dict[str, Any]]:
    """List available XLIFF sample fixture files."""
    fixture_dir = find_fixtures_dir()
    if not fixture_dir.exists():
        return []

    results = []
    for file in sorted(fixture_dir.glob("*.xlf")):
        content = file.read_text(encoding="utf-8")
        try:
            parsed = XLIFFProcessor.parse_xliff(content)
            results.append(
                {
                    "filename": file.name,
                    "size_bytes": file.stat().st_size,
                    "source_language": parsed["source_language"],
                    "target_language": parsed["target_language"],
                    "segment_count": parsed["segment_count"],
                    "word_count": parsed["word_count"],
                }
            )
        except Exception as e:
            results.append(
                {
                    "filename": file.name,
                    "size_bytes": file.stat().st_size,
                    "error": str(e),
                }
            )
    return results


@router.get("/fixtures/{filename}")
def get_fixture_content(filename: str):
    """Get parsed inspection data and raw text for a specific fixture file."""
    fixture_dir = find_fixtures_dir()
    file_path = fixture_dir / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Fixture not found")

    raw_text = file_path.read_text(encoding="utf-8")
    try:
        parsed = XLIFFProcessor.parse_xliff(raw_text)
        return {
            "filename": filename,
            "raw_content": raw_text,
            "parsed": parsed,
        }
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to parse XLIFF fixture: {e}")


@router.post("/upload")
async def upload_xliff(file: UploadFile = File(...)):
    """Upload and parse an XLIFF file."""
    contents = await file.read()
    try:
        decoded = contents.decode("utf-8")
        parsed = XLIFFProcessor.parse_xliff(decoded)
        return {
            "filename": file.filename,
            "parsed": parsed,
            "raw_content": decoded,
        }
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid XLIFF file: {e}")
