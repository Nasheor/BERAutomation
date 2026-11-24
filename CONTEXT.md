# BER Automation — Calculation Context

Extracted from "Building Assessment using Google Maps and Google Street View.xlsx"
by Benjamin Kaiser (MTU, Jan 2025).

## Excel Structure

| Sheet | Purpose |
|-------|---------|
| Input | User inputs (building params, retrofit measures) |
| Data | Lookup tables (U-values, g-values, HDD, solar irradiance, heating systems) |
| Calculations | Core HWB calculation (1999 rows for bulk assessment) |
| Calculations Measures applied | Same formulas with retrofit measures applied |
| Energy+CO2 Calculations | Aggregation by fuel type, efficiency, CO2 |
| Output | Summary results |

## Input Parameters (Input sheet, columns A-AA)

| Col | Parameter | Example |
|-----|-----------|---------|
| C | Quantity | 1 |
| D | Building Type | Detached / Semi-D (Length/Width adj) / Terraced (Length/Width adj) |
| E | Length (m) | 12 |
| F | Width (m) | 10 |
| G | Storeys (heated) | 2 |
| H | Storey Height (m) | 3 |
| I | Year of Construction | after 2010 / 2000-2010 / 1990-2000 / 1980-1990 / before 1980 |
| J | Total Window/Door Area (m2) | `=Calcs!E2 * 0.15` (detached), `*0.14` (semi-d), `*0.13` (terraced) |
| K-N | Window area N/E/S/W | `=J2*(1/4)` each |
| O | Country | Ireland / Belgium / France / Germany / Netherlands |
| P | Residents | `=Calcs!C2/52` (gross_area / 52) |
| Q | Heating System | Oil / Gas / Biomass / All Electric / Heat Pumps |
| R | Hot water electric? | "x" if yes |
| T-AA | Retrofit measures | wall insulation, roof insulation, window U-value, heating system |

## U-Values (Data sheet, rows 9-13)

| Epoch | U_Window | U_Roof | U_Floor | U_Wall | g-value |
|-------|----------|--------|---------|--------|---------|
| after 2010 | 1.0 | 0.2 | 0.25 | 0.22 | 0.465 |
| 2000-2010 | 1.4 | 0.2 | 0.4 | 0.35 | 0.585 |
| 1990-2000 | 2.15 | 0.235 | 0.6 | 0.45 | 0.65 |
| 1980-1990 | 2.5 | 0.275 | 0.75 | 0.6 | 0.7 |
| before 1980 | 3.0 | 0.65 | 1.35 | 1.2 | 0.81 |

## Climate Data (Data sheet, rows 16-22)

| Country | HDD (Kd) | Heating Days | Solar N | Solar E | Solar S | Solar W |
|---------|----------|-------------|---------|---------|---------|---------|
| Ireland | 2149.1 | 219 | 102 | 227 | 423 | 240 |
| Belgium | 1825.5 | 209 | 160 | 222 | 321 | 225 |
| France NW | 1462 | 187 | 95 | 207 | 412 | 219 |
| Germany NW | 2157.1 | 211 | 133 | 215 | 331 | 207 |
| Netherlands | 1921.3 | 212 | 162 | 239 | 365 | 243 |

## Calculation Formulas (Calculations sheet, row 2)

### Geometry
```
C2 (gross_area) = length * width * storeys
D2 (net_area) = C2 * 0.8
E2 (envelope) = ((length + width) * 2) * storeys * storey_height
K2 (roof) = length * width
L2 (floor) = length * width
M2 (walls) = E2 - F2 (envelope - windows)
O2 (party walls) = length*storeys*height (semi-d length) | width*s*h (semi-d width) | *2 for terraced | 0 for detached
N2 (ext walls) = M2 - O2
P2 (volume) = D2 * (storey_height - 0.35) * storeys
```

### Transmission Heat Loss
```
AT2 (L_e) = U_win*A_win*1 + U_roof*A_roof*1 + U_floor*A_floor*0.7 + U_wall*A_extwall*1
AU2 (L_psi) = MAX(0.2 * (0.75 - L_e/(A_win+A_roof+A_floor+A_extwall)) * L_e, 0)
AV2 (L_t) = AT2 + AU2
AW2 (Q_t) = 0.024 * L_t * HDD  [kWh/a]
```

### Ventilation Heat Loss
```
BB2 (L_v) = 0.34 * 0.4 * volume
BC2 (Q_v) = 0.024 * L_v * HDD  [kWh/a]
```

### Internal Gains
```
BG2 (Q_i) = 0.024 * 3.75 * net_area * heating_days  [kWh/a]
```

### Solar Gains
```
BT2 (g_eff) = g_value * 0.9 * 0.98
BS2 (F_s) = 0.75
BU2 (Q_s) = (Irr_N*A_N + Irr_E*A_E + Irr_S*A_S + Irr_W*A_W) * F_s * g_eff  [kWh/a]
```

### Heating Demand
```
BY2 (Q_heating) = Q_t + Q_v - Q_i - Q_s  [kWh/a]
BZ2 (HWB) = Q_heating / gross_area  [kWh/m2a]
```

### Hot Water
```
CB2 (Q_hotwater) = residents * 40 * 365 * (4.2/3600) * 45  [kWh/a]
    = residents * 40L/day * 365days * 0.001167kWh/(L*K) * 45K
```

## Energy & CO2 (Energy+CO2 Calculations sheet)

| System | Efficiency/SCOP | CO2 Factor (t/kWh) |
|--------|-----------------|---------------------|
| Oil | 0.85 | 263.9e-6 |
| Gas | 0.90 | 194e-6 |
| Biomass | 0.875 | 0 |
| All Electric | 0.99 | 210e-6 |
| Air Source HP | 3.5 | 210e-6 |
| Ground Source HP | 4.5 | 210e-6 |
| Water Source HP | 4.5 | 210e-6 |

```
Final Energy = Useful Energy / Efficiency
CO2 = Final Energy * CO2_Factor
```

## Key Constants
- 0.024 = 24h / 1000 (converts W*Kd to kWh)
- 0.8 = net-to-gross floor area ratio
- 0.35 = floor thickness deducted from storey height for volume
- 0.7 = floor U-value reduction factor (ground contact)
- 0.75 = thermal bridge reference U-value
- 0.2 = thermal bridge scaling factor
- 0.4 = air changes per hour
- 3.75 = internal gains rate (W/m2 of net area)
- 0.9 = window frame factor
- 0.98 = dirt correction factor
- 0.75 = shading factor (F_s)
- 52 = m2 per person (for default occupancy)

## Vision Pipeline Architecture

### Footprint Extraction (Phase 3)

The pipeline uses a two-tier approach to extract building dimensions from satellite imagery:

**Scale — Mapbox, not Google (fixed Nov 2026)**
- Satellite images come from the **Mapbox** Static Images API, which uses 512 px tiles: zoom Z
  is half the metres/pixel of Google zoom Z. Use `geospatial/scale.py::satellite_meters_per_pixel()`
  (≈0.046 m/px at zoom 20 in Cork; a 640 px image covers ~29 m). `meters_per_pixel()` with its
  default 256 px tile is the Google scale.
- Until Nov 2026 the code used the Google scale for Mapbox images: Claude was told the image
  covered ~59 m, so every roof looked twice its real size. That was the main cause of the
  anchored, oversized footprints in the Sept 2026 validation. OpenCV's size filter and the
  overlay used the same wrong scale.

**Primary: Claude Vision (`ber_automation/vision/claude_analyzer.py::analyze_satellite()`)**
- **GPS path (zoom known — normal runs): `SATELLITE_CORNERS_PROMPT`.** Claude does *not* give
  metres. It outlines the **whole attached block** (detached house / both halves of a semi-d /
  terrace row up to the first gap) as 4 pixel corners (`block_corners_px`) and counts the homes
  in it (`units_in_block`). `_unit_from_block()` divides the block's **longer** edge by the
  count, converts to metres with the Mapbox scale, and returns the slice nearest the image centre
  as `contour_points` (drawn as the green outline).
  - Why the whole block: asked to outline one home, Claude outlined the whole pair/row anyway
    (it finds outer edges reliably, party walls poorly).
  - Why the longer edge rather than an edge Claude names: Claude mixed up the edge order; area per
    home = block area / count whichever edge is split, and rows are nearly always longer than deep.
  - Street View's type/units go in as a "hint (may be wrong)" for the home count.
  - Claude also returns `units_visible` (it can see every party wall / plot boundary, or the
    house is detached). When false, `census.choose_unit_count()` picks the count from the Small
    Area's room mix (see Census Priors). `FootprintResult` keeps `block_length_m`,
    `block_width_m`, `units_in_block`, `units_claude`, `units_visible`, `units_source`; the app
    shows them under the footprint card.
  - A reply without 4 valid corners → confidence 0 (OpenCV fallback), never a guess.
