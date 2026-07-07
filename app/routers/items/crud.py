from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, Form, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette import status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, delete

from app.db.session import get_session
from app.models.inventory import InventoryItem, ComercialCondition, ItemTag
from app.services.inventory_validation import parse_item_form, find_duplicate_ci, enum_options
from app.services.media import delete_item_image_files, validate_and_save_image, InvalidImageError

router = APIRouter()

DUPLICATE_MSG = "Already exist a card with the same key (duplicated variant)."


def _new_item_context(errors, raw_form: Dict[str, Any], existing=None) -> Dict[str, Any]:
    ctx = {"errors": errors, "form": raw_form, **enum_options()}
    if existing is not None:
        ctx["existing"] = existing
    return ctx


def _raw_form_echo(parsed: Dict[str, Any], *, rarity: str, condition: str, language: str,
                    comercial_condition: str, number_set, quantity) -> Dict[str, Any]:
    """Echo back what the user typed (raw strings) so the form re-renders as entered."""
    return {
        "name": parsed["name"] or "",
        "game": parsed["game"] or "",
        "set_name": parsed["set_name"] or "",
        "set_code": parsed["set_code"] or "",
        "number_set": number_set or 0,
        "rarity": rarity,
        "condition": condition,
        "language": language,
        "quantity": quantity or 0,
        "location": parsed["location"] or "",
        "comercial_condition": comercial_condition,
        "variant": parsed["variant"] or "",
        "notes": parsed["notes"] or "",
    }


def _resolved_form_echo(raw_form: Dict[str, Any], parsed: Dict[str, Any]) -> Dict[str, Any]:
    """Same as raw echo, but with enum fields resolved to their .value (used once
    parsing succeeded and we only failed on the duplicate-key check)."""
    return {
        **raw_form,
        "rarity": parsed["rarity"].value if parsed["rarity"] else "",
        "condition": parsed["condition"].value if parsed["condition"] else "",
        "language": parsed["language"].value if parsed["language"] else "",
        "comercial_condition": parsed["comercial_condition"].value if parsed["comercial_condition"] else "",
    }


