"""OpenCV-based building footprint extraction and image annotation."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from ber_automation.geospatial.scale import meters_per_pixel
from ber_automation.models import FootprintResult


def extract_footprint(
    image_path: str | Path,
    lat: float,
    zoom: int = 20,
    expected_length_m: float | None = None,
    expected_width_m: float | None = None,
) -> FootprintResult:
    """Extract building footprint from a satellite image using OpenCV.

    Pipeline:
        1. Grayscale → bilateral filter (edge-preserving smoothing)
        2. CLAHE (adaptive histogram equalization)
        3. Canny edge detection → dilate to close gaps
        4. Find contours, score by area + solidity + centrality + rectangularity
           + dimension match (when expected_length_m/width_m are provided)
        5. Fit minimum-area bounding rectangle → convert to meters

    Args:
        image_path: Path to the satellite image.
        lat: Latitude for pixel-to-meter conversion.
        zoom: Google Maps zoom level used when fetching the image.
        expected_length_m: Expected building length from Claude Vision. When
            provided, contours whose dimensions match are scored higher — this
            guides OpenCV to pick the right building among many in the image.
        expected_width_m: Expected building width from Claude Vision.

    Returns:
        FootprintResult with estimated length, width, area, and confidence.
    """
    img = cv2.imread(str(image_path))
    if img is None:
        raise FileNotFoundError(f"Cannot read image: {image_path}")

    h, w = img.shape[:2]
    cx, cy = w // 2, h // 2

    # 1. Grayscale + bilateral filter
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    filtered = cv2.bilateralFilter(gray, d=9, sigmaColor=75, sigmaSpace=75)

    # 2. CLAHE for contrast enhancement
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(filtered)

    # 3. Canny + dilate
    edges = cv2.Canny(enhanced, threshold1=30, threshold2=100)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    dilated = cv2.dilate(edges, kernel, iterations=2)

    # 4. Find contours
    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return FootprintResult(length_m=0, width_m=0, area_m2=0, confidence=0)

    # 5. Score contours
    mpp = meters_per_pixel(lat, zoom)
    min_side_px = 4.0 / mpp if mpp > 0 else 0  # 4m minimum side
    max_side_px = 25.0 / mpp if mpp > 0 else float("inf")  # 25m maximum side

    scored = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 100:  # skip tiny contours
            continue

        # Pixel-area bounds: skip contours outside plausible building size
        rect = cv2.minAreaRect(cnt)
        rect_w_px, rect_h_px = rect[1]
        long_px = max(rect_w_px, rect_h_px)
        short_px = min(rect_w_px, rect_h_px)
        if short_px < min_side_px or long_px > max_side_px:
            continue

        # Solidity: contour area / convex hull area
        hull = cv2.convexHull(cnt)
        hull_area = cv2.contourArea(hull)
        solidity = area / hull_area if hull_area > 0 else 0

        # Centrality: distance from contour centroid to image center
        M = cv2.moments(cnt)
        if M["m00"] == 0:
            continue
        cnt_cx = int(M["m10"] / M["m00"])
        cnt_cy = int(M["m01"] / M["m00"])
        dist = np.sqrt((cnt_cx - cx) ** 2 + (cnt_cy - cy) ** 2)
        max_dist = np.sqrt(cx**2 + cy**2)
        centrality = 1.0 - (dist / max_dist) if max_dist > 0 else 0

        # Rectangularity: contour area / bounding rect area
        rect_area = rect_w_px * rect_h_px
        rectangularity = area / rect_area if rect_area > 0 else 0

        # Dimension match: how closely does this contour's size match Claude's estimate?
        # Gives the highest weight to the contour that is the right size building.
        if expected_length_m is not None and expected_width_m is not None and mpp > 0:
            long_m = long_px * mpp
            short_m = short_px * mpp
            exp_long = max(expected_length_m, expected_width_m)
            exp_short = min(expected_length_m, expected_width_m)
            ratio_long = min(long_m, exp_long) / max(max(long_m, exp_long), 0.1)
            ratio_short = min(short_m, exp_short) / max(max(short_m, exp_short), 0.1)
            dim_match = min(ratio_long, ratio_short)  # both dimensions must match
        else:
            dim_match = 0.5  # neutral when no expectation

        score = (
            0.10 * (area / (w * h))
            + 0.20 * solidity
            + 0.20 * centrality
            + 0.15 * rectangularity
            + 0.35 * dim_match
        )
        scored.append((score, cnt, rect))

    if not scored:
        return FootprintResult(length_m=0, width_m=0, area_m2=0, confidence=0)

    # Pick best contour
    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best_cnt, best_rect = scored[0]

    # Convert pixels to meters
    rect_w_px, rect_h_px = best_rect[1]
    length_m = max(rect_w_px, rect_h_px) * mpp
    width_m = min(rect_w_px, rect_h_px) * mpp
    area_m2 = length_m * width_m

    # Confidence based on score (normalize to 0-1)
    confidence = min(1.0, best_score * 2.0)

    # Force low confidence if dimensions are implausibly large
    if length_m > 30 or width_m > 30:
        confidence = min(confidence, 0.15)

    # Contour points for visualization
    points = best_cnt.reshape(-1, 2).tolist()

    return FootprintResult(
        length_m=round(length_m, 1),
        width_m=round(width_m, 1),
        area_m2=round(area_m2, 1),
        confidence=round(confidence, 2),
        contour_points=points,
    )


def draw_footprint_overlay(
    image_path: str | Path,
    footprint: FootprintResult,
    output_path: str | Path,
    lat: float | None = None,
    zoom: int | None = None,
) -> Path:
    """Draw the detected footprint and architectural dimension annotations on the satellite image.

    Three cases for contour source:
    - 4-point contour (Claude bbox): drawn as a rectangle
    - Many-point contour (OpenCV polygon): polygon drawn, bounding rect used for annotation
    - No contour but lat/zoom known: centered rectangle computed from GPS scale

    Args:
        image_path: Original satellite image.
        footprint: Detected footprint result.
        output_path: Path to save the annotated image.
        lat: Latitude (required for GPS-scale centered-rect fallback).
        zoom: Zoom level (required for GPS-scale centered-rect fallback).

    Returns:
        Path to the saved overlay image.
    """
    img = cv2.imread(str(image_path))
    if img is None:
        raise FileNotFoundError(f"Cannot read image: {image_path}")

    img_h, img_w = img.shape[:2]
    GREEN = (0, 255, 0)

    ann_x1 = ann_y1 = ann_x2 = ann_y2 = None

    if footprint.contour_points:
        pts = np.array(footprint.contour_points, dtype=np.int32)
        if len(pts) == 4:
            # Claude bbox — 4 corners stored as [[x1,y1],[x2,y1],[x2,y2],[x1,y2]]
            bx1 = int(pts[:, 0].min())
            by1 = int(pts[:, 1].min())
            bx2 = int(pts[:, 0].max())
            by2 = int(pts[:, 1].max())
            cv2.rectangle(img, (bx1, by1), (bx2, by2), GREEN, 2)
            ann_x1, ann_y1, ann_x2, ann_y2 = bx1, by1, bx2, by2
        else:
            # OpenCV polygon
            cv2.drawContours(img, [pts], -1, GREEN, 2)
            bx, by, bw, bh = cv2.boundingRect(pts)
            ann_x1, ann_y1, ann_x2, ann_y2 = bx, by, bx + bw, by + bh

    elif lat is not None and zoom is not None:
        # GPS-scale centered rectangle fallback
        mpp = meters_per_pixel(lat, zoom)
        length_px = int(footprint.length_m / mpp)
        width_px = int(footprint.width_m / mpp)
        cx, cy = img_w // 2, img_h // 2
        ann_x1 = max(0, cx - length_px // 2)
        ann_x2 = min(img_w - 1, cx + length_px // 2)
        ann_y1 = max(0, cy - width_px // 2)
        ann_y2 = min(img_h - 1, cy + width_px // 2)
        cv2.rectangle(img, (ann_x1, ann_y1), (ann_x2, ann_y2), GREEN, 2)

    if ann_x1 is not None:
        _draw_dimension_annotations(
            img, ann_x1, ann_y1, ann_x2, ann_y2,
            footprint.length_m, footprint.width_m,
            img_w, img_h, GREEN,
        )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), img)
    return output_path


def _draw_dimension_annotations(
    img: np.ndarray,
    x1: int, y1: int, x2: int, y2: int,
    length_m: float, width_m: float,
    img_w: int, img_h: int,
    color: tuple,
) -> None:
    """Draw architectural dimension lines around a bounding rectangle."""
    DARK_BG = (20, 20, 20)
    WHITE = (255, 255, 255)
    MARGIN = 20
    TICK = 6
    FONT = cv2.FONT_HERSHEY_SIMPLEX
    FONT_SCALE = 0.5
    FONT_THICK = 1

    rect_w = x2 - x1
    rect_h = y2 - y1
    # Assign labels based on which pixel axis is longer
    if rect_w >= rect_h:
        h_label = f"{length_m:.1f}m"
        v_label = f"{width_m:.1f}m"
    else:
        h_label = f"{width_m:.1f}m"
        v_label = f"{length_m:.1f}m"

    # --- Horizontal dimension annotation (above or below) ---
    (tw_h, th_h), _ = cv2.getTextSize(h_label, FONT, FONT_SCALE, FONT_THICK)
    if y1 >= MARGIN + th_h + 6:
        oy = y1 - MARGIN        # place above top edge
        label_ty = oy - 4
    else:
        oy = y2 + MARGIN        # place below bottom edge
        label_ty = oy + th_h + 4

    cv2.line(img, (x1, oy), (x2, oy), color, 1)
    cv2.line(img, (x1, oy - TICK), (x1, oy + TICK), color, 2)
    cv2.line(img, (x2, oy - TICK), (x2, oy + TICK), color, 2)
    hcx = (x1 + x2) // 2
    if hcx - x1 > 15:
        cv2.arrowedLine(img, (hcx, oy), (x1 + 4, oy), color, 1, tipLength=0.4)
        cv2.arrowedLine(img, (hcx, oy), (x2 - 4, oy), color, 1, tipLength=0.4)
    tx = max(2, min(img_w - tw_h - 4, hcx - tw_h // 2))
    cv2.rectangle(img, (tx - 2, label_ty - th_h - 2), (tx + tw_h + 2, label_ty + 2), DARK_BG, -1)
    cv2.putText(img, h_label, (tx, label_ty), FONT, FONT_SCALE, WHITE, FONT_THICK)

    # --- Vertical dimension annotation (right or left) ---
    (tw_v, th_v), _ = cv2.getTextSize(v_label, FONT, FONT_SCALE, FONT_THICK)
    if x2 + MARGIN + tw_v + 6 <= img_w:
        ox = x2 + MARGIN        # place right of right edge
        label_tx = ox + 4
    else:
        ox = x1 - MARGIN        # place left of left edge
        label_tx = max(2, ox - tw_v - 4)

    cv2.line(img, (ox, y1), (ox, y2), color, 1)
    cv2.line(img, (ox - TICK, y1), (ox + TICK, y1), color, 2)
    cv2.line(img, (ox - TICK, y2), (ox + TICK, y2), color, 2)
    vcy = (y1 + y2) // 2
    if vcy - y1 > 15:
        cv2.arrowedLine(img, (ox, vcy), (ox, y1 + 4), color, 1, tipLength=0.4)
        cv2.arrowedLine(img, (ox, vcy), (ox, y2 - 4), color, 1, tipLength=0.4)
    label_ty_v = max(th_v + 2, min(img_h - 4, vcy + th_v // 2))
    cv2.rectangle(img, (label_tx - 2, label_ty_v - th_v - 2), (label_tx + tw_v + 2, label_ty_v + 2), DARK_BG, -1)
    cv2.putText(img, v_label, (label_tx, label_ty_v), FONT, FONT_SCALE, WHITE, FONT_THICK)


def draw_window_boxes(
    image_path: str | Path,
    windows: list[dict],
    output_path: str | Path,
) -> Path:
    """Draw window bounding boxes on a street view image.

    Args:
        image_path: Original street view image.
        windows: List of {"x1", "y1", "x2", "y2"} pixel-coordinate dicts.
        output_path: Path to save the annotated image.

    Returns:
        Path to the saved overlay image.
    """
    img = cv2.imread(str(image_path))
    if img is None:
        raise FileNotFoundError(f"Cannot read image: {image_path}")

    # BGR cyan = (255, 255, 0)
    CYAN = (255, 255, 0)
    FONT = cv2.FONT_HERSHEY_SIMPLEX

    # Semi-transparent fill pass
    overlay = img.copy()
    for w in windows:
        cv2.rectangle(overlay, (w["x1"], w["y1"]), (w["x2"], w["y2"]), CYAN, -1)
    cv2.addWeighted(overlay, 0.25, img, 0.75, 0, img)

    # Solid borders and index labels
    for i, w in enumerate(windows, 1):
        x1, y1, x2, y2 = w["x1"], w["y1"], w["x2"], w["y2"]
        cv2.rectangle(img, (x1, y1), (x2, y2), CYAN, 2)
        label = str(i)
        (tw, th), _ = cv2.getTextSize(label, FONT, 0.4, 1)
        cv2.rectangle(img, (x1 + 2, y1 + 2), (x1 + tw + 6, y1 + th + 6), (20, 20, 20), -1)
        cv2.putText(img, label, (x1 + 4, y1 + th + 3), FONT, 0.4, (255, 255, 255), 1)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), img)
    return output_path
