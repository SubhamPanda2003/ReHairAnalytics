import io
from PIL import Image


def process_image(data: bytes, max_dim: int = 1600, quality: int = 82):
    """Strip metadata, resize, compress. Returns (jpeg_bytes, content_type)."""
    img = Image.open(io.BytesIO(data))
    if getattr(img, "is_animated", False):
        img.seek(0)
    img = img.convert("RGB")
    img.thumbnail((max_dim, max_dim), Image.LANCZOS)
    out = io.BytesIO()
    clean = Image.new("RGB", img.size)
    clean.paste(img)
    clean.save(out, format="JPEG", quality=quality, optimize=True)
    return out.getvalue(), "image/jpeg"


def make_thumbnail(data: bytes, size: int = 400, quality: int = 75):
    img = Image.open(io.BytesIO(data)).convert("RGB")
    img.thumbnail((size, size), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=quality, optimize=True)
    return out.getvalue()


def to_base64_jpeg(data: bytes) -> str:
    import base64
    img = Image.open(io.BytesIO(data)).convert("RGB")
    img.thumbnail((1024, 1024), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=80)
    return base64.b64encode(out.getvalue()).decode()