@router.post("/items", name="create_item", response_class=HTMLResponse)
def create_item(
    request: Request,
    name: str = Form(...),
    game: str = Form(...),
    set_name: str = Form(...),
    number_set: int = Form(...),
    rarity: str = Form(...),
    condition: str = Form(...),
    language: str = Form(...),
    quantity: int = Form(...),
    set_code: Optional[str] = Form(None),
    location: Optional[str] = Form(None),
    comercial_condition: str = Form(ComercialCondition.COLLECTION.value),
    variant: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    session: Session = Depends(get_session),
):
    templates = request.app.state.templates

    errors, parsed = parse_item_form(
        name=name, game=game, set_name=set_name, number_set=number_set,
        rarity=rarity, condition=condition, language=language, quantity=quantity,
        set_code=set_code, location=location, comercial_condition=comercial_condition,
        variant=variant, notes=notes,
    )
    raw_form = _raw_form_echo(
        parsed, rarity=rarity, condition=condition, language=language,
        comercial_condition=comercial_condition, number_set=number_set, quantity=quantity,
    )

    if errors:
        return templates.TemplateResponse(
            request, "items/new.html", _new_item_context(errors, raw_form),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    existing = find_duplicate_ci(
        session, game=parsed["game"], set_code=parsed["set_code"], set_name=parsed["set_name"],
        number_set=parsed["number_set"], language_e=parsed["language"],
        condition_e=parsed["condition"], variant=parsed["variant"],
    )
    if existing:
        return templates.TemplateResponse(
            request,
            "items/new.html",
            _new_item_context([DUPLICATE_MSG], _resolved_form_echo(raw_form, parsed), existing=existing),
            status_code=status.HTTP_409_CONFLICT,
        )

    item = InventoryItem(
        name=parsed["name"], game=parsed["game"], set_name=parsed["set_name"],
        set_code=parsed["set_code"], number_set=parsed["number_set"],
        rarity=parsed["rarity"], condition=parsed["condition"], language=parsed["language"],
        quantity=parsed["quantity"], location=parsed["location"],
        comercial_condition=parsed["comercial_condition"], variant=parsed["variant"], notes=parsed["notes"],
    )
    try:
        session.add(item)
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = find_duplicate_ci(
            session, game=parsed["game"], set_code=parsed["set_code"], set_name=parsed["set_name"],
            number_set=parsed["number_set"], language_e=parsed["language"],
            condition_e=parsed["condition"], variant=parsed["variant"],
        )
        return templates.TemplateResponse(
            request,
            "items/new.html",
            _new_item_context([DUPLICATE_MSG], _resolved_form_echo(raw_form, parsed), existing=existing),
            status_code=status.HTTP_409_CONFLICT,
        )

    # Image is optional and attached only after the item exists (its filename
    # depends on item.id). If no file was chosen, browsers still send an
    # UploadFile with an empty filename, so check for that explicitly.
    if image is not None and image.filename:
        try:
            rel_path = validate_and_save_image(image, item.id)
            item.image_path = rel_path
            session.add(item)
            session.commit()
        except InvalidImageError as e:
            return RedirectResponse(
                url=str(request.url_for("item_detail_page", item_id=item.id).include_query_params(
                    err=f"Card created, but image was rejected: {e}"
                )),
                status_code=status.HTTP_303_SEE_OTHER,
            )

    url = request.url_for("items_page")
    if parsed["name"]:
        url = f"{url}?q={parsed['name']}"
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/item/{item_id}/merge-add", name="merge_item_quantity", response_class=HTMLResponse)
def merge_item_quantity(
    request: Request,
    item_id: int,
    add_qty: int = Form(..., ge=0),
    session: Session = Depends(get_session),
):
    if add_qty is None or add_qty < 0:
        return RedirectResponse(url=request.url_for("items_page"), status_code=status.HTTP_303_SEE_OTHER)

    item = session.get(InventoryItem, item_id)
    if not item:
        return RedirectResponse(url=request.url_for("items_page"), status_code=status.HTTP_303_SEE_OTHER)

    item.quantity = (item.quantity or 0) + add_qty
    session.add(item)
    session.commit()
    return RedirectResponse(
        url=request.url_for("item_detail_page", item_id=item_id), status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/item/{item_id}/edit", name="update_item", response_class=HTMLResponse)
def update_item(
    request: Request,
    item_id: int,
    name: str = Form(...),
    game: str = Form(...),
    set_name: str = Form(...),
    number_set: int = Form(...),
    rarity: str = Form(...),
    condition: str = Form(...),
    language: str = Form(...),
    quantity: int = Form(...),
    set_code: Optional[str] = Form(None),
    location: Optional[str] = Form(None),
    comercial_condition: str = Form(ComercialCondition.COLLECTION.value),
    variant: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    session: Session = Depends(get_session),
):
    templates = request.app.state.templates

    item = session.get(InventoryItem, item_id)
    if not item:
        return templates.TemplateResponse(
            request,
            "items/edit.html",
            {"item": None, "errors": ["The item didn't exist."], **enum_options()},
            status_code=status.HTTP_404_NOT_FOUND,
        )

    errors, parsed = parse_item_form(
        name=name, game=game, set_name=set_name, number_set=number_set,
        rarity=rarity, condition=condition, language=language, quantity=quantity,
        set_code=set_code, location=location, comercial_condition=comercial_condition,
        variant=variant, notes=notes,
    )

    if errors:
        return templates.TemplateResponse(
            request,
            "items/edit.html",
            {"item": item, "errors": errors, **enum_options()},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    existing = find_duplicate_ci(
        session, game=parsed["game"], set_code=parsed["set_code"], set_name=parsed["set_name"],
        number_set=parsed["number_set"], language_e=parsed["language"],
        condition_e=parsed["condition"], variant=parsed["variant"],
    )
    if existing and existing.id != item_id:
        return templates.TemplateResponse(
            request,
            "items/edit.html",
            {"item": item, "errors": [DUPLICATE_MSG], "existing": existing, **enum_options()},
            status_code=status.HTTP_409_CONFLICT,
        )

    item.name = parsed["name"]
    item.game = parsed["game"]
    item.set_name = parsed["set_name"]
    item.set_code = parsed["set_code"]
    item.number_set = parsed["number_set"]
    item.rarity = parsed["rarity"]
    item.condition = parsed["condition"]
    item.language = parsed["language"]
    item.quantity = parsed["quantity"]
    item.location = parsed["location"]
    item.comercial_condition = parsed["comercial_condition"]
    item.variant = parsed["variant"]
    item.notes = parsed["notes"]

    session.add(item)
    session.commit()

    return RedirectResponse(
        url=request.url_for("item_detail_page", item_id=item_id), status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/item/{item_id}/delete", name="delete_item", response_class=HTMLResponse)
def delete_item(
    request: Request,
    item_id: int,
    session: Session = Depends(get_session),
):
    item = session.get(InventoryItem, item_id)
    if item:
        session.exec(delete(ItemTag).where(ItemTag.item_id == item_id))
        if item.image_path:
            delete_item_image_files(item.image_path)
        session.delete(item)
        session.commit()
    return RedirectResponse(url=request.url_for("items_page"), status_code=status.HTTP_303_SEE_OTHER)