"""OpenCV-based building footprint extraction from satellite imagery."""

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
) -> FootprintResult:
    """Extract building footprint from a satellite image using OpenCV.

    Pipeline:
        1. Grayscale → bilateral filter (edge-preserving smoothing)
        2. CLAHE (adaptive histogram equalization)
        3. Canny edge detection → dilate to close gaps
        4. Find contours, score by area + solidity + centrality + rectangularity
        5. Fit minimum-area bounding rectangle → convert to meters

    Args:
        image_path: Path to the satellite image.
        lat: Latitude for pixel-to-meter conversion.
        zoom: Google Maps zoom level used when fetching the image.

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

        # Combined score (rebalanced: less area bias, more solidity/centrality)
        score = (
            0.15 * (area / (w * h))  # relative area (reduced from 0.30)
            + 0.30 * solidity         # compact shapes (increased from 0.25)
            + 0.30 * centrality       # centered shapes (increased from 0.25)
            + 0.25 * rectangularity   # rectangular shapes (increased from 0.20)
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
) -> Path:
    """Draw the detected footprint contour on the satellite image.

    Args:
        image_path: Original satellite image.
        footprint: Detected footprint result.
        output_path: Path to save the annotated image.

    Returns:
        Path to the saved overlay image.
    """
    img = cv2.imread(str(image_path))
    if img is None:
        raise FileNotFoundError(f"Cannot read image: {image_path}")

    if footprint.contour_points:
        pts = np.array(footprint.contour_points, dtype=np.int32)
        cv2.drawContours(img, [pts], -1, (0, 255, 0), 2)

        # Add dimension labels
        cv2.putText(
            img,
            f"{footprint.length_m:.1f}m x {footprint.width_m:.1f}m",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 0),
            2,
        )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), img)
    return output_path
