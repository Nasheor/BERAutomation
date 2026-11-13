# BER Automation

Estimates a home's Building Energy Rating (BER) from its Eircode or address. The tool fetches
a satellite image and Street View photos, reads the building with an AI vision model, fills
gaps from Census 2022 Small Area data, and calculates the energy demand with the HWB method.
Built for the CIRCUS project (Interreg North-West Europe) at Munster Technological University.

## Run it

```
pip install -r requirements.txt
copy .env.example .env          # then fill in the API keys
streamlit run app/streamlit_app.py
python main.py pipeline "T12 K7AC"
python -m pytest -q
```

## Layout

| Path | Contents |
|---|---|
| `app/streamlit_app.py` | Web app (also the file Streamlit Cloud deploys) |
| `main.py` | Command-line entry point |
| `ber_automation/` | The package: `geospatial/` (geocoding, images, census), `vision/` (AI and OpenCV image reading), `ber_engine/` (HWB calculator, rating bands), `pipeline.py`, `models.py`, `config.py`, `data/` (census tables shipped with the package) |
| `scripts/` | `validate_daft.py` (pipeline versus assessor), `build_census_data.py` |
| `tests/` | Unit tests |
| `data/validation/` | Evaluation data. `daft/1–5.xlsx`: the Excel tool filled in by an assessor for five Cork homes |
| `docs/` | `DOCUMENTATION.md`, `country_data.md`, `test_addresses.md`, `diagrams/`, `plans/`, `images/` |
| `docs/reference/` | Source material: the Excel assessment tool with its guide and sources, the HWB guide, the DEAP manual |
| `paper/` | Paper draft (`main.tex`, `references.bib`) |
| `presentations/` | Past talks and demos: `environ_2026/`, `circus_demo_2026_03/` |
| `images/` | Logos used by the app and the slides |
| `output/` | Fetched images and validation reports (not in git) |

`CONTEXT.md` is the working record: calculation formulas, how each pipeline step works,
validation results, deployment and planned work.

Deployment files, which must stay where they are: `app/streamlit_app.py`, `requirements.txt`,
`packages.txt`, `.streamlit/config.toml`.
