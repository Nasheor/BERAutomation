# BER Automation Pipeline - Technical Documentation

**Version:** 1.0
**Date:** February 2026
**Authors:** Avinash Nagarajan

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture](#2-architecture)
3. [Module Reference](#3-module-reference)
4. [Calculation Logic - The HWB Method](#4-calculation-logic---the-hwb-method)
5. [Data Flow & Pipeline](#5-data-flow--pipeline)
6. [Constants & Lookup Tables](#6-constants--lookup-tables)
7. [Vision & Geospatial Processing](#7-vision--geospatial-processing)
8. [Streamlit User Interface](#8-streamlit-user-interface)
9. [Testing Strategy](#9-testing-strategy)
10. [Drawbacks & Limitations](#10-drawbacks--limitations)
11. [Areas for Improvement](#11-areas-for-improvement)
12. [API Key Setup Guide](#12-api-key-setup-guide)
13. [Deployment](#13-deployment)

---

## 1. Project Overview

### What It Does

BER Automation estimates an Irish **Building Energy Rating (BER)** from just an **Eircode** (Irish postcode). It automates a manual workflow that previously required:

- Looking up an address on Google Maps
- Measuring building dimensions with the Maps "Measure distance" tool
- Viewing the building on Google Street View
- Visually estimating construction era, building type, storeys, and heating system
- Manually entering all parameters into an Excel spreadsheet

This project replaces that entire workflow with an automated pipeline: geocode the Eircode, fetch satellite and Street View imagery, extract building dimensions via computer vision, classify the building via AI, and compute the energy rating.

### Calculation Method

The energy calculation uses the **Austrian HWB (Heizwaermebedarf) annual balance method**, as described in the "Leitfaden fuer die Berechnung des Heizwaermebedarfs" by Die Umweltberatung (Vienna, 2019). This is **NOT** the Irish DEAP method. The HWB method provides a simpler steady-state annual balance that is well-suited to rapid screening-level assessments.

The primary source of truth is the Excel tool **"Building Assessment using Google Maps and Google Street View"** by Benjamin Kaiser (MTU, Jan 2025), from which every formula, constant, and lookup table was extracted and ported.

### Technology Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.13 |
| Data models | Pydantic v2 |
| Configuration | pydantic-settings + .env |
| HTTP client | httpx (async) |
| Computer vision | OpenCV (headless, no GPU) |
| AI vision | Anthropic Claude API |
| Geocoding & imagery | Google Maps APIs |
| Web UI | Streamlit |
| Testing | pytest + pytest-asyncio |

---

## 2. Architecture

### 2.1 High-Level Architecture

```
See: architecture_high_level.puml
```

The system follows a **pipeline architecture** with five sequential phases, each producing intermediate results that feed the next phase. Graceful degradation means any phase can fail without crashing the pipeline -- defaults fill in for missing data.

### 2.2 PlantUML Diagrams

#### System Context Diagram

**File: `docs/diagrams/context.puml`**

```plantuml
@startuml context
!theme plain

title BER Automation - System Context

actor "User" as user
rectangle "BER Automation System" as system {
}
cloud "Google Maps Platform" as google {
  [Geocoding API]
  [Static Maps API]
  [Street View API]
}
cloud "Anthropic" as anthropic {
  [Claude Vision API]
}

user --> system : Eircode / Manual Input
system --> google : Geocode, Fetch Images
system --> anthropic : Analyse Street View
system --> user : BER Rating + Report
@enduml
```

#### Component Architecture Diagram

**File: `docs/diagrams/components.puml`**

```plantuml
@startuml components
!theme plain

title BER Automation - Component Architecture

package "Presentation Layer" {
  [Streamlit App\napp/streamlit_app.py] as ui
  [CLI\nmain.py] as cli
}

package "Orchestration" {
  [BERPipeline\nber_automation/pipeline.py] as pipeline
}

package "Geospatial" <<Rectangle>> {
  [EircodeGeocoder\ngeospatial/geocoder.py] as geocoder
  [ImageryFetcher\ngeospatial/imagery.py] as imagery
  [Scale Calculator\ngeospatial/scale.py] as scale
}

package "Vision" <<Rectangle>> {
  [OpenCV Footprint\nvision/footprint.py] as footprint
  [Claude Analyzer\nvision/claude_analyzer.py] as claude
}

package "BER Engine" <<Rectangle>> {
  [HWBCalculator\nber_engine/calculator.py] as calculator
  [Constants\nber_engine/constants.py] as constants
  [Rating Scale\nber_engine/rating.py] as rating
}

package "Shared" <<Rectangle>> {
  [Pydantic Models\nmodels.py] as models
  [Config\nconfig.py] as config
}

' Presentation -> Orchestration
ui --> pipeline
cli --> pipeline
ui --> calculator : Manual mode\n(direct)
cli --> calculator : Manual mode\n(direct)

' Pipeline -> Modules
pipeline --> geocoder
pipeline --> imagery
pipeline --> footprint
pipeline --> claude
pipeline --> calculator

' Internal dependencies
footprint --> scale
calculator --> constants
calculator --> rating
geocoder --> config
imagery --> config
claude --> config

' Everything uses models
pipeline ..> models
calculator ..> models
geocoder ..> models
footprint ..> models
claude ..> models
@enduml
```

#### Pipeline Sequence Diagram

**File: `docs/diagrams/pipeline_sequence.puml`**

```plantuml
@startuml pipeline_sequence
!theme plain

title BER Automation - Pipeline Sequence

actor User
participant "Streamlit UI" as UI
participant "BERPipeline" as Pipeline
participant "EircodeGeocoder" as Geocoder
participant "Google Maps API" as Google
participant "ImageryFetcher" as Imagery
participant "OpenCV Footprint" as Footprint
participant "Claude Analyzer" as Claude
participant "Anthropic API" as Anthropic
participant "HWBCalculator" as Calculator

User -> UI : Enter Eircode
UI -> Pipeline : run(eircode)

== Phase 1: Geocoding ==
Pipeline -> Geocoder : geocode_eircode(eircode)
Geocoder -> Google : GET /geocode/json
Google --> Geocoder : {lat, lng, address}
Geocoder --> Pipeline : Coordinates

== Phase 2: Image Fetching (Parallel) ==
Pipeline -> Imagery : fetch_satellite_image(coords)
Pipeline -> Imagery : fetch_streetview_image(coords)
Imagery -> Google : GET /staticmap (satellite, zoom=20)
Imagery -> Google : GET /streetview (fov=90)
Google --> Imagery : satellite.png
Google --> Imagery : streetview.jpg
Imagery --> Pipeline : image paths

== Phase 3: Footprint Extraction ==
Pipeline -> Footprint : extract_footprint(satellite.png, lat, zoom)
note right of Footprint
  1. Grayscale + bilateral filter
  2. CLAHE enhancement
  3. Canny edges + dilate
  4. Score contours
  5. Bounding rect -> meters
end note
Footprint --> Pipeline : FootprintResult {length, width, area, confidence}

== Phase 4: AI Building Analysis ==
Pipeline -> Claude : analyze_streetview(streetview.jpg)
Claude -> Anthropic : POST /messages (image + prompt)
Anthropic --> Claude : JSON classification
Claude --> Pipeline : StreetViewAnalysis {epoch, type, storeys, heating}

== Phase 5: BER Calculation ==
Pipeline -> Calculator : calculate_ber(BuildingInput)
note right of Calculator
  HWB annual balance:
  Q_heating = Q_t + Q_v - Q_i - Q_s
  Final Energy = Q_h / efficiency
  BER = f(primary_energy / m2)
end note
Calculator --> Pipeline : BERResult {band, kWh/m2, CO2}

Pipeline --> UI : PipelineResult
UI --> User : BER Rating + Visualizations
@enduml
```

#### Calculation Flow Diagram

**File: `docs/diagrams/calculation_flow.puml`**

```plantuml
@startuml calculation_flow
!theme plain

title HWB Calculation Flow (Excel-Faithful)

start

:Input: length, width, storeys, storey_height,
building_type, construction_epoch, country,
heating_system;

partition "Geometry" {
  :gross_area = length x width x storeys;
  :net_area = gross_area x 0.8;
  :envelope = ((L+W) x 2) x storeys x height;
  :roof_area = floor_area = L x W;
  :party_walls = f(building_type);
  :window_total = envelope x fraction
  (0.15 detached / 0.14 semi-d / 0.13 terraced);
  :ext_walls = envelope - windows - party_walls;
  :volume = net_area x (height - 0.35) x storeys;
}

partition "Transmission Loss (Q_t)" {
  :L_e = U_win x A_win
  + U_roof x A_roof
  + U_floor x A_floor x **0.7**
  + U_wall x A_ext_wall;
  :U_mean = L_e / total_area;
  :L_psi = max(0.2 x (0.75 - U_mean) x L_e, 0);
  :L_t = L_e + L_psi;
  :Q_t = **0.024** x L_t x HDD;
}

partition "Ventilation Loss (Q_v)" {
  :L_v = 0.34 x **0.4** x volume;
  :Q_v = 0.024 x L_v x HDD;
}

partition "Internal Gains (Q_i)" {
  :Q_i = 0.024 x **3.75** x net_area x heating_days;
}

partition "Solar Gains (Q_s)" {
  :g_eff = g_value x 0.9 x 0.98;
  :Q_s = (Irr_N x A_N + Irr_E x A_E
  + Irr_S x A_S + Irr_W x A_W)
  x **0.75** x g_eff;
}

partition "Results" {
  :Q_heating = max(0, Q_t + Q_v - Q_i - Q_s);
  :HWB = Q_heating / gross_area;
  :Q_hotwater = residents x 40 x 365 x (4.2/3600) x 45;
  :final_energy = Q_heating/eff + Q_hotwater/eff_hw;
  :primary_energy = final_energy x PEF;
  :BER band = lookup(primary_energy / m2);
}

stop
@enduml
```

#### Data Model Class Diagram

**File: `docs/diagrams/data_models.puml`**

```plantuml
@startuml data_models
!theme plain

title BER Automation - Data Models

enum BuildingType {
  DETACHED
  SEMI_D_LENGTH
  SEMI_D_WIDTH
  TERRACED_LENGTH
  TERRACED_WIDTH
}

enum ConstructionEpoch {
  BEFORE_1980
  EPOCH_1980_1990
  EPOCH_1990_2000
  EPOCH_2000_2010
  AFTER_2010
}

enum HeatingSystem {
  OIL_BOILER
  GAS_BOILER
  BIOMASS
  ELECTRIC_DIRECT
  HEAT_PUMP_AIR
  HEAT_PUMP_GROUND
  HEAT_PUMP_WATER
  DISTRICT_HEATING
}

enum Country {
  IRELAND
  FRANCE
  GERMANY
  BELGIUM
  NETHERLANDS
  AUSTRIA
}

class BuildingInput {
  +length: float
  +width: float
  +heated_storeys: int
  +storey_height: float
  +building_type: BuildingType
  +construction_epoch: ConstructionEpoch
  +country: Country
  +heating_system: HeatingSystem
  +hot_water_electric_separate: bool
  +residents: Optional[float]
  +window_door_areas: Optional[WindowDoorAreas]
  --
  +floor_area_per_storey: float
  +total_heated_area: float
  +effective_residents: float
}

class RetrofitInput {
  +wall_insulation_cm: float = 12
  +roof_insulation_cm: float = 20
  +window_u_value: float = 1.0
  +heating_system_after: Optional[HeatingSystem]
}

class HWBResult {
  +floor_area: float
  +heated_volume: float
  +transmission_heat_loss: float
  +ventilation_heat_loss: float
  +solar_gains: float
  +internal_gains: float
  +heating_demand_kwh: float
  +hwb: float
  +final_energy_kwh: float
  +hot_water_kwh: float
  +co2_kg: float
}

class BERResult {
  +ber_band: str
  +kwh_per_m2: float
  +color_hex: str
  +hwb_result: HWBResult
  +building_input: BuildingInput
  +retrofit_ber_band: Optional[str]
  +retrofit_hwb_result: Optional[HWBResult]
}

class PipelineResult {
  +eircode: str
  +coordinates: Optional[Coordinates]
  +satellite_image_path: Optional[str]
  +streetview_image_path: Optional[str]
  +footprint: Optional[FootprintResult]
  +street_analysis: Optional[StreetViewAnalysis]
  +ber_result: Optional[BERResult]
  +errors: list[str]
}

BuildingInput --> BuildingType
BuildingInput --> ConstructionEpoch
BuildingInput --> HeatingSystem
BuildingInput --> Country
BERResult *-- HWBResult
BERResult *-- BuildingInput
PipelineResult *-- BERResult
@enduml
```

---

## 3. Module Reference

### 3.1 `ber_automation/models.py`

Central Pydantic models shared across all modules. Contains:

- **4 enums**: `BuildingType` (5 variants), `ConstructionEpoch` (5 epochs), `HeatingSystem` (8 types), `Country` (6 countries)
- **9 data models**: `Coordinates`, `WindowDoorAreas`, `BuildingInput`, `RetrofitInput`, `FootprintResult`, `StreetViewAnalysis`, `HWBResult`, `BERResult`, `PipelineResult`

All models use Pydantic v2 with field validation (e.g., `length > 0`, `confidence` in [0,1]).

### 3.2 `ber_automation/config.py`

Uses `pydantic-settings` to load configuration from environment variables or a `.env` file. Key settings:

| Setting | Default | Description |
|---------|---------|-------------|
| `GOOGLE_MAPS_API_KEY` | (required) | Google Maps API key |
| `ANTHROPIC_API_KEY` | (required) | Anthropic Claude API key |
| `satellite_zoom` | 20 | Satellite image zoom level |
| `streetview_fov` | 90 | Street View field of view |
| `claude_model` | claude-sonnet-4-5 | Claude model for vision analysis |

### 3.3 `ber_automation/ber_engine/constants.py`

All lookup tables ported directly from the Excel tool's Data sheet and Energy+CO2 Calculations sheet. Each constant has a comment referencing its exact Excel cell. Contains 19 named constants/tables.

### 3.4 `ber_automation/ber_engine/calculator.py`

The `HWBCalculator` class with three public methods:

- `calculate(building)` -- core HWB calculation
- `calculate_ber(building, retrofit?)` -- full BER with optional retrofit
- `calculate_with_retrofit_uvalues(building, retrofit)` -- U-value overlay for retrofit

### 3.5 `ber_automation/ber_engine/rating.py`

Single function `get_ber_band(kwh_per_m2)` mapping energy consumption to bands A1 through G.

### 3.6 `ber_automation/geospatial/geocoder.py`

- `validate_eircode(eircode)`: regex validation and normalisation
- `geocode_eircode(eircode)`: async Google Geocoding API call

### 3.7 `ber_automation/geospatial/imagery.py`

- `fetch_satellite_image(coords, output_path)`: Google Static Maps API (maptype=satellite)
- `fetch_streetview_image(coords, output_path)`: Google Street View Static API with availability check

### 3.8 `ber_automation/geospatial/scale.py`

Web Mercator pixel-to-meter conversion:
```
resolution = Earth_circumference * cos(lat) / 2^(zoom+8)
```

### 3.9 `ber_automation/vision/footprint.py`

OpenCV pipeline: Grayscale -> Bilateral Filter -> CLAHE -> Canny -> Dilate -> Contour Scoring -> Bounding Rectangle -> Meters

### 3.10 `ber_automation/vision/claude_analyzer.py`

Sends Street View image to Claude with a structured prompt requesting JSON output for: construction_epoch, building_type, estimated_storeys, heating_system_guess, adjacent_side, confidence, reasoning.

### 3.11 `ber_automation/pipeline.py`

`BERPipeline.run(eircode)` orchestrates all 5 phases with graceful degradation.

---

## 4. Calculation Logic - The HWB Method

### 4.1 Overview

The HWB (Heizwaermebedarf = heating energy demand) is a **steady-state annual energy balance**:

```
Q_heating = Heat Losses - Usable Gains
```

Where:
- **Heat Losses** = Transmission losses through the building fabric + Ventilation losses through air exchange
- **Usable Gains** = Solar energy through windows + Internal heat from occupants/appliances

If gains exceed losses, the building requires zero heating (Q_heating = 0).

### 4.2 Step-by-Step Calculation

#### Step 1: Geometry

| Quantity | Formula | Excel Cell |
|----------|---------|------------|
| Gross floor area | `length x width x storeys` | C2 |
| Net floor area | `gross x 0.8` | D2 |
| Envelope area | `((L+W) x 2) x storeys x height` | E2 |
| Roof area | `L x W` (single storey footprint) | K2 |
| Floor area | `L x W` (ground contact) | L2 |
| Party walls | varies by building type (see below) | O2 |
| Window/door area | `envelope x fraction` | F2 via J2 |
| External walls | `envelope - windows - party_walls` | N2 |
| Volume | `net_area x (height - 0.35) x storeys` | P2 |

**Party wall calculation (O2):**
- Detached: 0
- Semi-D (length adj): `length x storeys x height`
- Semi-D (width adj): `width x storeys x height`
- Terraced (length adj): `length x storeys x height x 2`
- Terraced (width adj): `width x storeys x height x 2`

**Window fraction (J2):**
- Detached: 15% of envelope
- Semi-detached: 14% of envelope
- Terraced: 13% of envelope

Windows are distributed equally across 4 orientations (25% each to N/E/S/W).

#### Step 2: Transmission Heat Loss

The transmission heat loss coefficient L_t (W/K) represents how many watts the building loses per degree Kelvin of temperature difference.

```
L_e = U_win x A_win x f_win
    + U_roof x A_roof x f_roof
    + U_floor x A_floor x f_floor
    + U_wall x A_extwall x f_wall
```

Where `f` factors are:
- f_win = 1.0 (full exposure)
- f_roof = 1.0 (full exposure)
- f_floor = **0.7** (ground contact reduces loss)
- f_wall = 1.0 (full exposure)

**Thermal bridge correction:**
```
U_mean = L_e / (A_win + A_roof + A_floor + A_extwall)
L_psi = max(0.2 x (0.75 - U_mean) x L_e, 0)
L_t = L_e + L_psi
```

This adds a thermal bridge supplement for poorly-insulated buildings (U_mean < 0.75). Well-insulated buildings (U_mean > 0.75) get L_psi = 0.

**Annual transmission loss (kWh):**
```
Q_t = 0.024 x L_t x HDD
```
Where 0.024 = 24 hours / 1000 (converts W-Kd to kWh).

#### Step 3: Ventilation Heat Loss

```
L_v = 0.34 x 0.4 x Volume
Q_v = 0.024 x L_v x HDD
```

- **0.34**: volumetric heat capacity of air (Wh/m3K)
- **0.4**: air changes per hour (n50 infiltration rate)

#### Step 4: Internal Gains

```
Q_i = 0.024 x 3.75 x net_area x heating_days
```

- **3.75 W/m2**: internal gain rate from occupants, lighting, appliances (applied to NET area, not gross)
- **heating_days**: days per year with heating demand (219 for Ireland)

#### Step 5: Solar Gains

```
g_eff = g_value x 0.9 x 0.98
Q_s = (Irr_N x A_N + Irr_E x A_E + Irr_S x A_S + Irr_W x A_W) x 0.75 x g_eff
```

- **g_value**: solar energy transmittance of glazing (varies by epoch: 0.81 for pre-1980 single glazing down to 0.465 for post-2010 triple glazing)
- **0.9**: frame factor (90% of window is glazing)
- **0.98**: dirt correction factor
- **0.75**: shading factor F_s (default obstruction from surroundings)
- **Irr_N/E/S/W**: solar irradiance by orientation during heating season (kWh/m2, from PHPP data)

#### Step 6: Heating Demand

```
Q_heating = max(0, Q_t + Q_v - Q_i - Q_s)
HWB = Q_heating / gross_area   [kWh/m2/year]
```

**Important:** The Excel uses NO utilisation factor (eta) for gains. This differs from EN 13790 / ISO 52016 which apply an eta factor to prevent over-counting gains. The HWB Leitfaden method uses a simpler direct subtraction.

#### Step 7: Hot Water

```
Q_hotwater = residents x 40 x 365 x (4.2/3600) x 45
```

- **40**: litres per person per day
- **365**: days per year
- **4.2/3600**: specific heat of water in kWh/(kg.K) = 0.001167
- **45**: temperature rise in Kelvin (from ~10C mains to ~55C delivery)

This gives approximately **765 kWh/person/year**.

Default residents = gross_area / 52 m2/person.

#### Step 8: Final Energy & CO2

```
final_energy_heating = Q_heating / system_efficiency
final_energy_hotwater = Q_hotwater / hotwater_efficiency
total_final = final_energy_heating + final_energy_hotwater
```

For boilers (efficiency < 1): final > useful (losses occur).
For heat pumps (SCOP > 1): final < useful (free environmental energy).

```
primary_energy = total_final x Primary_Energy_Factor
CO2 = total_final x CO2_factor
BER_band = lookup(primary_energy / gross_area)
```

#### Step 9: Retrofit

Retrofit applies overlay U-values using the R-value addition method:

```
R_new = R_old + (thickness_cm / 100) / conductivity
U_new = 1 / R_new
```

Where conductivity = 0.035 W/mK (typical insulation). For window replacement, the U-value is directly substituted.

---

## 5. Data Flow & Pipeline

### 5.1 Full Pipeline Mode

```
Eircode
  |
  v
[Geocoder] --> Coordinates (lat, lng)
  |
  v (parallel)
[Satellite Image Fetch]    [Street View Image Fetch]
  |                          |
  v                          v
[OpenCV Footprint]          [Claude Vision Analysis]
  |                          |
  v                          v
FootprintResult             StreetViewAnalysis
  {length, width}           {epoch, type, storeys, heating}
  |                          |
  +----------+---------------+
             |
             v
      [Merge into BuildingInput]
             |
             v
      [HWBCalculator.calculate_ber()]
             |
             v
         BERResult
```

### 5.2 Manual Mode

```
User Input (Streamlit form / CLI args)
  |
  v
BuildingInput (directly constructed)
  |
  v
[HWBCalculator.calculate_ber()]
  |
  v
BERResult
```

### 5.3 Graceful Degradation

Each pipeline phase catches exceptions independently:

| Phase Failure | Fallback |
|---------------|----------|
| Geocoding | Pipeline returns early with error |
| Satellite image | Footprint skipped; defaults used (10m x 8m) |
| Street View image | Claude analysis skipped; defaults used |
| Footprint extraction | Default dimensions 10m x 8m |
| Claude analysis | Default: Detached, before_1980, 2 storeys, gas |
| BER calculation | Error reported; no result |

---

## 6. Constants & Lookup Tables

### 6.1 U-Values by Epoch (W/m2K)

| Epoch | Window | Roof | Floor | Wall | Source |
|-------|--------|------|-------|------|--------|
| before 1980 | 3.00 | 0.65 | 1.35 | 1.20 | Austrian OIB (avg EFH+MFH) |
| 1980-1990 | 2.50 | 0.275 | 0.75 | 0.60 | Austrian OIB (avg 1982+1988) |
| 1990-2000 | 2.15 | 0.235 | 0.60 | 0.45 | Austrian OIB (avg 1988+1996) |
| 2000-2010 | 1.40 | 0.20 | 0.40 | 0.35 | OIB Richtlinie 6 |
| after 2010 | 1.00 | 0.20 | 0.25 | 0.22 | Improved NZEB |

### 6.2 Heating System Efficiencies

| System | Efficiency/SCOP | CO2 (kg/kWh) | Note |
|--------|-----------------|--------------|------|
| Oil boiler | 0.85 | 0.2639 | |
| Gas boiler | 0.90 | 0.194 | |
| Biomass | 0.875 | 0 | Carbon neutral |
| All Electric | 0.99 | 0.210 | Resistive heating |
| Air source HP | 3.50 (SCOP) | 0.210 | COP = 3.5 |
| Ground source HP | 4.50 (SCOP) | 0.210 | COP = 4.5 |
| Water source HP | 4.50 (SCOP) | 0.210 | COP = 4.5 |

### 6.3 BER Rating Scale

| Band | Max kWh/m2/yr | Typical Building |
|------|--------------|------------------|
| A1 | 25 | Passive house / NZEB |
| A2 | 50 | High-performance new build |
| A3 | 75 | Modern well-insulated |
| B1 | 100 | Post-2010 standard |
| B2 | 125 | 2000s build |
| B3 | 150 | Well-retrofitted older home |
| C1 | 175 | 1990s semi-d |
| C2 | 200 | Average Irish home |
| C3 | 225 | 1980s housing |
| D1 | 260 | Pre-1980 with some upgrades |
| D2 | 300 | Typical pre-1980 detached |
| E1-E2 | 340-380 | Poor insulation, old windows |
| F | 450 | Very poorly insulated |
| G | >450 | Uninsulated, single glazing |

---

## 7. Vision & Geospatial Processing

### 7.1 OpenCV Footprint Extraction Pipeline

```
Input: satellite.png (640x640, zoom=20)
  |
  v
[1] cvtColor(BGR -> GRAY)
  |
  v
[2] bilateralFilter(d=9, sigma=75)     -- edge-preserving smoothing
  |
  v
[3] CLAHE(clip=2.0, grid=8x8)          -- adaptive contrast
  |
  v
[4] Canny(30, 100)                      -- edge detection
  |
  v
[5] dilate(3x3 rect kernel, iter=2)    -- close edge gaps
  |
  v
[6] findContours(RETR_EXTERNAL)
  |
  v
[7] Score each contour:
    score = 0.3 * relative_area
          + 0.25 * solidity (area/hull_area)
          + 0.25 * centrality (1 - dist_from_center/max_dist)
          + 0.2 * rectangularity (area/bounding_rect_area)
  |
  v
[8] Best contour -> minAreaRect -> pixel dims
  |
  v
[9] pixels * meters_per_pixel(lat, zoom) -> meters
```

**meters_per_pixel formula:**
```
mpp = 40,075,016.686 * cos(lat_rad) / 2^(zoom + 8)
```

At Dublin (lat 53.35), zoom 20: mpp = 0.089 m/px.
A 640x640 image covers approximately 57m x 57m.

### 7.2 Claude Vision Analysis

The Street View image is base64-encoded and sent to Claude with a structured prompt that:

1. Describes 5 Irish construction eras with visual indicators (wall type, window type, roof, render)
2. Lists heating system visual clues (oil tank, gas meter, heat pump unit)
3. Requests JSON output with confidence and reasoning

---

## 8. Streamlit User Interface

Two modes accessible via the sidebar:

### 8.1 Full Pipeline Mode
- Eircode text input
- Shows: satellite image, street view, footprint overlay, AI analysis, BER rating

### 8.2 Manual Input Mode
- Three-column form: geometry / classification / heating
- Expandable retrofit measures section
- Before/after comparison when retrofit is enabled
- BER scale visualization with highlighted band

---

## 9. Testing Strategy

### 9.1 Test Coverage

**34 tests across 3 test files:**

| File | Tests | Scope |
|------|-------|-------|
| `test_calculator.py` | 19 | BER bands (9 parametrized), calculator logic (10) |
| `test_geocoder.py` | 11 | Eircode validation (5 valid, 6 invalid) |
| `test_pipeline.py` | 4 | End-to-end manual, all epochs/countries/heating systems |

### 9.2 Key Test Scenarios

- **Old house = high HWB**: pre-1980 detached house should have HWB > 100 kWh/m2/yr
- **New house = low HWB**: post-2010 should be significantly lower
- **Semi-D < Detached**: shared wall reduces transmission loss
- **Terraced < Semi-D**: two shared walls reduce it further
- **Heat pump < Oil boiler**: COP > 1 means lower final energy
- **Newer epoch = lower HWB**: improved U-values reduce losses
- **Retrofit improves rating**: wall + roof insulation + window + heat pump should lower primary energy
- **All enum combinations**: every epoch, country, and heating system produces a valid result

### 9.3 What's NOT Tested

- Google Maps API calls (require live API key)
- Anthropic API calls (require live API key)
- OpenCV footprint extraction (requires real satellite images)
- Streamlit UI rendering

---

## 10. Drawbacks & Limitations

### 10.1 Calculation Method

| Limitation | Impact | Severity |
|-----------|--------|----------|
| **Uses HWB, not DEAP** | Results differ from official Irish BER assessments which use the DEAP methodology. This tool provides estimates, not official ratings. | High |
| **No utilisation factor** | The Excel omits the EN 13790 gain utilisation factor (eta). This means solar and internal gains may be over-credited, especially for well-insulated buildings, leading to optimistic HWB values. | Medium |
| **Austrian U-values** | U-values are from Austrian OIB standards, not Irish building regulations. While broadly similar, specific values may differ (e.g., Irish Part L requirements). | Medium |
| **Simplified geometry** | Buildings are modelled as rectangular boxes. L-shaped, T-shaped, or irregular footprints are not handled. | Medium |
| **Single-zone model** | The entire building is one thermal zone. No distinction between heated/unheated rooms, conservatories, or extensions. | Low |
| **No cooling load** | Only heating demand is calculated. In a warming climate, cooling may become relevant for Irish buildings. | Low |
| **Volume double-counting** | The Excel formula `P2 = D2 * (H-0.35) * G2` appears to multiply by storeys twice (D2 already includes storeys). This is faithfully reproduced but may be an Excel bug. | Low |

### 10.2 Vision & AI

| Limitation | Impact | Severity |
|-----------|--------|----------|
| **Footprint accuracy** | OpenCV contour detection on satellite imagery is unreliable. Vegetation, shadows, adjacent buildings, and varying image quality cause frequent misdetection. | High |
| **Claude classification subjectivity** | Building era and type classification from a single Street View image is inherently uncertain. Confidence levels are self-reported by the model and not calibrated. | High |
| **Street View availability** | Rural areas and new developments often lack Street View coverage. The pipeline falls back to defaults in these cases. | Medium |
| **Single viewpoint** | Only one Street View image (heading=0) is analysed. The building may not be visible from this angle. | Medium |
| **No heating system detection** | Unless an oil tank or heat pump unit is clearly visible, heating system is essentially guessed. | Medium |

### 10.3 Data & Coverage

| Limitation | Impact | Severity |
|-----------|--------|----------|
| **Climate data granularity** | Only one climate data point per country (e.g., Mullingar for all of Ireland). Coastal vs inland differences are not captured. | Medium |
| **No sub-regional data** | France and Germany have NW variants in the Excel, but the code maps to a single country entry each. | Low |
| **Static 2022 HDD** | Heating degree days are from 2022 only. Climate change means these values shift year over year. | Low |
| **Primary Energy Factors** | PEFs are not in the Excel and are assumed values. The Irish BER system uses specific PEFs that may differ. | Medium |

### 10.4 Technical

| Limitation | Impact | Severity |
|-----------|--------|----------|
| **No caching** | Every pipeline run re-fetches images and re-calls Claude. No caching of geocoding results or AI analyses. | Medium |
| **Synchronous Streamlit** | asyncio.new_event_loop() is used as a workaround for Streamlit's synchronous execution model. This can cause issues with event loop management. | Low |
| **No database** | Results are not persisted. Each session starts fresh. | Low |
| **No authentication** | The Streamlit app has no user authentication. API keys are stored in .env or Streamlit secrets. | Low |

---

## 11. Areas for Improvement

### 11.1 High Priority

1. **Validate against SEAI BER dataset**: Cross-reference calculated ratings against the publicly available SEAI BER database (400,000+ rated buildings) to calibrate accuracy and identify systematic biases.

2. **Multi-angle Street View**: Fetch 4 images at 0/90/180/270 degree headings and send all to Claude for a more reliable classification with multiple viewpoints.

3. **Replace OpenCV with a building segmentation model**: The heuristic contour-scoring approach is fragile. A pre-trained building footprint segmentation model (e.g., from SpaceNet or Microsoft Building Footprints dataset) would be far more accurate.

4. **Implement proper Irish DEAP method**: Add a DEAP calculation mode alongside HWB for users who want results closer to official BER methodology.

5. **Add gain utilisation factor (eta)**: Implement the EN 13790 monthly method or at minimum the annual utilisation factor to prevent over-crediting of gains.

### 11.2 Medium Priority

6. **Result caching & persistence**: Cache geocoding, images, and Claude analyses in a SQLite database keyed by Eircode. Avoid redundant API calls.

7. **Regional climate data**: Use county-level or Met Eireann station-level HDD and solar data for Ireland instead of a single national value.

8. **Confidence-weighted pipeline**: Weight the footprint dimensions by confidence, blend with Claude's estimate, and propagate uncertainty through the calculation.

9. **Non-rectangular buildings**: Support L-shaped, T-shaped footprints by decomposing into rectangles or using the actual contour polygon area.

10. **Multi-building estates**: The Excel supports a "Quantity" field for identical buildings in housing estates. Add support for bulk assessment.

### 11.3 Lower Priority

11. **PDF report generation**: Generate a professional BER certificate-style PDF with all results, images, and recommendations.

12. **Historical weather data**: Use 10-year average HDD from Met Eireann instead of a single year.

13. **Cost estimation**: Estimate annual energy costs in EUR using current fuel prices, and retrofit investment payback periods.

14. **SEAI grant integration**: Show applicable SEAI grants for each retrofit measure.

15. **Batch processing**: Support CSV upload of multiple Eircodes for estate-level assessment.

16. **User accounts & history**: Add authentication and store assessment history per user.

---

## 12. API Key Setup Guide

### 12.1 Anthropic API Key (for Claude Vision)

1. **Create an account**: Go to [console.anthropic.com](https://console.anthropic.com) and sign up (or log in if you already have an account).

2. **Add billing**: Navigate to **Settings > Billing** and add a payment method. Claude API usage is pay-per-use. Vision requests with claude-sonnet-4-5 cost approximately $3 per 1000 images.

3. **Generate an API key**:
   - Go to **Settings > API Keys** (or directly to [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys))
   - Click **"Create Key"**
   - Give it a name (e.g., "BER Automation")
   - Copy the key immediately -- it is shown only once
   - The key starts with `sk-ant-...`

4. **Set the key in your environment**:
   ```bash
   # In your .env file at the project root:
   ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxxx
   ```

5. **Pricing reference** (as of 2026):
   - Claude Sonnet 4.5: ~$3/M input tokens, ~$15/M output tokens
   - A single Street View analysis uses ~1,500 input tokens (image) + ~300 output tokens
   - Approximate cost: ~$0.005 per analysis (~$5 per 1,000 Eircodes)

### 12.2 Google Maps API Keys (for Geocoding, Satellite, Street View)

1. **Create a Google Cloud project**:
   - Go to [console.cloud.google.com](https://console.cloud.google.com)
   - Click the project dropdown at the top > **"New Project"**
   - Name it (e.g., "BER Automation") and create

2. **Enable billing**:
   - Go to **Billing** in the left menu
   - Link a billing account (Google provides **$200/month free credit** for Maps APIs)

3. **Enable the required APIs**:
   - Go to **APIs & Services > Library**
   - Search for and enable each of these:
     - **Geocoding API** (converts Eircode to GPS coordinates)
     - **Maps Static API** (satellite images)
     - **Street View Static API** (street-level images)

4. **Create an API key**:
   - Go to **APIs & Services > Credentials**
   - Click **"+ Create Credentials" > "API Key"**
   - Copy the key

5. **Restrict the key** (strongly recommended):
   - Click on the newly created key
   - Under **"API restrictions"**, select **"Restrict key"**
   - Check only: Geocoding API, Maps Static API, Street View Static API
   - Under **"Application restrictions"**, optionally restrict to your IP address
   - Save

6. **Set the key in your environment**:
   ```bash
   # In your .env file at the project root:
   GOOGLE_MAPS_API_KEY=AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
   ```

7. **Pricing reference** (as of 2026):
   - Geocoding: $5 per 1,000 requests
   - Static Maps: $2 per 1,000 requests
   - Street View: $7 per 1,000 requests (image) + metadata requests are free
   - Total per Eircode pipeline run: ~$0.014
   - With $200/month free tier: ~14,000 pipeline runs/month at no cost

### 12.3 Final .env File

```bash
# .env (place at project root: BerAutomation/.env)
GOOGLE_MAPS_API_KEY=AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
ANTHROPIC_API_KEY=sk-ant-api03-XXXXXXXXXXXXXXXXXXXXXXXX
```

**Never commit this file to git.** It is already in `.gitignore`.

### 12.4 Verify Setup

```bash
# Test the manual calculator (no API keys needed):
python main.py manual --length 10 --width 8 --storeys 2 --epoch before_1980 --heating oil_boiler

# Test the full pipeline (requires both API keys):
python main.py pipeline D02X285

# Launch the web app:
python main.py app
# or: streamlit run app/streamlit_app.py
```

---

## 13. Deployment

### Streamlit Cloud

1. Push to GitHub
2. Add `packages.txt` (already provided: `libgl1-mesa-glx`, `libglib2.0-0` for OpenCV)
3. Connect at [share.streamlit.io](https://share.streamlit.io)
4. Set main file: `app/streamlit_app.py`
5. Add secrets in Streamlit dashboard:
   ```toml
   GOOGLE_MAPS_API_KEY = "AIza..."
   ANTHROPIC_API_KEY = "sk-ant-..."
   ```

### Local Development

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your keys
python -m pytest tests/ -v   # Verify 34 tests pass
python main.py app            # Launch UI
```
