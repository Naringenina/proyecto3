import io
import secrets
from pathlib import Path

MEDIA_ROOT = Path(__file__).resolve().parents[1] / "media"
MEDIA_ITEMS_DIR = MEDIA_ROOT / "items"
MEDIA_THUMBS_DIR = MEDIA_ITEMS_DIR / "_thumbs"


MAX_IMAGE_BYTES = 8 * 1024 * 1024  


_FORMAT_TO_EXT = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}


class InvalidImageError(Exception):
    """Raised when an uploaded file is not a valid/allowed image, or is too large."""


def thumb_path_for(original_path: Path) -> Path:
    return MEDIA_THUMBS_DIR / f"{original_path.stem}_thumb{original_path.suffix}"


def make_thumbnail(src_path: Path, max_px: int = 360) -> bool:
    try:
        from PIL import Image, ImageOps
    except Exception:
        return False

    try:
        MEDIA_THUMBS_DIR.mkdir(parents=True, exist_ok=True)
        dst_path = thumb_path_for(src_path)

        with Image.open(src_path) as img:
            img = ImageOps.exif_transpose(img)
            img.thumbnail((max_px, max_px))
            save_kwargs = {}
            ext = src_path.suffix.lower()
            if ext in (".jpg", ".jpeg"):
                save_kwargs.update({"quality": 85, "optimize": True, "progressive": True})
            elif ext == ".webp":
                save_kwargs.update({"quality": 80, "method": 6})
            img.save(dst_path, **save_kwargs)

        return True
    except Exception:
        return False


def delete_thumbnail_for(original_rel: str) -> None:
    try:
        p = Path(original_rel)
        thumb_abs = MEDIA_THUMBS_DIR / f"{p.stem}_thumb{p.suffix}"
        if thumb_abs.exists():
            thumb_abs.unlink()
    except Exception:
        pass


def delete_item_image_files(image_rel_path: str) -> None:
    try:
        fp = MEDIA_ROOT / image_rel_path
        if fp.exists():
            fp.unlink()
    except Exception:
        pass
    delete_thumbnail_for(image_rel_path)


def validate_and_save_image(upload_file, item_id: int) -> str:
    from PIL import Image, UnidentifiedImageError

    raw = upload_file.file.read(MAX_IMAGE_BYTES + 1)
    if not raw:
        raise InvalidImageError("Empty file.")
    if len(raw) > MAX_IMAGE_BYTES:
        raise InvalidImageError(f"Image exceeds the {MAX_IMAGE_BYTES // (1024 * 1024)}MB limit.")

    try:
        with Image.open(io.BytesIO(raw)) as img:
            img.verify()
        with Image.open(io.BytesIO(raw)) as img:
            real_format = (img.format or "").upper()
    except (UnidentifiedImageError, Exception):
        raise InvalidImageError("File is not a valid image.")

    ext = _FORMAT_TO_EXT.get(real_format)
    if not ext:
        raise InvalidImageError("Unsupported image type.")

    token = secrets.token_hex(8)
    filename = f"{item_id}_{token}.{ext}"
    MEDIA_ITEMS_DIR.mkdir(parents=True, exist_ok=True)
    dest_path = MEDIA_ITEMS_DIR / filename
    dest_path.write_bytes(raw)

    make_thumbnail(dest_path)

    rel_path = Path("items") / filename
    return rel_path.as_posix()