import csv
from typing import Optional, Dict, List, Tuple

from fastapi import UploadFile
from sqlalchemy import func, or_

from app.models.inventory import InventoryItem, Rarity, Condition, Language, ComercialCondition, Tag
from app.services.inventory_validation import enum_from_value

FIELD_SYNONYMS: Dict[str, List[str]] = {
    "name": ["name", "card_name", "nombre"],
    "game": ["game", "juego"],
    "set_name": ["set_name", "set", "collection", "coleccion", "colección"],
    "set_code": ["set_code", "code", "setcode", "codigo_set", "código_set"],
    "number_set": ["number_set", "set_number", "number", "no", "número"],
    "rarity": ["rarity", "rareza"],
    "condition": ["condition", "estado"],
    "language": ["language", "lang", "idioma"],
    "quantity": ["quantity", "qty", "cantidad", "stock"],
    "location": ["location", "ubicacion", "ubicación", "where"],
    "comercial_condition": ["comercial_condition", "status", "estado_comercial", "commercial_status"],
    "variant": ["variant", "variante", "finish", "foil"],
    "notes": ["notes", "nota", "observaciones", "comments"],
    "tags": ["tags", "etiquetas", "labels"],
}


def index_for(field: str, headers: List[str]) -> Optional[int]:
    want = field.lower()
    for i, h in enumerate(headers):
        hl = (h or "").strip().lower()
        if hl and hl == want:
            return i
    for syn in FIELD_SYNONYMS.get(field, []):
        for i, h in enumerate(headers):
            if (h or "").strip().lower() == syn:
                return i
    return None


def decode_upload(upload: UploadFile) -> Tuple[str, str]:
    raw = upload.file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    try:
        sample = text[:4096]
        dialect = csv.Sniffer().sniff(sample, delimiters=[",", ";", "\t"])
        delim = dialect.delimiter
    except Exception:
        delim = ","
    return text, delim


def apply_items_filters_from_query(
    stmt,
    *,
    q: Optional[str],
    game: Optional[str],
    set_name: Optional[str],
    rarity: Optional[str],
    condition: Optional[str],
    language: Optional[str],
    comercial_condition: Optional[str],
    number_set: Optional[int],
    quantity_min: Optional[int],
    quantity_max: Optional[int],
    tag: Optional[str],
):
    filters = []

    if q:
        term = f"%{q.strip().lower()}%"
        filters.append(or_(
            func.lower(InventoryItem.name).like(term),
            func.lower(InventoryItem.set_name).like(term),
            func.lower(InventoryItem.game).like(term),
            func.lower(InventoryItem.variant).like(term),
            func.lower(InventoryItem.notes).like(term),
        ))
    if game:
        filters.append(func.lower(InventoryItem.game).like(f"%{game.strip().lower()}%"))
    if set_name:
        filters.append(func.lower(InventoryItem.set_name).like(f"%{set_name.strip().lower()}%"))

    def _enum_opt(enum_cls, value: Optional[str]):
        if not value:
            return None
        try:
            return enum_from_value(enum_cls, value)
        except Exception:
            return None

    rarity_e = _enum_opt(Rarity, rarity)
    condition_e = _enum_opt(Condition, condition)
    language_e = _enum_opt(Language, language)
    comercial_condition_e = _enum_opt(ComercialCondition, comercial_condition)

    if rarity_e:
        filters.append(InventoryItem.rarity == rarity_e)
    if condition_e:
        filters.append(InventoryItem.condition == condition_e)
    if language_e:
        filters.append(InventoryItem.language == language_e)
    if comercial_condition_e:
        filters.append(InventoryItem.comercial_condition == comercial_condition_e)

    if number_set is not None:
        filters.append(InventoryItem.number_set == number_set)
    if quantity_min is not None:
        filters.append(InventoryItem.quantity >= quantity_min)
    if quantity_max is not None:
        filters.append(InventoryItem.quantity <= quantity_max)

    if tag:
        stmt = stmt.join(InventoryItem.tags).where(Tag.name == tag)

    for f in filters:
        stmt = stmt.where(f)
    return stmt