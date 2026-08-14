import io
import os
import cv2
import numpy as np
from PIL import Image, ImageOps


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


MIN_ALIGN_MATCHES = 10


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


# ---------------------------------------------------------------------------
# EXPERIMENTAL: rough hairs/cm^2 estimate.
#
# This deliberately does NOT ask the LLM to guess a hairs/cm^2 number -- both
# steps below are real, deterministic OpenCV computation:
#   1. Physical scale calibration from a detected face's eye distance (a real
#      neural face detector, not an LLM), using population-average
#      interpupillary distance as the reference since we have no way to
#      measure this specific user's actual IPD.
#   2. Hair-vs-scalp pixel coverage in a calibration-sized region, via color
#      k-means clustering -- deterministic pixel classification, not a
#      subjective AI impression.
#
# What this does NOT have: any validated relationship between "% of pixels
# look hair-colored in a photo" and "hairs per cm^2". Real trichoscopy solves
# this by directly counting visible hair shafts under fixed magnification --
# it does not infer count from 2D coverage, because a single lying/overlapping
# hair strand obscures far more area than its own cross-section. Lacking any
# ground-truth data to fit that relationship, the estimate below scales
# coverage proportionally against a cited clinical reference density as a
# stated modeling assumption, not a measurement. The returned margin is a
# documented (not empirically fitted) combination of the specific, named
# error sources below -- see ERROR_SOURCES_PCT.
# ---------------------------------------------------------------------------

_MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "models")
_YUNET_MODEL_PATH = os.path.join(_MODELS_DIR, "face_detection_yunet.onnx")
_face_detector = None
_face_detector_size = None

# Adult interpupillary distance: real population range is ~50-75mm, with 91.5%
# of adults between 55-70mm and a mean around 62mm (women ~61mm, men ~64mm).
AVG_IPD_MM = 62.0

# Where to sample coverage, relative to the midpoint between the detected eyes:
# straight up (toward the hairline/lower scalp) by 55mm, over a 50x50mm patch.
# A geometric placeholder, not empirically tuned -- may crop oddly for
# extreme head tilts or very close/far shots.
ROI_OFFSET_MM = (0.0, -55.0)
ROI_SIZE_MM = (50.0, 50.0)

# Real clinical trichoscopy reference: normal scalp density averages roughly
# 197-208 hairs/cm^2 (frontal/parietal), 148-230/cm^2 across ethnic population
# studies. Used only as a proportionality anchor, not a fitted calibration.
REFERENCE_DENSITY_HAIRS_CM2 = 200.0
# Assumed (NOT measured) hair-colored pixel fraction this method would see in
# the sampled region for a typical full, healthy head of hair.
REFERENCE_FULL_COVERAGE_FRACTION = 0.80

# Documented, named error budget -- each a stated judgment call, not a fitted
# statistic, combined in quadrature below.
ERROR_SOURCES_PCT = {
    "eye_calibration": 10,               # real IPD population variance (cited)
    "coverage_segmentation": 38,          # untested on real photos; hair/skin color and lighting dependent
    "reference_fraction_assumption": 25,  # REFERENCE_FULL_COVERAGE_FRACTION is an unvalidated guess
    "reference_density_population": 18,   # real clinical population/site variance in the anchor value
}


def _get_face_detector(w: int, h: int):
    global _face_detector, _face_detector_size
    if _face_detector is None:
        _face_detector = cv2.FaceDetectorYN_create(_YUNET_MODEL_PATH, "", (w, h))
        _face_detector_size = (w, h)
    elif _face_detector_size != (w, h):
        _face_detector.setInputSize((w, h))
        _face_detector_size = (w, h)
    return _face_detector


def _rotate_bgr(img, angle: int):
    if angle == 90:
        return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    if angle == 180:
        return cv2.rotate(img, cv2.ROTATE_180)
    if angle == 270:
        return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return img


def _detect_face_in_frame(frame) -> "dict | None":
    h, w = frame.shape[:2]
    try:
        detector = _get_face_detector(w, h)
        _, faces = detector.detect(frame)
    except Exception:
        return None
    if faces is None or len(faces) == 0:
        return None
    face = faces[0]  # highest score first
    right_eye = np.array(face[4:6], dtype=np.float64)
    left_eye = np.array(face[6:8], dtype=np.float64)
    px_dist = float(np.linalg.norm(left_eye - right_eye))
    if px_dist < 5:
        return None
    return {
        "mm_per_px": AVG_IPD_MM / px_dist,
        "eye_mid_px": ((right_eye + left_eye) / 2).tolist(),
        "confidence": float(face[-1]),
        "image_size": (w, h),
    }


