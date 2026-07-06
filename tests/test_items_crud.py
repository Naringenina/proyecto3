from sqlmodel import select

from app.models.inventory import InventoryItem


def test_create_item_success(client, session, item_payload):
    resp = client.post("/items", data=item_payload, follow_redirects=False)

    assert resp.status_code == 303
    items = session.exec(select(InventoryItem)).all()
    assert len(items) == 1
    assert items[0].name == "Pikachu"
    assert items[0].quantity == 2


def test_create_item_missing_required_field_returns_400(client, session, item_payload):
    item_payload["name"] = ""
    resp = client.post("/items", data=item_payload)

    assert resp.status_code == 400
    assert session.exec(select(InventoryItem)).all() == []


def test_create_item_duplicate_key_returns_409(client, session, item_payload):
    first = client.post("/items", data=item_payload, follow_redirects=False)
    assert first.status_code == 303

    second = client.post("/items", data=item_payload)
    assert second.status_code == 409
    assert len(session.exec(select(InventoryItem)).all()) == 1


def test_create_item_different_variant_is_not_a_duplicate(client, session, item_payload):
    client.post("/items", data=item_payload, follow_redirects=False)

    non_holo = item_payload | {"variant": ""}
    resp = client.post("/items", data=non_holo, follow_redirects=False)

    assert resp.status_code == 303
    assert len(session.exec(select(InventoryItem)).all()) == 2


def test_update_item(client, session, item_payload):
    client.post("/items", data=item_payload, follow_redirects=False)
    item = session.exec(select(InventoryItem)).first()

    updated = item_payload | {"quantity": 10, "location": "Binder B-2"}
    resp = client.post(f"/item/{item.id}/edit", data=updated, follow_redirects=False)

    assert resp.status_code == 303
    session.refresh(item)
    assert item.quantity == 10
    assert item.location == "Binder B-2"


def test_update_nonexistent_item_returns_404(client, item_payload):
    resp = client.post("/item/9999/edit", data=item_payload)
    assert resp.status_code == 404


def test_merge_add_quantity(client, session, item_payload):
    client.post("/items", data=item_payload, follow_redirects=False)
    item = session.exec(select(InventoryItem)).first()
    starting_qty = item.quantity

    resp = client.post(f"/item/{item.id}/merge-add", data={"add_qty": 5}, follow_redirects=False)

    assert resp.status_code == 303
    session.refresh(item)
    assert item.quantity == starting_qty + 5


def test_delete_item(client, session, item_payload):
    client.post("/items", data=item_payload, follow_redirects=False)
    item = session.exec(select(InventoryItem)).first()

    resp = client.post(f"/item/{item.id}/delete", follow_redirects=False)

    assert resp.status_code == 303
    assert session.exec(select(InventoryItem)).all() == []