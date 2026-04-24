# BER Automation: Estimating Building Energy Ratings at Scale Using AI
## Environ 2026 Conference Presentation

**Author:** Avinash Nagarajan, Munster Technological University
**Project:** CIRCUS — Connecting Initiatives for Rural Communities, Upscaling their Sustainable Energy (Interreg North-West Europe)
**Duration:** 10 minutes
**Format:** Each slide includes bullet-point content and full speaker notes.

---

## Slide 1 — Title

**Content:**
- BER Automation: Estimating Building Energy Ratings at Scale Using AI
- Avinash Nagarajan | Munster Technological University
- CIRCUS Interreg North-West Europe Programme
- Environ 2026

**Visual suggestion:** Clean title slide. CIRCUS Interreg NWE logo alongside MTU logo. Subtle background: satellite image of a residential street.

**Speaker notes:**
Good morning/afternoon. My name is Avinash Nagarajan, and I'm presenting work from the CIRCUS Interreg North-West Europe project at Munster Technological University. Today I want to show you a tool we've built that can estimate the energy performance of any residential building across eight European countries — using nothing but a postal address, and in under thirty seconds. I'll explain how it works, what it can tell you about buildings and retrofit priorities, and where we think it fits in the broader challenge of decarbonising our housing stock.

---

## Slide 2 — The Problem

**Content:**
- Buildings account for **40% of total energy consumption** in the EU
- They are the largest single source of CO₂ in most NWE countries
- Energy Performance Certificates (EPCs) are the primary tool for communicating a building's energy status
- But commissioning an official EPC requires:
  - A qualified assessor + 1–3 hour site visit
  - Certification software
  - **€150–€500 per property**
- This creates a major barrier for community energy organisations, local authorities, and Interreg partners trying to assess hundreds of homes

**Visual suggestion:** Split slide — left side: EU building stock stat (40% energy, bold graphic). Right side: a list of EPC requirements with a cost/time callout box.

**Speaker notes:**
Let me set the scene. Buildings are responsible for roughly forty percent of total energy use in the EU, and improving the energy performance of existing housing stock is central to both national climate targets and the ambitions of the CIRCUS project. The standard tool for this is the Energy Performance Certificate — called a BER in Ireland, a DPE in France, an Energieausweis in Germany or Austria. These certificates tell you how energy-efficient a building is and guide retrofit decisions.

The problem is access. Getting an official EPC means paying a qualified assessor to visit the property, conduct a detailed survey, and enter everything into certification software. In Ireland alone that costs between one hundred and fifty and five hundred euros per house, and takes a day of a specialist's time. For a community energy organisation trying to prioritise retrofit activities across an entire village or townland — often with limited budgets and volunteer capacity — this creates an enormous barrier. You simply cannot pre-assess hundreds of homes before knowing which ones to target.

---

## Slide 3 — The Opportunity

**Content:**
- Satellite imagery covers virtually every residential address in North-West Europe
- Google Street View provides photographic exterior surveys of most properties
- AI vision models can now classify building features from photographs
- The energy physics is well established — the HWB calculation method has been used by practitioners for decades
- **Question:** Can we automate the entire workflow?

**Visual suggestion:** A 2×2 grid showing: (1) satellite image of a house, (2) street view photo, (3) AI classification output, (4) BER gauge. Arrows connecting them.

**Speaker notes:**
But here is the opportunity. Satellite imagery is now ubiquitous — every address in North-West Europe can be seen from above at a resolution that lets you measure a building's footprint. Google Street View provides near-complete photographic coverage of residential streets, giving you an exterior survey of most properties without setting foot inside. And modern AI vision models — specifically large multimodal models like Claude — can now examine those photographs and make remarkably reliable inferences about when a building was constructed, what type it is, and what heating system it likely has.

The energy calculation itself isn't magic. The HWB annual balance method has been used by practitioners for years. What has been missing is a way to gather the building inputs automatically at scale. So we asked: can we automate the entire pipeline — from postal code to BER rating — using only publicly available data and AI vision?

---

## Slide 4 — What the Tool Does

**Content:**
- **Input:** A postal code or street address + country selection. That is all.
- **Output in under 30 seconds:**
  - BER band (Irish A1–G scale as cross-border reference)
  - Native country EPC band (DPE, Energieausweis, Energielabel, GEAK…)
  - Primary energy: kWh/m²/year
  - CO₂ emissions: kg/year
  - Full energy breakdown: transmission losses, ventilation, solar & internal gains
  - Building characteristics: dimensions, floor area, type, era, heating system
  - Retrofit comparison: estimated rating after insulation and heating upgrades
