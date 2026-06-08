In# BER Automation: Estimating Building Energy Ratings at Scale Using AI
## Environ 2026 Conference Presentation

**Presenter:** Avinash Nagarajan, Munster Technological University
**Project:** CIRCUS — Connecting Initiatives for Rural Communities, Upscaling their Sustainable Energy (Interreg North-West Europe)
**Duration:** 10 minutes
**Format:** Each slide includes bullet-point content and full speaker notes.

---

## Slide 1 — Title

**Content:**
- **BER Automation: Estimating Building Energy Ratings at Scale Using AI**
- Avinash Nagarajan | Munster Technological University
- CIRCUS Interreg North-West Europe Programme
- Environ 2026

**Visual suggestion:** Clean title slide with CIRCUS Interreg NWE and MTU logos. Subtle background featuring a satellite image of a residential neighbourhood with an overlay of building contours.

**Speaker notes:**
Good morning. My name is Avinash Nagarajan, representing the CIRCUS Interreg North-West Europe project at Munster Technological University. Today, I am excited to demonstrate a novel open-source tool that estimates the energy performance of residential buildings across eight European countries in under 30 seconds—using only a postal address. I will walk you through the AI pipeline powering this tool and discuss how it addresses the critical challenge of decarbonising our housing stock at scale.

---

## Slide 2 — The Challenge of Scale

**Content:**
- Buildings consume **40% of total energy** in the EU.
- Energy Performance Certificates (EPCs / BERs) are essential for targeting retrofits.
- **The Bottleneck:**
  - Official EPCs require a 1–3 hour site visit by a qualified assessor.
  - Costs range from **€150 to €500 per property**.
- **Impact:** Community energy groups and local authorities cannot afford to pre-assess entire neighbourhoods to find the worst-performing homes.

**Visual suggestion:** A bold split slide. On the left, the 40% energy statistic. On the right, an icon of a house with a €500 price tag and a "No Access" warning sign, representing the barrier to entry for community-wide screening.

**Speaker notes:**
To set the scene: buildings are responsible for roughly forty percent of all energy consumption in the EU. If we are to meet our 2050 climate targets, mass retrofitting is non-negotiable. The primary tool we have to guide this is the Energy Performance Certificate—the BER in Ireland, the DPE in France, the Energieausweis in Germany. 

The problem is scalability. Generating an official EPC requires a qualified assessor to physically visit the property, which costs hundreds of euros per house. For a community energy organisation trying to prioritise which homes in a village need the most urgent help, this cost is prohibitive. They are effectively flying blind. We needed a way to screen and prioritise homes at near-zero marginal cost.

---

## Slide 3 — An Automated, AI-Driven Solution

**Content:**
- **The Concept:** Can we automate the physical survey using publicly available data?
- **The Ingredients:**
  - Ubiquitous satellite imagery (building footprint).
  - Google Street View (exterior photographic survey).
  - Multimodal Large Language Models (Claude 3.5 Sonnet) for visual feature extraction.
  - Proven energy physics (Austrian HWB calculation method).
- **The Result:** An automated pipeline that outputs a comprehensive energy profile, including native EPC bands and retrofit pathways.

**Visual suggestion:** A dynamic 2x2 grid showing a satellite roof view, a Street View facade, a snippet of Claude AI JSON output, and the final BER rating dial.

**Speaker notes:**
The solution lies in combining ubiquitous geospatial data with recent breakthroughs in artificial intelligence. Every address in North-West Europe is visible via high-resolution satellite imagery, and Google Street View provides a comprehensive exterior photographic survey for most streets.

By passing these images to a multimodal AI—specifically Claude 3.5 Sonnet—we can automate the "visual inspection" phase of an energy assessment. The AI identifies the construction era, building type, and heating system. We then feed those parameters into a rigorous, established thermal calculation engine based on the Austrian HWB method. The result is a fully automated, end-to-end energy assessment tool.

---

## Slide 4 — The Pipeline Architecture

