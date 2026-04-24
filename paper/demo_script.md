# BER Automation Tool — Presenter Script
### CIRCUS Project Stakeholder Demo · March 2026

---

> **Setup checklist before you walk in:**
> - `presentation.html` open in Chrome, full-screen (F11)
> - Streamlit app running in a second tab: `python main.py app`
> - `test_addresses.md` open on phone or printed
> - Verify API keys work: `python main.py manual --length 10 --width 8 --storeys 2 --epoch before_1980 --heating oil_boiler`
> - Use ← → arrow keys to advance slides

---

## SLIDE 1 — Title

*[Wait for the room to settle. Count to five. Resist the urge to say "can everyone see my screen".]*

"Good morning. So — we've built a tool that looks at a building, figures out how leaky it is, and tells you how bad the owner's energy bills are.

We call it the BER Automation Tool. BER stands for Building Energy Rating — it's the A-to-G sticker on houses that tells you whether you're living in a well-insulated modern home or an expensive draughty box from 1972.

The goal is simple: you give it a postcode. Thirty seconds later, it gives you a rating, the annual CO₂ emissions, and what it would take to improve things. No spreadsheets. No manual measurement. No arguing with a satellite image ruler.

We support five countries across the CIRCUS consortium. Let's get into it."

---

## SLIDE 2 — The Problem

"Let me describe what BER assessment looks like today, because understanding the pain makes the solution much more satisfying.

To estimate the energy rating of a single building, a trained assessor currently has to:

Open Google Maps. Find the address. Use the 'Measure distance' tool to estimate how long and wide the building is — by clicking around the roof edge on a satellite image, praying there isn't a tree in the way. Then switch to Street View and visually decide: is this a 1970s semi-detached or a 1980s? Is that an oil tank in the garden or a wheelie bin? How many storeys? What kind of windows?

Then — and I'm not making this up — they type all of those estimates into an Excel spreadsheet. And read the answer out of a cell.

That's five manual steps per building. Five to ten minutes each. For an estate of 200 homes, you are looking at over sixteen hours of someone doing this. And then a different person looks at the same Street View image and decides it's a 1990s build, not 1980s, because the windows look slightly different to them.

The CIRCUS project needs to assess buildings at scale across five countries. This approach is not viable."

---

## SLIDE 3 — Solution Overview

"So here's what the tool does instead.

Five phases, all automated, running asynchronously. Phase one: geocode the postcode. Phase two: fetch a satellite image and — this is important — *four* Street View images at 90-degree intervals around the building. Not one. Four. Front, right, back, left.

Phase three: send all four images to Claude — Anthropic's AI — in a single request. Claude cross-references all the angles and classifies the building. It can spot the oil tank that's only visible from the back garden. It can see the shared party wall from the side. It's like giving an assessor four simultaneous vantage points instead of one.

Phase four: extract the building footprint from the satellite image. We use two independent methods — OpenCV computer vision and Claude's vision model — and then reconcile them. Because if there's one thing I've learned building this, it's that OpenCV will confidently identify a hedge as a building if you let it.

Phase five: run the HWB energy balance calculation and produce a BER band.

The whole thing in under 30 seconds. From postcode to rating."

---

## SLIDE 4 — System Architecture

"Here's the system architecture. I'll give you the quick tour — don't worry about memorising it.

On the left: the presentation layer. There's a Streamlit web app for the demo today, and a CLI for scripting and batch work.

In the middle: the BERPipeline orchestrator. This is the conductor — it calls everything in the right order, handles failures gracefully, and assembles the final result.

Then three specialist packages: Geospatial for geocoding and image fetching, Vision for the computer vision and AI analysis, and the BER Engine for the actual energy maths.

On the right, the two external dependencies: Google Maps — geocoding, satellite imagery, Street View — and the Anthropic Claude API.

