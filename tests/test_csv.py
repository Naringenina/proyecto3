import io

from sqlmodel import select

from app.models.inventory import InventoryItem, Rarity, Condition, Language, ComercialCondition


def _make_item(session, **overrides):
    defaults = dict(
        name="Charmander", game="Pokemon", set_name="Base Set", set_code="BS",
        number_set=46, rarity=Rarity.COMMON, condition=Condition.NM, language=Language.EN,
        quantity=3, comercial_condition=ComercialCondition.COLLECTION,
    )
    item = InventoryItem(**{**defaults, **overrides})
    session.add(item)
    session.commit()
    return item


def test_export_csv_header_with_no_items(client):
    resp = client.get("/export/csv")

    assert resp.status_code == 200
    assert resp.text.splitlines()[0] == (
        "name,game,set_name,set_code,number_set,rarity,condition,language,"
        "quantity,location,comercial_condition,variant,notes,tags,image_path"
    )


def test_export_csv_contains_item_row(client, session):
    _make_item(session, name="Pikachu")

    resp = client.get("/export/csv")

    assert resp.status_code == 200
    assert "Pikachu" in resp.text


def test_export_csv_respects_filters(client, session):
    _make_item(session, name="Pikachu", game="Pokemon")
    _make_item(session, name="Charizard", game="Pokemon", number_set=4)

    resp = client.get("/export/csv", params={"q": "pika"})

    assert "Pikachu" in resp.text
    assert "Charizard" not in resp.text


def test_export_sample_csv(client):
    resp = client.get("/export/sample")
    assert resp.status_code == 200
    assert "Pikachu" in resp.text


def test_import_csv_creates_items(client, session):
    csv_content = (
        "name,game,set_name,number_set,rarity,condition,language,quantity,tags\n"
        "Squirtle,Pokemon,Base Set,7,Common,NM,EN,4,water starter\n"
    )
    resp = client.post(
        "/import/csv",
        data={"dup_policy": "merge", "create_missing_tags": "true"},
        files={"file": ("cards.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )

    assert resp.status_code == 200
    item = session.exec(select(InventoryItem).where(InventoryItem.name == "Squirtle")).first()
    assert item is not None
    assert item.quantity == 4


def test_import_csv_missing_required_column_returns_400(client):
    csv_content = "name,game\nSquirtle,Pokemon\n"
    resp = client.post(
        "/import/csv",
        data={"dup_policy": "merge"},
        files={"file": ("cards.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )
    assert resp.status_code == 400


def test_import_csv_merge_policy_adds_quantity_to_existing(client, session):
    _make_item(session, name="Squirtle", number_set=7, quantity=2, set_code="BS")

    csv_content = (
        "name,game,set_name,set_code,number_set,rarity,condition,language,quantity\n"
        "Squirtle,Pokemon,Base Set,BS,7,Common,NM,EN,3\n"
    )
    client.post(
        "/import/csv",
        data={"dup_policy": "merge"},
        files={"file": ("cards.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )

    items = session.exec(select(InventoryItem).where(InventoryItem.name == "Squirtle")).all()
    assert len(items) == 1
    assert items[0].quantity == 5