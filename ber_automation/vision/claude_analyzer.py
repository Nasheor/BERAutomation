"""Claude Vision analysis of Street View images for building classification."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import anthropic

from ber_automation.config import get_settings
import math

from ber_automation.geospatial.census import choose_unit_count
from ber_automation.geospatial.scale import satellite_meters_per_pixel
from ber_automation.models import (
    BuildingType,
    CensusArea,
    Country,
    ConstructionEpoch,
    FootprintResult,
    HeatingSystem,
    HouseDescription,
    StreetViewAnalysis,
)
from ber_automation.vision.providers import (
    KEY_ENV_NAMES,
    api_key,
    media_type,
    mistral_complete,
    resolve_provider,
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


def _image_size(image_path: Path) -> tuple[int, int]:
    """(width, height) of an image file; falls back to 640x640 if it cannot be read."""
    try:
        from PIL import Image

        with Image.open(image_path) as img:
            return img.size
    except Exception:
        return 640, 640


def _response_text(message) -> str:
    """Concatenated text blocks of a response, skipping thinking blocks."""
    return "".join(
        block.text for block in message.content if getattr(block, "type", None) == "text"
    ).strip()


def _sampling_kwargs(settings) -> dict:
    """Sampling params for messages.create(); empty when the temperature setting is unset."""
    temperature = settings.claude_temperature
    return {"temperature": temperature} if isinstance(temperature, (int, float)) else {}


def _require_provider(provider: str | None, settings) -> str:
    """The provider to use (see resolve_provider); raises when its API key is missing."""
    provider = resolve_provider(provider, settings)
    if not api_key(provider, settings):
        raise ValueError(f"{KEY_ENV_NAMES[provider]} not configured")
    return provider


def _strip_code_fence(text: str) -> str:
    """Drop a markdown code fence wrapped around a JSON reply."""
    if text.startswith("```"):
        return "\n".join(text.split("\n")[1:-1])
    return text


async def _complete(parts: list[str | Path], provider: str, settings) -> str:
    """Send text and images, in the order given, to the chosen model; return its reply text.

    Both providers get the same parts in the same order, so results can be compared.
    """
    if provider == "mistral":
        return _strip_code_fence(await mistral_complete(settings, parts))

    content: list[dict] = []
    for part in parts:
        if isinstance(part, Path):
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type(part),
                    "data": base64.standard_b64encode(part.read_bytes()).decode("utf-8"),
                },
            })
        else:
            content.append({"type": "text", "text": part})

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    message = await client.messages.create(
        model=settings.claude_model,
        max_tokens=16000,
        **_sampling_kwargs(settings),
        messages=[{"role": "user", "content": content}],
    )
    return _strip_code_fence(_response_text(message))


_ANALYSIS_BODY = """
{
  "construction_epoch": one of ["before_1980", "1980_1990", "1990_2000", "2000_2010", "after_2010"],
  "building_type": one of ["detached", "semi_d_length", "semi_d_width", "terraced_length", "terraced_width"],
  "estimated_storeys": integer (1-4),
  "heating_system_guess": one of ["oil_boiler", "gas_boiler", "biomass", "electric_direct", "heat_pump_air", "heat_pump_ground", "heat_pump_water", "district_heating"],
  "heating_observed": true ONLY if you can see a heating clue belonging to the TARGET property (oil tank, boiler flue, gas meter box, heat pump unit, pellet store); false if heating_system_guess is a default from the setting,
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
- Gas meters, boilers and oil tanks are usually hidden from the street, so NOT seeing one is not evidence for or against any system
- If no clear indicator is visible, apply this rule from the setting (use the Property Location when given, otherwise the surroundings) — do not speculate about whether mains gas had reached the street or estate:
  - Housing estate or street within, or on the edge of, a city or large town: gas_boiler, whatever the building age
  - One-off house in open countryside, farmhouse, or small village: oil_boiler
  - district_heating is common in urban Luxembourg, Netherlands and Germany
- A suburb or townland name does not make a location rural: if the address names a city or large town, treat the property as urban, including peripheral estates

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


def _build_streetview_prompt(country_adj: str, multi: bool, location: str | None = None) -> str:
    # The images alone rarely show whether a street is urban or rural; the geocoded
    # address does, and that drives the heating-system default.
    location_block = (
        f"## Property Location\nGeocoded address: {location}\n"
        f"Use this to judge whether the property is in a city/town (mains gas likely) "
        f"or a rural area.\n\n"
        if location else ""
    )
    if multi:
        return (
            f"You are an expert building surveyor assessing a {country_adj} residential property "
            f"from Google Street View.\n\n"
            f"## How the images were taken\n"
            f"All images come from ONE camera position in the street, turned to different "
            f"headings. They are NOT views of different sides of the property.\n"
            f"- The image labelled FRONT is pointed at the property: the TARGET is the building "
            f"at its horizontal centre. Classify THAT building.\n"
            f"- The other images look along or across the street. They show neighbouring and "
            f"opposite buildings, not the property. Use them only as context: urban or rural "
            f"setting, whether the target's row continues (an edge of the target may appear at "
            f"the side of an adjacent heading), and the style of the estate. Never classify a "
            f"building from these images as if it were the target.\n"
            f"- Google sometimes blurs a property for privacy. If the target is blurred or hidden, "
            f"say so in the reasoning, estimate from the immediate neighbours in the FRONT image "
            f"(homes in one estate usually share era, type and storeys), and keep confidence at "
            f"0.5 or below.\n\n"
            + location_block
            + "Analyse these images and return a JSON object with the following fields:"
            + _ANALYSIS_BODY
        )
    return (
        f"You are an expert building surveyor analysing a {country_adj} residential building "
        f"from a Google Street View image.\n\n"
        + location_block
        + "Analyse this image and return a JSON object with the following fields:"
        + _ANALYSIS_BODY
    )


_VIEW_LABELS = {
    0: "FRONT — camera pointed at the property; the target is the building at the centre.",
    1: "Heading +90° from the property — street context, not the property.",
    2: "Heading +180° (behind the camera) — the opposite side of the street, not the property.",
    3: "Heading +270° from the property — street context, not the property.",
}


def _view_label(img_path: Path, position: int) -> str:
    """Label for a Street View image, from its heading index (streetview_<i>) or position."""
    try:
        index = int(img_path.stem.split("_")[1])
    except (IndexError, ValueError):
        index = position
    return f"Image {position + 1}: " + _VIEW_LABELS.get(index, "street context, not the property.")


async def analyze_streetview(
    image_paths: str | Path | list[str | Path],
    country: Country | None = None,
    location: str | None = None,
    provider: str | None = None,
) -> StreetViewAnalysis:
    """Send Street View image(s) to Claude Vision for building analysis.

    Accepts a single image path (backward-compatible) or a list of paths
    for multi-angle analysis.  When multiple images are provided the prompt
    instructs Claude to cross-reference all views.

    Args:
        image_paths: Path (or list of paths) to Street View image file(s).
        country: Country context for the prompt (defaults to Ireland).
        location: Geocoded address, used for urban/rural context when no
            heating system is visible.
        provider: Vision model provider, "claude" or "mistral" (default: the
            LLM_PROVIDER setting).

    Returns:
        StreetViewAnalysis with building classification and confidence.
    """
    settings = get_settings()
    provider = _require_provider(provider, settings)

    # Normalise to a list
    if isinstance(image_paths, (str, Path)):
        image_paths = [image_paths]
    image_paths = [Path(p) for p in image_paths]

    # One image per file (labelled by heading when there are several), then the prompt,
    # which depends on single vs multi-image
    multi = len(image_paths) > 1
    parts: list[str | Path] = []
    for idx, img_path in enumerate(image_paths):
        if multi:
            parts.append(_view_label(img_path, idx))
        parts.append(img_path)
    country_adj = COUNTRY_NAMES.get(country, "Irish") if country else "Irish"
    parts.append(_build_streetview_prompt(country_adj, multi=multi, location=location))

    response_text = await _complete(parts, provider, settings)

    try:
        data = json.loads(response_text)
    except json.JSONDecodeError:
        return StreetViewAnalysis(
            reasoning=f"Failed to parse model response: {response_text[:200]}"
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
        heating_observed=data.get("heating_observed") is True,
        confidence=data.get("confidence", 0.5),
        reasoning=data.get("reasoning", ""),
    )


TARGET_VIEWS = ("front", "side", "partial", "hidden")
MIN_SIMILAR_FACADE_PX = 30

_DESCRIPTION_BODY = """
## Task
1. Say what the FRONT image shows of the target (target_view).
2. Homes in one estate or row are usually built to the same design. Look through ALL the images, including the street-context ones, for the clearest house of the same design as the target, and report it as similar_house whenever one is visible:
   - Same design means the same roof form and covering, wall finish, number of storeys, proportions and chimney position as whatever IS visible of the target. Prefer a house in the target's own row, then its nearest neighbours, then the houses opposite. If nothing of the target is visible, the house must be an immediate neighbour or directly opposite.
   - Use it to fill in whatever is hidden or unclear on the target (a ground floor behind a hedge or wall, the front door and porch, a house seen only side-on, a blurred house). Describe those parts from the similar house instead of calling them "not visible", and list each one in inferred_from_similar. Whatever you can see on the target itself always wins.
   - Owners alter houses one at a time: extensions, solar panels, replacement windows and heating equipment on the similar house say nothing about the target. Do not carry them over.
3. Describe the target house.

Return ONLY a JSON object, no other text:
{
  "target_view": one of ["front", "side", "partial", "hidden"] ("front" = the target's street facade, clearly; "side" = only a gable or side wall; "partial" = the facade, partly hidden by a hedge, wall, tree or vehicle; "hidden" = blurred or not visible),
  "similar_house": null, or {"image": image number (1 if there is only one image), "x1": int, "x2": int} (the left and right pixel edges of that house's facade in that image; never the target itself; null only when no house of the same design is visible in any image),
  "inferred_from_similar": list of short phrases naming the details you could not see on the target and took from the similar house (e.g. "ground-floor windows", "front door and porch"); [] when similar_house is null or everything was seen on the target,
  "description": "3 to 5 short, plain sentences (no more) describing the TARGET house: wall finish, roof, windows on each floor (how many, frame type), door or porch, extensions. Say which details you saw on the target and which you assumed from the similar house"
}"""


def _build_description_prompt(
    country_adj: str,
    multi: bool,
    location: str | None = None,
    analysis: StreetViewAnalysis | None = None,
) -> str:
    if multi:
        views = (
            "## How the images were taken\n"
            "All images come from ONE camera position in the street, turned to different "
            "headings. They are NOT views of different sides of the property.\n"
            "- The image labelled FRONT is pointed at the property: the TARGET is the building "
            "at its horizontal centre.\n"
            "- The other images look along or across the street. They show neighbouring and "
            "opposite buildings, not the property.\n"
        )
    else:
        views = (
            "## The image\n"
            "The camera is pointed at the property: the TARGET is the building at the "
            "horizontal centre. Other buildings in the image are neighbours.\n"
        )
    location_block = f"\n## Property Location\nGeocoded address: {location}\n" if location else ""
    classified = (
        f"\n## Earlier classification\n"
        f"An earlier step classified the target as {analysis.building_type.value}, "
        f"{analysis.estimated_storeys} storey(s), built {analysis.construction_epoch.value}. "
        f"Describe what you see; if the images clearly contradict this, say so in the "
        f"description.\n"
        if analysis is not None else ""
    )
    return (
        f"You are an expert building surveyor. Describe a home from Google Street View for "
        f"an energy assessment. Housing stock: {country_adj}.\n\n"
        + views + location_block + classified + _DESCRIPTION_BODY
    )


def _view_index(img_path: Path, position: int) -> int:
    """Heading index of a Street View image (streetview_<i>), else its list position."""
    try:
        return int(img_path.stem.split("_")[1])
    except (IndexError, ValueError):
        return position


def _parse_similar_house(
    raw, image_paths: list[Path],
) -> tuple[int | None, int | None, int | None]:
    """(heading index, x1, x2) of the similar house Claude reported, or three Nones.

    Claude names the image by its number in the request (1-based); that is mapped back to
    the file's heading index. A range that is missing, outside the image or too narrow to
    be a facade is rejected.
    """
    if not isinstance(raw, dict):
        return None, None, None
    try:
        position = int(raw["image"]) - 1
        x1, x2 = sorted((int(raw["x1"]), int(raw["x2"])))
    except (KeyError, TypeError, ValueError):
        return None, None, None
    if not 0 <= position < len(image_paths):
        return None, None, None
    img_w, _ = _image_size(image_paths[position])
    x1, x2 = max(0, x1), min(img_w, x2)
    if x2 - x1 < MIN_SIMILAR_FACADE_PX:
        return None, None, None
    return _view_index(image_paths[position], position), x1, x2


async def describe_house(
    image_paths: str | Path | list[str | Path],
    analysis: StreetViewAnalysis | None = None,
    country: Country | None = None,
    location: str | None = None,
    provider: str | None = None,
) -> HouseDescription | None:
    """Describe the target house, filling hidden parts from a house of the same design.

    The front Street View image often shows the property side-on or behind a hedge, while
    another heading shows a neighbour built to the same design in full. This asks Claude
    for a plain description of the target and for the similar house it used. It is kept
    apart from analyze_streetview() on purpose: that prompt decides building type, storeys
    and era for the rating, and adding this task to it changed a borderline classification
    (T23 RK10, semi-detached to detached). Nothing returned here feeds the calculation.

    Args:
        image_paths: Path (or list of paths) to the Street View image file(s).
        analysis: The classification from analyze_streetview(), given as context.
        country: Country context for the prompt (defaults to Ireland).
        location: Geocoded address.
        provider: Vision model provider, "claude" or "mistral" (default: the
            LLM_PROVIDER setting).

    Returns:
        HouseDescription, or None when the reply could not be read.
    """
    settings = get_settings()
    provider = _require_provider(provider, settings)

    if isinstance(image_paths, (str, Path)):
        image_paths = [image_paths]
    image_paths = [Path(p) for p in image_paths]

    multi = len(image_paths) > 1
    parts: list[str | Path] = []
    for idx, img_path in enumerate(image_paths):
        if multi:
            parts.append(_view_label(img_path, idx))
        parts.append(img_path)
    country_adj = COUNTRY_NAMES.get(country, "Irish") if country else "Irish"
    parts.append(_build_description_prompt(country_adj, multi, location, analysis))

    response_text = await _complete(parts, provider, settings)
    try:
        data = json.loads(response_text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None

    target_view = data.get("target_view")
    if target_view not in TARGET_VIEWS:
        target_view = "front"
    view, x1, x2 = _parse_similar_house(data.get("similar_house"), image_paths)
    inferred = data.get("inferred_from_similar")
    inferred = [str(item) for item in inferred] if isinstance(inferred, list) else []
    return HouseDescription(
        target_view=target_view,
        similar_house_view=view,
        similar_house_x1=x1,
        similar_house_x2=x2,
        inferred_from_similar=inferred if view is not None else [],
        description=str(data.get("description") or ""),
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


SATELLITE_CORNERS_PROMPT = """You are an expert building surveyor analysing a satellite image of a {country_adj} residential property.

Your task: outline the roof of the building that contains the target home, in pixel coordinates, \
and count the homes in it. Do NOT estimate dimensions in metres — they are computed from your \
corners using the known scale.

## Image Geometry
- The image is {img_w} x {img_h} pixels. Pixel (0, 0) is the top-left corner; x grows to the right, y grows downwards.
- The image is centred on the property's geocoded address point, pixel ({cx}, {cy}). The target \
home is in the residential building at or nearest to this point. Geocoded points can land on the \
road or garden in front of the house, so pick the nearest house roof, not a road or a car.
- Scale: {mpp:.4f} metres per pixel (the image covers about {ground_w:.0f}m x {ground_h:.0f}m). \
A single {country_adj} home is typically 5–10 m wide along the street ({px_unit_lo:.0f}–{px_unit_hi:.0f} px) \
and 7–11 m deep ({px_depth_lo:.0f}–{px_depth_hi:.0f} px).

## Instructions
1. Find the roof of the building containing the target home (slate, tile, flat felt). IGNORE \
gardens, driveways, sheds, cars, tree canopies, roads, paths and hedgerows.
2. Outline the WHOLE attached building as one rectangle: a detached house on its own, both halves \
of a semi-detached pair, or the full terrace row up to the first gap between buildings (if the row \
runs off the image, stop at the image edge). It is easier to see the outer edges of a block than \
the party walls inside it, so outline the block — do not try to cut out one home.
3. Count the homes in that rectangle ("units_in_block"): use repeating chimneys, roof windows, \
ridge steps or colour changes in the roof, and the front doors/paths/driveways below. 1 for a \
detached house, 2 for a semi-detached pair.
4. Give the 4 corners in order around the perimeter (clockwise). The rectangle may be \
rotated — give the true corners, not an axis-aligned box.
5. If the building is L-shaped or irregular, outline its main rectangular part.

## Response Format
Return ONLY a JSON object:
{{
  "block_corners_px": [[x1, y1], [x2, y2], [x3, y3], [x4, y4]],
  "units_in_block": <integer >= 1>,
  "units_visible": <true if you can SEE where every home in the block ends (party-wall lines, ridge \
steps, hips, roof colour changes, or front plots clearly separated by walls or hedges), or the building \
is detached; false if any boundary between homes is inferred from the block length, the typical home \
width or the Street View hint>,
  "building_shape": "rectangular" or "l_shaped" or "irregular",
  "confidence": <float 0-1: how sure you are that you outlined the right building, that its edges \
are clearly visible and that the home count is right; use <= 0.3 if the roof is hidden by trees \
or shadow>,
  "reasoning": "<brief explanation: which building you picked, how you found its edges and how you counted the homes>"
}}"""


# A block outline with a corner this close to the image border (fraction of the image size)
# is cut off by the frame: the row runs on beyond it, so neither its length nor the homes in
# it were measured. Its confidence is capped below the 0.4 reconciliation threshold, so the
# OpenCV footprint is used instead. Whole blocks in the validation images stay >= 49 px
# (of 640) clear of the border; T23 AX03's cut-off terrace has corners at 0-2 px.
CLIPPED_EDGE_MARGIN = 0.02
CLIPPED_BLOCK_CONFIDENCE = 0.3


def _reaches_image_edge(corners: list, img_w: int, img_h: int) -> bool:
    """True when a corner of the block outline lies on, near or past the image border."""
    mx, my = img_w * CLIPPED_EDGE_MARGIN, img_h * CLIPPED_EDGE_MARGIN
    return any(
        x <= mx or y <= my or x >= img_w - mx or y >= img_h - my
        for x, y in ((float(p[0]), float(p[1])) for p in corners)
    )


def _lerp(a: tuple[float, float], b: tuple[float, float], t: float) -> tuple[float, float]:
    return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t


def _block_edges_px(corners: list) -> tuple[float, float] | None:
    """(long, short) mean edge lengths in pixels of a 4-corner outline; None if invalid."""
    try:
        pts = [(float(p[0]), float(p[1])) for p in corners]
    except (TypeError, ValueError, IndexError):
        return None
    if len(pts) != 4:
        return None
    c1, c2, c3, c4 = pts
    edge_a = (math.dist(c1, c2) + math.dist(c4, c3)) / 2
    edge_b = (math.dist(c2, c3) + math.dist(c1, c4)) / 2
    if edge_a <= 0 or edge_b <= 0:
        return None
    return max(edge_a, edge_b), min(edge_a, edge_b)


def _unit_from_block(
    corners: list, units: int, mpp: float, centre: tuple[float, float],
) -> tuple[float, float, list[list[int]]] | None:
    """Split a block outline into equal homes along its longer edge.

    The per-home area is block area / units whichever edge is divided; homes in a pair
    or row are almost always lined up along the block's longer side, so that edge is
    divided. The slice nearest *centre* (the geocoded point) is returned for drawing.

    Args:
        corners: 4 [x, y] pixel corners around the block's perimeter.
        units: Number of homes in the block (>= 1).
        mpp: Metres per pixel.
        centre: Pixel position of the geocoded address point.

    Returns:
        (length_m, width_m, unit_corners_px) for one home, or None if the corners
        are invalid.
    """
    try:
        pts = [(float(p[0]), float(p[1])) for p in corners]
    except (TypeError, ValueError, IndexError):
        return None
    if len(pts) != 4:
        return None
    c1, c2, c3, c4 = pts
    edge_a = (math.dist(c1, c2) + math.dist(c4, c3)) / 2
    edge_b = (math.dist(c2, c3) + math.dist(c1, c4)) / 2
    if edge_a <= 0 or edge_b <= 0:
        return None
    if edge_b > edge_a:  # rotate so that c1 -> c2 is the longer edge
        c1, c2, c3, c4 = c2, c3, c4, c1
        edge_a, edge_b = edge_b, edge_a

    units = max(1, min(units, 20))
    slices = []
    for k in range(units):
        t0, t1 = k / units, (k + 1) / units
        slices.append([_lerp(c1, c2, t0), _lerp(c1, c2, t1), _lerp(c4, c3, t1), _lerp(c4, c3, t0)])
    nearest = min(
        slices,
        key=lambda q: math.dist(centre, (sum(x for x, _ in q) / 4, sum(y for _, y in q) / 4)),
    )

    along_m = edge_a / units * mpp
    depth_m = edge_b * mpp
    return (
        max(along_m, depth_m),
        min(along_m, depth_m),
        [[int(round(x)), int(round(y))] for x, y in nearest],
    )


async def analyze_satellite(
    image_path: str | Path,
    lat: float,
    zoom: int | None = 20,
    building_type: str | None = None,
    adjacent_side: str | None = None,
    estimated_units_in_row: int | None = None,
    country: Country | None = None,
    census: CensusArea | None = None,
    storeys: int | None = None,
    provider: str | None = None,
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
        census: Census facts for the Small Area; its room mix picks the number of
            homes in the outlined block when Claude cannot see where they end.
        storeys: Storeys from Street View, for the per-home floor area (default 2).
        provider: Vision model provider, "claude" or "mistral" (default: the
            LLM_PROVIDER setting).

    Returns:
        FootprintResult with estimated dimensions and confidence.
    """
    settings = get_settings()
    provider = _require_provider(provider, settings)

    image_path = Path(image_path)

    country_adj = COUNTRY_NAMES.get(country, "Irish") if country else "Irish"
    mpp: float | None = None
    if zoom is not None:
        # GPS scale known: Claude marks roof corners in pixels; metres are computed here.
        mpp = satellite_meters_per_pixel(lat, zoom)
        img_w, img_h = _image_size(image_path)
        prompt = SATELLITE_CORNERS_PROMPT.format(
            country_adj=country_adj, img_w=img_w, img_h=img_h,
            cx=img_w // 2, cy=img_h // 2, mpp=mpp,
            ground_w=img_w * mpp, ground_h=img_h * mpp,
            px_unit_lo=5 / mpp, px_unit_hi=10 / mpp,
            px_depth_lo=7 / mpp, px_depth_hi=11 / mpp,
        )
    else:
        # Uploaded image, unknown scale: Claude estimates metres from visual references.
        prompt = SATELLITE_ANALYSIS_PROMPT.format(
            country_adj=country_adj, scale_paragraph=_VISUAL_REFERENCE_PARAGRAPH,
        )

    # Inject building-type context from street view when available
    if mpp is not None and building_type:
        # Corner path: Claude outlines the whole block, so pass the street-level read as a
        # hint for the home count rather than an instruction to cut out one unit.
        kind = {
            "detached": "a detached house",
            "semi_d_length": "one half of a semi-detached pair",
            "semi_d_width": "one half of a semi-detached pair",
        }.get(building_type, "one home in a terrace")
        units_hint = estimated_units_in_row or (1 if building_type == "detached" else None)
        prompt += (
            "\n\n## Hint from Street View (may be wrong — trust the roof you see)\n"
            f"- From the street the target looked like {kind}"
            + (f", in a building of about {units_hint} homes" if units_hint else "")
            + "."
        )
    elif building_type and building_type.startswith(("terraced", "semi_d")):
        units = estimated_units_in_row or (2 if building_type.startswith("semi_d") else 4)
        side = adjacent_side or "length"
        prompt += (
            f"\n\n## CRITICAL: Building Context from Street View\n"
            f"- This is ONE unit in a {'terraced row' if building_type.startswith('terraced') else 'semi-detached pair'} of ~{units} units\n"
            f"- The shared/party wall runs along the {side} side\n"
            f"- CRITICAL: Measure only ONE unit's roof footprint, NOT the entire row\n"
            f"- Divide the repeating dimension by {units} if you see the full row"
        )

    response_text = await _complete([image_path, prompt], provider, settings)

    try:
        data = json.loads(response_text)
    except json.JSONDecodeError:
        return FootprintResult(
            length_m=0, width_m=0, area_m2=0, confidence=0,
            source="claude_vision",
        )

    confidence = float(data.get("confidence", 0))
    building_shape = data.get("building_shape", "rectangular")
    contour_points: list[list[int]] = []
    block: dict = {}

    if mpp is not None:
        corners = data.get("block_corners_px")
        try:
            claude_units = max(1, int(data.get("units_in_block") or 1))
        except (TypeError, ValueError):
            claude_units = 1
        visible = data.get("units_visible") is True
        edges = _block_edges_px(corners) if corners else None
        if edges is None:
            return FootprintResult(
                length_m=0, width_m=0, area_m2=0, confidence=0,
                source="claude_vision",
            )
        block_long, block_short = edges[0] * mpp, edges[1] * mpp
        clipped = _reaches_image_edge(corners, img_w, img_h)
        if clipped:
            # Only part of the row is outlined, so block area / n says nothing about the
            # size of the homes: keep Claude's count and let OpenCV take over.
            units, units_source = claude_units, "claude"
            confidence = min(confidence, CLIPPED_BLOCK_CONFIDENCE)
        else:
            units, units_source = choose_unit_count(
                block_long, block_short, claude_units, visible, census,
                storeys=storeys, detached=building_type == "detached",
            )
        unit = _unit_from_block(corners, units, mpp, centre=(img_w / 2, img_h / 2))
        if unit is None:
            return FootprintResult(
                length_m=0, width_m=0, area_m2=0, confidence=0,
                source="claude_vision",
            )
        length, width, contour_points = unit
        block = dict(
            block_length_m=round(block_long, 1), block_width_m=round(block_short, 1),
            units_in_block=units, units_claude=claude_units, units_visible=visible,
            units_source=units_source, block_clipped=clipped,
        )
    else:
        length = float(data.get("length_m", 0))
        width = float(data.get("width_m", 0))

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
        contour_points=contour_points,
        **block,
    )


async def detect_windows(
    image_path: str | Path,
    facade_hint: tuple[int, int] | None = None,
    provider: str | None = None,
) -> list[dict]:
    """Detect the windows of one building in a Street View image.

    By default the image must be the view pointed at the property (heading camera →
    address): the target is the building at the horizontal centre. With *facade_hint*
    the building to mark is the one between those x pixels instead; this is used for a
    house of the same design as the property seen in another view. Claude also returns
    the facade's x-range; windows outside it (neighbours) are discarded.

    Args:
        image_path: Path to the street view image file.
        facade_hint: (x1, x2) pixel range of the building to mark, when it is not the
            building at the centre of the image.
        provider: Vision model provider, "claude" or "mistral" (default: the
            LLM_PROVIDER setting).

    Returns:
        List of {"x1", "y1", "x2", "y2"} dicts (pixel coords) for each window on
        the target facade. Returns [] if the target is blurred/hidden, no windows
        are found, or on any error.
    """
    from PIL import Image  # local import — PIL is guaranteed by streamlit

    settings = get_settings()
    try:
        provider = _require_provider(provider, settings)
    except ValueError:
        return []

    image_path = Path(image_path)
    if not image_path.exists():
        return []

    image_bytes = image_path.read_bytes()

    # Get actual image dimensions for the prompt (PIL reads header only, fast)
    try:
        import io
        with Image.open(io.BytesIO(image_bytes)) as im:
            img_w, img_h = im.size
    except Exception:
        img_w, img_h = 640, 640

    cx = img_w // 2
    if facade_hint is not None:
        hx1, hx2 = sorted(facade_hint)
        where = (
            f"The TARGET building is the house whose facade lies between about x = {hx1} and "
            f"x = {hx2}. Buildings to the left and right of it are neighbours.\n\n"
        )
    else:
        where = (
            f"The camera is pointed at the property being assessed, so the TARGET building is the "
            f"building at the horizontal centre of the image (around x = {cx}). Buildings to the "
            f"left and right of it are neighbours.\n\n"
        )
    prompt = (
        f"You are analysing a Google Street View photograph ({img_w}×{img_h} pixels).\n"
        + where +
        f"Your task: mark the windows on the TARGET building's facade only.\n\n"
        f"## Step 1 — find the target building\n"
        f"- Give the left and right edges of the target building's facade in pixels "
        f"(facade_x1, facade_x2). For a semi-detached or terraced home, use the party-wall "
        f"lines, so the neighbouring home is outside the range.\n"
        f"- Google blurs some homes for privacy. If the target facade is blurred, hidden "
        f"(trees, hedges, vehicles) or not in the image, set target_visible to false and "
        f"return no windows. Do NOT mark a neighbour's windows instead.\n\n"
        f"## Step 2 — mark its windows\n"
        f"- Rectangular glass panes set into the target building's walls, upper and ground floor\n"
        f"- Do NOT mark: neighbouring or background buildings, doors, shop fronts, vehicles, "
        f"sky, trees, or anything you are unsure about\n"
        f"- Every box must sit inside the wall, below the roofline\n\n"
        f"Return ONLY a JSON object (no other text):\n"
        f'{{"target_visible": true or false, "facade_x1": int, "facade_x2": int, '
        f'"windows": [{{"x1": int, "y1": int, "x2": int, "y2": int}}, ...]}}\n\n'
        f"Image coordinates: (0,0) is the top-left pixel, ({img_w},{img_h}) is the bottom-right."
    )

    try:
        response_text = await _complete([image_path, prompt], provider, settings)
        parsed = json.loads(response_text)
        facade: tuple[int, int] | None = None
        if isinstance(parsed, dict):
            if not parsed.get("target_visible", True):
                return []
            try:
                fx1, fx2 = int(parsed["facade_x1"]), int(parsed["facade_x2"])
                facade = (min(fx1, fx2), max(fx1, fx2))
            except (KeyError, TypeError, ValueError):
                facade = None
            parsed = parsed.get("windows") or []
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
            # Filter: window centre must lie on the target facade (drops neighbours)
            if facade is not None and not (facade[0] <= (x1 + x2) / 2 <= facade[1]):
                continue
            windows.append({"x1": x1, "y1": y1, "x2": x2, "y2": y2})
        return windows
    except Exception:
        return []
