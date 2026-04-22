# BER Automation Tool — Stakeholder Briefing Document

**Project:** CIRCUS — Connecting Initiatives for Rural Communities, Upscaling their Sustainable Energy
**Programme:** Interreg North-West Europe (NWE)
**Document type:** Technical overview and capability briefing
**Version:** 1.0 | March 2026

---

## Executive Summary

The BER Automation Tool is an AI-powered web application that estimates the **Building Energy Rating (BER)** of any residential property in North-West Europe using only a postal code or address. It requires no site visit, no manual survey, and no specialist knowledge to operate.

The tool fetches satellite and street-level imagery, analyses the building automatically using Claude AI vision, and applies a rigorous engineering calculation (the HWB annual balance method) to produce an energy performance estimate in under 30 seconds. Results are expressed in both the **Irish BER scale** (A1–G, as a common cross-border reference) and each country's own **native EPC certificate scale**.

The tool supports all eight partner countries relevant to the CIRCUS Interreg NWE programme: **Ireland, France, Germany, Belgium, Netherlands, Luxembourg, Switzerland, and Austria**.

---

## 1. Problem Statement

### Why Building Energy Rating Matters

Buildings account for approximately **40% of total energy consumption** in the EU and are the largest single source of CO₂ emissions in most North-West European countries. Improving the energy performance of existing housing stock is central to the EU's 2050 climate targets and the ambitions of the CIRCUS Interreg NWE project.

Energy Performance Certificates (EPCs) — called BER in Ireland, DPE in France, Energieausweis in Germany/Austria/Luxembourg, Energielabel in the Netherlands, EPC in Belgium, and GEAK in Switzerland — are the primary tool for communicating a building's energy status and guiding retrofit decisions.

### The Gap This Tool Fills

Commissioning an official EPC requires:
- A qualified energy assessor to visit the property
- A detailed on-site survey (typically 1–3 hours)
- Specialist certification software
- Fees of €150–€500 per property

This cost and effort creates a major barrier for:
- **Community energy organisations** trying to prioritise retrofit activities across hundreds of homes
- **Local authorities** conducting large-scale housing stock assessments
- **CIRCUS project partners** comparing energy performance across multiple countries
- **Researchers** needing rapid energy estimates for feasibility studies

The BER Automation Tool provides an **indicative BER estimate in under 30 seconds, at near-zero marginal cost**, enabling community partners to screen and prioritise their housing stock without expensive pre-surveys.

---

## 2. What the Tool Does

### 2.1 Input

A user provides:
1. A postal code or street address (e.g. `D02 X285`, `1234 Luxembourg`, `Marienplatz 1 Paderborn`)
2. The country

That is all that is required.

### 2.2 Output

The tool produces:
- **BER rating band** (Irish scale A1–G as reference, plus native country EPC band)
- **Primary energy** in kWh/m²/year
- **CO₂ emissions** in kg/m²/year and kg/year total
- **Energy breakdown**: transmission losses, ventilation losses, solar gains, internal gains, heating demand, hot water demand
- **Building characteristics**: estimated dimensions, floor area, building type, construction era, heating system
- **Retrofit comparison**: optional estimate of the rating after specified insulation and heating upgrades
- **Property imagery**: satellite view and multi-angle street view photographs

### 2.3 Accuracy Expectations

| Scenario | Expected accuracy |
|----------|-------------------|
| Clear, visible building with good Street View coverage | ±1–2 BER bands of official assessment |
| Partially obscured building or limited Street View | ±2–3 BER bands |
| No Street View available (rural) | ±3–4 BER bands (satellite footprint only) |
| Apartment / multi-unit block | Not recommended — designed for single-family residential |

The tool is designed for **screening and prioritisation**, not for official certification. It gives community partners and stakeholders the right order of magnitude to identify the worst-performing homes and focus retrofit resources effectively.

---

## 3. How the Tool Works — The Pipeline

The tool operates as a fully automated, sequential pipeline with five phases.

