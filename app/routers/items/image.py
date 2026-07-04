from fastapi import APIRouter, Depends, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette import status
from sqlmodel import Session

from app.db.session import get_session
from app.models.inventory import InventoryItem
from app.services.media import validate_and_save_image, delete_item_image_files, InvalidImageError

router = APIRouter()


@router.post("/item/{item_id}/image", name="upload_item_image", response_class=HTMLResponse)
def upload_item_image(
    request: Request,
    item_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    item = session.get(InventoryItem, item_id)
    if not item:
        return RedirectResponse(
            url=str(request.url_for("items_page").include_query_params(err="Item not found")),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        rel_path = validate_and_save_image(file, item_id)
    except InvalidImageError as e:
        return RedirectResponse(
            url=str(request.url_for("item_detail_page", item_id=item_id).include_query_params(err=str(e))),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if item.image_path:
        delete_item_image_files(item.image_path)

    item.image_path = rel_path
    session.add(item)
    session.commit()

    return RedirectResponse(
        url=str(request.url_for("item_detail_page", item_id=item_id).include_query_params(msg="Image updated")),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/item/{item_id}/image/delete", name="delete_item_image", response_class=HTMLResponse)
def delete_item_image(
    request: Request,
    item_id: int,
    session: Session = Depends(get_session),
):
    item = session.get(InventoryItem, item_id)
    if not item:
        return RedirectResponse(
            url=str(request.url_for("items_page").include_query_params(err="Item not found")),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if item.image_path:
        delete_item_image_files(item.image_path)
        item.image_path = None
        session.add(item)
        session.commit()

    return RedirectResponse(
        url=str(request.url_for("item_detail_page", item_id=item_id).include_query_params(msg="Image removed")),
        status_code=status.HTTP_303_SEE_OTHER,
    )