# BER Automation — GEMINI.md

## Project Context
This project is an automated Building Energy Rating (BER) estimation tool. It uses Google Maps APIs for geospatial data and Anthropic's Claude Vision for building analysis. The core calculation follows the **Austrian HWB (Heizwaermebedarf)** method.

## Engineering Standards & Patterns

### 1. Thermal Engine (ber_engine)
- **Source of Truth**: All formulas and constants are derived from `docs/Building Assessment using Google Maps and Google Street View.xlsx`.
- **Methodology**: Annual steady-state energy balance ($Q_{heating} = Q_{loss} - Q_{gains}$).
- **Portability**: Keep `calculator.py` decoupled from vision logic to allow pure-thermal simulations.

### 2. Vision Pipeline (vision)
- **Dual-Method Footprint**: Always prefer `claude_analyzer.analyze_satellite` but maintain `footprint.py` (OpenCV) as a validation/fallback layer.
- **Multi-Angle Street View**: Use `fetch_streetview_images` (plural) to provide Claude with a 360° view of the target building.
- **Confidence Gating**: Only apply AI-derived classifications if `confidence >= 0.4`. Below this, use the safe defaults defined in `pipeline.py`.

### 3. Data Integrity
- **Models**: Use `ber_automation/models.py` for all data structures. All models are Pydantic v2.
- **Enums**: Strictly use the provided Enums (`BuildingType`, `ConstructionEpoch`, etc.) to ensure compatibility with lookup tables.

### 4. Async Execution
- All API-heavy operations (Geocoding, Imagery, Claude) MUST be `async`.
- Use `httpx.AsyncClient` for Google APIs and `anthropic.AsyncAnthropic` for Claude.

## Future Development Focus
1. **DEAP Methodology**: Implementation of the official Irish DEAP method as an alternative calculation mode.
2. **Segmentation Models**: Replacing OpenCV heuristics with a dedicated building segmentation model (e.g., SAM or custom U-Net).
3. **Caching**: Implementing a database (SQLite) to cache geocoding and vision results by Eircode/Address.
4. **Validation**: Continuous cross-referencing against the SEAI public BER dataset.

## Development Commands
- **Run App**: `streamlit run app/streamlit_app.py`
- **Run Tests**: `pytest`
- **CLI Pipeline**: `python main.py pipeline <ADDRESS>`
