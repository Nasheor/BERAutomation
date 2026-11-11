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
  - A reply without 4 valid corners → confidence 0 (OpenCV fallback), never a guess.
- **Uploaded-image path (zoom=None): `SATELLITE_ANALYSIS_PROMPT`** — scale unknown, so Claude
  estimates metres from cars, doors, bins etc. and is told to measure one unit.
- Returns `FootprintResult` with `source="claude_vision"`
- Validation: dimensions clamped to [4m, 25m], area sanity check [20, 500] m2
- Known limit: a long block that runs off both ends of the image with no chimneys to count
  (T23 AX03) → Claude gives confidence ≤ 0.3 and OpenCV is used. A zoom-19 image would help.

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
- **Backward-compatible**: accepts a single path (str/Path) or a list of paths
- **Async client**: uses `anthropic.AsyncAnthropic` (not the synchronous client) to avoid
  blocking the event loop
- **Dual prompts**: multi-image prompt instructs cross-referencing; single-image prompt
  preserved for fallback/testing
- Returns: construction epoch, building type, storeys, heating system guess, confidence
- Used in Phase 4, feeds into `_build_input()` for non-geometric parameters

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
- Still open: epoch read one band newer for the 1980s houses; RK10 read as 2 storeys
  (assessor: 1) and oil; RK10 type unstable across runs.

### Test Coverage
- 80 tests total
- `tests/test_satellite_analysis.py` covers:
  - `analyze_satellite()` — uploaded-image path (metres, clamping), GPS path (block corners split
    along the longer edge into the slice nearest the centre; missing corners → confidence 0),
    malformed JSON, Mapbox scale = half the Google scale (mocked async Claude API)
  - `analyze_streetview()` — single image backward-compat, multi-image (4 views sent), malformed JSON defaults,
    `location` in the prompt only when given, `claude_temperature` sent only when set
  - `_reconcile_footprints()` — agreement boost, disagreement, Claude fallback, both fail, low confidence
  - `_build_input()` — high/low confidence, unreasonable area, clamping, no footprint, overrides,
    high-confidence street analysis used, low-confidence street analysis ignored
