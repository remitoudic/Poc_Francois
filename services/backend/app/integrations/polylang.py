"""Polylang (WordPress REST) connector. Talks to polylang-mock today, a real site later.

Real Polylang routes: https://polylang.pro/documentation/support/developers/rest-api/
`/wp-json/pll/v1/posts/{id}/xliff` is served by the mock only; on a real site the XLIFF export
needs a plugin endpoint (open item in docs/backend-implementation-plan.md).
"""

from __future__ import annotations

import html
import re
from typing import Any

import httpx

from app.integrations.source import (
    PublishedTranslation,
    SourceBusinessError,
    SourceLanguage,
    SourcePost,
    SourceTechnicalError,
)

_TAGS = re.compile(r"<[^>]+>")
_PER_PAGE = 100


def _text(rendered: str) -> str:
    return html.unescape(_TAGS.sub("", rendered or "")).strip()


def _words(rendered: str) -> int:
    return len(html.unescape(_TAGS.sub(" ", rendered or "")).split())  # tags separate words


def _post(data: dict[str, Any]) -> SourcePost:
    return SourcePost(
        id=data["id"],
        type=data.get("type", "post"),
        title=_text(data.get("title", {}).get("rendered", "")),
        lang=data.get("lang", ""),
        link=data.get("link"),
        words=_words(data.get("content", {}).get("rendered", "")),
        translations=data.get("translations") or {},
    )


class PolylangConnector:
    def __init__(
        self,
        base_url: str,
        username: str = "",
        app_password: str = "",
        timeout: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        auth = httpx.BasicAuth(username, app_password) if username else None
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"), auth=auth, timeout=timeout, transport=transport
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> PolylangConnector:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise SourceTechnicalError(f"Polylang {method} {path}: {exc}") from exc
        if response.status_code >= 500 or response.status_code == 429:
            raise SourceTechnicalError(f"Polylang {method} {path}: HTTP {response.status_code}")
        if response.status_code >= 400:
            code, message = None, response.text
            try:
                body = response.json()
                detail = body.get("detail", body) if isinstance(body, dict) else {}
                code, message = detail.get("code"), detail.get("message", message)
            except ValueError:
                pass
            raise SourceBusinessError(
                f"Polylang {method} {path}: {message}", status_code=response.status_code, code=code
            )
        return response

    async def list_languages(self) -> list[SourceLanguage]:
        response = await self._request("GET", "/wp-json/pll/v1/languages")
        return [SourceLanguage.model_validate(lang) for lang in response.json()]

    async def list_posts(self, lang: str, search: str | None = None) -> list[SourcePost]:
        """Posts and pages in one language, all pages of results."""
        posts: list[SourcePost] = []
        for route in ("posts", "pages"):
            page, total_pages = 1, 1
            while page <= total_pages:
                params: dict[str, Any] = {"lang": lang, "page": page, "per_page": _PER_PAGE}
                if search:
                    params["search"] = search
                response = await self._request("GET", f"/wp-json/wp/v2/{route}", params=params)
                posts.extend(_post(p) for p in response.json())
                total_pages = int(response.headers.get("X-WP-TotalPages", "1"))
                page += 1
        return posts

    async def get_post(self, post_id: int) -> SourcePost:
        try:
            response = await self._request("GET", f"/wp-json/wp/v2/posts/{post_id}")
        except SourceBusinessError as exc:
            if exc.status_code != 404:
                raise
            response = await self._request("GET", f"/wp-json/wp/v2/pages/{post_id}")
        return _post(response.json())

    async def get_xliff(self, post_id: int, target_lang: str) -> str:
        response = await self._request(
            "GET", f"/wp-json/pll/v1/posts/{post_id}/xliff", params={"target": target_lang}
        )
        return response.text

    async def publish_translation(
        self, source: SourcePost, target_lang: str, title: str, segments: list[str], status: str = "draft"
    ) -> PublishedTranslation:
        """Create the translated post, or update it if one already exists, linked to the source
        through Polylang's `translations[lang]=id` parameter. Safe to call again (idempotent)."""
        route = "pages" if source.type == "page" else "posts"
        params = {"lang": target_lang, f"translations[{source.lang}]": source.id}
        body = {
            "title": title,
            "content": "".join(f"<p>{html.escape(s, quote=False)}</p>" for s in segments),
            "status": status,
        }
        existing = source.translations.get(target_lang)
        path = f"/wp-json/wp/v2/{route}/{existing}" if existing else f"/wp-json/wp/v2/{route}"
        response = await self._request("POST", path, params=params, json=body)
        data = response.json()
        return PublishedTranslation(
            id=data["id"], lang=data.get("lang", target_lang), link=data.get("link"),
            translations=data.get("translations") or {},
        )