- **Supported countries:** Ireland, France, Germany, Belgium, Netherlands, Luxembourg, Switzerland, Austria
- Accessible via a browser-based web app — no specialist knowledge required

**Visual suggestion:** Screenshot of the Streamlit app with a result displayed, annotated with callouts for each output type. Country flag row at the bottom.

**Speaker notes:**
Here is what the tool actually does. A user opens the web application, types in a postal code or street address — it could be a Dublin Eircode, a French code postal, a German Postleitzahl — selects the country, and clicks run. Within thirty seconds the tool returns a full building energy profile.

You get the Irish BER band as a consistent cross-border reference scale, alongside the native EPC certificate format that residents in each country would recognise. You get primary energy in kilowatt-hours per square metre per year, CO₂ emissions, a full breakdown of where the energy is being lost, and the building's physical characteristics as the AI estimated them. You also get a retrofit comparison: what would the rating become if you added wall and roof insulation, replaced the windows, or switched to a heat pump?

The tool supports all eight partner countries of the CIRCUS Interreg NWE programme, plus Switzerland and Austria. No specialist knowledge is needed to operate it — a community energy officer or local authority staff member can use it directly.

---

## Slide 5 — The Pipeline

**Content:**
- Five automated phases:

```
Address + Country
      ↓
Phase 1: GEOCODING          → GPS coordinates (Google Geocoding API)
      ↓
Phase 2: IMAGE FETCHING     → Satellite image (zoom 20, 640×640 px)
                            → 4 Street View images at 0° / 90° / 180° / 270°
                              (auto-heading: camera→building geodesic bearing)
      ↓
Phase 3: AI BUILDING        → Claude Vision analyses 4 street views
         ANALYSIS           → Building type, construction era, storeys,
                              heating system, confidence score
      ↓
Phase 4: FOOTPRINT          → Claude Vision measures satellite image (primary)
         EXTRACTION         → OpenCV contour detection (cross-validation)
                            → Reconciliation: if both agree within 30%, boost confidence
      ↓
Phase 5: HWB CALCULATION    → Transmission + ventilation losses
                            → Solar + internal gains
                            → Final energy → Primary energy → BER band
      ↓
Result: BER rating + native EPC + CO₂ + retrofit comparison
```

**Visual suggestion:** Vertical pipeline flowchart matching the above. Each phase in a distinct colour block with the technology used shown alongside.

**Speaker notes:**
Let me walk through how the pipeline actually works, because I think the engineering decisions here are interesting.

Phase one is straightforward geocoding — we convert the address to GPS coordinates using the Google Geocoding API, with a country filter to ensure we stay within the right borders.

Phase two fetches two types of imagery. A satellite image at zoom level twenty gives us a top-down view of the building at roughly nine centimetres per pixel. For Street View, rather than simply sending a camera facing north, we query the Street View metadata API to find where the nearest camera physically was, compute the geodesic compass bearing from that camera to the building, and then fetch four images at ninety-degree intervals around that bearing. This means the building is centred in every photograph, and we get a full exterior view from all four sides — front, right, rear, and left.

Phase three sends all four street view images simultaneously to Claude Sonnet, Anthropic's AI vision model, along with a detailed country-specific prompt. Claude returns its assessment of the building type, construction era, number of storeys, heating system, and a confidence score between zero and one.

Phase four extracts the building's footprint dimensions from the satellite image — also using Claude Vision, with the map scale injected into the prompt so Claude can reason in real metres. An independent OpenCV contour-detection algorithm runs as a cross-validation: if both methods agree within thirty percent, confidence is boosted; if they disagree, the AI result is trusted; if the AI fails, OpenCV acts as fallback.

Phase five runs the energy calculation, which I'll describe next.

---

## Slide 6 — AI Building Analysis

**Content:**
- **Model:** Claude Sonnet (Anthropic) — multimodal vision + language
- **Input:** 4 street view images sent in a single API request (cross-referencing enabled)
- **Returns:**