Everything talks through strongly-typed Pydantic data models. If Claude returns something unexpected — malformed JSON, a philosophical essay instead of a building classification — the models catch it and the pipeline falls back to safe defaults. It never crashes. It just becomes slightly less precise, which it tells you about via a confidence score."

---

## SLIDE 5 — Pipeline Sequence

"This sequence diagram shows exactly what data flows where. Let me walk you through it.

The user enters an Eircode. The pipeline geocodes it — that's a Google API call that takes about 200 milliseconds. We get back coordinates.

Then we fetch imagery. In parallel: a satellite image at zoom level 20 — close enough that a 640×640 pixel image covers roughly a 57-metre square patch of ground — and four Street View images at 0, 90, 180, and 270 degree headings relative to the building.

Those four images go to Claude in a *single* API call. This matters both for cost and for quality — Claude can reason across all four views simultaneously rather than giving four independent assessments that you then have to aggregate yourself.

In parallel, the satellite image goes to OpenCV and Claude separately for footprint extraction. We get two independent dimension estimates and reconcile them.

Everything feeds into the HWB calculator. Out comes a BERResult: the band, the energy consumption per square metre, the CO₂, a full heat loss breakdown.

Total API calls for one Irish address: one Geocoding, one Static Maps, four Street View, one Claude for street view, one Claude for satellite. About €0.015 per address. For context, Google's free tier covers roughly 14,000 of these per month."

---

## SLIDE 6 — AI Vision Deep Dive

"Let me go deeper on the AI and vision components because this is where most of the interesting engineering lives.

For Street View: we fetch four images centred on the auto-computed bearing from the road to the building. Claude receives all four in one request with a structured prompt that explains the five Irish construction eras with visual identifiers — what a 1970s wall render looks like versus a 1990s one, what a pre-1980 sash window looks like, and so on. Claude outputs JSON: epoch, building type, storeys, heating system guess, and a confidence score between 0 and 1.

That confidence score is the critical bit. We gate on it. If Claude reports confidence below 0.4 — which happens when the building is behind a hedge, in a new development without Street View coverage, or the image is a close-up of someone's front gate — we don't use the classification. We fall back to conservative defaults. The philosophy is: wrong data is worse than no data.

For satellite footprint: two tiers. OpenCV runs a pipeline of bilateral filtering, CLAHE contrast enhancement, Canny edge detection, contour scoring by area, solidity, centrality, and rectangularity. It returns a length and width in metres — converted from pixels using the Web Mercator scale formula, which accounts for the cosine of latitude. At Dublin's latitude, zoom level 20 gives about 0.09 metres per pixel. Claude runs independently with the same image plus the computed scale and context about what type of building to expect. We reconcile: agree within 30% and we use Claude's result and bump the confidence. Disagree and we trust Claude. Claude fails and we trust OpenCV. Both fail and we use 10 × 8 metres — which is, for better or worse, statistically a reasonable Irish house."

---

## SLIDE 7 — HWB Calculation

"The energy calculation uses the Austrian HWB method — Heizwärmebedarf, which translates literally as 'heating heat demand', because German compounds are a force of nature.

The core equation: heating demand equals transmission losses plus ventilation losses, minus internal gains, minus solar gains. It is a steady-state annual energy balance. Simple, transparent, and eminently auditable — every formula, constant, and lookup table in the code traces directly back to a specific cell in the Excel tool developed by Benjamin Kaiser at MTU.

Transmission losses: how much heat leaks through the walls, roof, floor, and windows. This is dominated by U-values, which are epoch-specific. A pre-1980 wall has a U-value of 1.2 watts per square metre kelvin. A post-2010 wall is 0.22. That's nearly six times better insulation. Windows are even more dramatic — 3.0 for old single glazing down to 1.0 for modern double glazing. There's also a thermal bridge supplement for older buildings because the edges and corners leak disproportionately.

Ventilation losses: we assume 0.4 air changes per hour — a standard infiltration rate for an unventilated building. Ireland with its 2,149 heating degree days makes this hurt considerably. Germany is almost identical. France is noticeably gentler at 1,462.