- **Uploaded-image path (zoom=None): `SATELLITE_ANALYSIS_PROMPT`** — scale unknown, so Claude
  estimates metres from cars, doors, bins etc. and is told to measure one unit.
- Returns `FootprintResult` with `source="claude_vision"`
- Validation: dimensions clamped to [4m, 25m], area sanity check [20, 500] m2
- **Image-edge guard (`_reaches_image_edge()`):** the prompt tells Claude to stop the outline at
  the image edge when a row runs off it. A corner within 2 % of the image size (13 px of 640)
  of the border means the outline is only part of the row: its length and home count were
  not measured. Claude's count is kept (no census re-split), confidence is capped at 0.3
  (below the 0.4 reconciliation threshold, so OpenCV is used) and `block_clipped` is set.
  Whole blocks in the validation images stay ≥ 49 px clear of the border; AX03's cut-off
  terrace has corners at 0–2 px. Before the guard this relied on Claude rating such blocks
  ≤ 0.3 itself, which stopped happening once `units_visible` was added. A zoom-19 image
  would let the whole row be measured.

**Secondary: OpenCV (`ber_automation/vision/footprint.py::extract_footprint()`)**
- Canny edge detection + contour scoring (solidity, centrality, rectangularity, relative area)
- Scoring weights rebalanced: area=0.15, solidity=0.30, centrality=0.30, rectangularity=0.25
- Pixel-area bounds filter skips contours outside 4m–25m range
- Forces confidence < 0.15 if any dimension exceeds 30m

**Reconciliation (`ber_automation/pipeline.py::BERPipeline._reconcile_footprints()`)**
- If both methods succeed and areas agree within 30%: use Claude result, boost confidence +0.15
- If they disagree: trust Claude
- If Claude fails (confidence < 0.4): fall back to OpenCV
- If both fail: return None

**Input Validation (`_build_input()`)**
- Confidence threshold: 0.4 (raised from 0.2)
- Dimensions clamped to [4.0, 25.0] meters
- Area must be in [20, 500] m2 or defaults (10m × 8m) are used
- User overrides always take precedence

### Street View Analysis — Multi-Angle (`analyze_streetview()`)
- **Multi-angle capture**: `fetch_streetview_images()` fetches 4 images at 90° intervals
  around the auto-computed base heading (camera→building bearing)
- **All images sent in one Claude request**: Claude cross-references front/right/rear/left
  views to identify features only visible from certain angles (oil tanks, heat pumps,
  shared walls, gas meters)
- **One panorama, no duplicates (Nov 2026)**: metadata is requested with `source=outdoor`
  (Google's own 360° panoramas; falls back to any panorama), and all 4 views are fetched by
  that `pano_id`. Views that are near-duplicates of an earlier one (64×64 greyscale mean diff
  < 4) are deleted, so fewer than 4 can come back. Old `streetview_*` files and overlays are
  cleared before each fetch, and each view's `_annotated` overlay is removed before window
  detection. Cause of the app screenshot `docs/images/streetview_duplicate_views.png`, where Front = Right and Rear =
  Left: user-contributed partial panoramas return the nearest edge for out-of-range headings.
  The app captions views by file index (`streetview_2` = Rear) because positions can shift.
- **Backward-compatible**: accepts a single path (str/Path) or a list of paths
- **Async client**: uses `anthropic.AsyncAnthropic` (not the synchronous client) to avoid
  blocking the event loop
- **Dual prompts**: multi-image prompt instructs cross-referencing; single-image prompt
  preserved for fallback/testing
- Returns: construction epoch, building type, storeys, heating system guess, confidence
- Used in Phase 4, feeds into `_build_input()` for non-geometric parameters
- **The 4 views are one camera turned 4 ways, not 4 sides of the house.** Only
  `streetview_0` (heading camera → address) shows the property; the others look along or
  across the street at other buildings. Since Nov 2026 each image is preceded by a text label
  (`_view_label()`, by file index: "Image 1: FRONT — … target is the building at the centre",
  others "street context, not the property"), and the multi-image prompt says so. If the
  target is privacy-blurred, Claude estimates from the neighbours in the FRONT image with
  confidence ≤ 0.5 — this lands at 0.40–0.45, just above the 0.4 gate in `_build_input()`;
  below it, the defaults (detached, before_1980) would be used instead.

### Census Priors: Era, Heating and Home Count (`ber_automation/geospatial/census.py`, Ireland only)
- Street View can't separate adjacent decades (replacement PVC windows, re-tiled roofs);
  Claude read every 1980s house as 1990s and prompt changes didn't move it.
- **Data:** CSO Census 2022 table SAP2022T6T2SA (households by year built, per Small Area of
  80–120 homes), merged into the 5 HWB epochs →
  `ber_automation/data/cso_year_built_sa2022.csv` (18,920 areas, ~1 MB, CC BY 4.0), and
  SAP2022T6T5SA (households by central-heating fuel) → `cso_heating_sa2022.csv`
  (gas/oil/electricity/wood/lpg/coal/peat/other/none), and SAP2022T6T4SA (households by
  number of rooms, 1–7 and 8+) → `cso_rooms_sa2022.csv`.
  Rebuild all three: `python scripts/build_census_data.py [--source-dir DIR]`. The tables also
  hold person counts (`...C02`); only households (`...C01`) are used.
- **Lookup:** point → Small Area via the CSO/Tailte Éireann ArcGIS service
  `SMALL_AREA_2022_Genralised_20m_view` (sic), run in parallel with the Street View call.
  Any failure → None (falls back to Street View). Non-Irish countries → None.
- **`choose_epoch(prior, analysis)`:** no usable Street View reading (conf < 0.4) → dominant
  census period; Claude's band adjacent to the dominant one → dominant, unless that band is
  ≥ 25 % of the area and conf ≥ 0.8; two or more bands away → Claude if ≥ 10 % of the area
  is from that period, else dominant. Fewer than 20 stated households → no prior.
- **`choose_heating(area, analysis, epoch)`:** Claude now returns `heating_observed`
  (true only if a tank/flue/meter/heat pump of the target is visible). Observed → Claude.
  Otherwise: gas ≥ 15 % of the area's homes → gas boiler (network present; older homes
  there may still be oil); else the most common of oil / electricity / wood (electricity +
  after_2010 → heat_pump_air). No fuel mix (< 20 households) → CSO urban flag: urban → gas,
  rural → oil. No census → Claude's guess.
- Why not the urban flag alone: CSO "urban areas" are 848 settlements, including
  1-small-area villages (Annascaul, Ahascragh) with no gas, and towns without a gas network
  (Sligo, Letterkenny: 86 small areas each), while Tower (12) has gas. RK10's area is 52 %
  oil / 38 % gas, so "most common fuel" would also be wrong; the gas threshold isn't.
- **`choose_unit_count(block_long, block_short, claude_units, units_visible, area, storeys,
  detached)`:** party walls are often invisible from above, and then Claude's home count is a
  guess from the block length (HYW6's 17 m block came back as 1, 2, 3 or 4 homes across
  runs). When `units_visible` is false, each count n is scored by how typical a home of
  block area / n × storeys (default 2) is for the area's room mix: a mixture of log-normal
  floor areas centred on rooms × 20 m² (spread 0.25, "8+" = 8.5 rooms). Only counts leaving
  ≥ 4 m of frontage per home are tried (max 12); ties go to Claude's count. Claude's count is
  kept when it saw the boundaries, when Street View says detached, or with no room mix
  (< 20 households). The ranking on the validation houses is the same for 18–22 m²/room and
  spread 0.15–0.3.
- `PipelineResult.census` (CensusArea: small_area, urban, urban_area, era, heating_shares,
  rooms_shares)
  plus `epoch_source` / `heating_source` ("census" | "census_urban" | "streetview" |
  "default" | "override") record the decisions; the app's Era/Heating cards show the values
  used, with a caption giving the census mixes.

### Window Detection (`detect_windows()`, display only)
- Runs on the **front view only** (`streetview_0`); the other headings never show the property.
  1 Claude call per property instead of 4.
- Prompt: target = building at the horizontal image centre. Claude returns
  `{"target_visible", "facade_x1", "facade_x2", "windows": [...]}`; windows whose centre is
  outside the facade x-range (neighbours) are dropped, and `target_visible: false` (privacy
  blur, hedge, van) → no windows. A bare JSON list reply is still accepted.
