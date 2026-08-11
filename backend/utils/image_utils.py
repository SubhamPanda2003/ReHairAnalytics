import io
import cv2
import numpy as np
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


MIN_ALIGN_MATCHES = 10


def _decode_bgr(data: bytes):
    arr = np.frombuffer(data, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def align_and_diff(baseline_bytes: bytes, current_bytes: bytes):
    """Align `current` onto `baseline`'s frame (ORB features + RANSAC homography),
    then render a change heatmap highlighting where the two now-aligned photos
    visibly differ. This measures visible pixel change only -- not hair count or
    density -- so callers should present it as "visual change", not a
    measurement.

    Returns (heatmap_jpeg_bytes, aligned). `aligned` is False when there weren't
    enough matched features for a reliable transform (very different angle, low
    detail, etc.); a heatmap is still produced from the resized-but-unaligned
    pair, so callers should surface that caveat rather than presenting it as a
    precise comparison.
    """
    base = _decode_bgr(baseline_bytes)
    cur = _decode_bgr(current_bytes)
    if base is None or cur is None:
        return None, False

    h, w = base.shape[:2]
    cur = cv2.resize(cur, (w, h))

    base_gray = cv2.cvtColor(base, cv2.COLOR_BGR2GRAY)
    cur_gray = cv2.cvtColor(cur, cv2.COLOR_BGR2GRAY)

    orb = cv2.ORB_create(2000)
    kp1, des1 = orb.detectAndCompute(base_gray, None)
    kp2, des2 = orb.detectAndCompute(cur_gray, None)

    aligned_cur, aligned_ok = cur, False
    if des1 is not None and des2 is not None and len(kp1) >= MIN_ALIGN_MATCHES and len(kp2) >= MIN_ALIGN_MATCHES:
        matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
        good = []
        for pair in matcher.knnMatch(des2, des1, k=2):
            if len(pair) == 2:
                m, n = pair
                if m.distance < 0.75 * n.distance:
                    good.append(m)
        if len(good) >= MIN_ALIGN_MATCHES:
            src_pts = np.float32([kp2[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
            dst_pts = np.float32([kp1[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
            homography, _ = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
            if homography is not None:
                aligned_cur = cv2.warpPerspective(cur, homography, (w, h))
                aligned_ok = True

    # Blur before diffing so single-pixel sensor/lighting noise doesn't dominate
    # the heatmap -- it should track real structural change, not grain.
    b_blur = cv2.GaussianBlur(cv2.cvtColor(base, cv2.COLOR_BGR2GRAY), (7, 7), 0)
    c_blur = cv2.GaussianBlur(cv2.cvtColor(aligned_cur, cv2.COLOR_BGR2GRAY), (7, 7), 0)
    diff = cv2.GaussianBlur(cv2.absdiff(b_blur, c_blur), (15, 15), 0)
    diff = cv2.normalize(diff, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

    heat = cv2.applyColorMap(diff, cv2.COLORMAP_JET)
    overlay = cv2.addWeighted(aligned_cur, 0.55, heat, 0.45, 0)

    ok, buf = cv2.imencode(".jpg", overlay, [cv2.IMWRITE_JPEG_QUALITY, 88])
    if not ok:
        return None, False
    return buf.tobytes(), aligned_ok
