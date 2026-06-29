import pytest

from tests.test_decks_api import _create, _slides, deck_api as deck_api


@pytest.mark.asyncio
async def test_status_history_restore_rename_and_download(deck_api):
    client, repository, storage = deck_api
    deck_id = (await _create(client, name='../../Quarterly\r\nReport: Q1')).json()["id"]
    headers = {"x-user-id": "alice"}

    for number in range(2, 7):
        response = await client.put(
            f"/api/v1/decks/{deck_id}",
            headers=headers,
            json={"slides": _slides(f"Version {number}")},
        )
        assert response.status_code == 200

    history = await client.get(
        f"/api/v1/decks/{deck_id}/versions", headers=headers
    )
    assert history.status_code == 200
    versions = history.json()["versions"]
    assert [item["version_number"] for item in versions] == [6, 5, 4, 3, 2]
    assert all("storage_key" not in item for item in versions)
    version_two_id = versions[-1]["id"]

    status = await client.get(f"/api/v1/decks/{deck_id}/status", headers=headers)
    assert status.status_code == 200
    assert status.json()["current_version_number"] == 6

    restored = await client.post(
        f"/api/v1/decks/{deck_id}/versions/{version_two_id}/restore",
        headers=headers,
    )
    assert restored.status_code == 200
    assert restored.json()["current_version_number"] == 7
    assert restored.json()["current_version_id"] != version_two_id

    renamed = await client.patch(
        f"/api/v1/decks/{deck_id}", headers=headers, json={"name": "Final Deck"}
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Final Deck"

    deck = await repository.get(deck_id, "alice")
    assert deck is not None and deck.current_version is not None
    expected = await storage.read(deck.current_version.storage_key)
    downloaded = await client.get(f"/api/v1/decks/{deck_id}/download", headers=headers)
    assert downloaded.status_code == 200
    assert downloaded.content == expected
    assert downloaded.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )
    assert downloaded.headers["content-disposition"] == (
        'attachment; filename="Final Deck.pptx"'
    )


@pytest.mark.asyncio
async def test_download_sanitizes_attachment_filename(deck_api):
    client, _repository, _storage = deck_api
    deck_id = (await _create(client, name="../Q1\r\nReport?.pptx")).json()["id"]

    response = await client.get(
        f"/api/v1/decks/{deck_id}/download", headers={"x-user-id": "alice"}
    )

    assert response.status_code == 200
    disposition = response.headers["content-disposition"]
    assert "\r" not in disposition and "\n" not in disposition
    assert ".." not in disposition and "/" not in disposition and "?" not in disposition
    assert disposition.endswith('.pptx"')


@pytest.mark.asyncio
async def test_history_routes_are_all_owner_scoped(deck_api):
    client, repository, _storage = deck_api
    deck_id = (await _create(client)).json()["id"]
    deck = await repository.get(deck_id, "alice")
    assert deck is not None and deck.current_version is not None
    version_id = deck.current_version.id
    headers = {"x-user-id": "bob"}

    responses = [
        await client.get(f"/api/v1/decks/{deck_id}/status", headers=headers),
        await client.get(f"/api/v1/decks/{deck_id}/versions", headers=headers),
        await client.post(
            f"/api/v1/decks/{deck_id}/versions/{version_id}/restore",
            headers=headers,
        ),
        await client.get(f"/api/v1/decks/{deck_id}/download", headers=headers),
    ]

    assert [response.status_code for response in responses] == [404, 404, 404, 404]
