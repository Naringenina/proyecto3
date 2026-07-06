import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

from app.main import app
from app.db.session import get_session
from app.services import media as media_service
from app.models.inventory import Rarity, Condition, Language, ComercialCondition


@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(session, tmp_path, monkeypatch):
    def get_session_override():
        return session

    app.dependency_overrides[get_session] = get_session_override

    media_root = tmp_path / "media"
    monkeypatch.setattr(media_service, "MEDIA_ROOT", media_root)
    monkeypatch.setattr(media_service, "MEDIA_ITEMS_DIR", media_root / "items")
    monkeypatch.setattr(media_service, "MEDIA_THUMBS_DIR", media_root / "items" / "_thumbs")

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture
def item_payload():
    return {
        "name": "Pikachu",
        "game": "Pokemon",
        "set_name": "Base Set",
        "set_code": "BS",
        "number_set": 25,
        "rarity": Rarity.COMMON.value,
        "condition": Condition.NM.value,
        "language": Language.EN.value,
        "quantity": 2,
        "location": "Binder A-1",
        "comercial_condition": ComercialCondition.COLLECTION.value,
        "variant": "Holo",
        "notes": "First edition",
    }


def make_png_bytes(size=(10, 10)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, color=(255, 0, 0)).save(buf, format="PNG")
    return buf.getvalue()