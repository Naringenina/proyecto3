from sqlmodel import select

from app.models.inventory import InventoryItem, Tag, ItemTag


def _make_item(session, **overrides):
    from app.models.inventory import Rarity, Condition, Language, ComercialCondition

    defaults = dict(
        name="Charmander", game="Pokemon", set_name="Base Set", set_code="BS",
        number_set=46, rarity=Rarity.COMMON, condition=Condition.NM, language=Language.EN,
        quantity=3, comercial_condition=ComercialCondition.COLLECTION,
    )
    item = InventoryItem(**{**defaults, **overrides})
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def test_bulk_adjust_qty(client, session):
    a = _make_item(session, quantity=3)
    b = _make_item(session, name="Bulbasaur", number_set=1, quantity=5)

    resp = client.post(
        "/items/bulk/adjust-qty",
        data={"ids": [a.id, b.id], "delta": 2},
        follow_redirects=False,
    )

    assert resp.status_code == 303
    session.refresh(a)
    session.refresh(b)
    assert a.quantity == 5
    assert b.quantity == 7


def test_bulk_adjust_qty_never_goes_below_zero(client, session):
    a = _make_item(session, quantity=1)

    client.post("/items/bulk/adjust-qty", data={"ids": [a.id], "delta": -10}, follow_redirects=False)

    session.refresh(a)
    assert a.quantity == 0


def test_bulk_set_status(client, session):
    from app.models.inventory import ComercialCondition

    a = _make_item(session)
    resp = client.post(
        "/items/bulk/set-status",
        data={"ids": [a.id], "status_value": ComercialCondition.TRADE.value},
        follow_redirects=False,
    )

    assert resp.status_code == 303
    session.refresh(a)
    assert a.comercial_condition == ComercialCondition.TRADE


def test_bulk_add_tag_creates_missing_tag_and_links_it(client, session):
    a = _make_item(session)

    resp = client.post(
        "/items/bulk/add-tag",
        data={"ids": [a.id], "tag_name": "vintage", "create_missing": True},
        follow_redirects=False,
    )

    assert resp.status_code == 303
    tag = session.exec(select(Tag).where(Tag.name == "vintage")).first()
    assert tag is not None
    link = session.exec(
        select(ItemTag).where(ItemTag.item_id == a.id, ItemTag.tag_id == tag.id)
    ).first()
    assert link is not None


def test_bulk_remove_tag(client, session):
    a = _make_item(session)
    client.post("/items/bulk/add-tag", data={"ids": [a.id], "tag_name": "vintage"}, follow_redirects=False)

    resp = client.post(
        "/items/bulk/remove-tag",
        data={"ids": [a.id], "tag_name": "vintage"},
        follow_redirects=False,
    )

    assert resp.status_code == 303
    tag = session.exec(select(Tag).where(Tag.name == "vintage")).first()
    remaining_link = session.exec(
        select(ItemTag).where(ItemTag.item_id == a.id, ItemTag.tag_id == tag.id)
    ).first()
    assert remaining_link is None


def test_bulk_delete(client, session):
    a = _make_item(session)
    b = _make_item(session, name="Squirtle", number_set=7)

    resp = client.post("/items/bulk-delete", data={"ids": [a.id, b.id]}, follow_redirects=False)

    assert resp.status_code == 303
    assert session.exec(select(InventoryItem)).all() == []


def test_bulk_actions_with_no_ids_redirect_with_error(client):
    resp = client.post("/items/bulk-delete", data={}, follow_redirects=False)
    assert resp.status_code == 303
    assert "err=" in resp.headers["location"]