**Content:**
- **Phase 1: Geocoding** → Address to GPS coordinates.
- **Phase 2: Imagery** → Satellite (zoom 20) + 4x Street View images (0°, 90°, 180°, 270°).
- **Phase 3: AI Survey** → Claude 3.5 cross-references all 4 views simultaneously.
- **Phase 4: Footprint** → Dual-method extraction (Claude AI primary, OpenCV fallback).
- **Phase 5: Thermal Engine** → HWB steady-state annual balance calculation.

**Visual suggestion:** A horizontal flowchart mapping the five phases, starting from a user entering an address to the final BER certificate output.

**Speaker notes:**
Let’s look under the hood at the pipeline architecture. When a user enters an address, Phase 1 geocodes it. Phase 2 fetches the imagery. Crucially, we don't just fetch one Street View image; we compute the exact geodesic bearing from the camera to the building and fetch four images at 90-degree intervals, giving us a 360-degree exterior survey.

In Phase 3, the AI analyses these images. Phase 4 extracts the building dimensions from the satellite view. Finally, Phase 5 runs the thermal physics calculation to determine the final energy demand and CO2 emissions. Let's dive deeper into the AI and footprint extraction phases, as they represent the most significant technical hurdles we've overcome.

---

## Slide 5 — Advanced AI Vision & Confidence Gating

**Content:**
- **Multi-Angle Cross-Referencing:**
  - 4 images sent to Claude in a single request.
  - Detects hidden features (e.g., rear heat pumps, side oil tanks, shared party walls).
- **Country-Specific Prompts:**
  - Models adapt to local typologies (e.g., district heating in NL vs. oil tanks in rural IE).
- **Confidence Gating:**
  - AI self-reports confidence (0.0 to 1.0).
  - **Rule:** If confidence < 0.4 (due to trees, poor angles), the tool safely degrades to conservative defaults rather than propagating hallucinations.

**Visual suggestion:** A composite showing four Street View angles of the same house, highlighting a heat pump visible only in the rear view. Beside it, a "Confidence Score: 0.85" badge.

**Speaker notes:**
The most powerful aspect of the AI survey is multi-angle cross-referencing. By sending all four Street View images to Claude simultaneously, the model acts like a human surveyor walking around the property. It might spot an oil tank hidden at the back, or confirm a shared party wall only visible from the side.

We've also embedded country-specific architectural knowledge into the prompts, helping the AI distinguish between a 1980s German blockwork building and a 1980s Irish cavity-wall home. Crucially, we implemented "Confidence Gating." If the building is blocked by large trees and the AI returns a confidence score below 0.4, the pipeline ignores the AI and falls back to safe, conservative defaults. This ensures we never propagate poor-quality guesses into the final energy calculation.

---

## Slide 6 — Dual-Method Footprint Extraction

**Content:**
- **Primary:** Claude Vision (Context-Aware)
  - Receives GPS scale (metres per pixel).
  - Uses Street View context to measure only one unit in a terraced row.
- **Secondary:** OpenCV (Algorithmic)
  - Canny edge detection and contour scoring.
- **Reconciliation:**
  - If both agree within 30%, confidence is boosted.
  - OpenCV acts as a robust fallback if AI struggles with image complexity.

**Visual suggestion:** A satellite image with two overlapping bounding boxes: one generated by Claude (green) and one by OpenCV (blue). Text notes: "Agreement within 15% -> Confidence Boosted."

**Speaker notes:**
Extracting the building's physical dimensions from a satellite image is notoriously difficult. To solve this, we use a dual-method approach. Our primary engine is Claude Vision, which receives the exact scale in metres-per-pixel. Because Claude is context-aware, if it knows from the Street View analysis that the building is part of a 4-unit terrace, it knows to measure just one unit, not the entire roofline.

As a safety net, we run an independent OpenCV edge-detection algorithm. If both the AI and the deterministic algorithm agree on the area within 30%, we boost the overall confidence score. If they disagree, we trust the AI. If the AI fails entirely, OpenCV serves as a reliable fallback.

---

## Slide 7 — The Thermal Calculation Engine

**Content:**
- **Method:** HWB (Heizwärmebedarf) annual heating balance.
- **Standards-Based:** Grounded in ISO 13790 steady-state monthly balance.
- **The Equation:**
  - *Heating Demand = (Transmission + Ventilation Losses) – (Solar + Internal Gains)*