| Parameter | Examples |
|-----------|---------|
| Building type | Detached, Semi-detached, Terraced |
| Construction era | Before 1980, 1980–1990, 1990–2000, 2000–2010, After 2010 |
| Storeys | 1, 2, 3, or 4 |
| Heating system | Oil boiler, gas boiler, heat pump (air/ground), biomass, district heating |
| Confidence | 0.0 – 1.0 |
| Reasoning | Plain-language explanation of what the AI observed |

- **Country-specific architectural knowledge** embedded in prompts:
  - Ireland/France: look for external oil tanks in rural areas
  - Luxembourg/Netherlands: district heating dominant in urban areas
  - Germany: heavy exterior insulation render common post-1980
  - Switzerland: triple glazing and heat pumps more common post-2010 (Minergie standards)
- **Confidence gating:** if confidence < 0.4, safe defaults are used — the tool does not propagate a low-quality guess

**Visual suggestion:** Example street view image with AI output panel alongside — building type label, era, heating system icon, confidence bar, and a short reasoning excerpt.

**Speaker notes:**
The building analysis phase is where AI vision does the heavy lifting. We send all four street view images to Claude in a single request, so the model can cross-reference them. An oil tank that's only visible from the rear, a heat pump unit on the side wall, or a shared party wall that's only apparent from the left — the model can pick all of these up when it has the full exterior survey.

We've embedded country-specific architectural knowledge directly into the prompts. The visual signatures of construction eras differ significantly between countries — a 1980s German building with heavy external insulation render looks very different from a 1980s Irish cavity-wall semi-D. Rural Irish and French properties are much more likely to have oil tanks than urban German or Dutch properties. District heating infrastructure is common in Luxembourg and the Netherlands but rare in rural Ireland. This localisation meaningfully improves classification accuracy.

A critical design decision is what we call confidence gating. The model returns a confidence score with every analysis. If that score falls below 0.4 — for example because the building is obscured by trees, or there is no Street View coverage — the tool does not use the uncertain classification. Instead it falls back to conservative defaults and shows the user a clear warning. We would rather give an honest default than propagate a low-quality AI guess through to the final energy calculation.

---

## Slide 7 — The Energy Calculation

**Content:**
- **Method:** HWB (Heizwärmebedarf) annual heating balance
- Based on ISO 13790 steady-state monthly balance — the same underlying standard used by professional EPC tools across Europe
- Ported from an Excel tool developed at MTU (Benjamin Kaiser, January 2025)

**Annual energy balance:**
```
Q_heating = Transmission losses (fabric) + Ventilation losses
           − Solar gains (passive solar through windows)
           − Internal gains (occupants + appliances)

Final energy = Q_heating ÷ heating system efficiency (or SCOP for heat pumps)
Primary energy = Final energy × Primary Energy Factor (country-specific)
CO₂ = Final energy × CO₂ emission factor (country- and fuel-specific)
```

- **Every input is country-specific:**
  - Heating Degree Days (winter severity) — from degreedays.net 2022
  - Solar irradiance during heating season — from PHPP climate database
  - Primary Energy Factor for electricity — from each country's national EPBD regulation
  - Grid CO₂ intensity — from national grid operators, 2022

**Visual suggestion:** Clean energy balance diagram showing four arrows: two in (transmission loss, ventilation loss) and two out (solar gain, internal gain), flowing into Q_heating → final energy → primary energy → BER band.

**Speaker notes:**
The energy calculation is the HWB annual heating balance — Heizwärmebedarf, or heating energy requirement in German. This is a steady-state annual method based on ISO 13790, the same standard that underpins professional EPC calculation tools across Europe. It was ported cell by cell from an Excel workbook developed by Benjamin Kaiser at MTU in January 2025.

The core balance is straightforward: heating demand equals transmission losses through walls, roof, floor and windows, plus ventilation losses from air exchange, minus usable solar gains through glazing and internal heat from occupants and appliances. That heating demand is then divided by the heating system's efficiency — or seasonal coefficient of performance for heat pumps — to get final energy consumption. Final energy is multiplied by a country-specific Primary Energy Factor to get the primary energy figure that determines the EPC band.

Every country-specific input is sourced from authoritative data: heating degree days from degreedays.net, solar irradiance from the Passive House Planning Package climate database, primary energy factors from each country's national EPBD transposition, and grid carbon intensity from national grid operators. The same building in different countries produces a genuinely different calculation — not just a different label.

---

## Slide 8 — CO₂ Across Countries: A Policy Insight

