# Plan: Mistral as a second vision model, and the paper strategy

Status: saved 2026-11-12, **not implemented**. Deployment for supervisor feedback comes first (see CONTEXT.md, "Deployment").

## Context

The BER tool reads satellite and Street View images with one vision model, Claude, hard-wired in
`ber_automation/vision/claude_analyzer.py`. You want users to choose between Claude and Mistral,
and you want a paper on how well AI estimates a home's BER compared with its official rating.
You are a researcher on a funded project (CIRCUS, MTU), want the paper to support a move into
AI/ML engineering roles, and aim to submit in about 6 months.

Two findings shape the plan:

- **No official BERs exist in the repo.** Every accuracy figure so far compares the AI with one
  human assessor on 5 Cork houses, using the same simplified calculator.
- **The calculator is the Austrian HWB method, not DEAP** (the official Irish method). A band
  mismatch against an official BER can therefore come from the calculator, not the AI. The paper
  has to separate the two, or reviewers will.

Part A is the code change to approve. Part B is advice; it needs no approval and no code yet.

---

## Part A — Add Mistral, user-selectable (implementation)

### Approach

Keep one analysis module and add a thin provider switch inside it. The three functions that call
the model (`analyze_streetview`, `analyze_satellite`, `detect_windows`) repeat the same
"build content → call Claude → strip code fence" block; that block becomes one private helper
that dispatches on the provider. Prompts and all parsing stay identical for both models, which
is also what a fair comparison in the paper needs.

Mistral is called over its REST API with `httpx` (already a dependency, already mocked with
`respx` in tests), not the `mistralai` SDK. Reason: no new dependency, and the SDK's import
path has changed between versions.

`claude_analyzer.py` keeps its name and `FootprintResult.source` keeps the value
`"claude_vision"` (pipeline logic and tests depend on it; the app already labels it
"AI Vision"). The model actually used is recorded in two new result fields instead.

### Changes

1. **`ber_automation/config.py`** — new settings: `llm_provider: str = "claude"` (`LLM_PROVIDER`),
   `mistral_api_key: str = ""`, `mistral_model: str = "mistral-large-2512"`,
   `mistral_temperature: float | None = 0.0`. `MISTRAL_API_KEY` is already in `.env` but ignored
   today. Confirm the model ID is vision-capable with `GET /v1/models` before fixing the default.

2. **New `ber_automation/vision/providers.py`**
   - `PROVIDERS = ("claude", "mistral")`, display labels, `resolve_provider(provider, settings)`
     (None → `settings.llm_provider` when it is a valid string, else `"claude"`; this keeps the
     existing tests, whose settings are `MagicMock`s, on Claude), `model_name(provider, settings)`,
     `available_providers(settings)` (those with an API key).
   - `async mistral_complete(settings, parts) -> str`: POST
     `https://api.mistral.ai/v1/chat/completions` with text parts and images as
     `{"type": "image_url", "image_url": "data:image/jpeg;base64,..."}`,
     `response_format={"type": "json_object"}`, temperature from settings; one retry on 429/5xx;
     returns the reply text (string or joined text chunks).

3. **`ber_automation/vision/claude_analyzer.py`**
   - New private `_complete(parts, provider)`: `parts` is an ordered list of text strings and
     image paths. Claude branch builds the same content blocks and `messages.create(...)` kwargs
     as today (existing test assertions on the request stay valid; `anthropic` stays imported
     here so existing patches work). Mistral branch calls `providers.mistral_complete`.
   - Fold the three copies of the media-type map and the code-fence strip into this path.
   - Add `provider: str | None = None` to the three public functions. Missing key raises
     `"<PROVIDER>_API_KEY not configured"` (`detect_windows` still returns `[]`).
   - "Failed to parse Claude response" → "Failed to parse model response".

4. **`ber_automation/models.py`** — `PipelineResult.llm_provider` and `llm_model` (both optional).

5. **`ber_automation/pipeline.py`** — `BERPipeline(output_dir=None, provider=None)`; pass
   `provider` to the three analyzer calls (lines ~128, ~160, ~258); set the two new result
   fields in `_run_vision_and_calc`; error text names the provider
   ("AI analysis failed (Mistral): ...").