```
┌─────────────────────────────────────────────────────────────────┐
│  USER INPUT: address + country                                  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                    ┌────────▼────────┐
            Phase 1 │   GEOCODING     │  Google Maps API
                    │  address → GPS  │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
            Phase 2 │ IMAGE FETCHING  │  Google Maps Static API
                    │ satellite +     │  Google Street View API
                    │ 4× street views │  (4 angles: 0°/90°/180°/270°)
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
            Phase 3 │  AI BUILDING    │  Claude Vision (Anthropic)
                    │  ANALYSIS       │  → building type, era, heating
                    │  (street view)  │  → estimated storeys & units
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
            Phase 4 │  FOOTPRINT      │  Claude Vision (primary)
                    │  EXTRACTION     │  OpenCV image processing (fallback)
                    │  (satellite)    │  → building length × width in metres
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
            Phase 5 │  HWB ENERGY     │  Austrian HWB annual balance method
                    │  CALCULATION    │  → kWh/m²/yr, CO₂, BER band
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │     RESULT      │
                    │ BER + native EPC│
                    └─────────────────┘
```

### Phase 1 — Geocoding

The address or postal code is converted to GPS coordinates (latitude/longitude) using the Google Geocoding API. A country filter is applied to ensure the result stays within the correct country. Irish Eircodes receive special validation and formatting.

### Phase 2 — Image Fetching

Two types of imagery are fetched in parallel:
- **Satellite image** (640×640 px, zoom level 20) — used for measuring the building's roof footprint
- **Street View images** — four photographs taken at 90° intervals around the property, giving a full exterior view from all sides

The Street View images use automatic heading calculation: the tool queries the Street View metadata API to find where the nearest camera actually is, then computes the precise compass bearing from the camera to the building, ensuring the building is always centred in the photograph.

### Phase 3 — AI Building Analysis (Street View)

