"""Mock of a WordPress site with Polylang Pro, for FOX MLO development.

Real Polylang routes (https://polylang.pro/documentation/support/developers/rest-api/):
  GET  /wp-json/pll/v1/languages
  GET  /wp-json/wp/v2/posts|pages?lang=xx        (each item has `lang` and `translations`)
  GET  /wp-json/wp/v2/posts|pages/{id}
  POST /wp-json/wp/v2/posts|pages                 (?lang=xx&translations[yy]=id)
  POST /wp-json/wp/v2/posts|pages/{id}            (?lang=xx&translations[yy]=id)

Mock-only (not part of Polylang's REST API):
  GET  /wp-json/pll/v1/posts/{id}/xliff?target=xx  ready-made .xliff for one post × target language
  POST /mock/reset                                 restore the seed data
"""

import copy
import html
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape, quoteattr

from fastapi import FastAPI, HTTPException, Query, Request, Response

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SEED = json.loads((DATA_DIR / "seed.json").read_text(encoding="utf-8"))
SITE = SEED["site"]
LANG_SLUGS = {lang["slug"] for lang in SEED["languages"]}

app = FastAPI(title="Polylang mock", version="1.0.0")

store: dict[int, dict[str, Any]] = {}


def reset_store() -> None:
    store.clear()
    for post in copy.deepcopy(SEED["posts"]):
        post.setdefault("status", "publish")
        post.setdefault("date", "2026-10-01T09:00:00")
        store[post["id"]] = post


reset_store()


# --- Serialisation -------------------------------------------------------------------------


def _content_html(post: dict[str, Any]) -> str:
    return "".join(f"<p>{escape(s)}</p>" for s in post["segments"])


def _translations(post: dict[str, Any]) -> dict[str, int]:
    """Polylang's `translations` always includes the item itself."""
    return {**post.get("translations", {}), post["lang"]: post["id"]}


def to_wp(post: dict[str, Any]) -> dict[str, Any]:
    route = "pages" if post["type"] == "page" else "posts"
    return {
        "id": post["id"],
        "date": post["date"],
        "slug": post["slug"],
        "status": post["status"],
        "type": post["type"],
        "link": f"https://{SITE}/{post['lang']}/{post['slug']}/",
        "title": {"rendered": escape(post["title"])},
        "content": {"rendered": _content_html(post), "protected": False},
        "excerpt": {
            "rendered": f"<p>{escape(post['segments'][0])}</p>" if post["segments"] else ""
        },
        "lang": post["lang"],
        "translations": _translations(post),
        "_links": {"self": [{"href": f"/wp-json/wp/v2/{route}/{post['id']}"}]},
    }


