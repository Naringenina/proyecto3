from typing import Optional, List
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette import status
from sqlmodel import Session, select, delete

from app.db.session import get_session
from app.models.inventory import InventoryItem, Tag, ItemTag, ComercialCondition
from app.services.inventory_validation import enum_from_value
from app.services.media import delete_item_image_files

router = APIRouter()


def _safe_redirect(return_to: Optional[str], request: Request) -> str:
    if return_to:
        try:
            base = urlsplit(str(request.base_url))
            target = urlsplit(return_to)
            if (target.scheme, target.netloc) == (base.scheme, base.netloc):
                return return_to
        except Exception:
            pass
    return str(request.url_for("items_page"))


def _with_message(dest: str, message: str) -> str:
    sep = "&" if "?" in dest else "?"
    return f"{dest}{sep}msg={message}"


@router.post("/items/bulk/adjust-qty", name="bulk_adjust_qty", response_class=HTMLResponse)
def bulk_adjust_qty(
    request: Request,
    ids: Optional[List[int]] = Form(None),
    delta: Optional[int] = Form(None),
    return_to: Optional[str] = Form(None),
    session: Session = Depends(get_session),
):
    if not ids:
        return RedirectResponse(
            url=str(request.url_for("items_page").include_query_params(err="No items selected")),
            status_code=status.HTTP_303_SEE_OTHER,
        )
    if delta is None:
        return RedirectResponse(
            url=str(request.url_for("items_page").include_query_params(err="Missing delta")),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    items = session.exec(select(InventoryItem).where(InventoryItem.id.in_(ids))).all()
    for it in items:
        it.quantity = max(0, (it.quantity or 0) + delta)
        session.add(it)
    session.commit()

    dest = _safe_redirect(return_to, request)
    return RedirectResponse(url=_with_message(dest, "Quantities updated"), status_code=status.HTTP_303_SEE_OTHER)


@router.post("/items/bulk/set-status", name="bulk_set_status", response_class=HTMLResponse)
def bulk_set_status(
    request: Request,
    ids: Optional[List[int]] = Form(None),
    status_value: Optional[str] = Form(None),
    return_to: Optional[str] = Form(None),
    session: Session = Depends(get_session),
):
    if not ids:
        return RedirectResponse(
            url=str(request.url_for("items_page").include_query_params(err="No items selected")),
            status_code=status.HTTP_303_SEE_OTHER,
        )
    if not status_value:
        return RedirectResponse(
            url=str(request.url_for("items_page").include_query_params(err="Missing status value")),
            status_code=status.HTTP_303_SEE_OTHER,
        )
    try:
        status_e = enum_from_value(ComercialCondition, status_value)
    except Exception:
        return RedirectResponse(
            url=str(request.url_for("items_page").include_query_params(err="Invalid status")),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    items = session.exec(select(InventoryItem).where(InventoryItem.id.in_(ids))).all()
    for it in items:
        it.comercial_condition = status_e
        session.add(it)
    session.commit()

    dest = _safe_redirect(return_to, request)
    return RedirectResponse(url=_with_message(dest, "Status updated"), status_code=status.HTTP_303_SEE_OTHER)


@router.post("/items/bulk/add-tag", name="bulk_add_tag", response_class=HTMLResponse)
def bulk_add_tag(
    request: Request,
    ids: Optional[List[int]] = Form(None),
    tag_name: Optional[str] = Form(None),
    create_missing: Optional[bool] = Form(True),
    return_to: Optional[str] = Form(None),
    session: Session = Depends(get_session),
):
    tag_name = (tag_name or "").strip()
    if not ids or not tag_name:
        return RedirectResponse(
            url=str(request.url_for("items_page").include_query_params(err="Select items and a tag")),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    tag = session.exec(select(Tag).where(Tag.name == tag_name)).first()
    if not tag:
        if not create_missing:
            return RedirectResponse(
                url=str(request.url_for("items_page").include_query_params(err="Tag not found")),
                status_code=status.HTTP_303_SEE_OTHER,
            )
        tag = Tag(name=tag_name)
        session.add(tag)
        session.commit()
        session.refresh(tag)

    for iid in ids:
        exists_link = session.exec(
            select(ItemTag).where(ItemTag.item_id == iid, ItemTag.tag_id == tag.id)
        ).first()
        if not exists_link:
            session.add(ItemTag(item_id=iid, tag_id=tag.id))
    session.commit()

    dest = _safe_redirect(return_to, request)
    return RedirectResponse(url=_with_message(dest, f"Tag '{tag_name}' attached"), status_code=status.HTTP_303_SEE_OTHER)


@router.post("/items/bulk/remove-tag", name="bulk_remove_tag", response_class=HTMLResponse)
def bulk_remove_tag(
    request: Request,
    ids: Optional[List[int]] = Form(None),
    tag_name: Optional[str] = Form(None),
    return_to: Optional[str] = Form(None),
    session: Session = Depends(get_session),
):
    tag_name = (tag_name or "").strip()
    if not ids or not tag_name:
        return RedirectResponse(
            url=str(request.url_for("items_page").include_query_params(err="Select items and a tag")),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    tag = session.exec(select(Tag).where(Tag.name == tag_name)).first()
    if tag:
        session.exec(delete(ItemTag).where(ItemTag.item_id.in_(ids), ItemTag.tag_id == tag.id))
        session.commit()

    dest = _safe_redirect(return_to, request)
    return RedirectResponse(url=_with_message(dest, f"Tag '{tag_name}' removed"), status_code=status.HTTP_303_SEE_OTHER)


@router.post("/items/bulk-delete", name="bulk_delete", response_class=HTMLResponse)
def bulk_delete(
    request: Request,
    ids: Optional[List[int]] = Form(None),
    return_to: Optional[str] = Form(None),
    session: Session = Depends(get_session),
):
    if not ids:
        return RedirectResponse(
            url=str(request.url_for("items_page").include_query_params(err="No items selected")),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    items = session.exec(select(InventoryItem).where(InventoryItem.id.in_(ids))).all()
    for it in items:
        session.exec(delete(ItemTag).where(ItemTag.item_id == it.id))
        if it.image_path:
            delete_item_image_files(it.image_path)
        session.delete(it)
    session.commit()

    dest = _safe_redirect(return_to, request)
    return RedirectResponse(url=_with_message(dest, "Items deleted"), status_code=status.HTTP_303_SEE_OTHER)