6. **`app/streamlit_app.py`** — an "AI model" selectbox beside the country selector, listing
   providers that have a key; pass the choice into both `BERPipeline(...)` constructions (run at
   ~1090 and re-analyse at ~1198); show "Analysed with <provider> (<model>)" under
   "AI Building Analysis".

7. **`main.py`** — `--provider {claude,mistral}` on the `pipeline` subcommand.

8. **`scripts/validate_daft.py`** — `--provider {claude,mistral,both}`. Reports record provider
   and model. Claude keeps `report.json`; Mistral writes `report_mistral.json`. With `both`, the
   second model re-analyses the images fetched for the first (`reanalyse()`), so both see
   identical inputs.

9. **`.env.example`** — add `MISTRAL_API_KEY`, `LLM_PROVIDER`, `MISTRAL_MODEL`, and the missing
   `MAPBOX_ACCESS_TOKEN`.

10. **Tests** — new `tests/test_llm_providers.py` (respx): Mistral request shape (labels before
    images, data-URI images, JSON mode, model, temperature), string and chunk-list replies,
    missing key, 429 retry, provider resolution. Add one `analyze_satellite(provider="mistral")`
    case to `tests/test_satellite_analysis.py` showing the same JSON gives the same footprint.
    Existing Claude tests must pass unchanged.

11. **Docs** — CONTEXT.md: provider section and how to run a comparison; fix the stale model
    name in `docs/DOCUMENTATION.md`.

### Verification

1. `.venv\Scripts\python.exe -m pytest -q` — all 121 existing tests plus the new ones pass.
2. Live smoke test: `python main.py pipeline "T12 K7AC" --provider mistral` returns a footprint
   and classification, with `llm_provider`/`llm_model` in the result.
3. `python scripts/validate_daft.py --provider both --runs 3` (about 45 calls per model): compare
   `report.json` and `report_mistral.json`; record the result in CONTEXT.md as a new "Part B".
4. Streamlit, started from `C:\Users\nagar\PyCharmProjects\BERAutomation`: run one address with
   each model; check the caption and that "Re-analyse" uses the selected model.

Unknown until step 3: how well Mistral places roof corners in pixel coordinates. Prompts stay
identical for both models; a weak result is a finding for the paper, not something to tune away
silently.

---

## Part B — The paper (advice)

### What to write

**Working title:** "How much do images add? Benchmarking vision-language models against official
Building Energy Ratings in Ireland."

**The angle that fits you and the goal.** For AI/ML engineering roles, the valuable skill to show
is rigorous evaluation of an LLM system on a real task, not "we built a tool". The repo already
holds the unusual ingredients: a physics calculator in the loop, open census priors, two
providers, and measured run-to-run instability.

**Research questions**
1. How close is an image-only pipeline to the official BER band and kWh/m²/yr?
2. What do the images add over open statistics alone? In the last validation the census, not
   the model, decided heating and home count in all 15 runs. A census-only baseline is the first
   thing a reviewer will ask for.
3. Do two commercial models (Claude, Mistral) differ in accuracy, stability across repeated
   runs, cost and speed? Mistral being EU-hosted is a relevant point for public-sector use.
4. Do the models know when they are wrong (confidence and "I could not see it" flags versus
   actual error)?

**Design that survives review**
- **Separate method error from perception error.** Compare at three levels: (a) AI-read inputs
  versus certificate inputs (type, year, floor area, storeys, heating); (b) HWB on the
  certificate's inputs versus the official BER (calculator error alone); (c) full pipeline
  versus official BER.
- **Baselines:** always-predict-the-commonest-band; census-only; images-only; images + census.
- **Sample:** about 250 homes across at least 4 counties, balanced by urban/rural, dwelling
  type and era. n = 5 supports no claim.
- **Reliability:** 3 runs per home per model; report agreement, not only accuracy.