- T23 HYW6's house is privacy-blurred by Google → 0 windows (correct). Before Nov 2026 all
  boxes for it were on neighbours. Small windows (e.g. beside a porch) are sometimes missed.

### House Description and Similar House (`describe_house()`, display only, Nov 2026)
- **Why:** the front view often shows the property side-on or behind a hedge (T12 E9X2: a
  tall hedge hides the ground floor and door), while another heading, or the same image,
  shows a neighbour built to the same design in full.
- `describe_house(sv_paths, analysis, country, location)` sends the same labelled images in
  a **separate request** and returns a `HouseDescription` (stored on
  `PipelineResult.house_description`): `target_view` (`front` / `side` / `partial` /
  `hidden`), the similar house (`similar_house_view` = heading index of its image,
  `similar_house_x1/x2` = its facade's x-range), `inferred_from_similar` (details not seen
  on the target and taken from that house) and a short `description`. The classification
  is passed in as context; the description says so when the images contradict it (T23 RK10:
  "1-1.5 storey, not the 2 storeys given earlier").
- **Nothing here feeds the calculation.** A first version put this task inside the
  `analyze_streetview()` prompt. That flipped T23 RK10 from semi-detached (correct) to
  detached, 4 runs of 4 against 4 of 4 with the old prompt on the same images: the house
  is joined to its neighbour only by a low garage link, and the old prompt already called
  the pairing uncertain (confidence 0.4). The classification prompt is therefore unchanged
  (a test asserts it does not mention `similar_house`), and using the similar house for
  type, storeys or era is left until there is a sample large enough to measure it.