**Content:**
- Installing a heat pump produces very different CO₂ outcomes depending on electricity grid carbon intensity:

| Country | Grid CO₂ (g/kWh) | Heat pump CO₂ reduction vs gas |
|---------|-------------------|-------------------------------|
| Switzerland | **29** | ~93% |
| France | **52** | ~89% |
| Belgium | 163 | ~72% |
| Austria | 156 | ~73% |
| Luxembourg | 197 | ~66% |
| Ireland | 210 | ~64% |
| Netherlands | 290 | ~51% |
| Germany | **385** | ~49% |

- The same physical building, the same heat pump, same SCOP of 3.5
- **Critical implication for CIRCUS partners:** advising communities on retrofit priority must account for local grid decarbonisation
- In France, a heat pump retrofit today is a near-zero-carbon heating solution
- In Germany today, it roughly halves CO₂ but is not yet transformational — grid decarbonisation must follow

**Visual suggestion:** Bar chart of grid CO₂ intensity by country, colour-coded from green (CH) to red (DE). Below it: a simple infographic showing the same house with heat pump and the percentage CO₂ cut for each country.

**Speaker notes:**
This is one of the most striking outputs the tool surfaces for cross-border work, and I think it's worth pausing on. The tool shows not just a BER band but the CO₂ impact of retrofit measures, and that CO₂ figure varies dramatically across our eight countries — not because of anything about the buildings, but because of how each country generates its electricity.

Switzerland's grid is dominated by hydropower and nuclear, producing just twenty-nine grams of CO₂ per kilowatt-hour. France's nuclear-heavy grid sits at fifty-two grams. At the other end, Germany's coal and gas mix emits three hundred and eighty-five grams per kilowatt-hour — more than thirteen times Switzerland's figure.

What this means in practice: install an air-source heat pump with a seasonal COP of 3.5 in a French home, and you cut CO₂ by roughly eighty-nine percent compared to a gas boiler. The same heat pump in Germany cuts CO₂ by about forty-nine percent — still significant, but far from transformational, and only until Germany's grid decarbonises further.

For CIRCUS partners advising communities on where to focus retrofit resources, this matters enormously. In France and Switzerland, pushing hard on heat pump uptake now makes sense. In Germany, insulation-first strategies may be more immediately effective for CO₂, and heat pump advice should be framed in the context of a transitioning grid. The tool makes this visible, by country, for every assessment.

---

## Slide 9 — Retrofit Analysis

**Content:**
- Built-in before/after retrofit comparison — no extra input required beyond describing the upgrade
- **Example: Pre-1980 Irish detached house, gas boiler**

| Scenario | Primary energy | BER band | CO₂ |
|----------|---------------|----------|-----|
| Baseline | 177.6 kWh/m²/yr | **C2** | 31.3 kg/m²/yr |
| + Wall insulation (12 cm) + Roof insulation (20 cm) + Triple glazing | ~130 kWh/m²/yr | **B3** | ~22.9 kg/m²/yr |
| + Switch to air-source heat pump | ~50 kWh/m²/yr | **A2** | ~4.3 kg/m²/yr |
| **Total improvement** | | **C2 → A2** | **−86% CO₂** |

- Helps community partners show homeowners the **pathway from their current rating to an A-rated home**
- Identifies which houses benefit most from insulation versus heating system change
- Directly supports SEAI/national grant scheme conversations

**Visual suggestion:** Side-by-side BER band gauge showing C2 (left) vs A2 (right), with an arrow between them. Below: three-row table showing the retrofit stages.

**Speaker notes:**
The retrofit analysis capability is what makes the tool actionable rather than just descriptive. For any building assessed through the pipeline, you can specify a retrofit package — how many centimetres of wall insulation, how many centimetres of roof insulation, a target window U-value, and whether to switch the heating system — and the tool recalculates the BER side-by-side with the current rating.

The example here is a pre-1980 detached Irish house on a gas boiler — a very common typology in rural Ireland. Its baseline rating is C2, at 177.6 kilowatt-hours per square metre per year. Add wall and roof insulation plus triple-glazed windows, and it reaches B3 with a twenty-seven percent CO₂ reduction. Add a heat pump on top of that, and it reaches A2 — an eighty-six percent cut in CO₂ compared to the unimproved baseline.

For a community energy officer using this at a public meeting, they can pull up any address, show the current estimated rating, and then show what's achievable with a standard deep retrofit package. It makes the retrofit pathway tangible and evidence-based for homeowners who may never have seen their building's energy profile before.