**Official BER source (recommended)**
- **Primary:** property listings show address, BER band, BER number and kWh/m²/yr. Collect them
  by hand into a spreadsheet (no scraping; check the sites' terms). Then look each BER number up
  on SEAI's register, which returns the certificate extract. Check on the first few lookups that
  the extract gives floor area, year built, type and heating; I could not confirm the fields.
- **Fallback and baseline data:** SEAI's anonymised BER Research Tool (bulk download, research
  use allowed with acknowledgement) for population baselines and to calibrate HWB against DEAP.
- Publish only anonymised attributes (Small Area, not addresses).

**Closest prior work to position against:** zero-shot VLM classification of UK EPC grades from
street view (ASCE i3CE 2025); Peng & Bentley, staged VLM EPC pre-assessment (arXiv 2603.00115,
2026); Sheng et al. 2022 (Street View + EPC, CNN). Your differences: official Irish
certificates, an interpretable calculator instead of direct label prediction, the census
ablation, two providers, and reliability measurement.

**Fix before reusing `paper/main.tex`:** results tables are placeholders; the method section is
out of date (Mapbox scale, one camera turned four ways, census priors); the CIRCUS acronym is
expanded wrongly; several 2024–25 citations need checking.

### Where to publish

Dates marked "pattern" are inferred from the previous edition; the 2027 calls are not out yet.

| Venue | Why | Dates |
|---|---|---|
| **ACM SIGSPATIAL 2027** (main or GeoAI workshop) — primary | ACM proceedings; geospatial + ML audience; fits a 6-month timeline | Pattern: papers late May (2026: 22 May) |
| **ACM BuildSys / e-Energy 2027** | Best-known ACM venues for ML in buildings; strong signal for engineering roles | Pattern: papers late Jan (2026: 22 Jan). Likely too soon; take it if the 2027 date is later |
| **Climate Change AI workshop, NeurIPS 2027** | Short paper; strongest ML brand; can extend into *Environmental Data Science* | Pattern: late Aug (2026: 29 Aug) |
| **SBE27 Delft** (5–7 Oct 2027) | Confirmed dates; IOP proceedings; suits CIRCUS dissemination | Abstract 18 Dec 2026; full paper 16 Apr 2027 |
| **EG-ICE 2027** | Computing-in-engineering community | Pattern: abstract mid-Dec, paper ~1 Apr |
| **Journal extension:** *Energy and AI*; *Data-Centric Engineering* (BuildSys collection) | Longer version with the full dataset | Rolling |

Missed for 2027: Building Simulation 2027 (abstracts closed 15 Aug 2026) and the CIBSE Technical
Symposium (call closed).

**Suggested route:** SBE27 abstract now (cheap, confirmed, covers the project) → SIGSPATIAL
full paper as the main ML-facing publication → CCAI short paper or journal extension. Keep the
SBE27 and SIGSPATIAL contributions distinct (practice results versus benchmark and method) to
avoid duplicate submission.

### Follow-up work for the paper (not part of this change)

- A spreadsheet format for the official-BER sample and a `scripts/validate_official.py` that
  runs both models, the baselines and the three-level comparison.
- Census-only and images-only switches in the pipeline for the ablation.

### Sources

- Mistral vision docs: https://docs.mistral.ai/capabilities/vision
- SBE27 Delft call: https://sbe27delft.4tu.nl/Call%20for%20Papers/
- BuildSys / e-Energy 2026 dates: https://www.myhuiban.com/conference/1783
- SIGSPATIAL 2026: https://sigspatial2026.sigspatial.org/
- CCAI NeurIPS 2026 workshop: https://www.climatechange.ai/events/neurips2026
- EG-ICE: https://eg-ice.org/
- Building Simulation 2027: https://energy-models.com/forum/building-simulation-2027-29-aug-1-sep-2027-vienna-abstract-deadline-15-aug-2026
- SEAI BER data: https://www.seai.ie/ber/support-for-ber-assessors/ber-assessment-data ; https://ndber.seai.ie/BERResearchTool/
- Prior work: https://www.repository.cam.ac.uk/handle/1810/383138 ; https://arxiv.org/abs/2603.00115 ; https://eprints.whiterose.ac.uk/191089
