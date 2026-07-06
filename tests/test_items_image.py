from sqlmodel import select

from app.models.inventory import InventoryItem
from tests.conftest import make_png_bytes


def _create_item(client, item_payload):
    client.post("/items", data=item_payload, follow_redirects=False)


def test_upload_valid_image_sets_image_path(client, session, item_payload):
    _create_item(client, item_payload)
    item = session.exec(select(InventoryItem)).first()

    resp = client.post(
        f"/item/{item.id}/image",
        files={"file": ("card.png", make_png_bytes(), "image/png")},
        follow_redirects=False,
    )

    assert resp.status_code == 303
    session.refresh(item)
    assert item.image_path is not None
    assert item.image_path.startswith("items/")


def test_upload_rejects_spoofed_content_type(client, session, item_payload):
    _create_item(client, item_payload)
    item = session.exec(select(InventoryItem)).first()

    resp = client.post(
        f"/item/{item.id}/image",
        files={"file": ("fake.png", b"<script>not an image</script>", "image/png")},
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert "err=" in resp.headers["location"]
    session.refresh(item)
    assert item.image_path is None


def test_upload_oversized_image_is_rejected(client, session, item_payload, monkeypatch):
    from app.services import media as media_service

    _create_item(client, item_payload)
    item = session.exec(select(InventoryItem)).first()

    monkeypatch.setattr(media_service, "MAX_IMAGE_BYTES", 100)
    resp = client.post(
        f"/item/{item.id}/image",
        files={"file": ("card.png", make_png_bytes(size=(200, 200)), "image/png")},
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert "err=" in resp.headers["location"]
    session.refresh(item)
    assert item.image_path is None


def test_delete_item_image(client, session, item_payload):
    _create_item(client, item_payload)
    item = session.exec(select(InventoryItem)).first()
    client.post(
        f"/item/{item.id}/image",
        files={"file": ("card.png", make_png_bytes(), "image/png")},
        follow_redirects=False,
    )
    session.refresh(item)
    assert item.image_path is not None

    resp = client.post(f"/item/{item.id}/image/delete", follow_redirects=False)

    assert resp.status_code == 303
    session.refresh(item)
    assert item.image_path is None


def test_create_item_with_image_in_one_step(client, session, item_payload):
    resp = client.post(
        "/items",
        data=item_payload,
        files={"image": ("card.png", make_png_bytes(), "image/png")},
        follow_redirects=False,
    )

    assert resp.status_code == 303
    item = session.exec(select(InventoryItem)).first()
    assert item is not None
    assert item.image_path is not None


def test_create_item_with_invalid_image_still_creates_item(client, session, item_payload):
    resp = client.post(
        "/items",
        data=item_payload,
        files={"image": ("fake.png", b"not an image", "image/png")},
        follow_redirects=False,
    )

    assert resp.status_code == 303
    assert "err=" in resp.headers["location"]
    item = session.exec(select(InventoryItem)).first()
    assert item is not None
    assert item.image_path is None