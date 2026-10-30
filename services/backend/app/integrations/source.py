"""Where source content comes from and where translations go back (architecture §7).

Polylang (WordPress) is the only source today; another CMS would add a SourceConnector.
"""

from typing import Protocol

from pydantic import BaseModel

from app.integrations.errors import BusinessError, TechnicalError


class SourceTechnicalError(TechnicalError):
    """Source unreachable, timed out or answered 5xx. Retried by Temporal."""


class SourceBusinessError(BusinessError):
    """Source refused the request (4xx): unknown post, invalid language, rejected link."""

    def __init__(self, message: str, status_code: int | None = None, code: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


class SourceLanguage(BaseModel):
    slug: str  # e.g. "fr", "de-at"
    name: str
    locale: str
    is_default: bool = False


class SourcePost(BaseModel):
    id: int
    type: str  # "post" or "page"
    title: str
    lang: str
    link: str | None = None
    words: int = 0  # words in the rendered content
    translations: dict[str, int] = {}  # lang slug -> post id, as Polylang returns it


class PublishedTranslation(BaseModel):
    id: int
    lang: str
    link: str | None = None
    translations: dict[str, int] = {}


class SourceConnector(Protocol):
    async def list_languages(self) -> list[SourceLanguage]: ...
    async def list_posts(self, lang: str, search: str | None = None) -> list[SourcePost]: ...
    async def get_post(self, post_id: int) -> SourcePost: ...
    async def get_xliff(self, post_id: int, target_lang: str) -> str: ...
    async def publish_translation(
        self, source: SourcePost, target_lang: str, title: str, segments: list[str], status: str = "draft"
    ) -> PublishedTranslation: ...