- Claude has to be told to report the similar house **whenever one is visible**. Asked to
  do it only "when the facade is not fully visible", it skipped it for E9X2 ("the hedge
  hides only the lower ground floor ... a similar house is not needed").
- `HouseDescription.uses_similar_house`: a similar house was found and either the front
  view is not `front` or something was inferred from it. Only then are its windows marked:
  `detect_windows(path, facade_hint=(x1, x2))` names the house by x-range instead of "the
  building at the centre", and `draw_window_boxes(..., color=SIMILAR_WINDOW_COLOR,
  title="Similar house")` draws them in orange (the property's stay cyan), on top of the
  front view's own boxes when the similar house is a neighbour in that image.
  `PipelineResult.similar_house_windows` is the count.
- Timing: the description request starts right after the classification and runs alongside
  the satellite analysis; the similar-house windows run alongside the front-view windows.
  Claude image calls per property: 3 → 4, or 5 when a similar house is used.
- App: "Description" and a note under *AI Building Analysis* ("The front image shows the
  house partly hidden. From a house of the same design in the Rear image, the AI took: ...
  This is for the description only; it does not change the rating."); the similar house's
  image is captioned "similar house (orange boxes)".

### Claude API Client (async fix)
- Both `analyze_satellite()` and `analyze_streetview()` now use `anthropic.AsyncAnthropic`
  with `await client.messages.create(...)`, fixing the previous event-loop-blocking bug
  where the synchronous `anthropic.Anthropic` client was called from async functions.

### Settings Caching
- `get_settings()` now uses `@lru_cache(maxsize=1)` to avoid re-parsing `.env` on every call

### FootprintResult Model Fields
- `length_m`, `width_m`, `area_m2`, `confidence` — core dimensions
- `contour_points` — OpenCV contour for visualization
- `source` — `"opencv"`, `"claude_vision"`, or `"fallback"`
- `building_shape` — `"rectangular"`, `"l_shaped"`, or `"irregular"`

### Street View Confidence Gating
- `_build_input()` now requires `street_analysis.confidence >= 0.4` before applying
  Claude's classification (building type, epoch, storeys, heating system)
- If confidence is below 0.4 (e.g. vegetation-blocked view), safe defaults are used:
  detached, before_1980, 2 storeys, gas_boiler
- Prompt includes explicit visibility check: instructs Claude to set confidence <= 0.1
  when no building facade is visible (trees, hedges, obstructions)

### Heating System Default — Location-Aware (Sept 2026)
- `analyze_streetview(image_paths, country, location=None)`: the pipeline passes
  `coords.formatted_address` as `location`; the prompt gains a "Property Location" block.
  `reanalyse()` goes through the same call.
- Prompt rule when no heating indicator is visible (meters, flues and oil tanks are usually
  hidden, so *not seeing one is not evidence*):
  - estate/street within or on the edge of a city or large town → `gas_boiler`, any age
  - one-off house in open countryside, farmhouse, small village → `oil_boiler`
  - Claude is told not to speculate about whether mains gas reached the estate
- Replaced the old rule "gas for 2000+ builds, oil for older rural buildings", which made
  Claude call Cork city suburbs rural (it never saw the address) and guess oil.

### Model and Sampling (Nov 2026)
- `Settings.claude_model = "claude-sonnet-5-5"`. `claude-sonnet-4-5-20250929` started returning
  404 on this account in Nov 2026 (Sonnet 4.5 retires 2026-11-30).
- Sonnet 5.5 rejects `temperature`, so `Settings.claude_temperature` now defaults to `None`
  (parameter omitted). Set `CLAUDE_TEMPERATURE=0` only when pointing `claude_model` at an older
  model that accepts it. Applied to all three vision calls via `_sampling_kwargs()`.
- Sonnet 5.5 thinks by default: `max_tokens` is 16000 (was 1024) and replies are read with
  `_response_text()`, which joins the `text` blocks and skips `thinking` blocks
  (`message.content[0]` can be a thinking block).
- Even without temperature 0, repeat runs on the same images mostly agree; T23 RK10 still
  flips between detached and semi-d.

### Vision Model Providers: Claude and Mistral (`ber_automation/vision/providers.py`, Nov 2026)
- **Why:** the paper compares two commercial models on the same task (accuracy, agreement
  between repeat runs, cost); Mistral is also EU-hosted.
- All four model calls (`analyze_streetview`, `describe_house`, `analyze_satellite`,
  `detect_windows`) take `provider: str | None` and go through one helper,
  `claude_analyzer._complete(parts, provider, settings)`. `parts` is the ordered list of text
  strings and image paths. **Both models get the same prompts, labels and images in the same
  order**; all parsing after the reply is shared.
  - Claude: the anthropic SDK, same request as before (existing tests unchanged).
  - Mistral: `providers.mistral_complete()` posts to `/v1/chat/completions` with httpx (no
    new dependency), **streamed**, `max_tokens` 16000 (as for Claude), `reasoning_effort`
    `low`, no JSON mode. Images are `{"type": "image_url", "image_url": "data:image/jpeg;base64,..."}`.
    The JSON object is cut out of the reply (`json_object_text()`), thinking chunks are
    skipped, one retry on 429 / 5xx, errors carry Mistral's own message.
- **Why streamed, `low` and no JSON mode (Nov 2026, `T12 K7AC`):** at Mistral's default
  reasoning level the Street View, satellite and description requests sent nothing back
  for over 7 minutes (also streamed: no first byte). With JSON mode on, the satellite
  request hung even at `low`. Not streamed, `low` was unreliable (the description
  answered in 6 s, the other two hung). Streamed at `low` all three answer in 10 to 20 s
  and a full pipeline run takes about 1 minute. Mistral Large 4 cannot switch reasoning
  off; `MISTRAL_REASONING_EFFORT` can be set to `medium` or `high` to test again later.
  For the paper: Claude runs at its default (adaptive) thinking, Mistral at `low`.
- Choosing: `resolve_provider(provider, settings)` → the argument, else `LLM_PROVIDER`
  (default `claude`). `BERPipeline(output_dir, provider=None)` passes it to every call and
  records `PipelineResult.llm_provider` / `llm_model`. Errors name the model
  ("AI analysis failed (Mistral): ..."). A missing key gives "MISTRAL_API_KEY not configured".
- Settings: `MISTRAL_API_KEY`, `MISTRAL_MODEL` (default `mistral-large-4-0`, a fixed ID
  rather than `mistral-large-latest`, so every run of the study uses the same model; it
  lists `vision` among its capabilities in `GET /v1/models`), `MISTRAL_TEMPERATURE`
  (default unset), `LLM_PROVIDER`.
- **Sampling:** both models run with their default sampling. Claude's current models
  refuse a temperature, so setting one only for Mistral would make the agreement between
  repeat runs incomparable. Mistral refuses temperature 0 unless `top_p` is 1 ("top_p must
  be 1 when using greedy sampling", 400), so a configured temperature is sent with
  `top_p=1`. Errors now carry Mistral's own message.
- Mistral Large 4 is a reasoning model: its reply is a list of chunks, a `thinking` chunk
  first, then the text; `_reply_text()` keeps only the text chunks.
- Where it can be chosen: `python main.py pipeline "T12 K7AC" --provider mistral`;
  `python scripts/validate_daft.py --runs 3 --provider both` (the second model re-analyses
  the images fetched for the first, and each model gets its own report: `report.json` for
  Claude, `report_mistral.json`); the app shows an "AI model" choice in Full Pipeline mode
  **only when both keys are configured** (the live app has no Mistral key, so it is
  unchanged), and "Analysed with Claude (model)" under *AI Building Analysis*.
- `FootprintResult.source` stays `"claude_vision"` for either model (pipeline logic and tests
  depend on the value; the app labels it "AI Vision").
- The first key in `.env` was refused (401 "Invalid API Key"); a new key works (Nov 2026).
  First comparison on the 5 homes: *Part B — Mistral Large 4 against Claude*. Mistral
  places roof corners much less consistently than Claude. The prompts stay identical for
  both models; a weak result is a finding, not something to tune away.
- After the refactor a live Claude run of `T12 K7AC` gave A3, 67 kWh/m²/yr, as before.

## Calculation Inputs, Presets and the Energy Diagram (app, 2026-11-23)

Made for the supervisor's review of the live app ("show the current window U-value and where it
comes from", "what are internal gains", "HWB units wrong: HWB × floor area", "redraw the chart
as a house with gains, heating and hot water in kWh/yr").

- **Presets the user can change:** `CalculationOverrides` (`models.py`) holds optional `u_wall`,
  `u_roof`, `u_floor`, `u_window`, `g_value`, `window_share`, `air_change_rate`,
  `internal_gain_w_m2`, `heating_efficiency`; `BuildingInput.overrides` (None = all presets).
  `resolve_presets(building)` (`calculator.py`) gives the values in use: era table U/g, window
  share by type, 0.4 ach, 3.75 W/m², efficiency by heating system, then the overrides on top.
  The calculator reads only from it, so without overrides every result is unchanged (checked on
  400 combinations of type, era, country and heating before and after). Retrofit insulation is
  added to the U-values in use, not the era table; a new heating system drops an efficiency the
  user had set for the old one.
- **HWBResult** now also holds the annual balance and its parts: `transmission_loss_kwh`,
  `ventilation_loss_kwh` (kWh/yr; `transmission_heat_loss`/`ventilation_heat_loss` stay in W/K),
  areas, thermal bridge, HDD, heating days, residents, `presets`. All have defaults, so older
  saved results still load (the app asks to recalculate them for the diagram).
- `ber_automation/ber_engine/inputs.py`: `calculation_inputs(building, sources)` lists every value
  used with its origin (images / census / preset / set by you / country climate) and its source
  (Excel sheet and cell, OIB guidance, degreedays.net, PHPP, SEAI). `energy_formulas(ber)` writes
  each result as its formula with the home's numbers. `PipelineResult.dimensions_source`
  ("satellite"/"default"/"override") and `type_source` ("streetview"/"default"/"override") were
  added so the footprint and type origins are known.
- **App:** the mixed-unit bar chart (W/K, kWh/yr and kWh/m²/yr on one axis) is gone. The gauge
  moved to the top row; below it `app/energy_diagram.py` draws the house (internal and solar gains
  in, heating from the boiler = HWB × floor area, transmission and ventilation out, hot-water
  tank), all kWh/yr, arrow width by size, with a line checking losses = gains + heating. HWB is
  shown per m² and as kWh/yr. Expanders: "How these numbers are calculated" and "Calculation
  inputs" (open on the main result). What-If and Manual Input have an **Assumptions** tab
  (presets pre-filled, changed ones listed, "Reset to presets"; they restart at the new presets
  when era, type or heating changes). The retrofit window slider starts at the current window U.
- Checked headlessly with `streamlit.testing.v1.AppTest` (manual mode and a ready-made pipeline
  result): window U 3.0 → 1.2 on a pre-1980 detached house moves primary energy 188 → 164.
- **Open:** the supervisor's "cap the number of solar panels per house": the app has no PV; the
  user is asking what was meant.

## Official-BER Sample for the Paper (`data/validation/official/`, Nov 2026)

- `sample.csv`: one row per home, filled in by hand from property listings and checked
  against SEAI's register (no scraping). 21 homes on 2026-11-23 (Cork 7, Dublin 8, Kerry 2,
  Kildare, Meath, Offaly, Waterford; 13 urban, 8 rural; bands A2 to D2, none E to G yet).
  Columns and
  the collection steps are in the `README.md` next to it. Required: `id`, `eircode`,
  `county`, `settlement` (urban/rural), `listing_source`, `date_recorded`, `ber_number`
  (9 digits), `ber_band`, `ber_kwh_m2_yr`. Optional, from the certificate or register:
  `listing_url`, `dwelling_type` (detached / semi_detached / terraced; houses only),
  `year_built`, `floor_area_m2`, `storeys`, `heating`, `register_checked`, `notes`.
- `ber_automation/evaluation/official_sample.py`: `load_official_sample(path)` →
  `(homes, problems)`. It normalises Eircodes, reports unusable values, duplicates and a
  band that does not match the kWh value (the band follows from the value on the BER
  scale, so a mismatch is a typing mistake in one of the two). A row with an unusable
  required value is left out; a bad optional value is reported and dropped.
  `OfficialHome.epoch` maps `year_built` to the calculator's era; `summarise()` counts
  homes per county, settlement, dwelling type, era and band.
- `python scripts/add_official_home.py`: checklist for manual lookups (listing values, then
  the register values). **Default since 2026-11-17 is clipboard mode:** per home the user
  pastes the listing link, copies the listing page (Ctrl+A, Ctrl+C) and presses Enter,
  answers urban/rural, copies the register result page and presses Enter, then confirms.
  `parse_listing_text` finds the Eircode (only when the page shows exactly one; several
  are listed and asked for) and the number after "BER No"/"BER Number";
  `county_from_listing_url` reads the county from the link; `parse_register_text` reads the
  values after the labels "Building Energy Rating", "Dwelling Type", "Year Of
  Construction", "Floor Area", "Date Of Issue" (same line or the next). Anything not found
  is asked for; a register page that does not show the home's BER number or a rating must
  be copied again ("type" to type the values). The clipboard is read with tkinter
  (`read_clipboard`); `run(..., clipboard=...)` takes any function, which is how the tests
  drive it. Clipboard mode does not ask for storeys, heating or notes; `--type` gives the
  old mode that asks for every value. **First real use (2026-11-23, home 21, D13 DC65):** every
  value was read from the copied daft.ie and register pages, nothing had to be typed. If a
  later page is missed, get the copied text from the user and adjust the patterns.
  Each answer is checked as typed (Eircode, 9-digit BER
  number, duplicates, band vs kWh, houses only); a row is saved only when `check_row`
  passes, with the next id, today's date and `register_checked=yes`. Register text can be
  pasted as shown ("C2 177.03 (kWh/m2/yr)", "Semi-detached house", "137.17 (m2)"):
  `parse_rating`, `dwelling_from_register`, `first_number`. No web requests.
- `python scripts/check_official_sample.py` prints the problems and the counts against the
  plan (about 250 homes, at least 4 counties). No API calls.
- **Register lookups cannot be scripted (checked 2026-11-13):** the search form at
  `ndber.seai.ie/pass/ber/search.aspx` takes a BER number or MPRN only (no Eircode) and
  runs Google reCAPTCHA v3, i.e. bot detection. Lookups are done by hand in a browser
  unless SEAI provides another route. Data requests go to info@ber.seai.ie (who, what,
  why); the full data file is limited by S.I. 243/2012 to the assessor and the owner.
- **What the register shows (first lookup, BER 113779219, 2026-11-13):** address
  (no Eircode), band and kWh/m²/yr, CO2 indicator, date of issue and expiry, type of
  rating (existing/new/provisional), DEAP version, dwelling type, year of construction,
  floor area, plus certificate and advisory-report PDFs. **Not shown:** storeys,
  heating system, U-values; those are in the advisory report or the full data file.
  The listing (daft.ie) gave band and BER number but no kWh value.
- `python scripts/validate_official.py [--offline] [--runs N] [--provider claude|mistral|both]
  [--ids 1,4]` → `output/official_validation/report_<provider>.json`. The comparison is in
  `ber_automation/evaluation/official_compare.py` (no API calls, unit-tested):
  - **(a) inputs:** pipeline's dwelling type, era, floor area (gross L × W × storeys against
    DEAP's total floor area), and storeys / heating when recorded, against the certificate.
  - **(b) certificate values:** the calculator on the pipeline's inputs with the certificate's
    era, floor area (length and width scaled by one factor, plan shape kept), dwelling kind
    (the pipeline's shared side kept when the kind agrees, else the length side), and storeys
    and heating when recorded. The register gives no storeys, heating or U-values, so this is
    calculator error plus those unknown inputs, not the calculator on full certificate inputs.
  - **(c) pipeline:** band and primary kWh/m²/yr against the official BER (exact, within one
    band, signed band offset, kWh % error). Summaries count every run (n = homes × runs); run
    agreement = share of runs giving the commonest band.
  - **Baseline:** commonest band among the other homes (leave-one-out; ties go towards C1),
    kWh = their median in that band. On the 13 homes: exact 5/13, within one 6/13 (C3 is 5 of 13).
- **First live check (2026-11-13, home 1, R35 HH93, Claude, 1 run):** official C2 177; pipeline
  B1 87 (−51%), with era 1990–2000 from the census (certificate 2001) and 10 × 8 m × 2 = 160 m²
  (certificate 137 m², +17%; 10 × 8 m is the OpenCV default). With the certificate's era and area
  (b) gives A3 71 (−60%): the calculator's 2000–2010 era is far more efficient than DEAP rated
  this house. One home only; the full run is still to do.
- **First full run (2026-11-23, 21 homes, Claude Sonnet 5.5, 3 runs each, n = 63;**
  `output/official_validation/report_claude_21homes_2026-11-23.json`, ~1 h):

  | | band exact | within one | mean band offset | kWh error, mean abs / median |
  |---|---|---|---|---|
  | baseline (commonest band, leave-one-out) | 0/21 | 4/21 | +1.14 | 153% / +20% |
  | (b) calculator on certificate era, area, type | 18/63 | 30/63 | −1.90 | 32% / −24% |
  | (c) pipeline | 11/63 | 19/63 | −1.35 | 55% / −29% |

  (a) inputs: dwelling type 45/63, era 38/63 (census for 59 runs), floor area mean |error| 80%,
  median +31%; 17 of 63 runs fell back to the 10 × 8 m footprint. Run agreement 94%.
  By certificate year (median kWh error, (c) / (b)): before 2000 −34% / −28% and −3.0 bands
  on average; 2000–2010 −50% / −57%; after 2010 +18% / +7%. **The calculator rates older homes
  as far more efficient than DEAP**, even with the certificate's own era and area ((b)), so most
  of the error is the HWB-versus-DEAP gap, not image reading. New homes come out close.
  **The baseline is degenerate here:** A3 and C3 each hold 5 of 21 homes, so leaving one out always
  tips the commonest band to the other one (ties go towards C1), giving 0 exact. A median-kWh
  baseline or the census-only switch would be a fairer reference.
  Failures: "Footprint extraction found no building contour" (X91 A3V9 1 run, V92 NFR9, V93 C7N8
  all runs), no Street View for one run each of P17 HW84, P43 K277, K78 A9T4.
  The background process ended with exit code −1 *after* printing the summary and writing the
  report (Windows event-loop teardown); the results are complete. About 1 minute per pipeline run
  (63 runs in about 62 minutes).
- Not built yet: census-only / images-only switches (the remaining baselines).

## Daft Validation (`scripts/validate_daft.py`)

`data/validation/daft/1–5.xlsx` are copies of the Kaiser Excel tool filled in by a human assessor
for five Cork Eircodes. They hold the assessor's inputs and the Excel outputs — **not**
listed BER certificates. "Assessor BER" below = `HWBCalculator` on the assessor's inputs.

```
python scripts/validate_daft.py --offline   # Part A only, no API calls
python scripts/validate_daft.py --runs 3    # Part A + live pipeline, 3 vision runs per property
```
Run 1 fetches images; runs 2+ use `reanalyse()` on the same images, so differences between
runs are model variance only. Output: `output/daft_validation/report.json` (+ per-Eircode
`result*.json` and images).

**Part A — calculator parity vs Excel:** all five within 0.12% on every output
(useful/final energy, hot water, CO2). Residual differences come from hand-entered
per-orientation window areas that do not sum exactly to the total.

**Part B — pipeline vs assessor (2026-09-19, temperature 0, 3 runs each):**

| Eircode | Type | Footprint area | Storeys | Epoch | Heating | BER assessor → pipeline |
|---|---|---|---|---|---|---|
| T23 HYW6 | wrong side (length vs width) | +52% | ok | one band newer | ok | B2 → B1 |
| T23 RK10 | ok | +25…+44% | ok | one band newer | oil (assessor: gas) | B2 → B1 |
| T12 K7AC | ok | −2…+12% | ok | ok | ok | A3 → A3 |
| T23 AX03 | terraced (assessor: semi-d) | +125…+132% | ok | ok | ok | B1 → A3 |
| T12 TP3C | ok | +30% | ok | one band newer | ok | B1 → B1 |

- Storeys 5/5, heating 4/5 (was 1/5 before the location-aware rule), type 3/5, epoch 3/5,
  BER band exact 2/5, within one band 4/5.
- **Footprint is the dominant error and looks anchored, not measured:** `analyze_satellite`
  returned length 10.5 m for 4 of 5 properties (assessor: 9.0, 9.5, 5.6, 9.0) and widths from
  a small set (6.0 / 6.8 / 7.8), with confidence 0.75–1.0 every time — so the 0.4 confidence
  gate filters nothing. T23 AX03 is measured ~2 units wide and `_correct_terrace_footprint()`
  does not correct it.
- **Epoch bias:** all three 1980–1990 houses are read as 1990–2000 (PVC replacement windows
  make older estates look newer).
- n = 5, one city: treat as directional, not statistical.

**Part B — after the footprint fix (2026-11-11, Sonnet 5.5, 3 runs each):**
Mapbox scale + block outline split by home count (see Footprint Extraction). The model also
changed (Sonnet 4.5 → 5.5), so this is not a footprint-only comparison.
Reports: `report_before_footprint_fix.json` (Sept), `report.json` (this run).

| Eircode | Footprint source | Footprint area (Sept → now) | BER assessor → pipeline |
|---|---|---|---|
| T23 HYW6 | Claude | +52% → +48% | B2 → B1 |
| T23 RK10 | Claude | +25…+44% → +25…+31% (one run −38%) | B2 → B1/B2 |
| T12 K7AC | Claude | −2…+12% → +1…+3% | A3 → A3 |
| T23 AX03 | OpenCV (Claude conf 0.3) | +125…+132% → +18% | B1 → A3 |
| T12 TP3C | Claude | +30% → −13% | B1 → B1 |

- BER within one band 5/5 (was 4/5); exact 2/5 (RK10 exact in 1 of 3 runs).
- The remaining footprint error is the **home count**, not the measurement: HYW6's block is
  17.3 × 9.1 m and Claude counts 2 homes; 3 would give 5.8 × 9.1 = 52 m² (assessor 54).
- Claude's confidence now varies (0.4–0.65) instead of always 0.75–1.0.

**Part B — after the front-view classification prompt (2026-11-11, 3 runs each):**
Report: `report.json` (previous run kept as `report_after_footprint_fix.json`).
- RK10's type is now semi-d in 3/3 runs (was detached in 2/3). Its footprint moved from
  +25…+31% to −37%: the semi-d hint makes the satellite step split an 8 × 9 m block in two.
- Everything else unchanged: HYW6 +47%, K7AC +1…+2%, AX03 +18% (OpenCV), TP3C −13% (one run +27%).
- BER: within one band 5/5; exact 2/5 (K7AC, TP3C). RK10 is B1 in all runs (assessor B2).
- Still open, with Claude's own reasons:
  - Era one band newer for all three 1980s houses (PVC windows, concrete tiles read as 1990s).
    Prompt fixes tried 2026-11-12 and reverted (no change, 3/3 runs still 1990s):
    (1) list PVC/tiles as not-evidence + Irish period table + "tie -> older band";
    (2) say 1980s/1990s look alike, add an `area_development` field.
    Claude ignores the tie-break. Its own build-year ranges: HYW6 1985-98, RK10 1990-2005,
    TP3C 1995-2005, AX03 1998-2008, K7AC 2000-08, so taking the lower bound fixes HYW6 only
    and risks AX03. Next idea: a per-location prior from CSO Census 2022 Small Area
    "year built" data. Reports: report_era_v1.json, report_era_v2.json.
    **Fixed 2026-11-12 by the census prior** (see Construction Era above).
  - RK10 storeys: Claude sees a dormer bungalow with rooms in the roof and says 2; the
    assessor used 1. Needs a rule for dormers (the Excel has no 1.5-storey option).
  - RK10 heating: Claude calls Kilnamucky "a small rural locality" → oil; assessor: gas.
    **Fixed 2026-11-12 by the census heating default.**
  - HYW6: the property is privacy-blurred in Street View; type/era come from the neighbours.

**Part B — with the census era prior (2026-11-12, 3 runs each):**
Report: `report.json` (previous: `report_classify_labels.json`).
- Era correct 4/5 in all runs (was 2/5): HYW6, RK10 → 1980s. TP3C stays 1990s: its Small
  Area is 82 % 1991–2000 builds, but the assessor says 1980s.
- BER exact 3/5 (K7AC, RK10 B2, TP3C), within one band 5/5. HYW6 B1 (95 kWh/m²a; B2
  starts at 100), held back by its +47 % footprint. AX03 A3 vs B1 (terraced vs semi-d).

**Part B — with the census heating default (2026-11-12, 3 runs each):**
Report: `report.json` (previous: `report_census_era.json`).
- Heating gas 5/5 in all runs (RK10 was oil: Claude still guesses oil, `heating_observed`
  false, census overrides). Claude reported `heating_observed: false` for all 15 runs.
- RK10 now 108 kWh/m²a vs assessor 108.8 (B2 exact), but partly by cancellation: footprint
  −35 % and 2 storeys vs 1.
- BER exact 3/5, within one band 5/5 (unchanged count; RK10 was already B2).

**Part B — with the census home count (2026-11-12, 3 runs each):**
Report: `report.json` (previous: `report_census_heating.json`). Claude said
`units_visible: false` in all 15 runs, so the census picked the count every time.

| Eircode | Block (m) | Homes Claude → census | Footprint area (before → now) | BER assessor → pipeline (before → now) |
|---|---|---|---|---|
| T23 HYW6 | 17.4 × 9.1 | 2 → 3 | +45…+48% → −2…−3% | B2 → B1 → **B2** (100.6 vs 103.3) |
| T23 RK10 | 9.1 × 8.0 | 2 → 1 | −33…−38% → +26…+29% | B2 → B2 → B1 (96.6 vs 108.8) |
| T12 K7AC | 12.1 × 9.9 | 2 → 2 | +1…+3% → +3…+4% | A3 → A3 |
| T23 AX03 | 25.7 × 8.2 | 6 → 4 | +18% (OpenCV) → +80…+90% | B1 → A3 |
| T12 TP3C | 12.2 × 9.0 | 2 → 2 | −13% → −13…−16% | B1 → B1 |

- BER exact 3/5 (HYW6, K7AC, TP3C; was K7AC, RK10, TP3C), within one band 5/5.
- Footprint mean |error| (median run) 24 % → 27 %; without AX03 25 % → 11 %.
- HYW6, the case this targets, is fixed. RK10's earlier B2 came from errors cancelling
  (−35 % footprint, 2 storeys vs 1); undoing the split leaves +27 % with the storeys error.
- **AX03 regressed, two causes:** (1) Claude's confidence is now 0.4 in all runs (was ≤ 0.3,
  likely the new `units_visible` field taking the count doubt out of the confidence), so its
  block is used instead of OpenCV. (2) The terrace runs off both ends of the image: the
  outline covers 87 % of the 29.5 m frame and is only part of the row, and Tivoli's Small Area
  (047277001) is mostly 5–7-room homes, so 4 homes of 105 m² fit it best, while AX03 is a
  56 m² home (likelihood 0.18 vs 0.65). Claude's own count (6) would give +25 %.
  **Fixed by the image-edge guard** (next section).

**Part B — with the image-edge guard (2026-11-12, 3 runs each):**
Report: `report.json` (previous: `report_census_units.json`).

| Eircode | Footprint source | Footprint area (before → now) | BER assessor → pipeline |
|---|---|---|---|
| T23 HYW6 | Claude, 3 homes (census) | −2…−3% → −1…−2% | B2 → B2 |
| T23 RK10 | Claude, 1 home (census) | +26…+29% → +25…+29% | B2 → B1 |
| T12 K7AC | Claude, 2 homes | +3…+4% → +3…+5% | A3 → A3 |
| T23 AX03 | OpenCV (Claude block clipped) | +80…+90% → +18% | B1 → A3 |
| T12 TP3C | OpenCV (Claude block clipped) | −13…−16% → −3%, +27%, −3% | B1 → B1 |

- BER exact 3/5 (HYW6, K7AC, TP3C), within one band 5/5 — same as before the guard.
- Footprint mean |error| (median run) 27 % → 11 %.
- AX03 is back to the OpenCV result in all runs (block corners at the top edge).
- **TP3C changed for a reason outside the guard:** in this session Claude outlined its
  semi-d pair together with the offset building attached above it, running off the top
  edge (17.4 × 10.0 m, "the building continues off the top edge"), in all 3 runs. Earlier
  sessions outlined only the pair (12.2 × 9.0 m, 82 px clear of the edge) on what looks like
  the same image (the earlier outline lines up with this image's roof edges), same prompt,
  temperature 0. The guard caught it: split in 2, the clipped block would give 87 m² (+38 %).
  OpenCV then gave −3 % twice; once its confidence was 0.38, under the 0.4 gate in
  `_build_input()`, so the 10 × 8 m default was used (+27 %).
- OpenCV is passed Claude's dimensions as the expected size (`expected_length_m/width_m`),
  so its contour choice and confidence follow Claude's answer even when that answer was
  rejected. For a clipped block those dimensions are not measured; not passing them is a
  possible next step (untested).

### Part B — with the house description step (2026-11-12, 3 runs each)

Report: `report.json` (previous: `report_edge_guard.json`). The description is display
only, so this run checks that the rating inputs did not move.

| Eircode | Type, storeys, era | Footprint area (before → now) | BER assessor → pipeline | Front view / similar house |
|---|---|---|---|---|
| T23 HYW6 | unchanged | −1…−2% → −2% | B2 → B2 | partial (blurred) / house in the Left image, 6 windows marked |
| T23 RK10 | unchanged (semi-d, 2 storeys) | +25…+29% → +26…+29% | B2 → B1 | front / neighbour in the Front image (door and porch, 2 runs of 3) |
| T12 K7AC | unchanged | +3…+5% → +4…+5% | A3 → A3 | front / pair opposite, nothing inferred |
| T23 AX03 | unchanged | +18% → +18% | B1 → A3 | partial in 2 runs (car, hedge) / row in the Left image, no windows found on it |
| T12 TP3C | unchanged | −3%, +27%, −3% → +27% ×3 | B1 → B1 | front / neighbour in the Front image, nothing inferred |

- BER exact 3/5 (HYW6, K7AC, TP3C), within one band 5/5: the same as before.
- Building type, storeys, era and heating are the same in all 15 runs as in the previous
  report.
- **TP3C's footprint is worse in this run, for the reason already listed as open:** OpenCV
  confidence was 0.38 in all 3 runs (before: 0.9, 0.38, 1.0), under the 0.4 gate, so the
  10 × 8 m default was used each time. The satellite path is not touched by this change.
  Footprint mean |error| (median run) is therefore 16 % in this run against 11 % before.
- The first version of this change (similar house inside the classification prompt) was
  also run: it gave RK10 as detached in 3 runs of 3. Its band then matched the assessor
  (B2) only because the wrong type offset the wrong storey count. That version was dropped.
- The descriptions run to 7–9 sentences although the prompt asks for 3 to 5.

### Part B — Mistral Large 4 against Claude (2026-11-13, 3 runs each)

Reports: `report_mistral.json` (Mistral, `mistral-large-4-0`, reasoning `low`, streamed)
against `report_claude_description_step.json` (Claude Sonnet 5.5, same code, run
2026-11-12). Each model fetched its own images; the Google and Mapbox images for a
coordinate are the same, so the inputs match.

| Eircode | Claude: type, st, footprint, BER | Mistral: type, st, footprint (3 runs), BER (3 runs) | Assessor BER |
|---|---|---|---|
| T23 HYW6 | semi-d, 2, −2% ×3, B2 ×3 | semi-d, 2, −16% / +48% / +17%, B2 / B1 / B1 | B2 |
| T23 RK10 | semi-d, **2**, +26…+29%, B1 ×3 | semi-d / terraced / terraced, **1** ×3, −29% / −29% / +8%, B2 / B1 / B1 | B2 |
| T12 K7AC | semi-d, 2, +4…+5%, A3 ×3 | semi-d, 2, −3% / +117% / +70%, A3 ×3 | A3 |
| T23 AX03 | terraced, 2, +18% ×3 (OpenCV), A3 ×3 | terraced, 2, +18% / +162% / +18%, A3 ×3 | B1 |
| T12 TP3C | semi-d, 2, +27% ×3 (OpenCV), B1 ×3 | semi-d, 2, +39% / −28% / −3%, B1 ×3 | B1 |

- **BER band:** exact Claude 9/15 runs (3/5 homes in every run), Mistral 8/15; within
  one band both 15/15.
- **Footprint area, mean |error| over all runs:** Claude 16%, Mistral 40% (worst +162%,
  +117%). Claude's runs agree within 3% on every home; Mistral's differ by up to 130
  points on the same images.
- **Storeys:** Mistral read RK10 (a dormer bungalow) as 1 storey in all 3 runs, which
  matches the assessor; Claude reads 2 every time (the open dormer issue). Mistral called
  RK10 terraced in 2 runs (wrong).
- **Era and heating:** the same as Claude except one RK10 run (1990–2000); heating comes
  from the census for both.
- **Confidence:** Mistral reports 0.65–0.97 for its satellite reading and 0.8–0.9 for
  Street View, Claude 0.4–0.7 and 0.4–0.6, so Mistral's confidence does not warn about its
  large footprint errors (research question 4: do the models know when they are wrong).
- One Mistral satellite request returned 503 "Service unavailable" after the retry
  (AX03 run 1); the pipeline fell back to OpenCV.
- Caveats: 5 homes, one city; Mistral at `low` reasoning because its default level hung
  (see *Vision Model Providers*); compared with an assessor, not official BERs.

### Test Coverage
- 246 tests total (`tests/test_community_stock.py`: weights cover every home, totals scale with households, old oil area worse than new gas area, unmodelled fuels reported, missing mixes fall back, typical home size/type, one-home estimate uses the pipeline rules; `tests/test_community_assess.py` (geocoder, census and pipeline mocked): census estimate per located home, image analysis for chosen homes with failures kept per home, rerun reuses saved results, sample spread over Small Areas, summaries, address list from CSV or plain text; `tests/test_community_page.py`: map zoom shows every home, one map trace per band, band chart order, ranking CSV; `tests/test_calculator.py` presets and overrides: presets by era/type/heating, empty overrides change nothing, each override moves the demand the right way, retrofit on overridden U, efficiency dropped with a new system, energy balance closes, old results load; `tests/test_calculation_inputs.py`: origins from pipeline sources, manual input, overrides, formulas with the home's numbers; `tests/test_energy_diagram.py`: every flow labelled in kWh/yr, balance line, no heating needed; `tests/test_official_compare.py`: band distance, score signs, inputs compared only when recorded, certificate values put in (area scaled, plan shape and shared side kept), leave-one-out baseline and its tie rule, summaries, run agreement; `tests/test_add_official_home.py`: register text parsed, row saved and passes the checker, re-ask on bad answers, duplicates refused, band/kWh mismatch not saved, ids continue; `tests/test_official_sample.py`: sample CSV read and normalised, band/kWh mismatch, unusable rows dropped, duplicates, empty template; `tests/test_llm_providers.py`: provider choice and fallback, Mistral request shape and part order, chunked replies, retry on 429, key missing, provider passed through the pipeline and recorded; `tests/test_similar_house.py`: similar house parsed, image number → heading index when a duplicate view was dropped, invalid replies ignored, classification passed as context and its prompt untouched, `uses_similar_house`, pipeline finds the image, `facade_hint` prompt, orange boxes drawn over cyan; `tests/test_census.py`: era prior + choose_epoch rules, choose_heating rules (gas threshold, observed clue, non-gas fuel, heat pump, urban fallback), choose_unit_count (room-mix count whatever Claude said, pairs kept, wrong split undone, Claude kept when seen/detached/no rooms, frontage limit, storeys), lookup with mocked service, data files, `_build_input` + overrides; `tests/test_detect_windows.py`: neighbour windows outside the facade dropped, blurred target, legacy list reply; `tests/test_streetview_fetch.py`: outdoor panorama + pano pinning, fallback, duplicate views dropped, stale files cleared)
- `tests/test_satellite_analysis.py` covers:
  - `analyze_satellite()` — uploaded-image path (metres, clamping), GPS path (block corners split
    along the longer edge into the slice nearest the centre; missing corners → confidence 0;
    census room mix sets the home count only when `units_visible` is false; a block outline at
    the image edge keeps Claude's count, is capped at 0.3 and loses to OpenCV;
    `_reaches_image_edge()` on, past and near the border and for a whole block),
    malformed JSON, Mapbox scale = half the Google scale (mocked async Claude API)
  - `analyze_streetview()` — single image backward-compat, multi-image (4 views sent), malformed JSON defaults,
    `location` in the prompt only when given, `claude_temperature` sent only when set
  - `_reconcile_footprints()` — agreement boost, disagreement, Claude fallback, both fail, low confidence
  - `_build_input()` — high/low confidence, unreasonable area, clamping, no footprint, overrides,
    high-confidence street analysis used, low-confidence street analysis ignored

## Repository Layout (reorganised 2026-11-12)

The layout table is in `README.md`. What moved:

- Assessor spreadsheets: `tests/Daft/` → `data/validation/daft/` (evaluation data, not tests;
  the official-BER sample for the paper goes next to it).
- Source material (Excel tool with guide and sources, HWB guide, DEAP manual): `docs/` →
  `docs/reference/`.
- Talks and demos: root, `docs/` and `paper/` → `presentations/environ_2026/` and
  `presentations/circus_demo_2026_03/`. `paper/` now holds only `main.tex` and
  `references.bib`.
- Removed: `excel_extraction.txt` (13 MB cell dump of the Excel tool), `data/constants.json`
  and `data/ber_rating_scale.json` (unused since the MVP; the values live in
  `ber_engine/constants.py` and `rating.py`), `GEMINI.md` (stale agent notes),
  `verify_notes.py`, `Redon/`. `.claude/settings.local.json` is no longer tracked.
- Unchanged, because Streamlit Cloud depends on them: `app/streamlit_app.py`,
  `requirements.txt`, `packages.txt`, `.streamlit/config.toml`.

## Deployment (Streamlit Community Cloud, invite-only)

GitHub Pages cannot host the tool (static pages only; the app needs a Python server and API
keys). It is deployed on Streamlit Community Cloud from the private repo.

- **Source:** repo `Nasheor/BERAutomation`, branch `daft-validation`, main file
  `app/streamlit_app.py`. Pushing to the branch redeploys the app. The first build ran on
  Python 3.14 (the cloud default when 3.12 is not chosen under *Advanced settings*) and failed
  because `Pillow<11` has no 3.14 build; the pin is now `<13`, so 3.12 to 3.14 all install.
- **URL:** https://berautomation-iw3xyejivxips5ebhzzm5c.streamlit.app/ (live since 2026-11-12;
  a Full Pipeline run of `T12 K7AC` completed).
- **Access:** the repo is private, so the app is private; only email addresses invited under
  the app's *Share* menu can open it. The free tier allows one private app. Every Full Pipeline
  run spends Anthropic, Google and Mapbox credit on the keys below.
- **Keys:** `GOOGLE_MAPS_API_KEY`, `MAPBOX_ACCESS_TOKEN`, `ANTHROPIC_API_KEY` are pasted into the
  app's *Secrets* as TOML. At start-up `app/streamlit_app.py` copies them from `st.secrets` into the
  environment and clears the cached `Settings` (no `.env` on the server). Without this the
  first live run failed with "GOOGLE_MAPS_API_KEY not configured". `.streamlit/secrets.toml` is the local,
  git-ignored copy to paste from; regenerate it from `.env` if a key changes, and update the
  app's Secrets too.
- **Build inputs:** `requirements.txt`; `packages.txt` (apt) holds only `libglib2.0-0`.
  `libgl1-mesa-glx` was removed: it no longer exists on current Debian images and
  `opencv-python-headless` does not need it. If a build reports a missing GL library, add
  `libgl1`.
- **Imports:** the app adds the repo root to `sys.path`, so `ber_automation` is always the copy
  next to `app/`, whatever folder Streamlit starts in. (An older copy of the project exists at
  `F:\Circus\BERAutomation`; starting Streamlit there used its old `.env` key and June code.)
- **Server files:** images and overlays are written to `output/` on the app's disk, which is
  temporary and shared by everyone using the app.
- **App modules:** since 2026-11-23 the app also imports `app.energy_diagram` and `app.community_page`
  (Community mode, live since 2026-11-24); this works because the repo root is put on
  `sys.path` first (see *Imports*), with `app/` as a namespace package (no `__init__.py`).
- **What is live (2026-11-24):** everything. `daft-validation` was fast-forwarded to `09c7fc6`
  and pushed on 2026-11-24: the supervisor-feedback changes (*Calculation Inputs, Presets and the
  Energy Diagram*), the official-BER work (validation script, clipboard mode, home 21, the
  21-home run notes) and **Community mode** (*Community Assessment*). Image analysis in Community
  mode spends API credit on the app's keys (about a minute per home, at most 25 homes at a time).
- **Branches (2026-11-24):** `main`, `daft-validation` and `community` are all at `09c7fc6` plus
  this docs commit, all pushed. `main` was fast-forwarded the same day (it had been at `7884c0c`,
  29 commits behind); there is no `master` branch. `official-validation` (`9c9fa30`),
  `app-feedback` (`f727e74`), `organise-codebase` and `similar-house-evidence` are all contained
  in `main` and need no further merging.
  New work goes on a branch and is merged into `daft-validation` only when the user says so,
  because every push there redeploys the supervisor's app.

## Community Assessment (`ber_automation/community/`, Phase 1, 2026-11-24)

CIRCUS works with communities; the tool rated one address at a time. Plan (approved
2026-11-24): Phase 1 core (this), Phase 2 programme scenarios and energy schemes (grouped
retrofit, heat density, roof PV with a panel cap), Phase 3 area-level validation against SEAI's
public BER data. Input is an address list; Ireland first (census).

- **Census stock model** (`stock.py`): per Small Area, every era × fuel × room-count
  combination is a typical home rated by the calculator, weighted by the product of the census
  shares and scaled by the households. Assumptions: the three are independent (the census does
  not cross them); semi-detached in CSO urban areas, detached in rural; rooms × 20 m²,
  one storey under 70 m², footprint 1.25 : 1; coal, peat, LPG, other and none are not modelled
  and those homes are assumed like the rest (`modelled_share`, about 80 % in rural areas);
  electricity after 2010 = heat pump. About 2–3 ms per Small Area (all 18,919 in about a
  minute). `census_home_estimate(area)` is the most likely single home: era and heating from
  `choose_epoch` / `choose_heating` with no images, the commonest room count.
- **Dwelling type** comes from the urban flag for now. The census "type of accommodation" table
  is not in `data/` yet: adding it to `build_census_data.py` needs a download from the CSO API
  (to confirm with the user, with the table code).
- `assess.py`: `assess_community(entries, name, analyse="none"|"all"|N|ids)`: geocode and census
  lookup for every address (5 at a time), census estimate, then the full pipeline for the chosen
  homes (3 at a time, one run each; a sample of N is spread round-robin over the Small Areas).
  Saved to `output/communities/<name>/community.json` after each home; a rerun reuses located
  homes and image results, so it resumes without paying twice. One home failing is recorded in
  its `errors` and does not stop the rest. `summary.py`: ranking (worst primary kWh/m² first),
  band counts, totals for the listed homes and for their whole Small Areas, census-versus-image
  agreement. `addresses.py` reads a CSV (address / eircode / postcode column, optional id) or a
  plain list.
- `python scripts/assess_community.py <csv> --name X [--analyse none|all|N|ids] [--provider]`.
- **App:** sidebar mode "Community" (`app/community_page.py`): upload or paste a list → "Quick
  census estimate"; open a saved community; tiles (homes rated, heat demand, primary energy, CO2,
  average), the Small Areas' census totals, band charts (listed homes and all homes in the areas),
  a map coloured by band (Plotly `Scattermap`, MapLibre, no token; zoom fitted to the homes), the
  ranked table with CSV and JSON downloads, problems, "Analyse with images" (sample / chosen / all,
  capped at 25 homes in the app; more through the CLI) and one home in the single-home view.
  Checked with `AppTest`; the map tiles could not be rendered headlessly (zoom unit-tested), and
  the user confirmed the map works in the local app on 2026-11-24.
- **First run, census only, the 21 official-sample homes (2026-11-24):** all located, 21 Small
  Areas with 2,226 households; listed homes 220 MWh/yr heat demand, 321 MWh/yr primary, 65 t
  CO2/yr; the areas 20,203 MWh/yr heat demand, 6,039 t CO2/yr. Against the certificates: band
  exact 4/21, within one 7/21, mean offset −1.6 bands, median kWh error −33 %; the community's
  primary-energy total is 40 % under the certificates' (321 versus 538 MWh/yr): the same
  older-homes gap as the pipeline (see the 21-home run above).

## Planned Work

- **Mistral as a second, user-selectable vision model, and the paper** (AI estimate versus
  official BER): full plan in `docs/plans/mistral_provider_and_paper_plan.md` (saved
  2026-11-12). **Part A, the provider switch, is implemented** (see *Vision Model
  Providers*) but not yet run against Mistral. It covers the provider switch (`providers.py`, `_complete()`
  in `claude_analyzer.py`, `--provider` flags, app selector), the paper's research questions
  and study design (official BERs from listings + SEAI register, about 250 homes, census-only
  baseline, HWB-versus-DEAP error separated from perception error), and target venues with
  dates (SBE27 Delft abstract due 18 Dec 2026).
- The official-BER sample format and its checker exist (see *Official-BER Sample for the
  Paper*); the sample is being collected: 21 of about 250 homes on 2026-11-23, none in
  bands E to G yet.
- **Session 2026-11-23/24 (summary):** home 21 added with clipboard mode (parsers work on
  real daft.ie and register pages); first full official-BER run on 21 homes (see *Official-BER
  Sample*: most of the error is the calculator rating older homes better than DEAP); the
  supervisor's comments on the app done and live (see *Calculation Inputs, Presets and the
  Energy Diagram*); community assessment Phase 1 built on branch `community` (see *Community
  Assessment*).
- **Supervisor's comments on the app (2026-11-23):** window U-values and their source, preset
  values shown for the image data, what internal gains are, HWB units (HWB × floor area), a
  house-style chart with notes on each metric: **done**. "The number of solar panels for each
  house must be capped": **open**, the app has no PV; the user is asking the supervisor. Likely
  meaning: rooftop PV capped by usable roof area, planned in community Phase 2.
- **Resume here (2026-11-24):** community Phase 1 is merged into `main` and `daft-validation`
  and live; the user ran it locally first and the map works. Decisions pending from the user: (1) may the CSO Census 2022
  "type of accommodation" Small Area table be downloaded (table code to confirm; it would
  replace the urban/rural dwelling-type guess in the stock model); (2) a small live image run
  (about 5 homes, about 5 minutes of API use) to check census-versus-image and resuming;
  (3) go-ahead for Phase 2 (programme scenarios, grouped retrofit, heat density, rooftop PV with
  a panel cap) and Phase 3 (SEAI public BER data at area level; the user downloads it).
  Plan file: `C:/Users/nagar/.claude/plans/abundant-shimmying-rain-of-7975d1e2-787d-4a3c-8b09-e7bc02f85aad.md`.
- Next for the paper: a fairer baseline than the leave-one-out commonest band (degenerate on
  the 21 homes: A3 and C3 tie), such as the median kWh or the census-only estimate, which now
  exists (`census_home_estimate`, 4/21 exact); an images-only switch; why the calculator rates
  pre-2010 homes so much better than DEAP (HWB-versus-DEAP gap); keep collecting homes,
  especially bands E to G; a valid Mistral key and the two-model comparison.
- **Checking the app without a browser** (the Claude in Chrome extension was not connected on
  2026-11-23/24): `streamlit.testing.v1.AppTest.from_file("app/streamlit_app.py")` drives the
  real script (switch `at.sidebar.radio[0]` to a mode, set inputs, click buttons, read
  `at.metric` / `at.markdown` / `at.dataframe`); a ready-made `PipelineResult` or a saved
  community put into `at.session_state` avoids API calls. Plotly figures were checked as images
  with `fig.write_html(...)` and headless Edge (`msedge --headless=new --screenshot=...
  --virtual-time-budget=...`; add `--use-angle=swiftshader --enable-unsafe-swiftshader` for
  WebGL). MapLibre map tiles did not render reliably that way, so the map zoom is unit-tested.
  The driver scripts were kept in `output/dev/` (not in git).
