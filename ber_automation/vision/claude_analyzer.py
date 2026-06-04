"""Claude Vision analysis of Street View images for building classification."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import anthropic

from ber_automation.config import get_settings
from ber_automation.geospatial.scale import meters_per_pixel
from ber_automation.models import (
    BuildingType,
    Country,
    ConstructionEpoch,
    FootprintResult,
    HeatingSystem,
    StreetViewAnalysis,
)

COUNTRY_NAMES: dict[Country, str] = {
    Country.IRELAND: "Irish",
    Country.FRANCE: "French",
    Country.GERMANY: "German",
    Country.BELGIUM: "Belgian",
    Country.NETHERLANDS: "Dutch",
    Country.LUXEMBOURG: "Luxembourgish",
    Country.SWITZERLAND: "Swiss",
    Country.AUSTRIA: "Austrian",
}

_ANALYSIS_BODY = """
{
  "construction_epoch": one of ["before_1980", "1980_1990", "1990_2000", "2000_2010", "after_2010"],
  "building_type": one of ["detached", "semi_d_length", "semi_d_width", "terraced_length", "terraced_width"],
  "estimated_storeys": integer (1-4),
  "heating_system_guess": one of ["oil_boiler", "gas_boiler", "biomass", "electric_direct", "heat_pump_air", "heat_pump_ground", "heat_pump_water", "district_heating"],
  "adjacent_side": "length" or "width" (which side is shared for semi-d/terraced; use "length" for detached),
  "estimated_units_in_row": integer (how many units in the terrace row; 1 for detached, 2 for semi-d, 3+ for terraced),
  "confidence": float 0-1,
  "reasoning": "brief explanation of your assessment"
}

## CRITICAL: Building Visibility Check
BEFORE analysing building features, assess whether a residential building is actually visible in the image(s). If the view is blocked by trees, hedgerows, vegetation, fences, walls, or any other obstruction and you CANNOT see the building facade (walls, windows, roof, door), you MUST:
- Set "confidence" to 0.1 or lower
- Set "reasoning" to explain that the building is not visible
- Still provide your best guess for the other fields, but the low confidence signals that these are unreliable

Only set confidence above 0.5 if you can clearly see architectural features (wall material, windows, roofline). Set confidence between 0.2-0.5 if the building is only partially visible.

## Building Era Indicators (North-West Europe)

**Before 1980**: Solid masonry walls (brick or stone), single-glazed timber windows, no cavity insulation, prominent chimneys, older slate or clay-tile roofs, render or exposed brick facades.

**1980-1990**: Cavity block walls introduced, timber or early PVC windows (often still single-glazed), basic roof insulation, blockwork render, some flat-roof extensions.

**1990-2000**: Standard cavity block, PVC double-glazed windows common, concrete tile roofs, plaster/dash render, more uniform suburban estates.

**2000-2010**: Improved cavity wall insulation, double-glazed PVC throughout, concrete tiles, modern render/brick facades, larger window areas, tightened building regulations.

**After 2010**: High-performance insulation, triple-glazed windows possible, clean modern facades, potential heat pump units visible, near-zero energy building (NZEB/passive) influences, often flat or low-pitch roofs.

## Heating System Clues
- Oil boiler: external oil tank (cylindrical or rectangular, often green/grey)
- Gas boiler: gas meter on external wall, boiler flue on wall
- Heat pump (air source): large external fan unit (box-shaped, often on side/rear wall)
- District heating: no boiler or tank visible, pipe connections at ground level
- Biomass: woodchip/pellet storage, larger flue
- If no clear indicator, default to gas_boiler for 2000+ builds, oil_boiler for older rural buildings; district_heating is common in urban Luxembourg, Netherlands and Germany

## Building Type
- Detached: standalone, no shared walls
- Semi-detached: paired with one neighbour
- Terraced: row of 3+ houses sharing walls on both sides (end-of-terrace = semi-d)
- For semi-d/terraced, "adjacent_side" is whether the LONGER or SHORTER wall is shared

## Unit Count (estimated_units_in_row)
- Detached: always 1
- Semi-detached: always 2
- Terraced: count the visible doors/front bays in the continuous row (typically 3-8)
- End-of-terrace: classify as semi-d with units=2
- If you cannot count exactly, estimate from the roof length and repeating pattern

