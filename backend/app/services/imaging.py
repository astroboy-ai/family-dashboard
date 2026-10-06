"""Thumbnails and EXIF extraction for uploaded images.

Two jobs in one place because both need Pillow and both read the original bytes
once:

``generate_thumbnail``
    Downscale to a web-sized image so a note listing does not pull a 4 MB
    original per tile. Stored beside the original and referenced by
    ``media_assets.thumb_key``.

``read_exif``
    Extract the EXIF tags a viewer can show as an overlay. Read-only by design:
    the result is returned to the caller and never written to the asset, and GPS
    is deliberately **not** copied into ``note.location`` — a photo's coordinates
    are not the same claim as a note's location.

Both are best-effort. A corrupt or exotic file must not fail the upload that
already succeeded, so every failure returns None and is logged.
"""

from __future__ import annotations

import io
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Longest edge of a thumbnail. 480 keeps a 3-up grid sharp on a retina phone
# while staying well under 100 KB for a JPEG.
THUMB_MAX_EDGE = 480
THUMB_QUALITY = 82

# EXIF tag ids worth surfacing. Names come from Pillow's ExifTags so the labels
# match what other viewers show.
_INTERESTING_TAGS = {
    271: "Make",
    272: "Model",
    274: "Orientation",
    305: "Software",
    306: "DateTime",
    34853: "GPSInfo",
}


def _exif_to_text(value: Any) -> Any:
    """Flatten EXIF values into something JSON-serialisable.

    Pillow returns IFDRational for numbers, bytes for some strings, and nested
    dicts for GPS. A raw value would break JSONB serialisation downstream.
    """

    if isinstance(value, dict):
        return {str(key): _exif_to_text(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_exif_to_text(item) for item in value]
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="replace").strip("\x00").strip()
        except Exception:  # noqa: BLE001
            return None
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    # IFDRational and friends.
    try:
        as_float = float(value)
    except (TypeError, ValueError):
        return str(value)
    # Rationals are often exact integers; keep them clean.
    return int(as_float) if as_float.is_integer() else round(as_float, 6)


def _gps_to_decimal(gps: dict[Any, Any]) -> tuple[float, float] | None:
    """Convert EXIF GPS (degrees/minutes/seconds) to signed decimal.

    Returns None when the data is incomplete or malformed — a half-parsed
    coordinate is worse than none, because it looks plausible on a map.
    """

    def to_degrees(value: Any) -> float | None:
        try:
            parts = [float(part) for part in value]
        except (TypeError, ValueError):
            return None
        if len(parts) != 3:
            return None
        return parts[0] + parts[1] / 60 + parts[2] / 3600

    latitude = to_degrees(gps.get(2))
    longitude = to_degrees(gps.get(4))
    if latitude is None or longitude is None:
        return None

    # 1 = North, 0 = South; 1 = East, 0 = West.
    if str(gps.get(1, "N")).upper().startswith("S"):
        latitude = -latitude
    if str(gps.get(3, "E")).upper().startswith("W"):
        longitude = -longitude

    if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
        return None
    return round(latitude, 6), round(longitude, 6)


def read_exif(data: bytes) -> dict[str, Any] | None:
    """Return a JSON-safe EXIF summary, or None when there is nothing to show.

    Never raises: an image without EXIF is normal, not an error.
    """

    try:
        from PIL import Image
    except ImportError:
        logger.warning("exif_unavailable_no_pillow")
        return None

    try:
        with Image.open(io.BytesIO(data)) as image:
            raw = image.getexif()
            if not raw:
                return None

            summary: dict[str, Any] = {}
            for tag_id, label in _INTERESTING_TAGS.items():
                if label == "GPSInfo":
                    continue
                value = raw.get(tag_id)
                if value is None:
                    continue
                cleaned = _exif_to_text(value)
                if cleaned not in (None, ""):
                    summary[label] = cleaned

            gps_raw = raw.get_ifd(0x8825) if hasattr(raw, "get_ifd") else None
            if gps_raw:
                coordinates = _gps_to_decimal(gps_raw)
                if coordinates is not None:
                    latitude, longitude = coordinates
                    summary["GPSLatitude"] = latitude
                    summary["GPSLongitude"] = longitude
                    summary["GPS"] = f"{latitude}, {longitude}"

            return summary or None
    except Exception as error:  # noqa: BLE001
        logger.info("exif_read_failed", error=f"{type(error).__name__}: {error}")
        return None


def generate_thumbnail(data: bytes, mime: str) -> tuple[bytes, str] | None:
    """Downscale an image. Returns (bytes, mime) or None if not possible.

    Animated formats (GIF, animated WebP) are flattened to their first frame:
    the thumbnail is a preview, and re-encoding the animation would multiply the
    stored size for no benefit.
    """

    try:
        from PIL import Image, ImageOps
    except ImportError:
        logger.warning("thumbnail_unavailable_no_pillow")
        return None

    try:
        with Image.open(io.BytesIO(data)) as image:
            # Honour the camera's orientation flag before measuring, or a
            # portrait photo gets scaled as landscape and comes out squashed.
            image = ImageOps.exif_transpose(image)

            if image.mode not in ("RGB", "L"):
                # Flatten alpha onto white rather than letting JPEG decide.
                background = Image.new("RGB", image.size, (255, 255, 255))
                if image.mode in ("RGBA", "LA", "P"):
                    converted = image.convert("RGBA")
                    background.paste(converted, mask=converted.split()[-1])
                else:
                    background.paste(image.convert("RGB"))
                image = background
            elif image.mode == "L":
                image = image.convert("RGB")

            image.thumbnail((THUMB_MAX_EDGE, THUMB_MAX_EDGE), Image.Resampling.LANCZOS)

            buffer = io.BytesIO()
            # JPEG for photos; PNG only when transparency survived, which cannot
            # happen after the flatten above, so JPEG is always correct here.
            image.save(buffer, format="JPEG", quality=THUMB_QUALITY, optimize=True)
            return buffer.getvalue(), "image/jpeg"
    except Exception as error:  # noqa: BLE001
        logger.info("thumbnail_generation_failed", error=f"{type(error).__name__}: {error}")
        return None