def detect_face_calibration(image_bytes: bytes) -> "dict | None":
    """Detect the most confident face via YuNet and derive a physical scale
    (mm per pixel) from its eye distance vs. population-average IPD.
    Returns None only when no face is found at all in any orientation (or
    the eye distance is degenerate) -- never calibrates off a guess. Unlike
    an earlier version of this function, a low YuNet confidence score no
    longer causes a reject by itself; the raw confidence is returned instead
    so the caller can show it and let the estimate through with an
    honestly-low confidence rather than silently discarding a real (if
    imperfect) face detection.

    Tries the image upright first, then rotated 90/180/270 if that finds
    nothing. Upright covers every canvas-captured selfie from this app's own
    scan flow (never rotated); the fallback exists for file-picker uploads of
    photos stored sideways relative to their pixel data -- most commonly a
    photo that predates the fix to process_image()'s EXIF-orientation
    handling, since a live YuNet install genuinely does not reliably find a
    90-degree-rotated face. Returns {"mm_per_px", "eye_mid_px", "confidence",
    "image_size", "rotation"} -- rotation is 0 unless a rotated attempt is
    what actually found the face.
    """
    img = _decode_bgr(image_bytes)
    if img is None:
        return None
    for angle in (0, 90, 180, 270):
        frame = img if angle == 0 else _rotate_bgr(img, angle)
        result = _detect_face_in_frame(frame)
        if result:
            result["rotation"] = angle
            return result
    return None


def estimate_hair_coverage(image_bytes: bytes, calib: dict) -> "float | None":
    """Fraction of pixels classified as hair-colored (vs. scalp/skin) in a
    calibration-sized region positioned relative to the detected eyes, via
    color k-means clustering. Deterministic pixel classification, not an AI
    guess -- but accuracy depends heavily on hair/skin color contrast and
    lighting, which has not been validated against real photos.
    """
    img = _decode_bgr(image_bytes)
    if img is None:
        return None
    img = _rotate_bgr(img, calib.get("rotation", 0))  # match the frame calibration was computed in
    w, h = calib["image_size"]
    mm_per_px = calib["mm_per_px"]
    ex, ey = calib["eye_mid_px"]
    cx = ex + ROI_OFFSET_MM[0] / mm_per_px
    cy = ey + ROI_OFFSET_MM[1] / mm_per_px
    half_w_px = (ROI_SIZE_MM[0] / 2) / mm_per_px
    half_h_px = (ROI_SIZE_MM[1] / 2) / mm_per_px
    x0, x1 = int(max(0, cx - half_w_px)), int(min(w, cx + half_w_px))
    y0, y1 = int(max(0, cy - half_h_px)), int(min(h, cy + half_h_px))
    if x1 - x0 < 10 or y1 - y0 < 10:
        return None

    roi = img[y0:y1, x0:x1]
    pixels = roi.reshape(-1, 3).astype(np.float32)
    if len(pixels) < 50:
        return None
    k = 3  # hair / scalp-skin / other (highlights, shadow, background)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 0.5)
    _, labels, centers = cv2.kmeans(pixels, k, None, criteria, 3, cv2.KMEANS_PP_CENTERS)
    # Treat the darkest cluster as "hair" -- true for most hair colors against
    # scalp/skin, but breaks down for gray/blonde hair on fair skin, a known,
    # unresolved limitation of this approach.
    hair_cluster = int(np.argmin(centers.sum(axis=1)))
    return float(np.sum(labels.flatten() == hair_cluster)) / len(labels)


def combine_error_sources(error_sources: dict) -> float:
    """Combine named, independent error-source percentages into one overall
    margin via quadrature (root-sum-square), clamped to a sane ceiling. Shared
    so any caller adjusting individual source terms (e.g. an LLM-informed
    per-photo adjustment to coverage_segmentation) recomputes the total the
    same way estimate_hair_density() does, rather than duplicating the formula.
    """
    return min(80.0, sum(v ** 2 for v in error_sources.values()) ** 0.5)


def density_result(hairs_per_cm2: float, coverage: float, calib: dict, error_sources: dict) -> dict:
    """Build the result dict for a given coverage/calibration/error-source set.
    Shared by estimate_hair_density() and by callers that recompute the margin
    after adjusting a source term (e.g. per-photo LLM reliability assessment)."""
    margin_pct = combine_error_sources(error_sources)
    margin = margin_pct / 100.0
    return {
        "hairs_per_cm2": round(hairs_per_cm2),
        "margin_pct": round(margin_pct),
        "low": max(0, round(hairs_per_cm2 * (1 - margin))),
        "high": round(hairs_per_cm2 * (1 + margin)),
        "coverage_fraction": round(coverage, 3),
        "calibration_confidence": round(calib["confidence"], 2),
        "error_sources": dict(error_sources),
        "rotation": calib.get("rotation", 0),
    }


def estimate_hair_density(image_bytes: bytes) -> "dict | None":
    """EXPERIMENTAL rough hairs/cm^2 estimate -- see module docstring above for
    exactly what is and isn't real about this. Returns None when face/eye
    calibration fails (no confident detection), rather than fabricating a
    number without a scale reference.
    """
    calib = detect_face_calibration(image_bytes)
    if calib is None:
        return None
    coverage = estimate_hair_coverage(image_bytes, calib)
    if coverage is None:
        return None

    hairs_per_cm2 = (coverage / REFERENCE_FULL_COVERAGE_FRACTION) * REFERENCE_DENSITY_HAIRS_CM2
    return density_result(hairs_per_cm2, coverage, calib, ERROR_SOURCES_PCT)