Return ONLY the JSON object, no other text."""


def _build_streetview_prompt(country_adj: str, multi: bool) -> str:
    if multi:
        return (
            f"You are an expert building surveyor analysing a {country_adj} residential building "
            f"from multiple Google Street View images taken at different angles "
            f"(approximately 90 degrees apart) around the same location.\n\n"
            f"Cross-reference all views to build a complete picture of the building. "
            f"Look for details that may only be visible from certain angles (e.g. an oil "
            f"tank at the side, a heat pump at the rear, a shared wall only visible from "
            f"the side).\n\n"
            f"Analyse these images and return a JSON object with the following fields:"
            + _ANALYSIS_BODY
        )
    return (
        f"You are an expert building surveyor analysing a {country_adj} residential building "
        f"from a Google Street View image.\n\n"
        f"Analyse this image and return a JSON object with the following fields:"
        + _ANALYSIS_BODY
    )


async def analyze_streetview(
    image_paths: str | Path | list[str | Path],
    country: Country | None = None,
) -> StreetViewAnalysis:
    """Send Street View image(s) to Claude Vision for building analysis.

    Accepts a single image path (backward-compatible) or a list of paths
    for multi-angle analysis.  When multiple images are provided the prompt
    instructs Claude to cross-reference all views.

    Args:
        image_paths: Path (or list of paths) to Street View image file(s).
        country: Country context for the prompt (defaults to Ireland).

    Returns:
        StreetViewAnalysis with building classification and confidence.
    """
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY not configured")

    # Normalise to a list
    if isinstance(image_paths, (str, Path)):
        image_paths = [image_paths]
    image_paths = [Path(p) for p in image_paths]

    media_types_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}

    # Build content blocks: one image block per file, then the text prompt
    content: list[dict] = []
    for idx, img_path in enumerate(image_paths):
        image_data = base64.standard_b64encode(img_path.read_bytes()).decode("utf-8")
        suffix = img_path.suffix.lower()
        media_type = media_types_map.get(suffix, "image/jpeg")
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": image_data,
            },
        })

    # Choose prompt based on single vs multi-image
    country_adj = COUNTRY_NAMES.get(country, "Irish") if country else "Irish"
    prompt_text = _build_streetview_prompt(country_adj, multi=len(image_paths) > 1)
    content.append({"type": "text", "text": prompt_text})

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    message = await client.messages.create(
        model=settings.claude_model,
        max_tokens=1024,
        messages=[{"role": "user", "content": content}],
    )

    # Parse response
    response_text = message.content[0].text.strip()

    # Handle potential markdown code blocks
    if response_text.startswith("```"):
        lines = response_text.split("\n")
        response_text = "\n".join(lines[1:-1])

    try:
        data = json.loads(response_text)
    except json.JSONDecodeError:
        return StreetViewAnalysis(
            reasoning=f"Failed to parse Claude response: {response_text[:200]}"
        )

    # Map to enums with defaults
    try:
        epoch = ConstructionEpoch(data.get("construction_epoch", "before_1980"))
    except ValueError:
        epoch = ConstructionEpoch.BEFORE_1980

    try:
        btype = BuildingType(data.get("building_type", "detached"))
    except ValueError:
        btype = BuildingType.DETACHED

    try:
        hsys = HeatingSystem(data.get("heating_system_guess", "gas_boiler"))
    except ValueError:
        hsys = HeatingSystem.GAS_BOILER

    # Parse unit count with safe guard
    try:
        units_in_row = max(1, int(data.get("estimated_units_in_row", 1)))
    except (TypeError, ValueError):
        units_in_row = 1

    return StreetViewAnalysis(
        construction_epoch=epoch,
        building_type=btype,
        estimated_storeys=data.get("estimated_storeys", 2),
        heating_system_guess=hsys,
        adjacent_side=data.get("adjacent_side", "length"),
        estimated_units_in_row=units_in_row,
        confidence=data.get("confidence", 0.5),
        reasoning=data.get("reasoning", ""),
    )


_GPS_SCALE_PARAGRAPH = """\
## Scale Information
- Image scale: {mpp:.4f} meters per pixel
- Image covers approximately {ground_w:.0f}m x {ground_h:.0f}m on the ground"""

_VISUAL_REFERENCE_PARAGRAPH = """\
## Scale Estimation (no GPS data — estimate from visual references)
No GPS-derived scale is available for this image. Estimate building dimensions \
using common reference objects that may be visible:
- Parked car: ~4.5m long, ~2m wide
- Parking space (marked bay): ~5m × 2.5m
- Road lane: ~3.5m wide
- Residential front door: ~0.9m wide
- Wheelie bin: ~0.6m wide, ~1.1m tall
- Person standing: ~1.7m tall
Identify whichever references are visible, anchor your scale estimate, then \
measure the building roof footprint."""

SATELLITE_ANALYSIS_PROMPT = """You are an expert building surveyor analysing a satellite image of a {country_adj} residential property.

