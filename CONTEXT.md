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
  detection. Cause of the app screenshot `images/output.png`, where Front = Right and Rear =
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

## Daft Validation (`scripts/validate_daft.py`)

`tests/Daft/1–5.xlsx` are copies of the Kaiser Excel tool filled in by a human assessor
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

### Test Coverage
- 121 tests total (`tests/test_census.py`: era prior + choose_epoch rules, choose_heating rules (gas threshold, observed clue, non-gas fuel, heat pump, urban fallback), choose_unit_count (room-mix count whatever Claude said, pairs kept, wrong split undone, Claude kept when seen/detached/no rooms, frontage limit, storeys), lookup with mocked service, data files, `_build_input` + overrides; `tests/test_detect_windows.py`: neighbour windows outside the facade dropped, blurred target, legacy list reply; `tests/test_streetview_fetch.py`: outdoor panorama + pano pinning, fallback, duplicate views dropped, stale files cleared)
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

## Deployment (Streamlit Community Cloud, invite-only)

GitHub Pages cannot host the tool (static pages only; the app needs a Python server and API
keys). It is deployed on Streamlit Community Cloud from the private repo.

- **Source:** repo `Nasheor/BERAutomation`, branch `daft-validation`, main file
  `app/streamlit_app.py`, Python 3.12. Pushing to the branch redeploys the app.
- **URL:** set when the app is created (record it here).
- **Access:** the repo is private, so the app is private; only email addresses invited under
  the app's *Share* menu can open it. The free tier allows one private app. Every Full Pipeline
  run spends Anthropic, Google and Mapbox credit on the keys below.
- **Keys:** `GOOGLE_MAPS_API_KEY`, `MAPBOX_ACCESS_TOKEN`, `ANTHROPIC_API_KEY` are pasted into the
  app's *Secrets* as TOML. Streamlit Cloud exposes them as environment variables, which
  `Settings` reads (no `.env` on the server). `.streamlit/secrets.toml` is the local,
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

## Planned Work

- **Mistral as a second, user-selectable vision model, and the paper** (AI estimate versus
  official BER): full plan in `docs/plans/mistral_provider_and_paper_plan.md` (saved
  2026-11-12, not implemented). It covers the provider switch (`providers.py`, `_complete()`
  in `claude_analyzer.py`, `--provider` flags, app selector), the paper's research questions
  and study design (official BERs from listings + SEAI register, about 250 homes, census-only
  baseline, HWB-versus-DEAP error separated from perception error), and target venues with
  dates (SBE27 Delft abstract due 18 Dec 2026).
- Waiting on supervisor feedback on the deployed tool before starting.
