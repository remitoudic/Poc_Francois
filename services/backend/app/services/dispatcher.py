import logging
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.models.job import DestinationDelivery

logger = logging.getLogger(__name__)


class DestinationDispatcher:
    """Service to transport and deliver processed XLIFF payloads to destination servers."""

    @classmethod
    async def dispatch(
        cls,
        destination_url: str,
        job_id: int,
        job_name: str,
        source_lang: str,
        target_lang: str,
        segment_count: int,
        word_count: int,
        xliff_content: str,
        db: Session = None,
    ) -> dict[str, Any]:
        """
        Send processed XLIFF payload to destination server via HTTP POST.
        """
        payload = {
            "job_id": job_id,
            "job_name": job_name,
            "source_language": source_lang,
            "target_language": target_lang,
            "segment_count": segment_count,
            "word_count": word_count,
            "xliff_content": xliff_content,
        }

        # If sending to local/internal simulation endpoint or if db provided
        if "simulate-destination" in destination_url and db is not None:
            delivery = DestinationDelivery(
                job_id=job_id,
                source_filename=job_name,
                source_language=source_lang,
                target_language=target_lang,
                segment_count=segment_count,
                word_count=word_count,
                payload_size=len(xliff_content.encode("utf-8")),
            )
            db.add(delivery)
            db.commit()
            db.refresh(delivery)

            return {
                "success": True,
                "status_code": 200,
                "response_body": f"Simulated destination server received delivery #{delivery.id} ({len(xliff_content)} chars)",
                "delivery_id": delivery.id,
            }

        # Otherwise dispatch via real HTTP client
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.post(destination_url, json=payload)
                return {
                    "success": res.status_code in (200, 201, 202, 204),
                    "status_code": res.status_code,
                    "response_body": res.text[:1000],
                }
        except Exception as e:
            logger.error(f"Failed to dispatch to {destination_url}: {e}")
            return {
                "success": False,
                "status_code": 500,
                "response_body": f"Transport error: {e!s}",
            }