def build_xliff(post: dict[str, Any], target: str) -> str:
    units = "\n".join(
        f'      <trans-unit id="u-{i:03d}" resname={quoteattr(f"{post['slug']}-{i}")}>\n'
        f"        <source>{escape(text)}</source>\n"
        f'        <target state="new"></target>\n'
        f"      </trans-unit>"
        for i, text in enumerate(post["segments"], start=1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">\n'
        f'  <file original="post-{post["id"]}" source-language="{post["lang"]}" '
        f'target-language="{target}" datatype="html">\n'
        f"    <header><note>{escape(post['title'])} · {SITE}</note></header>\n"
        "    <body>\n"
        f"{units}\n"
        "    </body>\n"
        "  </file>\n"
        "</xliff>\n"
    )


# --- Helpers -------------------------------------------------------------------------------


def _get(post_id: int, post_type: str | None = None) -> dict[str, Any]:
    post = store.get(post_id)
    if post is None or (post_type and post["type"] != post_type):
        raise HTTPException(
            404, detail={"code": "rest_post_invalid_id", "message": "Invalid post ID."}
        )
    return post


def _check_lang(lang: str) -> None:
    if lang not in LANG_SLUGS:
        raise HTTPException(
            400, detail={"code": "rest_invalid_param", "message": f"Invalid language: {lang}"}
        )


def _translation_params(request: Request) -> dict[str, int]:
    """Parse `translations[fr]=512` style query parameters."""
    result = {}
    for key, value in request.query_params.multi_items():
        match = re.fullmatch(r"translations\[([a-zA-Z_-]+)\]", key)
        if match:
            result[match.group(1)] = int(value)
    return result


def _link(post: dict[str, Any], translations: dict[str, int]) -> None:
    """Merge translation groups, as Polylang does: every member points at every other one."""
    group = _translations(post)
    for lang, other_id in translations.items():
        other = _get(other_id)
        if other["lang"] != lang:
            raise HTTPException(
                400,
                detail={
                    "code": "pll_invalid_translation",
                    "message": f"Post {other_id} is in '{other['lang']}', not '{lang}'.",
                },
            )
        group.update(_translations(other))
    for member_id in group.values():
        member = store[member_id]
        member["translations"] = {k: v for k, v in group.items() if v != member_id}


async def _body(request: Request) -> dict[str, Any]:
    if not await request.body():
        return {}
    return await request.json()


def _segments_from_content(content: str) -> list[str]:
    paragraphs = re.findall(r"<p>(.*?)</p>", content, flags=re.S)
    # Stored unescaped, like the seed; serialisation escapes again.
    return [html.unescape(p.strip()) for p in paragraphs] or [html.unescape(content.strip())]


# --- Routes --------------------------------------------------------------------------------


@app.get("/wp-json/pll/v1/languages")
def list_languages():
    return [
        {
            "name": lang["name"],
            "slug": lang["slug"],
            "locale": lang["locale"],
            "is_default": lang.get("is_default", False),
            "flag_url": f"https://{SITE}/wp-content/plugins/polylang-pro/flags/{lang['slug']}.png",
            "home_url": f"https://{SITE}/{lang['slug']}/",
            "page_on_front": 0,
            "page_for_posts": 0,
        }
        for lang in SEED["languages"]
    ]


def _list(post_type: str, lang: str | None, search: str | None, page: int, per_page: int):
    items = [p for p in store.values() if p["type"] == post_type]
    if lang:
        _check_lang(lang)
        items = [p for p in items if p["lang"] == lang]
    if search:
        items = [p for p in items if search.lower() in p["title"].lower()]
    items.sort(key=lambda p: p["id"])
    total = len(items)
    start = (page - 1) * per_page
    body = [to_wp(p) for p in items[start : start + per_page]]
    pages = max(1, -(-total // per_page))
    return Response(
        content=json.dumps(body),
        media_type="application/json",
        headers={"X-WP-Total": str(total), "X-WP-TotalPages": str(pages)},
    )


@app.get("/wp-json/wp/v2/posts")
def list_posts(
    lang: str | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
):
    return _list("post", lang, search, page, per_page)


@app.get("/wp-json/wp/v2/pages")
def list_pages(
    lang: str | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
):
    return _list("page", lang, search, page, per_page)


@app.get("/wp-json/wp/v2/posts/{post_id}")
def get_post(post_id: int):
    return to_wp(_get(post_id, "post"))


@app.get("/wp-json/wp/v2/pages/{post_id}")
def get_page(post_id: int):
    return to_wp(_get(post_id, "page"))


async def _create(post_type: str, request: Request, lang: str | None):
    body = await _body(request)
    lang = lang or body.get("lang")
    if not lang:
        raise HTTPException(400, detail={"code": "rest_missing_param", "message": "lang required"})
    _check_lang(lang)
    title = body.get("title", "")
    title = title.get("raw", "") if isinstance(title, dict) else title
    content = body.get("content", "")
    content = content.get("raw", "") if isinstance(content, dict) else content
    post_id = max(store) + 1
    post = {
        "id": post_id,
        "type": post_type,
        "lang": lang,
        "slug": body.get("slug") or re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-"),
        "title": title,
        "segments": body.get("segments") or _segments_from_content(content),
        "status": body.get("status", "draft"),
        "date": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S"),
        "translations": {},
    }
    store[post_id] = post
    _link(post, _translation_params(request))
    return Response(content=json.dumps(to_wp(post)), status_code=201, media_type="application/json")


async def _update(post_type: str, post_id: int, request: Request, lang: str | None):
    post = _get(post_id, post_type)
    body = await _body(request)
    if lang or body.get("lang"):
        post["lang"] = lang or body["lang"]
        _check_lang(post["lang"])
    if "title" in body:
        post["title"] = (
            body["title"].get("raw", "") if isinstance(body["title"], dict) else body["title"]
        )
    if "status" in body:
        post["status"] = body["status"]
    if "segments" in body:
        post["segments"] = body["segments"]
    elif "content" in body:
        content = body["content"]
        content = content.get("raw", "") if isinstance(content, dict) else content
        post["segments"] = _segments_from_content(content)
    _link(post, _translation_params(request))
    return to_wp(post)


@app.post("/wp-json/wp/v2/posts")
async def create_post(request: Request, lang: str | None = None):
    return await _create("post", request, lang)


@app.post("/wp-json/wp/v2/pages")
async def create_page(request: Request, lang: str | None = None):
    return await _create("page", request, lang)


@app.post("/wp-json/wp/v2/posts/{post_id}")
async def update_post(post_id: int, request: Request, lang: str | None = None):
    return await _update("post", post_id, request, lang)


@app.post("/wp-json/wp/v2/pages/{post_id}")
async def update_page(post_id: int, request: Request, lang: str | None = None):
    return await _update("page", post_id, request, lang)


@app.get("/wp-json/pll/v1/posts/{post_id}/xliff")
def get_xliff(post_id: int, target: str = Query(..., description="Target language slug")):
    """MOCK ONLY: ready-made .xliff for one post × target language."""
    post = _get(post_id)
    _check_lang(target)
    if target == post["lang"]:
        raise HTTPException(
            400, detail={"code": "rest_invalid_param", "message": "target equals source"}
        )
    ready_made = DATA_DIR / "xliff" / f"{post_id}.{target}.xlf"
    content = ready_made.read_text("utf-8") if ready_made.exists() else build_xliff(post, target)
    return Response(
        content=content,
        media_type="application/xliff+xml",
        headers={"Content-Disposition": f'attachment; filename="p{post_id}.{target}.xlf"'},
    )


@app.post("/mock/reset")
def reset():
    reset_store()
    return {"status": "reset", "posts": len(store)}


@app.get("/health")
def health():
    return {"status": "ONLINE", "posts": len(store)}