Internal gains: 3.75 watts per square metre of net floor area from occupants, lighting, and appliances. Solar gains: window area times orientation times irradiance times glazing transmittance times shading and frame factors. These gains partially offset the losses — but only partially, given Irish weather.

The result is annual heating demand in kWh. Divide by gross floor area and you get HWB in kWh/m²/year. Apply heating system efficiency, add hot water demand, multiply by primary energy factor, look up the band. Done."

---

## SLIDE 8 — Output and Retrofit

"Here's what the tool actually produces.

A BER band — A1 through G — the primary energy consumption in kWh per square metre per year, annual CO₂ in kilograms, and a full heat loss breakdown showing exactly where the energy is going. For an old poorly-insulated house, it's almost always transmission through the walls and windows.

As a concrete example: a pre-1980 detached house with an oil boiler — which is a very significant fraction of the Irish housing stock — comes out around band D2. About 286 kWh/m²/year. Around 4,100 kg of CO₂ per year.

The retrofit model is where this gets interesting for CIRCUS. You specify wall insulation — we add R-value using conductivity 0.035 W/mK, standard mineral wool — roof insulation, window replacement by target U-value, and an optional heating system upgrade. The tool recalculates everything with the overlay U-values applied.

That D2 house, with 12 cm wall insulation, 20 cm roof insulation, new windows at U=1.0, and an air source heat pump replacing the oil boiler, reaches band B1. That is a jump of five BER bands. More than half the energy consumption eliminated. And the calculation shows you exactly what each intervention contributes."

---

## SLIDE 9 — CIRCUS Country Coverage

"The tool supports all five CIRCUS partner countries because the HWB engine has country-specific climate data baked in.

Ireland and Germany have almost identical heating demand — around 2,150 heating degree days — which is perhaps why we get on so well. France is noticeably milder, and Belgium and the Netherlands sit in the middle. The solar irradiance data is orientation-specific per country, so the solar gain calculation is properly calibrated for each location.

For Ireland, the full automated pipeline works today — enter an Eircode and walk away. For the other four countries, we use Manual Input mode in the Streamlit app: you enter the building parameters, select the country, and the correct climate data is applied automatically.

Extending the geocoding and image pipeline to support street addresses in the other countries is technically straightforward — Google Maps APIs work globally. It's on the roadmap as a high priority because it unlocks the same one-click workflow for our Belgian, French, German, and Dutch partners."

---

## SLIDE 10 — Live Demo

*[Switch to the Streamlit app now.]*

"Let me show you this working. I'm switching to the app.

I'll start with the full automated pipeline — an Irish Eircode.

*[Enter the first test address from `test_addresses.md` — suggested: IE-1, D14 V6K2.]*

I'm entering this Eircode and running. You can watch the pipeline status update: geocoding... fetching imagery... running street view analysis... extracting footprint... calculating.

Here are the satellite and Street View images. These are the actual images the AI is analysing. You can see why four angles matter — the front view might show a nice hedge, but the 90-degree view shows the side extension, and the 270-degree might show the back garden with whatever heating kit is sitting out there.

Claude has come back with: *[read result aloud — epoch, building type, storeys, heating, confidence]*. The footprint extraction gives us *[length × width]* metres.

And the final result: *[BER band]*, *[kWh/m²/year]*, *[CO₂ kg/year]*.

*[Enable retrofit.]*

Now let me turn on the retrofit — I'll add standard wall and roof insulation and upgrade the heating system to a heat pump. Before: *[Band X]*. After: *[Band Y]*. That's a *[N]*-band improvement in one click.

*[Switch to Manual mode — suggested: DE-1, Germany pre-1980 detached.]*

Let me show Manual mode quickly with a German scenario. I'll select Germany, enter the parameters for a pre-1980 detached house in Cologne. Note that the tool automatically applies German HDD — 2,157 heating degree days, almost identical to Ireland. The result comes out in the same format as the Irish calculation, making cross-country comparison straightforward."