---

## Slide 10 — Accuracy, Limitations & What's Next

**Content:**
- **Accuracy:**

| Scenario | Expected accuracy |
|----------|-------------------|
| Clear building, good Street View coverage | ±1–2 BER bands |
| Obscured or limited Street View | ±2–3 BER bands |
| No Street View (rural) | ±3–4 BER bands (satellite only) |

- **This is a screening tool, not an official EPC:**
  - Not a substitute for formal certification (building regulations, property transactions, green loans)
  - Designed for prioritisation — finding where to focus, not certifying what's there
- **Known limitations:**
  - Apartments and multi-unit blocks: footprint method not designed for these
  - U-values from Austrian OIB standards (broadly comparable, not Irish Part L exact)
  - Electricity CO₂ factors from 2022 — grids are decarbonising
- **Validation status:**
  - Matches source MTU Excel tool to within rounding tolerance
  - Field validation against SEAI BER certificate database (400k+ records) — ongoing
- **What's next:**
  - Batch processing for estate-level assessment
  - Regional climate data (county-level HDD for Ireland)
  - Open to collaboration — CIRCUS partners, SEAI, local authorities, researchers

**Visual suggestion:** Two-column layout. Left: accuracy table. Right: "Appropriate use" callout box and next steps list. CIRCUS/MTU contact details at the bottom.

**Speaker notes:**
I want to be clear about what the tool is and isn't. For a building with good Street View coverage and a clearly visible facade, we expect agreement within one to two BER bands of an official assessment. For buildings with partial coverage or obstruction, that widens to two to three bands. For genuinely rural properties with no Street View at all, the tool falls back to satellite-only footprint estimation and the uncertainty is greater.

This is intentionally a screening and prioritisation tool. It should not be used as a substitute for an official EPC for anything that legally requires one — property transactions, building regulations compliance, green finance products. For those purposes you still need a qualified assessor. But for identifying where the worst-performing homes are in a community, for prioritising outreach and retrofit support, for preparing evidence for funding applications — this is exactly the right tool.

On what comes next: we are currently working to validate the tool against the SEAI BER certificate database, which contains over four hundred thousand rated Irish properties. That will let us quantify systematic biases and calibrate confidence for different building typologies. We're also exploring batch processing so that community organisations can upload a list of addresses and get assessments in bulk. And we're actively looking for collaboration — with CIRCUS partners across the eight countries, with SEAI, with local authorities, and with other researchers working in this space. If any of that sounds relevant to your work, I'd very much welcome a conversation.

Thank you.

---

## Appendix: Key Technical References

| Component | Source |
|-----------|--------|
| HWB calculation method | *Leitfaden für die Berechnung des Heizwärmebedarfs*, Die Umweltberatung (2019) |
| U-values by epoch | Austrian OIB guidelines, via Kaiser Excel tool (MTU, Jan 2025) |
| Heating degree days | degreedays.net, base 15.5°C, 2022 |
| Solar irradiance | PHPP (Passive House Planning Package) climate database |
| Electricity CO₂ factors | SEAI (IE), RTE (FR), UBA (DE), ELIA (BE), RVO (NL), ILR (LU), SFOE (CH), E-Control (AT) — 2022 |
| Primary energy factors | National EPBD transpositions per country |
| Native EPC thresholds | National building regulation documents — see `docs/country_data.md` |
| Original Excel tool | Benjamin Kaiser, Munster Technological University, January 2025 |

---

## Appendix: Glossary for Slides

| Term | Definition |
|------|-----------|
| BER | Building Energy Rating — Irish national EPC, scale A1–G |
| EPC | Energy Performance Certificate — general term across EU |
| HWB | Heizwärmebedarf — annual heating demand (kWh/m²/yr) |
| Primary energy | Energy extracted from nature, including generation losses |
| SCOP | Seasonal Coefficient of Performance — heat pump efficiency ratio |
| HDD | Heating Degree Days — cumulative measure of winter severity |
| PEF | Primary Energy Factor — country-specific electricity multiplier |
| CIRCUS | Connecting Initiatives for Rural Communities, Upscaling their Sustainable Energy |
| NZEB | Nearly Zero Energy Building |

---

*BER Automation Tool v1.0 — CIRCUS Interreg NWE Project*
*Munster Technological University | Environ 2026*
