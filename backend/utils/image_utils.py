import io
import cv2
import numpy as np
from PIL import Image, ImageOps

from .constants import MIN_ALIGN_MATCHES


def process_image(data: bytes, max_dim: int = 1600, quality: int = 82):
    """Strip metadata, resize, compress. Returns (jpeg_bytes, content_type).

    Applies EXIF orientation (exif_transpose) before stripping metadata.
    Without this, a photo with a non-default EXIF Orientation tag -- common
    for anything that went through a phone's native camera/gallery rather
    than this app's own canvas-captured selfie flow -- gets its orientation
    hint discarded while the pixel data itself stays sideways/upside-down,
    permanently, since the tag that could have corrected it later is gone.
    That silently breaks anything downstream that reads raw pixels without
    its own orientation logic: YuNet face detection, the coverage ROI
    placement, thumbnails -- all of it.
    """
    img = Image.open(io.BytesIO(data))
    if getattr(img, "is_animated", False):
        img.seek(0)
    img = ImageOps.exif_transpose(img)
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


def _decode_bgr(data: bytes):
    arr = np.frombuffer(data, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def _orb_matches(base_gray, cur_gray):
    """ORB feature detect + BFMatcher + Lowe's ratio test. Returns (kp1, kp2, good)."""
    orb = cv2.ORB_create(2000)
    kp1, des1 = orb.detectAndCompute(base_gray, None)
    kp2, des2 = orb.detectAndCompute(cur_gray, None)
    if des1 is None or des2 is None or len(kp1) < MIN_ALIGN_MATCHES or len(kp2) < MIN_ALIGN_MATCHES:
        return kp1, kp2, []
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    good = []
    for pair in matcher.knnMatch(des2, des1, k=2):
        if len(pair) == 2:
            m, n = pair
            if m.distance < 0.75 * n.distance:
                good.append(m)
    return kp1, kp2, good


def _ransac_homography(kp1, kp2, good):
    if len(good) < MIN_ALIGN_MATCHES:
        return None
    src_pts = np.float32([kp2[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst_pts = np.float32([kp1[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    homography, _ = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
    return homography


def compare_photos(baseline_bytes: bytes, current_bytes: bytes) -> dict:
    """One ORB/homography pass over a baseline/current photo pair, producing both
    the visual change heatmap and the framing-consistency numbers in a single
    pass -- align_and_diff() and framing_consistency() both need this same
    feature-matching step, so callers needing both (e.g. building AI-insight
    context) should call this directly instead of running it twice.

    Returns {"heatmap_jpeg": bytes|None, "aligned": bool, "match_count": int,
    "scale_shift_pct": float|None}. heatmap_jpeg highlights visible pixel change
    only -- not hair count or density. aligned is False when there weren't enough
    matched features for a reliable transform; a heatmap is still produced from
    the resized-but-unaligned pair, so callers should surface that caveat rather
    than presenting it as a precise comparison. scale_shift_pct is roughly how
    much closer/farther the camera appears to have been vs baseline (e.g. 25.0
    means ~25% more zoomed in or out); None when no homography could be computed.
    """
    base = _decode_bgr(baseline_bytes)
    cur = _decode_bgr(current_bytes)
    if base is None or cur is None:
        return {"heatmap_jpeg": None, "aligned": False, "match_count": 0, "scale_shift_pct": None}

    h, w = base.shape[:2]
    cur = cv2.resize(cur, (w, h))

    base_gray = cv2.cvtColor(base, cv2.COLOR_BGR2GRAY)
    cur_gray = cv2.cvtColor(cur, cv2.COLOR_BGR2GRAY)

    kp1, kp2, good = _orb_matches(base_gray, cur_gray)
    homography = _ransac_homography(kp1, kp2, good)
    aligned_cur, aligned_ok, scale_shift_pct = cur, False, None
    if homography is not None:
        aligned_cur = cv2.warpPerspective(cur, homography, (w, h))
        aligned_ok = True
        scale = float(np.sqrt(abs(np.linalg.det(homography[:2, :2]))))
        scale_shift_pct = round(abs(scale - 1.0) * 100, 1)

    # Blur before diffing so single-pixel sensor/lighting noise doesn't dominate
    # the heatmap -- it should track real structural change, not grain.
    b_blur = cv2.GaussianBlur(cv2.cvtColor(base, cv2.COLOR_BGR2GRAY), (7, 7), 0)
    c_blur = cv2.GaussianBlur(cv2.cvtColor(aligned_cur, cv2.COLOR_BGR2GRAY), (7, 7), 0)
    diff = cv2.GaussianBlur(cv2.absdiff(b_blur, c_blur), (15, 15), 0)
    diff = cv2.normalize(diff, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

    heat = cv2.applyColorMap(diff, cv2.COLORMAP_JET)
    overlay = cv2.addWeighted(aligned_cur, 0.55, heat, 0.45, 0)

    ok, buf = cv2.imencode(".jpg", overlay, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return {
        "heatmap_jpeg": buf.tobytes() if ok else None,
        "aligned": aligned_ok,
        "match_count": len(good),
        "scale_shift_pct": scale_shift_pct,
    }


def align_and_diff(baseline_bytes: bytes, current_bytes: bytes):
    """Back-compat wrapper around compare_photos() for the change-maps endpoint.
    Returns (heatmap_jpeg_bytes, aligned)."""
    cmp = compare_photos(baseline_bytes, current_bytes)
    return cmp["heatmap_jpeg"], cmp["aligned"]


def framing_consistency(baseline_bytes: bytes, current_bytes: bytes) -> dict:
    """Back-compat wrapper around compare_photos() for callers that only need the
    framing-consistency numbers, not the heatmap image.
    Returns {"aligned": bool, "match_count": int, "scale_shift_pct": float|None}."""
    cmp = compare_photos(baseline_bytes, current_bytes)
    return {"aligned": cmp["aligned"], "match_count": cmp["match_count"], "scale_shift_pct": cmp["scale_shift_pct"]}
