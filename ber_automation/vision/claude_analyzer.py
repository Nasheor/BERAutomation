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
    ConstructionEpoch,
    FootprintResult,
    HeatingSystem,
    StreetViewAnalysis,
)

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

## Irish Building Era Indicators

**Before 1980**: Solid walls (9-inch brick or stone), single-glazed timber windows, no cavity insulation, chimneys prominent, older slate or tile roofs, pebble-dash render common.

**1980-1990**: Cavity block walls begin, timber or early PVC windows (still often single-glazed), basic roof insulation, blockwork render, some flat-roof extensions.

**1990-2000**: Standard cavity block, PVC double-glazed windows common, concrete tile roofs, plaster/dash render, more uniform suburban estates.

**2000-2010**: Improved cavity wall insulation, double-glazed PVC throughout, concrete tiles, modern render/brick facades, larger window areas, building regs improved.

**After 2010**: High-performance insulation, triple-glazed windows possible, clean modern facades, potential heat pump units visible, NZEB-influenced design, often flat or low-pitch roofs.

## Heating System Clues
- Oil boiler: external oil tank (green/grey cylindrical or rectangular tank)
- Gas boiler: gas meter on external wall, boiler flue on wall
- Heat pump (air source): large external fan unit (box-shaped)
- Biomass: woodchip/pellet storage, larger flue
- If no clear indicator, default to gas_boiler for 2000+ builds, oil_boiler for older

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

ANALYSIS_PROMPT_SINGLE = (
    "You are an expert building surveyor analysing an Irish residential building "
    "from a Google Street View image.\n\n"
    "Analyse this image and return a JSON object with the following fields:"
    + _ANALYSIS_BODY
)

ANALYSIS_PROMPT = (
    "You are an expert building surveyor analysing an Irish residential building "
    "from multiple Google Street View images taken at different angles "
    "(approximately 90 degrees apart) around the same location.\n\n"
    "Cross-reference all views to build a complete picture of the building. "
    "Look for details that may only be visible from certain angles (e.g. an oil "
    "tank at the side, a heat pump at the rear, a shared wall only visible from "
    "the side).\n\n"
    "Analyse these images and return a JSON object with the following fields:"
    + _ANALYSIS_BODY
)


async def analyze_streetview(
    image_paths: str | Path | list[str | Path],
) -> StreetViewAnalysis:
    """Send Street View image(s) to Claude Vision for building analysis.

    Accepts a single image path (backward-compatible) or a list of paths
    for multi-angle analysis.  When multiple images are provided the prompt
    instructs Claude to cross-reference all views.

    Args:
        image_paths: Path (or list of paths) to Street View image file(s).

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
    prompt_text = ANALYSIS_PROMPT if len(image_paths) > 1 else ANALYSIS_PROMPT_SINGLE
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


SATELLITE_ANALYSIS_PROMPT = """You are an expert building surveyor analysing a Google Maps satellite image of an Irish residential property.

Your task: identify the BUILDING ROOF footprint and estimate its dimensions in meters.

## Scale Information
- Image scale: {mpp:.4f} meters per pixel
- Image covers approximately {ground_w:.0f}m x {ground_h:.0f}m on the ground

## Instructions
1. Find the BUILDING ROOF — look for a rectangular or L-shaped structure with a distinct roof colour/texture (slate, tile, flat felt)
2. IGNORE: gardens, driveways, fences, walls, sheds, tree canopies, roads, paths, hedgerows
3. Estimate the building's LENGTH (longest side) and WIDTH (shortest side) in meters
4. If the building is L-shaped or irregular, estimate the dimensions of the main rectangular portion

## Typical Irish House Dimensions
- Small terraced: 6-8m x 5-7m
- Semi-detached: 8-10m x 6-8m
- Detached: 9-14m x 7-10m
- Large detached: 12-20m x 8-12m
- Very few Irish houses exceed 20m in any dimension

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
    zoom: int = 20,
    building_type: str | None = None,
    adjacent_side: str | None = None,
    estimated_units_in_row: int | None = None,
) -> FootprintResult:
    """Send a satellite image to Claude Vision for building footprint analysis.

    Args:
        image_path: Path to the satellite image file.
        lat: Latitude for scale computation.
        zoom: Google Maps zoom level.
        building_type: Building type from street view (e.g. "terraced_length").
        adjacent_side: Which side is shared ("length" or "width").
        estimated_units_in_row: Number of units in terrace row.

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

    # Compute scale for the prompt
    mpp = meters_per_pixel(lat, zoom)
    # Assume 640x640 default image size
    ground_w = 640 * mpp
    ground_h = 640 * mpp

    prompt = SATELLITE_ANALYSIS_PROMPT.format(
        mpp=mpp, ground_w=ground_w, ground_h=ground_h,
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