Your task: identify the BUILDING ROOF footprint and estimate its dimensions in meters.

{scale_paragraph}

## Instructions
1. Find the BUILDING ROOF — look for a rectangular or L-shaped structure with a distinct roof colour/texture (slate, tile, flat felt)
2. IGNORE: gardens, driveways, fences, walls, sheds, tree canopies, roads, paths, hedgerows
3. Estimate the building's LENGTH (longest side) and WIDTH (shortest side) in meters
4. If the building is L-shaped or irregular, estimate the dimensions of the main rectangular portion

## Typical NWE Residential House Dimensions
- Small terraced: 5-8m x 5-7m
- Semi-detached: 7-11m x 6-9m
- Detached: 8-14m x 7-11m
- Large detached: 12-20m x 8-13m
- Very few houses in this region exceed 22m in any dimension

## Response Format
Return ONLY a JSON object:
{{
  "length_m": <float, longest dimension in meters>,
  "width_m": <float, shortest dimension in meters>,
  "building_shape": "rectangular" or "l_shaped" or "irregular",
  "confidence": <float 0-1, how certain you are about the dimensions>,
  "reasoning": "<brief explanation>"
}}"""


async def analyze_satellite(
    image_path: str | Path,
    lat: float,
    zoom: int | None = 20,
    building_type: str | None = None,
    adjacent_side: str | None = None,
    estimated_units_in_row: int | None = None,
    country: Country | None = None,
) -> FootprintResult:
    """Send a satellite image to Claude Vision for building footprint analysis.

    Args:
        image_path: Path to the satellite image file.
        lat: Latitude for scale computation.
        zoom: Google Maps zoom level. Pass None for user-uploaded images where
            the zoom/altitude is unknown — Claude will estimate scale from
            visible reference objects instead.
        building_type: Building type from street view (e.g. "terraced_length").
        adjacent_side: Which side is shared ("length" or "width").
        estimated_units_in_row: Number of units in terrace row.
        country: Country context for the prompt (defaults to Ireland).

    Returns:
        FootprintResult with estimated dimensions and confidence.
    """
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY not configured")

    image_path = Path(image_path)
    image_data = base64.standard_b64encode(image_path.read_bytes()).decode("utf-8")

    suffix = image_path.suffix.lower()
    media_types = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
    media_type = media_types.get(suffix, "image/jpeg")

    country_adj = COUNTRY_NAMES.get(country, "Irish") if country else "Irish"
    if zoom is not None:
        mpp = meters_per_pixel(lat, zoom)
        ground_w = 640 * mpp
        ground_h = 640 * mpp
        scale_paragraph = _GPS_SCALE_PARAGRAPH.format(mpp=mpp, ground_w=ground_w, ground_h=ground_h)
    else:
        scale_paragraph = _VISUAL_REFERENCE_PARAGRAPH
    prompt = SATELLITE_ANALYSIS_PROMPT.format(
        country_adj=country_adj, scale_paragraph=scale_paragraph,
    )

    # Inject building-type context from street view when available
    if building_type and building_type.startswith(("terraced", "semi_d")):
        units = estimated_units_in_row or (2 if building_type.startswith("semi_d") else 4)
        side = adjacent_side or "length"
        prompt += (
            f"\n\n## CRITICAL: Building Context from Street View\n"
            f"- This is ONE unit in a {'terraced row' if building_type.startswith('terraced') else 'semi-detached pair'} of ~{units} units\n"
            f"- The shared/party wall runs along the {side} side\n"
            f"- CRITICAL: Measure only ONE unit's roof footprint, NOT the entire row\n"
            f"- Divide the repeating dimension by {units} if you see the full row"
        )

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    message = await client.messages.create(
        model=settings.claude_model,
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_data,
                        },
                    },
                    {
                        "type": "text",
                        "text": prompt,
                    },
                ],
            }
        ],
    )

    response_text = message.content[0].text.strip()

    # Handle potential markdown code blocks
    if response_text.startswith("```"):
        lines = response_text.split("\n")
        response_text = "\n".join(lines[1:-1])

    try:
        data = json.loads(response_text)
    except json.JSONDecodeError:
        return FootprintResult(
            length_m=0, width_m=0, area_m2=0, confidence=0,
            source="claude_vision",
        )

    length = float(data.get("length_m", 0))
    width = float(data.get("width_m", 0))
    confidence = float(data.get("confidence", 0))
    building_shape = data.get("building_shape", "rectangular")

    # Validate and clamp dimensions to reasonable Irish house bounds
    length = max(4.0, min(25.0, length))
    width = max(4.0, min(25.0, width))

    # Ensure length >= width
    if width > length:
        length, width = width, length

    area = length * width

    # Sanity check: reject unreasonable areas
    if area < 20 or area > 500:
        confidence = min(confidence, 0.15)

    return FootprintResult(
        length_m=round(length, 1),
        width_m=round(width, 1),
        area_m2=round(area, 1),
        confidence=round(min(1.0, confidence), 2),
        source="claude_vision",
        building_shape=building_shape,
    )


async def detect_windows(image_path: str | Path) -> list[dict]:
    """Send a Street View image to Claude Vision to detect window bounding boxes.

    Args:
        image_path: Path to the street view image file.

    Returns:
        List of {"x1", "y1", "x2", "y2"} dicts (pixel coords) for each visible
        window. Returns [] if no windows found or on any error.
    """
    from PIL import Image  # local import — PIL is guaranteed by streamlit

    settings = get_settings()
    if not settings.anthropic_api_key:
        return []

    image_path = Path(image_path)
    if not image_path.exists():
        return []

    image_bytes = image_path.read_bytes()
    image_data = base64.standard_b64encode(image_bytes).decode("utf-8")
    suffix = image_path.suffix.lower()
    media_types = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
    media_type = media_types.get(suffix, "image/jpeg")

    # Get actual image dimensions for the prompt (PIL reads header only, fast)
    try:
        import io
        with Image.open(io.BytesIO(image_bytes)) as im:
            img_w, img_h = im.size
    except Exception:
        img_w, img_h = 640, 640

    prompt = (
        f"You are analysing a Google Street View photograph ({img_w}×{img_h} pixels).\n"
        f"Your task: identify windows on the residential building facade visible in this image.\n\n"
        f"## Mark ONLY these (windows on building walls):\n"
        f"- Rectangular glass panes set into building walls\n"
        f"- Window frames and glazing that are clearly part of a wall surface\n"
        f"- Both upper-floor and ground-floor windows\n\n"
        f"## Do NOT mark:\n"
        f"- Sky, clouds, or any area at or above the building roofline\n"
        f"- Trees, vegetation, hedges\n"
        f"- Parked cars, vans, motorcycles, or any vehicles\n"
        f"- Road surfaces, pavements, gutters\n"
        f"- Doors, solid walls, or fences with no glass\n"
        f"- Shop fronts or commercial display glass (unless the building is clearly residential)\n"
        f"- Distant buildings in the background — only mark the main foreground building\n"
        f"- Any area you are uncertain about\n\n"
        f"## Rules:\n"
        f"- Every window box must be entirely below the roofline of the building\n"
        f"- Boxes must sit inside the wall — not in the sky or on the ground\n"
        f"- If no building facade with clear windows is visible, return []\n\n"
        f"Return ONLY a JSON array, one entry per window (no other text):\n"
        f'[{{"x1": int, "y1": int, "x2": int, "y2": int}}, ...]\n\n'
        f"Image coordinates: (0,0) is the top-left pixel, ({img_w},{img_h}) is the bottom-right."
    )

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    try:
        message = await client.messages.create(
            model=settings.claude_model,
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_data,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        response_text = message.content[0].text.strip()
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            response_text = "\n".join(lines[1:-1])
        parsed = json.loads(response_text)
        if not isinstance(parsed, list):
            return []

        windows = []
        for w in parsed:
            if not all(k in w for k in ("x1", "y1", "x2", "y2")):
                continue
            try:
                x1, y1, x2, y2 = int(w["x1"]), int(w["y1"]), int(w["x2"]), int(w["y2"])
            except (TypeError, ValueError):
                continue
            # Ensure correct ordering
            x1, x2 = min(x1, x2), max(x1, x2)
            y1, y2 = min(y1, y2), max(y1, y2)
            bw, bh = x2 - x1, y2 - y1
            # Filter: must be within image bounds
            if x1 < 0 or y1 < 0 or x2 > img_w or y2 > img_h:
                continue
            # Filter: minimum size (15×15 px) — smaller is noise
            if bw < 15 or bh < 15:
                continue
            # Filter: maximum size — a single window shouldn't dominate the image
            if bw > img_w * 0.6 or bh > img_h * 0.6:
                continue
            # Filter: aspect ratio — windows are roughly 0.2–5× wide-to-tall
            aspect = bw / bh
            if aspect < 0.2 or aspect > 5.0:
                continue
            windows.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2})
        return windows
    except Exception:
        return []
