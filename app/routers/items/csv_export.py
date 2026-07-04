import csv
import io
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse, PlainTextResponse
from sqlalchemy.orm import selectinload
from sqlmodel import Session, select

from app.db.session import get_session
from app.models.inventory import InventoryItem
from .csv_shared import apply_items_filters_from_query

router = APIRouter()

CSV_HEADER = [
    "name", "game", "set_name", "set_code", "number_set",
    "rarity", "condition", "language",
    "quantity", "location", "comercial_condition",
    "variant", "notes", "tags", "image_path",
]


@router.get("/export/csv", name="export_csv")
def export_csv(
    q: Optional[str] = Query(default=None),
    tag: Optional[str] = Query(default=None),
    game: Optional[str] = Query(default=None),
    set_name: Optional[str] = Query(default=None),
    rarity: Optional[str] = Query(default=None),
    condition: Optional[str] = Query(default=None),
    language: Optional[str] = Query(default=None),
    comercial_condition: Optional[str] = Query(default=None),
    number_set: Optional[int] = Query(default=None),
    quantity_min: Optional[int] = Query(default=None),
    quantity_max: Optional[int] = Query(default=None),
    session: Session = Depends(get_session),
):
    stmt = select(InventoryItem).options(selectinload(InventoryItem.tags))
    stmt = apply_items_filters_from_query(
        stmt, q=q, game=game, set_name=set_name, rarity=rarity, condition=condition,
        language=language, comercial_condition=comercial_condition,
        number_set=number_set, quantity_min=quantity_min, quantity_max=quantity_max, tag=tag,
    ).order_by(InventoryItem.name.asc(), InventoryItem.set_name.asc(), InventoryItem.number_set.asc())

    rows: List[InventoryItem] = session.exec(stmt).all()

    def _gen():
        out = io.StringIO(newline="")
        writer = csv.writer(out)
        writer.writerow(CSV_HEADER)
        yield out.getvalue()
        out.seek(0); out.truncate(0)

        for it in rows:
            tags_txt = ", ".join([t.name for t in it.tags]) if getattr(it, "tags", None) else ""
            writer.writerow([
                it.name, it.game, it.set_name, it.set_code or "", it.number_set,
                it.rarity.value, it.condition.value, it.language.value,
                it.quantity, it.location or "", it.comercial_condition.value,
                it.variant or "", it.notes or "", tags_txt, it.image_path or "",
            ])
            yield out.getvalue()
            out.seek(0); out.truncate(0)

    filename = f"cards_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        _gen(), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/sample", name="export_sample_csv")
def export_sample_csv():
    sample = io.StringIO(newline="")
    w = csv.writer(sample)
    w.writerow([
        "name", "game", "set_name", "set_code", "number_set",
        "rarity", "condition", "language",
        "quantity", "location", "comercial_condition",
        "variant", "notes", "tags",
    ])
    w.writerow([
        "Pikachu", "Pokemon", "Base Set", "BS", 25,
        "Common", "NM", "EN",
        2, "Binder A-1", "Collection",
        "Holo", "First edition", "electric, mascot",
    ])
    return PlainTextResponse(
        sample.getvalue(), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="cards_sample.csv"'},
    )