All four Street View images are sent simultaneously to **Claude Sonnet** (Anthropic's latest AI model) along with a detailed country-specific system prompt.

The AI analyses the images and returns:

| Parameter | Examples |
|-----------|---------|
| **Building type** | Detached, Semi-detached, Terraced (with party wall orientation) |
| **Construction era** | Before 1980, 1980–1990, 1990–2000, 2000–2010, After 2010 |
| **Number of storeys** | 1, 2, 3, or 4 |
| **Heating system** | Oil boiler, gas boiler, heat pump (air/ground/water), biomass, district heating |
| **Units in terrace row** | Number of houses sharing a continuous roofline |
| **Confidence score** | 0.0–1.0 (how clearly the building was visible) |
| **Reasoning** | Plain-language explanation of what the AI observed |

The AI prompt includes country-specific building knowledge: for example, it knows that oil tanks are common in rural Ireland, that district heating is prevalent in Luxembourg and the Netherlands, and that French stone buildings have very different visual signatures from German brick construction.

**Confidence gating:** If the AI confidence falls below 0.4 (e.g. the building is obscured by trees or the address is rural with no coverage), the analysis is not used and the tool falls back to sensible defaults. The user is shown a warning.

### Phase 4 — Footprint Extraction (Satellite)

The satellite image is sent to Claude Vision with a prompt that includes:
- The **map scale** in metres per pixel (calculated from the GPS latitude and zoom level)
- The **ground area covered** by the image in metres
- **Context from Phase 3** — if the building is terraced, Claude is told how many units are in the row and which side the party wall is on, so it measures one unit rather than the whole block

Claude returns the estimated **building length and width in metres**, a shape classification (rectangular, L-shaped, irregular), and a confidence score.

As a cross-validation step, an **OpenCV image processing algorithm** independently extracts the largest contour from the satellite image and estimates the building dimensions. If both methods agree within 30%, confidence is boosted. If they disagree, the AI result is trusted. If the AI fails, the OpenCV result is used as a fallback.

A safety net corrects for cases where the AI measures an entire terrace row: the repeating dimension is divided by the number of units.

Sanity checks reject unreasonable results (area below 20 m² or above 500 m²) and clamp all dimensions to the realistic range for NWE residential housing (4–25 metres in any direction).

### Phase 5 — Energy Calculation (HWB Method)

With the building classified and measured, the tool runs the **HWB (Heizwärmebedarf) annual heating balance**, an engineering method ported from an Excel tool developed at Munster Technological University (Benjamin Kaiser, January 2025).

The calculation follows *"Leitfaden für die Berechnung des Heizwaermebedarfs"* (Die Umweltberatung, 2019) and mirrors the formulas from the original Excel workbook cell by cell.

**Energy balance:**
```
Annual heating demand = Transmission losses + Ventilation losses
                      − Internal gains − Solar gains

Final energy = Annual heating demand ÷ Heating system efficiency (or SCOP)
Hot water energy = Residents × 40 litres/day × 365 × (4.2/3600) × 45°C rise

Total final energy = Final energy (heating) + Final energy (hot water)
Primary energy = Total final energy × Primary Energy Factor (country-specific)
CO₂ emissions = Total final energy × CO₂ emission factor (country- and system-specific)
```

Every input to this calculation is country-specific:
- **Heating degree days** — how cold and how long the winter is (from degreedays.net)
- **Solar irradiance** during heating season by orientation (from PHPP database)
- **Primary energy factor** for electricity (from each country's national EPBD regulation)
- **CO₂ emission factor** for electricity (from each country's grid operator, 2022)

---

## 4. Country-Specific Capability

### 4.1 Eight Supported Countries

The tool was built to support all Interreg NWE CIRCUS partner countries plus Switzerland and Austria:

| Country | EPC Scale | Notes |
|---------|-----------|-------|
| Ireland | BER (A1–G, 15 bands) | Primary reference scale |
| France | DPE (A–G, 7 bands) | Reformed July 2021 |
| Germany | Energieausweis (A+–H, 9 bands) | GEG 2020 |
| Belgium | EPC Flanders (A+–F, 7 bands) | Flanders EPB 2022 |
| Netherlands | Energielabel (A++++–G, 11 bands) | NTA 8800:2022 |
| Luxembourg | Energiepass (A+–G, 8 bands) | Règlement Grand-Ducal 2016 |
| Switzerland | GEAK (A–G, 7 bands) | EnDK / SIA 380/1:2016 |
| Austria | Energieausweis (A++–G+, 9 bands) | OIB Richtlinie 6:2019 |

For every address, the tool shows **both** the Irish BER band (as a consistent cross-border reference allowing direct comparison between countries) and the native EPC band that a resident of that country would recognise from their own national system.

### 4.2 Why Results Differ Dramatically Between Countries

The same physical building produces very different ratings depending on location. The key drivers:

**Electricity grid carbon intensity (CO₂ per kWh):**

| Country | CO₂ g/kWh electricity | Dominant source |
|---------|------------------------|----------------|
| Switzerland | **29** | Hydro + nuclear |
| France | **52** | Nuclear (70%+) |
| Belgium | 163 | Nuclear + gas |
| Austria | 156 | Hydro + gas |
| Luxembourg | 197 | Imports (FR/DE mix) |
| Ireland | 210 | Gas + wind |
| Netherlands | 290 | Gas + wind |
| Germany | **385** | Coal + gas |

**Impact:** Installing a heat pump in France cuts CO₂ by 93% compared to gas. The same heat pump in Germany cuts CO₂ by only 49% — and produces nearly as much CO₂ per kWh as gas in some countries. This is a critical consideration for CIRCUS partners advising communities on retrofit priorities.

**Why EPC band thresholds matter:**

The Netherlands Energielabel awards an **A** to a building at 160 kWh/m²/yr primary energy. The Irish BER would give the same building a **C1**. This is not because Dutch buildings are better — it is because Dutch building regulations set a lower Primary Energy Factor for electricity (1.45 vs Ireland's 2.08), and the Dutch scale has wider bands. Using the native EPC scale alongside the Irish BER reference prevents misinterpretation.

### 4.3 AI Prompt Localisation

The Claude Vision prompts contain country-specific knowledge. For example:
- **Ireland/France**: look for external oil tanks (cylindrical, often green/grey), especially in rural areas
- **Luxembourg/Netherlands/Germany**: district heating is common in urban areas — look for absent boiler flues
- **Germany**: heavy external insulation render systems common on 1980–2000 buildings
- **Switzerland**: triple glazing and heat pumps more common post-2010 due to strict Minergie standards
- **Belgium/Netherlands**: compact terraced brick housing is the dominant typology in towns

---

## 5. User Interface

### 5.1 Full Pipeline Mode

The primary mode for non-technical users. A single text box accepts any address or postal code. A country dropdown applies the correct climate data and EPC scale. One button click runs the entire 5-phase pipeline.

Results are displayed as:
- Satellite photograph of the property
- Four Street View photographs (2×2 grid: Front, Right, Rear, Left)
- Building footprint metrics (dimensions, area, confidence, method)
- AI analysis summary (building type, era, storeys, heating system, reasoning)
- BER rating badge (Irish scale) with optional native EPC badge
- Energy breakdown horizontal bar chart
- BER gauge/dial
- Full BER scale bar with current position highlighted
- Key metrics: floor area, heated volume, final energy, hot water demand, CO₂

### 5.2 Manual Input Mode

For users who know their building details and want to calculate a BER directly, without API calls. Four tabs collect:
- **Geometry**: length, width, storeys, storey height
- **Classification**: building type, construction era, country, number of residents
- **Heating**: heating system, separate electric hot water
- **Retrofit**: wall insulation (cm), roof insulation (cm), window U-value, heating system after retrofit

Results include the same full display as pipeline mode, plus a side-by-side **retrofit comparison** panel showing current vs after-retrofit BER bands, energy savings percentage, and band improvement.

### 5.3 Command-Line Interface

For integration into batch workflows and automated pipelines:

```bash
# Full pipeline from address
python main.py pipeline "D02 X285" --country ireland

# Manual calculation
python main.py manual --length 10 --width 8 --storeys 2 \
    --epoch before_1980 --country luxembourg --heating gas_boiler

# Launch web app
python main.py app
```

---

## 6. Technical Architecture

### 6.1 Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Web UI | Streamlit (Python) | Browser-based interface |
| AI Vision | Claude Sonnet (Anthropic API) | Building analysis from images |
| Geocoding | Google Geocoding API | Address → GPS coordinates |
| Satellite imagery | Google Maps Static API | Building roof view |
| Street View | Google Street View API | Building facade views |
| Computer vision | OpenCV (Python) | Fallback footprint extraction |
| Data validation | Pydantic | Input/output data models |
| HTTP client | httpx (async) | API calls |
| Charts | Plotly | Energy breakdown and gauge charts |

### 6.2 Key Engineering Decisions

**Why Claude Vision?**
Traditional computer vision (OpenCV) can detect building contours in satellite images but cannot classify building type, construction era, or heating system from street photographs. Claude Vision handles both tasks in a single API call, combining visual understanding with country-specific architectural knowledge.

**Why multi-angle Street View?**
A single front-facing photograph misses features only visible from the side or rear: oil tanks, heat pump units, extensions, shared party walls, boiler flues. Four images at 90° intervals give a complete exterior survey. The images are sent together so Claude can cross-reference all views simultaneously.

**Why auto-heading?**
The Google Street View API takes a `heading` parameter (compass bearing) to control which direction the camera faces. Rather than using a fixed bearing (which would often look away from the building), the tool queries the Street View metadata API to find where the nearest panorama camera physically was, then computes the geodesic bearing from that camera position to the target building. This ensures the building is centred in every photograph.

**Why dual footprint extraction?**
AI vision is the primary footprint method because it can identify the building outline within a complex satellite scene. OpenCV acts as an independent check: if both methods agree within 30%, confidence is boosted. This catches cases where the AI has misjudged scale.

**Why a confidence threshold of 0.4?**
Below this threshold, the AI has indicated it cannot clearly see the building. Using uncertain classifications would produce misleading energy estimates. The pipeline falls back to representative defaults (10m × 8m, detached, gas boiler, before 1980) rather than propagate low-quality data.

### 6.3 Data Flow and Privacy

- No address data or imagery is stored by the application
- Google Maps API processes geocoding and image requests under Google's privacy policy
- Images are sent to Anthropic's Claude API for analysis under Anthropic's privacy policy
- The tool does not log or retain any user-submitted addresses

---

## 7. The Energy Calculation in Detail

### 7.1 HWB Annual Balance Method

The Heizwärmebedarf (HWB) method calculates the building's annual energy balance from physical first principles. It is a steady-state monthly balance method based on the ISO 13790 standard, the same underlying approach used by professional energy assessment tools across Europe.

**Heat losses:**
- **Transmission losses** — heat escaping through walls, roof, floor, and windows. Determined by the U-value (insulation quality) of each element, its area, and the annual Heating Degree Days (a measure of winter severity).
- **Ventilation losses** — heat carried out by air exchange. Assumes a fixed air change rate of 0.4 h⁻¹.
- **Thermal bridge correction** — additional losses from junctions between building elements (window reveals, roof-wall interfaces). Calculated automatically from the mean U-value.

**Heat gains (reduce the heating demand):**
- **Solar gains** — passive heat from sunlight through windows. Calculated from window area, orientation, solar irradiance data for the heating season, the glazing g-value (how much solar energy passes through), and shading correction.
- **Internal gains** — heat from occupants and appliances. Fixed at 3.75 W/m² of net floor area during the heating season.

**Results chain:**
```
Heating demand (kWh/yr) → divide by heating system efficiency → Final energy (kWh/yr)
Final energy × Primary Energy Factor → Primary energy (kWh/m²/yr) → BER band
Final energy × CO₂ factor → Annual CO₂ emissions (kg/yr)
```

### 7.2 Default U-Values by Construction Era

The tool uses U-values (thermal transmittance, W/m²K) sourced from Austrian OIB guidelines. Lower U-values mean better insulated elements.

| Era | Wall U | Roof U | Floor U | Window U | Notes |
|-----|--------|--------|---------|---------|-------|
| Before 1980 | 1.20 | 0.65 | 1.35 | 3.00 | Solid masonry, single glazing |
| 1980–1990 | 0.60 | 0.275 | 0.75 | 2.50 | Early cavity wall, basic roof insulation |
| 1990–2000 | 0.45 | 0.235 | 0.60 | 2.15 | Cavity wall, double glazing emerging |
| 2000–2010 | 0.35 | 0.20 | 0.40 | 1.40 | Improved cavity, standard double glazing |
| After 2010 | 0.22 | 0.20 | 0.25 | 1.00 | High-performance, NZEB-influenced |

Manual inputs allow these defaults to be overridden for buildings where the actual construction is known.

### 7.3 Heating System Efficiencies

| System | Efficiency / SCOP | Notes |
|--------|-------------------|-------|
| Oil boiler | 0.85 | Standard condensing efficiency |
| Gas boiler | 0.90 | Modern condensing boiler |
| Biomass | 0.875 | Pellet/chip boiler |
| Electric direct | 0.99 | Near-100% conversion |
| Air-source heat pump | **3.50** | SCOP — delivers 3.5 kWh heat per 1 kWh electricity |
| Ground/water-source heat pump | **4.50** | Higher SCOP due to stable ground temperature |
| District heating | 0.95 | Network distribution efficiency |

**Why heat pumps are transformative:** A gas boiler at 90% efficiency converts 1 kWh gas to 0.9 kWh heat. An air-source heat pump with SCOP 3.5 converts 1 kWh electricity to 3.5 kWh heat. This is why heat pump retrofits produce such large reductions in both final energy and CO₂ (especially in countries with clean electricity grids).

---

## 8. Retrofit Analysis

### 8.1 How the Retrofit Calculation Works

The tool can calculate a **side-by-side before/after comparison** for a standard retrofit package:
- **Wall insulation**: user-specified additional exterior insulation thickness (cm). The tool computes the new wall U-value by adding the additional thermal resistance.
- **Roof insulation**: similarly computes new roof U-value.
- **Window replacement**: user specifies target U-value (e.g. 1.4 for standard double, 0.8 for triple glazing).
- **Heating system upgrade**: optionally switch from oil/gas to a heat pump.

### 8.2 Typical Retrofit Impact (Ireland, pre-1980 detached, gas boiler)

| Measure | Primary energy | BER | CO₂ | Saving |
|---------|---------------|-----|-----|--------|
| Baseline | 177.6 kWh/m²/yr | C2 | 31.3 kg/m²/yr | — |
| Wall + roof insulation + triple glazing | ~130 kWh/m²/yr | B3 | ~22.9 kg/m²/yr | −27% |
| Above + switch to heat pump | ~50 kWh/m²/yr | A2 | ~4.3 kg/m²/yr | −86% |

The retrofit analysis helps community partners show homeowners the **pathway from their current rating to an A-rated home** and the energy/CO₂ savings at each step.

---

## 9. Limitations and Appropriate Use

### 9.1 This Tool Is Not an Official EPC

The BER Automation Tool produces **indicative estimates** for screening and prioritisation. It should not be used:
- As a substitute for an official energy assessment for building regulations compliance
- As the basis for financial products (mortgages, green loans) that require official certification
- For the purchase or sale of property (where official EPCs are legally required)

For these purposes, a qualified energy assessor must conduct an official assessment.

### 9.2 Known Limitations

| Limitation | Impact | Mitigation |
|-----------|--------|-----------|
| Street View coverage gaps (rural areas) | Lower building classification confidence | Satellite-only fallback with confidence warning |
| U-values from Austrian OIB guidelines | May not match local construction practice exactly | Manual override available |
| Electricity CO₂ factors are 2022 values | Grids are changing — Germany and Ireland decarbonising rapidly | Values updated periodically |
| Belgium: uses Flanders EPC thresholds | Brussels/Wallonia EPC may differ slightly | Noted in UI |
| Swiss GEAK: single-metric approximation | Official GEAK uses two separate ratings | Noted in output |
| Apartments and multi-unit blocks | Footprint method measures entire building, not one flat | Not recommended for apartments |
| Buildings obscured by trees/hedges | AI cannot classify facade → low confidence → default values | Confidence warning displayed |

### 9.3 Validation Status

The tool has been validated against manual calculations from the source Excel workbook (Benjamin Kaiser, MTU 2025) and produces matching results to within rounding tolerance. Field validation against official BER certificates is an ongoing activity; early results suggest agreement within ±1–2 bands for standard semi-detached and terraced properties with clear Street View imagery.

---

## 10. Use Cases for CIRCUS Partners

### 10.1 Community Housing Stock Assessment

A community energy organisation can enter all addresses in a village or townland and generate indicative BER ratings for the entire housing stock in a matter of hours, without any site visits. This allows them to:
- Map energy performance across the community
- Identify the worst-performing homes (priority for deep retrofits)
- Estimate aggregate CO₂ savings potential
- Prepare evidence for funding applications

### 10.2 Retrofit Prioritisation

By running the retrofit comparison for multiple homes, the tool helps partners identify which houses would benefit most from insulation (pre-1980 solid-wall detached homes) versus which would benefit most from a heating system change (already-insulated homes on oil or electric direct heating).

### 10.3 Cross-Border Benchmarking

The Irish BER scale as a common reference allows CIRCUS partners in Ireland, France, Germany, Belgium, and the Netherlands to compare their housing stocks on a single standardised scale, while the native EPC scale ensures results are interpretable by residents in each country.

### 10.4 Community Engagement

The visual interface — satellite imagery, street photographs, energy gauge, and breakdown chart — makes energy performance tangible and accessible to non-technical audiences. Partners can use the tool in community meetings to show residents their estimated rating and the impact of specific retrofit measures.

### 10.5 Research and Policy

The command-line interface allows batch processing for academic research. The detailed energy breakdown (transmission vs ventilation vs solar gains vs internal gains) provides insights into the dominant sources of energy loss in different housing typologies and climates.

---

## 11. How to Get Started

### 11.1 Web Application

```bash
python main.py app
```

This launches the Streamlit web app in your browser. No configuration needed beyond having valid API keys set in the environment.

### 11.2 Required API Keys

| Key | Purpose | How to obtain |
|-----|---------|---------------|
| `ANTHROPIC_API_KEY` | Claude Vision analysis | console.anthropic.com |
| `GOOGLE_MAPS_API_KEY` | Geocoding + Street View + Satellite | console.cloud.google.com |

Both keys must be set as environment variables or in a `.env` file.

### 11.3 Quick Test — All Countries

The following addresses provide a good demonstration across all eight supported countries:

| Address | Country | Expected building type |
|---------|---------|----------------------|
| `V93 H2RH` | ireland | Rural, likely pre-1980 detached |
| `44000 Nantes` | france | NW French urban residential |
| `33098 Paderborn` | germany | NW German terraced/semi-D |
| `1000 Bruxelles` | belgium | Belgian urban residential |
| `7241 Lochem` | netherlands | Dutch rural/village |
| `1234 Luxembourg` | luxembourg | Luxembourgish urban |
| `4001 Basel` | switzerland | Swiss urban, NW region |
| `1010 Wien` | austria | Austrian urban residential |

---

## 12. Provenance and Methodology Sources

| Component | Source |
|-----------|--------|
| HWB calculation method | *Leitfaden für die Berechnung des Heizwärmebedarfs*, Die Umweltberatung (2019) |
| U-values by epoch | Austrian OIB guidelines, via Kaiser Excel tool (MTU, Jan 2025) |
| Heating degree days | degreedays.net, base 15.5°C, 2022 data |
| Solar irradiance / heating days | PHPP (Passive House Planning Package) climate database |
| Electricity CO₂ factors | National grid operators / statistical agencies, 2022 reporting year (SEAI IE, RTE FR, UBA DE, ELIA BE, RVO NL, ILR LU, SFOE CH, E-Control AT) |
| Primary energy factors | National EPBD transpositions (S.I. 259/2016 IE, RE2020 FR, GEG 2020 DE, EPB 2022 BE, NTA 8800 NL, RGD 2016 LU, SIA 380/1 CH, OIB Rl.6 AT) |
| Native EPC band thresholds | National building regulation documents (see `docs/country_data.md` for full detail) |
| Original Excel tool | Benjamin Kaiser, Munster Technological University, January 2025 |

---

## Appendix A — BER Scale Reference

| Irish BER band | kWh/m²/yr | Typical building |
|---------------|-----------|-----------------|
| A1 | ≤ 25 | New passive house / NZEB |
| A2 | ≤ 50 | New high-performance build |
| A3 | ≤ 75 | Post-2010 well-insulated + heat pump |
| B1 | ≤ 100 | Post-2010 standard + heat pump |
| B2 | ≤ 125 | Post-2000 retrofitted |
| B3 | ≤ 150 | Post-2000 standard |
| C1–C3 | 150–225 | Post-1990 average |
| D1–D2 | 225–300 | 1980s typical |
| E1–E2 | 300–380 | Pre-1980, partially insulated |
| F | 380–450 | Pre-1980, poorly insulated |
| G | > 450 | Pre-1980, uninsulated solid wall, oil/electric heating |

---

## Appendix B — Glossary

| Term | Definition |
|------|-----------|
| **BER** | Building Energy Rating — the Irish national EPC system, scale A1–G |
| **EPC** | Energy Performance Certificate — the general term for a building's energy rating document |
| **HWB** | Heizwärmebedarf — annual heating demand in kWh/m²/yr (German: *heating energy requirement*) |
| **Primary energy** | Total energy extracted from nature, including generation and transmission losses. Used for EPC ratings. |
| **Final energy** | Energy delivered to and used in the building (what appears on the fuel bill). |
| **U-value** | Thermal transmittance in W/m²K. Lower is better insulated. |
| **g-value** | Solar energy transmittance of glazing. Higher means more passive solar gain. |
| **SCOP** | Seasonal Coefficient of Performance — efficiency ratio for heat pumps. SCOP 3.5 means 3.5 kWh heat per 1 kWh electricity. |
| **HDD** | Heating Degree Days — cumulative measure of winter severity. Higher = colder climate. |
| **PEF** | Primary Energy Factor — multiplier converting final energy to primary energy. Country-specific for electricity. |
| **NZEB** | Nearly Zero Energy Building — EU standard for high-performance new builds. |
| **CIRCUS** | Connecting Initiatives for Rural Communities, Upscaling their Sustainable Energy — the Interreg NWE project this tool was developed for. |

---

*BER Automation Tool v1.0 — CIRCUS Interreg NWE Project*
*Munster Technological University | March 2026*
*This document is for stakeholder briefing purposes. For official energy assessments, use a certified energy assessor.*
