from typing import Optional, List, Dict, Any, Tuple

from sqlalchemy import func
from sqlmodel import Session, select

from app.models.inventory import (
    InventoryItem, Rarity, Condition, Language, ComercialCondition,
)


def normalize_str(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    s2 = s.strip()
    return s2 if s2 else None


def enum_from_value(enum_cls, value: str):
    try:
        return enum_cls(value)
    except Exception:
        return enum_cls[value]


def safe_enum(enum_cls, value: str, errors: List[str], error_msg: str):
    try:
        return enum_from_value(enum_cls, value)
    except Exception:
        errors.append(error_msg)
        return None


def find_duplicate_ci(
    session: Session,
    *,
    game: str,
    set_code: Optional[str],
    set_name: str,
    number_set: int,
    language_e: Language,
    condition_e: Condition,
    variant: Optional[str],
) -> Optional[InventoryItem]:
    g = (game or "").strip().lower()
    sc = (set_code or "").strip().lower()
    sn = (set_name or "").strip().lower()
    v = (variant or "").strip().lower()
    stmt = select(InventoryItem).where(
        func.lower(InventoryItem.game) == g,
        func.lower(func.coalesce(InventoryItem.set_code, "")) == sc,
        func.lower(InventoryItem.set_name) == sn,
        InventoryItem.number_set == number_set,
        InventoryItem.language == language_e,
        InventoryItem.condition == condition_e,
        func.lower(func.coalesce(InventoryItem.variant, "")) == v,
    )
    return session.exec(stmt).first()


def parse_item_form(
    *,
    name: str,
    game: str,
    set_name: str,
    number_set: int,
    rarity: str,
    condition: str,
    language: str,
    quantity: int,
    set_code: Optional[str] = None,
    location: Optional[str] = None,
    comercial_condition: str = ComercialCondition.COLLECTION.value,
    variant: Optional[str] = None,
    notes: Optional[str] = None,
) -> Tuple[List[str], Dict[str, Any]]:
    errors: List[str] = []

    name = normalize_str(name)
    game = normalize_str(game)
    set_name = normalize_str(set_name)
    set_code = normalize_str(set_code)
    location = normalize_str(location)
    variant = normalize_str(variant)
    notes = normalize_str(notes)

    if not name:
        errors.append("The name is required.")
    if not game:
        errors.append("The game is required.")
    if not set_name:
        errors.append("The set is required.")
    if number_set is None:
        errors.append("The number in set is required.")
    if quantity is None or quantity < 0:
        errors.append("The quantity must be an integer ≥ 0.")

    rarity_e = safe_enum(Rarity, rarity, errors, "Invalid rarity.")
    condition_e = safe_enum(Condition, condition, errors, "Invalid condition.")
    language_e = safe_enum(Language, language, errors, "Invalid language.")
    comercial_condition_e = safe_enum(
        ComercialCondition, comercial_condition, errors, "Invalid comercial condition."
    )

    parsed = dict(
        name=name, game=game, set_name=set_name, set_code=set_code, number_set=number_set,
        rarity=rarity_e, condition=condition_e, language=language_e, quantity=quantity,
        location=location, comercial_condition=comercial_condition_e,
        variant=variant, notes=notes,
    )
    return errors, parsed


def enum_options() -> Dict[str, list]:
    return {
        "rarities": list(Rarity),
        "conditions": list(Condition),
        "languages": list(Language),
        "comercial_conditions": list(ComercialCondition),
    }