- **Localised Climate Data:**
  - Heating Degree Days (winter severity).
  - Solar irradiance (by orientation).
  - National Primary Energy Factors (PEF).

**Visual suggestion:** A clean, balanced scale graphic. On the "Losses" side: Transmission (walls, windows) and Ventilation. On the "Gains" side: Solar (sun icon) and Internal (people/appliances).

**Speaker notes:**
Once we have the building's era, type, dimensions, and heating system, we pass it to the thermal engine. We use the Austrian HWB method, which is based on the ISO 13790 standard—the same physics underpinning professional EPC software.

The calculation is an annual energy balance: we calculate transmission losses through the fabric and ventilation losses, and subtract usable solar gains and internal gains from occupants. We divide that by the heating system's efficiency to get final energy. Every input here is localised. We use specific Heating Degree Days, solar irradiance data, and national Primary Energy Factors for all eight supported countries, ensuring the physics reflect local reality.

---

## Slide 8 — Cross-Border Policy Insights: Grid CO₂

**Content:**
- The impact of a heat pump retrofit depends entirely on the local grid.
- **Grid CO₂ Intensity (g/kWh):**
  - Switzerland: **29** | France: **52** | Ireland: **210** | Germany: **385**
- **CO₂ Reduction vs. Gas Boiler (Heat Pump SCOP 3.5):**
  - France: **~89% reduction**
  - Germany: **~49% reduction**
- **Takeaway:** Retrofit advice must be localised. In coal-heavy grids, insulation-first strategies may yield better immediate CO₂ savings than rapid electrification.

**Visual suggestion:** A bar chart showing grid CO₂ intensity by country, colour-coded from green (Switzerland) to red (Germany). Next to it, the percentage drop in emissions for a standard heat pump install in France vs. Germany.

**Speaker notes:**
Because this tool operates across eight countries, it surfaces critical policy insights. The most striking is the impact of electricity grid carbon intensity on retrofit strategy. 

If you install a heat pump in a French home, powered largely by nuclear energy, you cut the home's heating CO2 emissions by nearly 90% compared to a gas boiler. If you install that exact same heat pump in a German home, powered by a mix including coal, you only cut emissions by about 49%. 

For community groups planning retrofit campaigns, this is vital data. In France or Switzerland, mass heat pump rollouts make immediate climate sense. In Germany or the Netherlands, an "insulation-first" approach might be more effective for immediate CO2 reduction while waiting for the grid to decarbonise. The tool makes this visible for every single assessment.

---

## Slide 10 — Validation & Next Steps

**Content:**
- **Accuracy & Limitations:**
  - Designed for *screening*, not official certification.
  - Accuracy: ±1–2 BER bands (with good Street View coverage).
- **Ongoing Validation:**
  - Cross-referencing against the SEAI BER public database (400,000+ records) to calibrate confidence.
- **Future Roadmap:**
  - Implementing the official Irish DEAP methodology as an alternative mode.
  - Deep-learning segmentation models (e.g., SAM) for more precise footprints.
  - Batch-processing for estate-wide CSV uploads.
- **Collaborate with us:** CIRCUS Partners, Local Authorities, SEAI.

**Visual suggestion:** A 3-column footer. Left: "Screening Only" warning icon. Middle: SEAI Validation graphic. Right: "Next Steps" checklist. Contact email at the bottom.

**Speaker notes:**
To conclude, I must emphasize that this is a screening tool. It is not a replacement for a certified EPC for legal or financial purposes. In areas with clear Street View coverage, we expect it to be accurate within 1 to 2 BER bands. 

We are currently validating the tool against the SEAI's database of 400,000 official BER certificates to fine-tune our models and identify systemic biases. Moving forward, we plan to implement the official Irish DEAP methodology alongside the HWB method, upgrade our footprint extraction to use advanced segmentation models, and enable bulk CSV processing so communities can assess hundreds of homes at the click of a button.

The code is open source, and we are actively looking for collaboration with researchers, local authorities, and policymakers. Thank you very much for your time.

---

*BER Automation Tool v1.0 — CIRCUS Interreg NWE Project*
*Munster Technological University | Environ 2026*
