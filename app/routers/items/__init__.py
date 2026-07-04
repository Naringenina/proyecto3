from fastapi import APIRouter

from .crud import router as crud_router
from .image import router as image_router
from .bulk import router as bulk_router
from .csv_export import router as csv_export_router
from .csv_import import router as csv_import_router

router = APIRouter(tags=["items"])
router.include_router(crud_router)
router.include_router(image_router)
router.include_router(bulk_router)
router.include_router(csv_export_router)
router.include_router(csv_import_router)