from io import BytesIO
from pathlib import Path
from uuid import uuid4
import warnings

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError


MAX_PHOTO_BYTES = 2 * 1024 * 1024


def photo_directory():
    return Path(current_app.config.get("PROFILE_PHOTO_DIR", Path(current_app.instance_path) / "profile_photos"))


def save_profile_photo(upload):
    content = upload.stream.read(MAX_PHOTO_BYTES + 1)
    if len(content) > MAX_PHOTO_BYTES:
        raise ValueError("Ukuran foto maksimal 2 MB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as source:
                if source.format not in {"JPEG", "PNG", "WEBP"}:
                    raise ValueError("Pilih foto JPG, PNG, atau WebP")
                if source.width * source.height > 16_000_000:
                    raise ValueError("Resolusi foto maksimal 16 megapiksel")
                source.load()
                normalized = ImageOps.exif_transpose(source).convert("RGBA")
                normalized.thumbnail((1024, 1024))
                # Re-encode pixels only, without embedded metadata or trailing payloads.
                clean = Image.new("RGBA", normalized.size)
                clean.paste(normalized)
                output = BytesIO()
                clean.save(output, format="PNG")
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise ValueError("File foto tidak valid. Pilih gambar JPG, PNG, atau WebP") from error
    directory = photo_directory()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (uuid4().hex + ".png")
    try:
        path.write_bytes(output.getvalue())
    except OSError:
        path.unlink(missing_ok=True)
        raise
    return path
