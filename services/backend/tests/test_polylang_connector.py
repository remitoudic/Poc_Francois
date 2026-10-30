"""PolylangConnector against the polylang-mock app, in-process (no network)."""

import importlib.util
from pathlib import Path

import httpx
import pytest

from app.integrations.errors import BusinessError
from app.integrations.polylang import PolylangConnector
from app.integrations.source import SourceBusinessError, SourceTechnicalError
from app.xliff import parse

MOCK_MAIN = Path(__file__).resolve().parents[2] / "polylang-mock" / "app" / "main.py"


def _load_mock():
    spec = importlib.util.spec_from_file_location("polylang_mock_main", MOCK_MAIN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mock = _load_mock()


@pytest.fixture
async def polylang():
    mock.reset_store()
    connector = PolylangConnector("http://polylang", transport=httpx.ASGITransport(app=mock.app))
    yield connector
    await connector.aclose()


async def test_languages(polylang):
    langs = await polylang.list_languages()
    assert {"en", "fr"} <= {lang.slug for lang in langs}
    assert sum(lang.is_default for lang in langs) == 1


async def test_list_posts_includes_pages_and_translations(polylang):
    posts = await polylang.list_posts("en")
    assert posts and all(p.lang == "en" for p in posts)
    assert {p.type for p in posts} <= {"post", "page"}
    assert all(p.title and "<" not in p.title for p in posts)


async def test_get_xliff_parses(polylang):
    post = (await polylang.list_posts("en"))[0]
    doc = parse(await polylang.get_xliff(post.id, "fr"))
    assert doc.source_lang == "en" and doc.target_lang == "fr"
    assert doc.units and doc.words > 0


async def test_unknown_post_is_a_business_error(polylang):
    with pytest.raises(SourceBusinessError) as err:
        await polylang.get_xliff(999999, "fr")
    assert err.value.status_code == 404 and err.value.code == "rest_post_invalid_id"
    assert isinstance(err.value, BusinessError)


async def test_publish_creates_linked_translation_then_updates_it(polylang):
    source = next(p for p in await polylang.list_posts("en") if "fr" not in p.translations)
    first = await polylang.publish_translation(source, "fr", "Titre", ["Bonjour & bienvenue.", "Deuxième."])
    assert first.lang == "fr" and first.translations.get("en") == source.id

    source = await polylang.get_post(source.id)  # now knows its fr translation
    assert source.translations["fr"] == first.id
    second = await polylang.publish_translation(source, "fr", "Titre v2", ["Corrigé."])
    assert second.id == first.id  # updated, not duplicated
    assert mock.store[first.id]["segments"] == ["Corrigé."]


async def test_server_errors_are_technical():
    def boom(request):
        return httpx.Response(503)

    async with PolylangConnector("http://polylang", transport=httpx.MockTransport(boom)) as connector:
        with pytest.raises(SourceTechnicalError):
            await connector.list_languages()
