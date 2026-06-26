from app.models.schemas import DeckSummary, DeckDetail, SaveDeckRequest, UpdateDeckRequest

def test_deck_summary_excludes_full_slides():
    summary = DeckSummary(
        id="abc",
        name="Test Deck",
        deck_type="sales_9",
        slide_count=9,
        thumbnail_b64=None,
        created_at="2026-06-26T00:00:00Z",
        updated_at="2026-06-26T00:00:00Z",
    )
    data = summary.model_dump()
    assert "slides" not in data
    assert data["slide_count"] == 9

def test_save_deck_request_requires_name_and_slides():
    req = SaveDeckRequest(
        name="My Deck",
        deck_type="sales_9",
        theme="minimalist",
        aspect_ratio="16:9",
        slides=[],
    )
    assert req.name == "My Deck"

def test_update_deck_request_partial():
    req = UpdateDeckRequest(name="New Name")
    assert req.name == "New Name"
    assert req.slides is None

def test_deck_detail_includes_slides():
    detail = DeckDetail(
        id="abc",
        name="Test Deck",
        deck_type="sales_9",
        theme="minimalist",
        aspect_ratio="16:9",
        slides=[],
        thumbnail_b64=None,
        created_at="2026-06-26T00:00:00Z",
        updated_at="2026-06-26T00:00:00Z",
    )
    data = detail.model_dump()
    assert "slides" in data
