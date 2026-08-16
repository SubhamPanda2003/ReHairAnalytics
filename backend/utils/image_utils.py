import io
import cv2
import numpy as np
from PIL import Image, ImageOps

from .constants import MIN_ALIGN_MATCHES, ALIGN_CORRECTION_MIN_MATCHES, BLUR_VARIANCE_MIN


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


def to_base64_jpeg_for_scoring(data: bytes) -> str:
    """Same as to_base64_jpeg, but lighting-normalized first (see
    normalize_lighting). Use this specifically for photos being sent to the AI
    for a MEASUREMENT call (analyze_metrics, estimate_density_llm) -- not for
    descriptive-insight calls (generate_summary, generate_region_insights),
    which should see the photo exactly as the user actually captured it, not
    a normalized version. Falls back to the unnormalized bytes if CLAHE can't
    decode them, rather than failing the whole scoring call over a
    preprocessing step.
    """
    normalized = normalize_lighting(data)
    return to_base64_jpeg(normalized if normalized is not None else data)


def _decode_bgr(data: bytes):
    arr = np.frombuffer(data, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def blur_variance(image_bytes: bytes, max_dim: int = 1024) -> "float | None":
    """Variance of the Laplacian -- the standard deterministic sharpness proxy:
    a blurry image has fewer sharp edges, so its second-derivative response is
    both smaller and less varied. Free, instant, and consistent call to call,
    unlike asking the LLM to judge blur (see analyze_quality) -- a real
    reject-gate for obviously-unusable frames without spending an API call to
    find out. Returns None if the photo can't be decoded.

    Threshold calibration (BLUR_VARIANCE_MIN): measured 2026-08-16 against 15
    real scalp photos (same source as CAPTURE_NOISE_FLOOR) -- sharp originals
    scored 88-1109 (mean 490), a mild Gaussian blur (radius=1.2, matching
    eval_noise_floor.py's "blur_mild" perturbation) scored 46-493, and a
    clearly-unusable strong blur (radius=4) scored 6-35. There's a clean gap
    between the strong-blur ceiling and the mild-blur floor -- a threshold in
    that gap rejects genuinely broken frames without touching normal capture
    softness. Resized to max_dim first so the score isn't just a proxy for
    resolution -- a bigger photo has more pixels to compute gradients over
    regardless of how sharp it actually is.
    """
    img = _decode_bgr(image_bytes)
    if img is None:
        return None
    h, w = img.shape[:2]
    scale = min(1.0, max_dim / max(h, w))
    if scale < 1.0:
        img = cv2.resize(img, (int(w * scale), int(h * scale)))
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def normalize_lighting(image_bytes: bytes, quality: int = 85) -> "bytes | None":
    """CLAHE (contrast-limited adaptive histogram equalization) on the
    luminance channel only (LAB color space, so hue/saturation are untouched)
    -- normalizes exposure/contrast differences between photos taken under
    different lighting, one of the measured contributors to capture noise
    (see CAPTURE_NOISE_FLOOR's docstring: +/-15% brightness was part of that
    perturbation test). Only meant to be applied to the copy of a photo sent
    to the AI for SCORING -- never to the stored/displayed photo, which stays
    exactly what the user actually captured. Returns None if the photo can't
    be decoded, rather than a fabricated image.
    """
    img = _decode_bgr(image_bytes)
    if img is None:
        return None
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    normalized = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
    ok, buf = cv2.imencode(".jpg", normalized, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buf.tobytes() if ok else None


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


def align_to_reference(reference_bytes: bytes, current_bytes: bytes, max_scale_shift_pct: float = 25.0) -> "tuple[bytes, bool]":
    """Warp `current` onto the same framing as `reference` -- same ORB+homography
    machinery as compare_photos, reused rather than duplicated. Targets the
    single largest measured noise source (see CAPTURE_NOISE_FLOOR's docstring:
    a 3-degree rotation alone swung one photo's score 30->65) by normalizing
    framing BEFORE scoring, instead of only accounting for it statistically
    after the fact.

    Deliberately more conservative than compare_photos' "aligned" flag: needs
    ALIGN_CORRECTION_MIN_MATCHES matched features (stricter than
    MIN_ALIGN_MATCHES, which only gates a diff-heatmap/framing_note -- a
    visual aid) AND a plausible implied scale change, since a bad warp here
    corrupts what the AI actually scores, not just a comparison image. Falls
    back to the ORIGINAL current_bytes, completely unchanged, whenever that
    bar isn't cleared -- never guesses at a correction.

    Returns (bytes, corrected). corrected=False means current_bytes came back
    exactly as given (no reference, too few matches, decode failure, or an
    implausible homography); corrected=True means the bytes are the warped
    version, resized to match reference_bytes' dimensions.
    """
    ref = _decode_bgr(reference_bytes) if reference_bytes else None
    cur = _decode_bgr(current_bytes)
    if ref is None or cur is None:
        return current_bytes, False

    h, w = ref.shape[:2]
    cur_resized = cv2.resize(cur, (w, h))
    ref_gray = cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY)
    cur_gray = cv2.cvtColor(cur_resized, cv2.COLOR_BGR2GRAY)

    kp1, kp2, good = _orb_matches(ref_gray, cur_gray)
    if len(good) < ALIGN_CORRECTION_MIN_MATCHES:
        return current_bytes, False
    homography = _ransac_homography(kp1, kp2, good)
    if homography is None:
        return current_bytes, False

    scale = float(np.sqrt(abs(np.linalg.det(homography[:2, :2]))))
    if abs(scale - 1.0) * 100 > max_scale_shift_pct:
        # An implausible implied zoom change usually means the matched
        # features are a coincidental overlap, not a real correspondence --
        # trust the raw photo over a warp built on a bad transform.
        return current_bytes, False

    warped = cv2.warpPerspective(cur_resized, homography, (w, h), borderMode=cv2.BORDER_REPLICATE)
    ok, buf = cv2.imencode(".jpg", warped, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        return current_bytes, False
    return buf.tobytes(), True


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


def mark_scalp_patches(image_bytes: bytes, max_dim: int = 800) -> "bytes | None":
    """Highlight areas of a hair/scalp photo that color-clustering identifies as
    scalp-colored rather than hair-colored, tinted red. Purely a visual aid for
    spotting where scalp shows through -- like the change-map heatmap, this
    marks visible pixel color, not a hair count or clinical assessment.

    K-means (k=3: hair / scalp-skin / other) same as the density estimate used
    to use, treating the darkest cluster as "hair" -- true for most hair colors
    against scalp/skin, but breaks down for gray/blonde hair on fair skin, a
    known, unresolved limitation of this heuristic. Runs on the whole photo (no
    face-based ROI -- that pipeline was removed), so for regions where a lot of
    face/neck skin is in frame (mainly "front"), some of that skin can get
    tinted too; it isn't restricted to the scalp specifically.

    Returns None if the photo can't be decoded, rather than a fabricated image.
    """
    img = _decode_bgr(image_bytes)
    if img is None:
        return None
    h, w = img.shape[:2]
    scale = min(1.0, max_dim / max(h, w))
    if scale < 1.0:
        img = cv2.resize(img, (int(w * scale), int(h * scale)))
        h, w = img.shape[:2]

    pixels = img.reshape(-1, 3).astype(np.float32)
    if len(pixels) < 50:
        return None
    k = 3
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 0.5)
    _, labels, centers = cv2.kmeans(pixels, k, None, criteria, 3, cv2.KMEANS_PP_CENTERS)
    hair_cluster = int(np.argmin(centers.sum(axis=1)))
    scalp_mask = (labels.reshape(h, w) != hair_cluster).astype(np.uint8) * 255

    # Morphological open+close to clear speckle noise into coherent patches --
    # "patches" implies contiguous areas, not a salt-and-pepper pixel scatter.
    kernel = np.ones((5, 5), np.uint8)
    scalp_mask = cv2.morphologyEx(scalp_mask, cv2.MORPH_OPEN, kernel)
    scalp_mask = cv2.morphologyEx(scalp_mask, cv2.MORPH_CLOSE, kernel)

    red_layer = np.zeros_like(img)
    red_layer[:] = (0, 0, 255)  # BGR red
    blended = cv2.addWeighted(img, 0.45, red_layer, 0.55, 0)
    mask_bool = scalp_mask > 0
    overlay = img.copy()
    overlay[mask_bool] = blended[mask_bool]

    ok, buf = cv2.imencode(".jpg", overlay, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return buf.tobytes() if ok else None
