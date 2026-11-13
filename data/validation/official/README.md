# Official-BER sample

`sample.csv` holds the homes used to compare the pipeline with official Building Energy
Ratings: one row per home. It is filled in by hand. Check it at any time with:

```
python scripts/check_official_sample.py
```

The check lists typing mistakes (for example a band that does not match the kWh value)
and shows how the sample is spread over counties, dwelling types, eras and bands.

## Which homes

- Houses only: detached, semi-detached or terraced. The pipeline does not handle apartments.
- The listing must show the Eircode, the BER band, the BER number and the energy value
  in kWh/m²/yr.
- Plan: about 250 homes in at least 4 counties, mixed by urban/rural, dwelling type and
  era, and not only the common bands (include A-rated and E to G homes).

## How to collect

1. Record the values from the listing by hand. Do not scrape; check the site's terms.
2. Look the BER number up on SEAI's public register (https://ndber.seai.ie) and confirm
   the band and kWh value. Set `register_checked` to `yes`.
3. Copy any further values the register shows (dwelling type, year of construction, floor
   area, heating) into the optional columns. Leave a cell empty when the value is not shown.

## Columns

Required:

| Column | Value |
|---|---|
| `id` | Your running number, unique |
| `eircode` | For example `T12 K7AC` |
| `county` | For example `Cork` |
| `settlement` | `urban` or `rural` |
| `listing_source` | Site the listing was on, for example `daft.ie` |
| `date_recorded` | Date you recorded it, `YYYY-MM-DD` |
| `ber_number` | The 9-digit BER number |
| `ber_band` | `A1` to `G` |
| `ber_kwh_m2_yr` | Energy value on the certificate, kWh/m²/yr |

Optional (from the certificate or register):

| Column | Value |
|---|---|
| `listing_url` | Link to the listing |
| `dwelling_type` | `detached`, `semi_detached` or `terraced` (end of terrace: `semi_detached`) |
| `year_built` | Year of construction |
| `floor_area_m2` | Total floor area, m² |
| `storeys` | 1 to 4 |
| `heating` | `oil_boiler`, `gas_boiler`, `biomass`, `electric_direct`, `heat_pump_air`, `heat_pump_ground`, `heat_pump_water` or `district_heating` |
| `register_checked` | `yes` or `no` |
| `notes` | Anything unusual (extension, recent retrofit, listing and register disagree) |

## Privacy

The file holds addresses of real homes. Keep it in the private repository. Anything
published from it uses anonymised attributes only (Small Area, not Eircode or address).