---

## SLIDE 11 — Limitations and Roadmap

"I want to be transparent about where the tool is today, because it would be easy to demo only the nice cases.

The most significant limitation: this is the HWB method, not the official DEAP method used for Irish BER certificates. So these are estimates — useful for screening, comparison, and prioritisation — but not certifiable ratings. The next step is to validate against the SEAI's public BER database, which has over 400,000 rated buildings, to understand how close we are and where the systematic biases are.

The vision pipeline has known failure modes. OpenCV contour detection on satellite imagery is genuinely difficult. Vegetation, shadows, irregular rooflines, adjacent buildings — all of these can throw it. We've mitigated this significantly with the two-tier Claude plus OpenCV approach and the confidence gating, but you'll occasionally get a footprint that's measuring a shed rather than a house. Claude's cross-check catches most of these, but not all.

And Claude's confidence is self-reported by the model. A confidence of 0.82 doesn't mean 82% accuracy in a formal statistical sense — it means Claude was fairly certain about what it saw. The 0.4 threshold for accepting the classification is based on qualitative testing, not a formal calibration exercise against labelled data.

On the roadmap: highest priority is validating against the SEAI dataset and extending geocoding to all CIRCUS countries. Medium priority is replacing OpenCV heuristics with a building segmentation model trained on actual aerial building footprint data — that would be a step change in accuracy. And longer term, adding the DEAP calculation method alongside HWB for cases where official-equivalent results are needed."

---

## SLIDE 12 — Q&A

"That's the demo. Sixty-three automated tests passing, five pipeline phases, five CIRCUS countries. Questions?"

---

## Anticipated Questions & Suggested Answers

**"How accurate is it actually?"**
> "We don't have a hard number yet — validating against the SEAI dataset is the immediate next step. Qualitatively, our test cases produce results in the right ballpark for known building types. The biases we're most worried about are post-2010 buildings where Irish Part L requirements differ from the Austrian U-values we're using, and any building where Street View gives Claude a view of a hedge instead of a facade. The SEAI validation will give us hard numbers on both."

**"What does it cost per address?"**
> "About €0.015 per Irish address end-to-end — split between Google APIs and the Claude Vision call. Google's $200/month free tier covers around 14,000 pipeline runs. For CIRCUS-scale assessment across thousands of buildings, the cost is negligible compared to assessor time."

**"Why four Street View angles? Doesn't that quadruple the Claude cost?"**
> "It increases the token count, but we send all four images in a single Claude request rather than four separate calls. The main overhead is image tokens. And the accuracy improvement is substantial — oil tanks, heat pump units, and shared party walls are frequently visible from only one angle. For the gain in classification quality, the extra cost is absolutely worth it."

**"Can it handle flats or apartments?"**
> "Not well currently. The pipeline models a building as a single rectangular box, which maps well to houses. Apartments need per-unit reasoning — which flat in the block, what floor, shared corridors. It's on the medium-priority roadmap."

**"What if Street View coverage doesn't exist for an address?"**
> "The pipeline catches the failure and continues with defaults — detached, pre-1980, 2 storeys, gas boiler. It still produces a result, flagging that street view analysis wasn't available. The user can override any of those defaults in the UI. Less accurate, but transparent about it."

**"Why HWB and not DEAP?"**
> "The Excel tool this is based on uses HWB — designed for rapid comparative assessment across European countries, not Irish certification. HWB is simpler, transparent, and well-suited to screening-level work. DEAP is significantly more complex, Ireland-specific, and requires additional input data we can't easily extract from imagery. We plan to add it as a precision mode alongside the rapid HWB screening estimate."

**"Is this open source? Can partners use it?"**
> "The code is in the CIRCUS project repository. It depends on commercial APIs — Google Maps and Anthropic — so partners would need their own keys. Setup takes about 15 minutes following the guide in the documentation. I'm happy to walk anyone through it."

---

*End of script.*
