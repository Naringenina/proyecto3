import csv
import io
from typing import Optional, Dict, List

from fastapi import APIRouter, Depends, Form, Request, UploadFile, File
from fastapi.responses import HTMLResponse
from starlette import status
from sqlmodel import Session, select

from app.db.session import get_session
from app.models.inventory import InventoryItem, Rarity, Condition, Language, ComercialCondition, Tag, ItemTag
from app.services.inventory_validation import normalize_str, enum_from_value, find_duplicate_ci
from .csv_shared import FIELD_SYNONYMS, index_for, decode_upload


def _split_tags(value: str) -> List[str]:
    import re
    if not value:
        return []
    parts = re.split(r"[;,]", value)
    return [p.strip() for p in parts if p.strip()]


router = APIRouter()


@router.post("/import/csv", name="import_csv", response_class=HTMLResponse)
def import_csv(
    request: Request,
    file: UploadFile = File(...),
    dup_policy: str = Form("merge"),
    create_missing_tags: bool = Form(True),
    session: Session = Depends(get_session),
):
    templates = request.app.state.templates
    text, delim = decode_upload(file)

    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delim)
    try:
        headers = next(reader)
    except StopIteration:
        return templates.TemplateResponse(
            request,
            "import.html", {"err": "Empty CSV file.", "result": None},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    headers_norm = [(h or "").strip() for h in headers]
    idx: Dict[str, Optional[int]] = {f: index_for(f, headers_norm) for f in FIELD_SYNONYMS.keys()}

    required = ["name", "game", "set_name", "number_set", "rarity", "condition", "language"]
    missing = [f for f in required if idx.get(f) is None]
    if missing:
        return templates.TemplateResponse(
            request,
            "import.html",
            {"err": f"Missing required columns: {', '.join(missing)}", "result": None},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    created = updated = skipped = 0
    errors: List[str] = []
    line_no = 1

    for row in reader:
        line_no += 1

        def get(field: str) -> Optional[str]:
            i = idx.get(field)
            if i is None or i >= len(row):
                return None
            val = row[i]
            return (val if val is not None else "").strip()

        try:
            name = normalize_str(get("name"))
            game = normalize_str(get("game"))
            set_name = normalize_str(get("set_name"))
            set_code = normalize_str(get("set_code"))
            number_set_str = get("number_set")
            rarity_s = get("rarity") or ""
            condition_s = get("condition") or ""
            language_s = get("language") or ""
            quantity_str = get("quantity")
            location = normalize_str(get("location"))
            comercial_condition_s = get("comercial_condition") or ComercialCondition.COLLECTION.value
            variant = normalize_str(get("variant"))
            notes = normalize_str(get("notes"))
            tags_s = get("tags")

            if not all([name, game, set_name, number_set_str, rarity_s, condition_s, language_s]):
                skipped += 1
                errors.append(f"Line {line_no}: missing required values.")
                continue

            try:
                number_set = int(number_set_str)
            except ValueError:
                skipped += 1
                errors.append(f"Line {line_no}: number_set must be integer.")
                continue

            try:
                rarity_e = enum_from_value(Rarity, rarity_s)
                condition_e = enum_from_value(Condition, condition_s)
                language_e = enum_from_value(Language, language_s)
                comercial_e = enum_from_value(ComercialCondition, comercial_condition_s)
            except Exception:
                skipped += 1
                errors.append(f"Line {line_no}: invalid enum in rarity/condition/language/comercial_condition.")
                continue

            quantity = 0
            if quantity_str not in (None, ""):
                try:
                    quantity = int(quantity_str)
                    if quantity < 0:
                        raise ValueError()
                except ValueError:
                    skipped += 1
                    errors.append(f"Line {line_no}: quantity must be integer ≥ 0.")
                    continue

            existing = find_duplicate_ci(
                session, game=game, set_code=set_code, set_name=set_name, number_set=number_set,
                language_e=language_e, condition_e=condition_e, variant=variant,
            )

            if existing:
                if dup_policy == "skip":
                    skipped += 1
                    continue
                elif dup_policy == "merge":
                    existing.quantity = (existing.quantity or 0) + quantity
                    session.add(existing)
                    session.commit()
                    item = existing
                    updated += 1
                else:
                    existing.name = name
                    existing.game = game
                    existing.set_name = set_name
                    existing.set_code = set_code
                    existing.number_set = number_set
                    existing.rarity = rarity_e
                    existing.condition = condition_e
                    existing.language = language_e
                    existing.quantity = quantity
                    existing.location = location
                    existing.comercial_condition = comercial_e
                    existing.variant = variant
                    existing.notes = notes
                    session.add(existing)
                    session.commit()
                    item = existing
                    updated += 1
            else:
                item = InventoryItem(
                    name=name, game=game, set_name=set_name, set_code=set_code, number_set=number_set,
                    rarity=rarity_e, condition=condition_e, language=language_e, quantity=quantity,
                    location=location, comercial_condition=comercial_e, variant=variant, notes=notes,
                )
                session.add(item)
                session.commit()
                created += 1

            if tags_s:
                for tname in _split_tags(tags_s):
                    tag = session.exec(select(Tag).where(Tag.name == tname)).first()
                    if not tag:
                        if not create_missing_tags:
                            continue
                        tag = Tag(name=tname)
                        session.add(tag)
                        session.commit()
                        session.refresh(tag)
                    exists_link = session.exec(
                        select(ItemTag).where(ItemTag.item_id == item.id, ItemTag.tag_id == tag.id)
                    ).first()
                    if not exists_link:
                        session.add(ItemTag(item_id=item.id, tag_id=tag.id))
                        session.commit()

        except Exception as e:
            skipped += 1
            errors.append(f"Line {line_no}: unexpected error: {e!r}")

    result = {
        "created": created, "updated": updated, "skipped": skipped,
        "errors": errors, "delimiter": delim, "total_rows": created + updated + skipped,
    }
    return templates.TemplateResponse(request, "import.html", {"err": None, "result": result})