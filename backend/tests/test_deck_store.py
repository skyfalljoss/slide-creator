import json
import os
import tempfile
from pathlib import Path

import pytest

from app.models.schemas import SlideData
from app.services.platform.deck_store import DeckStore


@pytest.fixture
def tmp_db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    Path(path).unlink(missing_ok=True)


@pytest.fixture
def sample_slides():
    return [
        SlideData(index=1, title="Cover", bullets=[], notes="", layout="title"),
        SlideData(index=2, title="Overview", bullets=["Bullet 1"], notes="Notes", layout="content"),
    ]


@pytest.mark.asyncio
async def test_create_and_get_deck(tmp_db_path, sample_slides):
    store = DeckStore(tmp_db_path)
    await store.initialize()

    deck_id = await store.create(
        name="Test Deck",
        deck_type="sales_9",
        theme="minimalist",
        aspect_ratio="16:9",
        slides=sample_slides,
        thumbnail_b64=None,
    )
    assert deck_id
    assert len(deck_id) == 36

    deck = await store.get(deck_id)
    assert deck is not None
    assert deck["name"] == "Test Deck"
    assert len(deck["slides"]) == 2


@pytest.mark.asyncio
async def test_list_decks(tmp_db_path, sample_slides):
    store = DeckStore(tmp_db_path)
    await store.initialize()

    await store.create("Deck A", "sales_9", "minimalist", "16:9", sample_slides)
    await store.create("Deck B", "internal_6", "bold", "16:9", sample_slides)

    decks = await store.list_all()
    assert len(decks) == 2
    assert decks[0]["slide_count"] == 2
    assert "slides" not in decks[0]


@pytest.mark.asyncio
async def test_list_decks_with_search(tmp_db_path, sample_slides):
    store = DeckStore(tmp_db_path)
    await store.initialize()

    await store.create("Revenue Pitch", "sales_9", "minimalist", "16:9", sample_slides)
    await store.create("Operations Review", "internal_6", "minimalist", "16:9", sample_slides)

    results = await store.list_all(search="Revenue")
    assert len(results) == 1
    assert results[0]["name"] == "Revenue Pitch"


@pytest.mark.asyncio
async def test_list_decks_with_type_filter(tmp_db_path, sample_slides):
    store = DeckStore(tmp_db_path)
    await store.initialize()

    await store.create("Deck A", "sales_9", "minimalist", "16:9", sample_slides)
    await store.create("Deck B", "internal_6", "minimalist", "16:9", sample_slides)

    results = await store.list_all(deck_type="sales_9")
    assert len(results) == 1
    assert results[0]["deck_type"] == "sales_9"


@pytest.mark.asyncio
async def test_update_deck(tmp_db_path, sample_slides):
    store = DeckStore(tmp_db_path)
    await store.initialize()

    deck_id = await store.create("Original", "sales_9", "minimalist", "16:9", sample_slides)

    success = await store.update(deck_id, name="Renamed")
    assert success

    deck = await store.get(deck_id)
    assert deck["name"] == "Renamed"


@pytest.mark.asyncio
async def test_delete_deck(tmp_db_path, sample_slides):
    store = DeckStore(tmp_db_path)
    await store.initialize()

    deck_id = await store.create("To Delete", "sales_9", "minimalist", "16:9", sample_slides)
    assert await store.delete(deck_id)

    deck = await store.get(deck_id)
    assert deck is None


@pytest.mark.asyncio
async def test_get_nonexistent_deck(tmp_db_path):
    store = DeckStore(tmp_db_path)
    await store.initialize()

    deck = await store.get("nonexistent-id")
    assert deck is None


@pytest.mark.asyncio
async def test_slides_serialization_roundtrip(tmp_db_path, sample_slides):
    store = DeckStore(tmp_db_path)
    await store.initialize()

    deck_id = await store.create("Roundtrip", "sales_9", "minimalist", "16:9", sample_slides)
    deck = await store.get(deck_id)

    assert deck is not None
    restored = deck["slides"]
    assert len(restored) == 2
    assert isinstance(restored[0], SlideData)
    assert restored[0].title == "Cover"
    assert restored[1].title == "Overview"
    assert restored[1].bullets == ["Bullet 1"]
