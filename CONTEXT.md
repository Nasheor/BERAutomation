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

**Primary: Claude Vision (`ber_automation/vision/claude_analyzer.py::analyze_satellite()`)**
- Sends the satellite image to Claude with a structured prompt (`SATELLITE_ANALYSIS_PROMPT`)
- Prompt includes computed scale (meters-per-pixel at given lat/zoom), ground coverage, and typical Irish house size ranges
- Instructs Claude to identify the **building roof** and ignore gardens, driveways, fences, trees
- Returns `FootprintResult` with `source="claude_vision"`
- Validation: dimensions clamped to [4m, 25m], area sanity check [20, 500] m2

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

### Test Coverage
- 53 tests total (34 original + 14 vision + 3 streetview multi-image + 2 confidence gating)
- `tests/test_satellite_analysis.py` covers:
  - `analyze_satellite()` — valid response, malformed JSON, out-of-bounds clamping (mocked async Claude API)
  - `analyze_streetview()` — single image backward-compat, multi-image (4 views sent), malformed JSON defaults
  - `_reconcile_footprints()` — agreement boost, disagreement, Claude fallback, both fail, low confidence
  - `_build_input()` — high/low confidence, unreasonable area, clamping, no footprint, overrides,
    high-confidence street analysis used, low-confidence street analysis ignored
