# Raw-data verification report

Written by `scripts/verify_society_raw_data.py` on 2026-11-08 13:12:42 UTC. **This file is generated; it is not edited by hand.** Re-create it with `python scripts/verify_society_end_to_end.py --check-subset` (starts a throw-away API and includes the live-API comparison) or with `python scripts/verify_society_raw_data.py` (files only).

> **What the data are.** BDG2 buildings labelled `Lodging/residential` include **student residence halls**. Of the 73 buildings used in the communities below, 56 labelled `Dormitory`, 9 labelled `Other - Lodging/Residential`, 8 labelled `Housing`. BDG2 does not describe the `Housing` and `Other - Lodging/Residential` labels further, so nothing here claims that they are family flats either. Each community is a group of real whole-building electricity meters. It is **not** data of family flats, **not** data of individual homes and **not** data of a registered housing society.

## 1. Verdict and inputs

127 of 127 checks passed: **all checks passed**.

| Item | Value |
|---|---|
| Raw input mode | `full` (full official files) |
| Raw period / hours / meters in the file | 2016-01-01 00:00:00 to 2017-12-31 23:00:00 / 17,544 / 1,578 |
| Comparison with the running API | run against http://127.0.0.1:38345 |
| Subset compared with the full official file | run |
| Verifier | `scripts/verify_society_raw_data.py`, SHA-256 `4381ff1bd8cc840d...` ; Python 3.11.15, pandas 3.1.0, numpy 2.4.6 |
| Source | Building Data Genome Project 2 (BDG2), Creative Commons Attribution-ShareAlike 4.0 (CC BY-SA 4.0), as stated in the LICENSE file of the repository |

SHA-256 of the input files as hashed in this run:

| File | SHA-256 | Check |
|---|---|---|
| `data/metadata/metadata.csv` | `992d0b29f24f96ad4332bc4dbb534b7bdd7dd2689aad093f94e93068ecddca02` | matches |
| `data/weather/weather.csv` | `a8189f1c6acdf3b9933a9e6354b8e7c1278cd56a7075929623a17565d44f04bd` | matches |
| `data/meters/raw/electricity.csv` | `039d909d8981e2d69eaeb366144e6ab7e84fa5e7e216aee42bddd95384a66418` | matches |
| `LICENSE` | `1df42bd84afc40e676a0cbf3d34e30e5151e3f0d995a68b406178dad3b0e23dc` | matches |
| `README.md` | `7f2a1539a17c3183fbfe69b06deea1d976ec9a4c92d34c4ad8d23e5b24fe8ca3` | matches |

## 2. The four data layers

| Layer | What it is | Verified here? |
|---|---|---|
| 1. Raw readings | BDG2 `electricity.csv` exactly as published, one value per meter and hour (kWh in that hour = average kW) | hashed (section 1) |
| 2. Cleaned readings | The raw readings with invalid ones set to missing. A reading is never changed, rounded beyond 3 decimals or filled in | re-done independently, compared value by value |
| 3. Aggregated community demand | Sum of the cleaned readings of the kept buildings; missing in any hour where one of them is missing | re-done independently, compared hour by hour |
| 4. ML predictions | Model forecasts of layer 3 | **not** verified here: they are estimates, not measurements (see `docs/society/RESULTS.md`) |

| Community | Meters | Meter-hours | Raw present | Missing in raw | Removed: negative | zero | stuck | spike | Cleaned valid | Hours with a community value | Community energy (kWh) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bull | 16 | 280,704 | 280,271 | 433 | 0 | 4,999 | 0 | 29 | 275,243 | 16,862 of 17,544 | 32,549,762 |
| eagle | 8 | 140,352 | 140,352 | 0 | 0 | 1,978 | 496 | 0 | 137,878 | 16,704 of 17,544 | 9,289,116 |
| fox | 11 | 192,984 | 192,947 | 37 | 0 | 62 | 0 | 0 | 192,885 | 17,486 of 17,544 | 26,464,352 |
| hog | 10 | 175,440 | 175,142 | 298 | 0 | 11 | 186 | 0 | 174,945 | 17,051 of 17,544 | 29,804,911 |
| peacock | 11 | 192,984 | 192,725 | 259 | 0 | 34 | 0 | 0 | 192,691 | 17,393 of 17,544 | 15,596,897 |
| rat | 9 | 157,896 | 157,116 | 780 | 0 | 471 | 0 | 0 | 156,645 | 16,620 of 17,544 | 8,328,446 |
| robin | 8 | 140,352 | 140,352 | 0 | 0 | 68 | 862 | 0 | 139,422 | 17,334 of 17,544 | 9,440,079 |

Effect of cleaning on the community figures, compared with a plain sum of the raw meters with no cleaning at all (`naive`):

| Community | Hours with a naive raw sum | Hours with a community value | Hours only in the naive sum | Energy in those hours (kWh) | Naive peak (kW) | Community peak (kW) |
|---|---:|---:|---:|---:|---:|---:|
| bull | 17,490 | 16,862 | 628 | 526,156 | 13,791 | 4,842 |
| eagle | 17,544 | 16,704 | 840 | 324,331 | 908 | 908 |
| fox | 17,528 | 17,486 | 42 | 53,958 | 2,283 | 2,283 |
| hog | 17,246 | 17,051 | 195 | 346,656 | 2,917 | 2,917 |
| peacock | 17,425 | 17,393 | 32 | 26,469 | 1,339 | 1,339 |
| rat | 17,085 | 16,620 | 465 | 200,724 | 938 | 938 |
| robin | 17,544 | 17,334 | 210 | 47,159 | 1,165 | 1,165 |

## 3. Exclusion criteria and rejected sites

A building enters a community only if all of these hold (checked in this order):

1. its BDG2 metadata `primaryspaceusage` is `Lodging/residential` (this label includes student residence halls);
2. its `sub_primaryspaceusage` is not one of ['Hotel'] (whitespace stripped, blank allowed);
3. it has a column in the electricity file;
4. after cleaning, at least 95% of its hours are valid;
5. its site keeps at least 8 such buildings; and
6. at least 94% of the site's hours have every kept meter valid.

Of 168 buildings labelled `Lodging/residential` in the metadata, 3 are hotels (excluded) and 19 have no electricity meter, leaving 146 candidates. Sub-use labels of all labelled buildings: Dormitory (93), Residence Hall (44), Other - Lodging/Residential (10), Housing (10), Lodging/residential (4), Hotel (3), Residence Hall/Dormitory (3), Multifamily Housing (1).

| Site | Labelled residential | Hotels | No meter | Candidates | Candidate valid share after cleaning (min / median / max) | Readings removed in the candidates (negative / zero / stuck / spike) | Meters >= 95 % valid | Community valid share | Result |
|---|---:|---:|---:|---:|---|---|---:|---:|---|
| Bear | 4 | 0 | 0 | 4 | 68.6% / 99.8% / 99.8% | 0 / 0 / 0 / 0 | 3 | - | rejected: only 3 meters pass the validity rule (need 8) |
| Bobcat | 3 | 0 | 0 | 3 | 94.0% / 94.0% / 94.1% | 0 / 0 / 0 / 0 | 0 | - | rejected: only 0 meters pass the validity rule (need 8) |
| Bull | 19 | 0 | 0 | 19 | 89.1% / 98.1% / 98.3% | 0 / 9,884 / 0 / 73 | 16 | 96.1% | **accepted** |
| Cockatoo | 29 | 1 | 1 | 27 | 81.7% / 91.9% / 91.9% | 0 / 638 / 0 / 0 | 0 | - | rejected: only 0 meters pass the validity rule (need 8) |
| Eagle | 10 | 0 | 0 | 10 | 0.0% / 98.6% / 99.2% | 0 / 7,384 / 553 / 0 | 8 | 95.2% | **accepted** |
| Fox | 12 | 0 | 0 | 12 | 83.2% / 100.0% / 100.0% | 0 / 70 / 2,936 / 0 | 11 | 99.7% | **accepted** |
| Hog | 11 | 0 | 0 | 11 | 73.3% / 100.0% / 100.0% | 0 / 2,495 / 2,390 / 0 | 10 | 97.2% | **accepted** |
| Lamb | 2 | 1 | 0 | 1 | 60.9% / 60.9% / 60.9% | 0 / 47 / 6,805 / 0 | 0 | - | rejected: only 0 meters pass the validity rule (need 8) |
| Mouse | 1 | 1 | 0 | 0 | - | - | - | - | rejected: no residential meters |
| Panther | 44 | 0 | 17 | 27 | 80.7% / 80.7% / 82.4% | 0 / 90,711 / 0 / 1 | 0 | - | rejected: only 0 meters pass the validity rule (need 8) |
| Peacock | 12 | 0 | 1 | 11 | 99.6% / 99.9% / 100.0% | 0 / 34 / 0 / 0 | 11 | 99.1% | **accepted** |
| Rat | 11 | 0 | 0 | 11 | 59.5% / 99.1% / 99.8% | 0 / 11,521 / 2,194 / 0 | 9 | 94.7% | **accepted** |
| Robin | 10 | 0 | 0 | 10 | 88.7% / 99.3% / 100.0% | 0 / 68 / 4,489 / 0 | 8 | 98.8% | **accepted** |

Meters rejected by rule 4 inside accepted sites:

| Community | Meter | Valid share after cleaning | Missing in raw | Negative | Zero | Stuck | Spike | Reason |
|---|---|---:|---:|---:|---:|---:|---:|---|
| bull | Bull_lodging_Anibal | 89.1% | 55 | 0 | 1,858 | 0 | 0 | below the 95% rule |
| bull | Bull_lodging_Danielle | 90.6% | 34 | 0 | 1,579 | 0 | 28 | below the 95% rule |
| bull | Bull_lodging_Terence | 91.4% | 46 | 0 | 1,448 | 0 | 16 | below the 95% rule |
| eagle | Eagle_lodging_Blake | 68.9% | 0 | 0 | 5,406 | 57 | 0 | below the 95% rule |
| eagle | Eagle_lodging_Garland | 0.0% | 17,544 | 0 | 0 | 0 | 0 | below the 95% rule |
| fox | Fox_lodging_Warren | 83.2% | 2 | 0 | 8 | 2,936 | 0 | below the 95% rule |
| hog | Hog_lodging_Edgar | 73.3% | 0 | 0 | 2,484 | 2,204 | 0 | below the 95% rule |
| rat | Rat_lodging_Lakisha | 64.0% | 100 | 0 | 4,022 | 2,194 | 0 | below the 95% rule |
| rat | Rat_lodging_Lucille | 59.5% | 70 | 0 | 7,028 | 0 | 0 | below the 95% rule |
| robin | Robin_lodging_Armand | 90.6% | 0 | 0 | 0 | 1,642 | 0 | below the 95% rule |
| robin | Robin_lodging_Donna | 88.7% | 0 | 0 | 0 | 1,985 | 0 | below the 95% rule |

## 4. Spike and stuck-sensor filtering

Applied to every meter separately, on the full 17,544-hour series, in this way:

| Rule | Definition | Threshold |
|---|---|---|
| Missing | no value in the raw file | kept as missing |
| Negative | reading below 0 | removed |
| Zero | reading exactly 0 kWh; labelled 'long' when the run of zeros lasts at least 24 h, otherwise 'short'; both are removed | `zero_is_invalid = True` |
| Stuck sensor | a run of identical POSITIVE readings; a missing, zero or negative reading ends the run | at least 48 consecutive hours |
| Spike | reading above 4.0 x the 99.5% quantile (linear interpolation) of that meter's positive readings; applies only to meters with at least 100 positive readings | 4.0 x p99.5 |

A reading hit by several rules is counted once, in the order negative, stuck, spike; zero readings are counted separately. Removed readings become missing; no value is replaced or interpolated.

## 5. Meter-level results

`Altered` is the number of stored values that differ from the raw reading of the same hour by more than the 3-decimal rounding (it must be 0). `Spike limit` is the value above which that meter's readings count as spikes. `Counts` says whether the independent removal counts equal the application's own cleaning report.

| Community | Code | Source id | Sub-use | Missing | Neg. | Zero | Stuck | Spike | Valid | Valid % | Spike limit (kWh/h) | Altered | Counts |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| bull | BUL-B01 | Bull_lodging_Abby | Dormitory | 31 | 0 | 300 | 0 | 0 | 17,213 | 98.1% | 90 | 0 | equal |
| bull | BUL-B02 | Bull_lodging_Allen | Dormitory | 24 | 0 | 276 | 0 | 0 | 17,244 | 98.3% | 102 | 0 | equal |
| bull | BUL-B03 | Bull_lodging_Caren | Dormitory | 26 | 0 | 282 | 0 | 0 | 17,236 | 98.2% | 900 | 0 | equal |
| bull | BUL-B04 | Bull_lodging_Carie | Dormitory | 28 | 0 | 301 | 0 | 0 | 17,215 | 98.1% | 304 | 0 | equal |
| bull | BUL-B05 | Bull_lodging_Charlotte | Dormitory | 25 | 0 | 277 | 0 | 0 | 17,242 | 98.3% | 103 | 0 | equal |
| bull | BUL-B06 | Bull_lodging_Dave | Dormitory | 27 | 0 | 299 | 0 | 1 | 17,217 | 98.1% | 1,824 | 0 | equal |
| bull | BUL-B07 | Bull_lodging_Elena | Dormitory | 31 | 0 | 302 | 0 | 0 | 17,211 | 98.1% | 50 | 0 | equal |
| bull | BUL-B08 | Bull_lodging_Graciela | Dormitory | 35 | 0 | 430 | 0 | 0 | 17,079 | 97.3% | 80 | 0 | equal |
| bull | BUL-B09 | Bull_lodging_Hugo | Dormitory | 15 | 0 | 300 | 0 | 11 | 17,218 | 98.1% | 444 | 0 | equal |
| bull | BUL-B10 | Bull_lodging_Jeremiah | Dormitory | 29 | 0 | 302 | 0 | 0 | 17,213 | 98.1% | 388 | 0 | equal |
| bull | BUL-B11 | Bull_lodging_Leonard | Dormitory | 29 | 0 | 300 | 0 | 0 | 17,215 | 98.1% | 204 | 0 | equal |
| bull | BUL-B12 | Bull_lodging_Lettie | Dormitory | 32 | 0 | 299 | 0 | 0 | 17,213 | 98.1% | 208 | 0 | equal |
| bull | BUL-B13 | Bull_lodging_Melissa | Dormitory | 28 | 0 | 298 | 0 | 0 | 17,218 | 98.1% | 1,408 | 0 | equal |
| bull | BUL-B14 | Bull_lodging_Perry | Dormitory | 27 | 0 | 273 | 0 | 0 | 17,244 | 98.3% | 324 | 0 | equal |
| bull | BUL-B15 | Bull_lodging_Travis | Dormitory | 24 | 0 | 482 | 0 | 17 | 17,021 | 97.0% | 4,476 | 0 | equal |
| bull | BUL-B16 | Bull_lodging_Xavier | Dormitory | 22 | 0 | 278 | 0 | 0 | 17,244 | 98.3% | 94 | 0 | equal |
| eagle | EAG-B01 | Eagle_lodging_Andy | Housing | 0 | 0 | 73 | 62 | 0 | 17,409 | 99.2% | 375 | 0 | equal |
| eagle | EAG-B02 | Eagle_lodging_Casey | Housing | 0 | 0 | 192 | 62 | 0 | 17,290 | 98.6% | 483 | 0 | equal |
| eagle | EAG-B03 | Eagle_lodging_Dawn | Housing | 0 | 0 | 191 | 62 | 0 | 17,291 | 98.6% | 460 | 0 | equal |
| eagle | EAG-B04 | Eagle_lodging_Edgardo | Housing | 0 | 0 | 179 | 62 | 0 | 17,303 | 98.6% | 346 | 0 | equal |
| eagle | EAG-B05 | Eagle_lodging_Stephanie | Housing | 0 | 0 | 209 | 62 | 0 | 17,273 | 98.5% | 488 | 0 | equal |
| eagle | EAG-B06 | Eagle_lodging_Terri | Housing | 0 | 0 | 776 | 62 | 0 | 16,706 | 95.2% | 970 | 0 | equal |
| eagle | EAG-B07 | Eagle_lodging_Tressa | Housing | 0 | 0 | 179 | 62 | 0 | 17,303 | 98.6% | 436 | 0 | equal |
| eagle | EAG-B08 | Eagle_lodging_Trina | Housing | 0 | 0 | 179 | 62 | 0 | 17,303 | 98.6% | 331 | 0 | equal |
| fox | FOX-B01 | Fox_lodging_Alana | Dormitory | 3 | 0 | 1 | 0 | 0 | 17,540 | 100.0% | 1,212 | 0 | equal |
| fox | FOX-B02 | Fox_lodging_Angla | Dormitory | 2 | 0 | 17 | 0 | 0 | 17,525 | 99.9% | 835 | 0 | equal |
| fox | FOX-B03 | Fox_lodging_Frances | Dormitory | 2 | 0 | 13 | 0 | 0 | 17,529 | 99.9% | 572 | 0 | equal |
| fox | FOX-B04 | Fox_lodging_Helen | Dormitory | 1 | 0 | 0 | 0 | 0 | 17,543 | 100.0% | 2,334 | 0 | equal |
| fox | FOX-B05 | Fox_lodging_Isabell | Dormitory | 3 | 0 | 1 | 0 | 0 | 17,540 | 100.0% | 157 | 0 | equal |
| fox | FOX-B06 | Fox_lodging_Jina | Dormitory | 2 | 0 | 5 | 0 | 0 | 17,537 | 100.0% | 768 | 0 | equal |
| fox | FOX-B07 | Fox_lodging_Morris | Dormitory | 1 | 0 | 17 | 0 | 0 | 17,526 | 99.9% | 131 | 0 | equal |
| fox | FOX-B08 | Fox_lodging_Stephan | Dormitory | 16 | 0 | 4 | 0 | 0 | 17,524 | 99.9% | 174 | 0 | equal |
| fox | FOX-B09 | Fox_lodging_Stephen | Dormitory | 1 | 0 | 2 | 0 | 0 | 17,541 | 100.0% | 489 | 0 | equal |
| fox | FOX-B10 | Fox_lodging_Wallace | Dormitory | 3 | 0 | 1 | 0 | 0 | 17,540 | 100.0% | 1,926 | 0 | equal |
| fox | FOX-B11 | Fox_lodging_Winifred | Dormitory | 3 | 0 | 1 | 0 | 0 | 17,540 | 100.0% | 470 | 0 | equal |
| hog | HOG-B01 | Hog_lodging_Brian | Dormitory | 0 | 0 | 1 | 0 | 0 | 17,543 | 100.0% | 692 | 0 | equal |
| hog | HOG-B02 | Hog_lodging_Celeste | Dormitory | 2 | 0 | 0 | 0 | 0 | 17,542 | 100.0% | 617 | 0 | equal |
| hog | HOG-B03 | Hog_lodging_Francisco | Dormitory | 0 | 0 | 0 | 0 | 0 | 17,544 | 100.0% | 1,167 | 0 | equal |
| hog | HOG-B04 | Hog_lodging_Hal | Dormitory | 0 | 0 | 0 | 0 | 0 | 17,544 | 100.0% | 1,231 | 0 | equal |
| hog | HOG-B05 | Hog_lodging_Mauricio | Dormitory | 1 | 0 | 1 | 0 | 0 | 17,542 | 100.0% | 1,524 | 0 | equal |
| hog | HOG-B06 | Hog_lodging_Nikki | Dormitory | 0 | 0 | 0 | 0 | 0 | 17,544 | 100.0% | 458 | 0 | equal |
| hog | HOG-B07 | Hog_lodging_Ora | Dormitory | 0 | 0 | 0 | 0 | 0 | 17,544 | 100.0% | 1,558 | 0 | equal |
| hog | HOG-B08 | Hog_lodging_Retha | Dormitory | 295 | 0 | 8 | 0 | 0 | 17,241 | 98.3% | 2,306 | 0 | equal |
| hog | HOG-B09 | Hog_lodging_Shanti | Dormitory | 0 | 0 | 0 | 186 | 0 | 17,358 | 98.9% | 1,978 | 0 | equal |
| hog | HOG-B10 | Hog_lodging_Shonda | Dormitory | 0 | 0 | 1 | 0 | 0 | 17,543 | 100.0% | 645 | 0 | equal |
| peacock | PEA-B01 | Peacock_lodging_Chloe | Dormitory | 39 | 0 | 2 | 0 | 0 | 17,503 | 99.8% | 248 | 0 | equal |
| peacock | PEA-B02 | Peacock_lodging_Francesca | Dormitory | 9 | 0 | 7 | 0 | 0 | 17,528 | 99.9% | 247 | 0 | equal |
| peacock | PEA-B03 | Peacock_lodging_Jamaal | Dormitory | 11 | 0 | 0 | 0 | 0 | 17,533 | 99.9% | 1,297 | 0 | equal |
| peacock | PEA-B04 | Peacock_lodging_James | Dormitory | 73 | 0 | 0 | 0 | 0 | 17,471 | 99.6% | 388 | 0 | equal |
| peacock | PEA-B05 | Peacock_lodging_Lou | Dormitory | 5 | 0 | 2 | 0 | 0 | 17,537 | 100.0% | 651 | 0 | equal |
| peacock | PEA-B06 | Peacock_lodging_Mathew | Dormitory | 39 | 0 | 10 | 0 | 0 | 17,495 | 99.7% | 356 | 0 | equal |
| peacock | PEA-B07 | Peacock_lodging_Matthew | Dormitory | 10 | 0 | 0 | 0 | 0 | 17,534 | 99.9% | 335 | 0 | equal |
| peacock | PEA-B08 | Peacock_lodging_Nova | Dormitory | 13 | 0 | 11 | 0 | 0 | 17,520 | 99.9% | 165 | 0 | equal |
| peacock | PEA-B09 | Peacock_lodging_Sergio | Dormitory | 10 | 0 | 0 | 0 | 0 | 17,534 | 99.9% | 603 | 0 | equal |
| peacock | PEA-B10 | Peacock_lodging_Terrie | Dormitory | 39 | 0 | 2 | 0 | 0 | 17,503 | 99.8% | 265 | 0 | equal |
| peacock | PEA-B11 | Peacock_lodging_Wes | Dormitory | 11 | 0 | 0 | 0 | 0 | 17,533 | 99.9% | 984 | 0 | equal |
| rat | RAT-B01 | Rat_lodging_Ardell | Other - Lodging/Residential | 76 | 0 | 0 | 0 | 0 | 17,468 | 99.6% | 135 | 0 | equal |
| rat | RAT-B02 | Rat_lodging_Ben | Other - Lodging/Residential | 201 | 0 | 0 | 0 | 0 | 17,343 | 98.9% | 2,411 | 0 | equal |
| rat | RAT-B03 | Rat_lodging_Christine | Other - Lodging/Residential | 52 | 0 | 0 | 0 | 0 | 17,492 | 99.7% | 513 | 0 | equal |
| rat | RAT-B04 | Rat_lodging_Dwight | Other - Lodging/Residential | 29 | 0 | 5 | 0 | 0 | 17,510 | 99.8% | 296 | 0 | equal |
| rat | RAT-B05 | Rat_lodging_Jeannette | Other - Lodging/Residential | 28 | 0 | 2 | 0 | 0 | 17,514 | 99.8% | 52 | 0 | equal |
| rat | RAT-B06 | Rat_lodging_Lorenzo | Other - Lodging/Residential | 76 | 0 | 100 | 0 | 0 | 17,368 | 99.0% | 32 | 0 | equal |
| rat | RAT-B07 | Rat_lodging_Marguerite | Other - Lodging/Residential | 158 | 0 | 0 | 0 | 0 | 17,386 | 99.1% | 226 | 0 | equal |
| rat | RAT-B08 | Rat_lodging_Marion | Other - Lodging/Residential | 108 | 0 | 0 | 0 | 0 | 17,436 | 99.4% | 331 | 0 | equal |
| rat | RAT-B09 | Rat_lodging_Ted | Other - Lodging/Residential | 52 | 0 | 364 | 0 | 0 | 17,128 | 97.6% | 34 | 0 | equal |
| robin | ROB-B01 | Robin_lodging_Celia | Dormitory | 0 | 0 | 0 | 120 | 0 | 17,424 | 99.3% | 425 | 0 | equal |
| robin | ROB-B02 | Robin_lodging_Dorthy | Dormitory | 0 | 0 | 0 | 120 | 0 | 17,424 | 99.3% | 232 | 0 | equal |
| robin | ROB-B03 | Robin_lodging_Elmer | Dormitory | 0 | 0 | 0 | 120 | 0 | 17,424 | 99.3% | 684 | 0 | equal |
| robin | ROB-B04 | Robin_lodging_Janie | Dormitory | 0 | 0 | 0 | 0 | 0 | 17,544 | 100.0% | 1,059 | 0 | equal |
| robin | ROB-B05 | Robin_lodging_Oliva | Dormitory | 0 | 0 | 0 | 120 | 0 | 17,424 | 99.3% | 440 | 0 | equal |
| robin | ROB-B06 | Robin_lodging_Phillip | Dormitory | 0 | 0 | 66 | 142 | 0 | 17,336 | 98.8% | 328 | 0 | equal |
| robin | ROB-B07 | Robin_lodging_Pricilla | Dormitory | 0 | 0 | 2 | 120 | 0 | 17,422 | 99.3% | 577 | 0 | equal |
| robin | ROB-B08 | Robin_lodging_Renea | Dormitory | 0 | 0 | 0 | 120 | 0 | 17,424 | 99.3% | 649 | 0 | equal |

## 6. Missing hours

An hour has no community value when at least one kept meter has no valid reading. `Blocked only by` lists the meter that is the single reason for most such hours.

| Community | Hours | With a value | Missing | Missing % | Gaps | Longest gap (h) | Starting | Blocked only by (hours) |
|---|---:|---:|---:|---:|---:|---:|---|---|
| bull | 17,544 | 16,862 | 682 | 3.89 % | 40 | 115 | 2016-05-26 15:00:00 | Bull_lodging_Travis (195) |
| eagle | 17,544 | 16,704 | 840 | 4.79 % | 56 | 533 | 2016-09-28 08:00:00 | Eagle_lodging_Terri (567) |
| fox | 17,544 | 17,486 | 58 | 0.33 % | 17 | 13 | 2017-11-07 14:00:00 | Fox_lodging_Morris (15) |
| hog | 17,544 | 17,051 | 493 | 2.81 % | 11 | 196 | 2016-06-12 07:00:00 | Hog_lodging_Retha (303) |
| peacock | 17,544 | 17,393 | 151 | 0.86 % | 26 | 58 | 2016-08-02 15:00:00 | Peacock_lodging_James (71) |
| rat | 17,544 | 16,620 | 924 | 5.27 % | 443 | 96 | 2017-08-28 00:00:00 | Rat_lodging_Ted (383) |
| robin | 17,544 | 17,334 | 210 | 1.20 % | 6 | 94 | 2017-05-03 02:00:00 | Robin_lodging_Phillip (88) |

## 7. Building mix of the accepted communities

| Community | Buildings | Sub-use labels in the BDG2 metadata |
|---|---:|---|
| bull | 16 | Dormitory (16) |
| eagle | 8 | Housing (8) |
| fox | 11 | Dormitory (11) |
| hog | 10 | Dormitory (10) |
| peacock | 11 | Dormitory (11) |
| rat | 9 | Other - Lodging/Residential (9) |
| robin | 8 | Dormitory (8) |

## 8. Raw against application

**Processed files.** The independent pipeline was compared with the application's processed files on 84 checks (selection, time grid, every meter, invalid readings, community sum): all passed. Details are in section 10.

**Running API** (overview totals, every calendar month, every building):

| Community | API energy (kWh) | Independent energy (kWh) | Difference | API valid h | Independent valid h | API peak (kW) | Independent peak (kW) | Months | Buildings |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bull | 32,549,761.910 | 32,549,761.910 | +0.0002 | 16,862 | 16,862 | 4,841.960 | 4,841.960 | 24 | 16 |
| eagle | 9,289,115.977 | 9,289,115.984 | -0.0072 | 16,704 | 16,704 | 907.685 | 907.685 | 24 | 8 |
| fox | 26,464,352.430 | 26,464,352.430 | +0.0000 | 17,486 | 17,486 | 2,283.160 | 2,283.160 | 24 | 11 |
| hog | 29,804,910.654 | 29,804,910.649 | +0.0054 | 17,051 | 17,051 | 2,917.163 | 2,917.163 | 24 | 10 |
| peacock | 15,596,896.757 | 15,596,896.740 | +0.0166 | 17,393 | 17,393 | 1,338.578 | 1,338.578 | 24 | 11 |
| rat | 8,328,445.710 | 8,328,445.710 | +0.0000 | 16,620 | 16,620 | 938.380 | 938.380 | 24 | 9 |
| robin | 9,440,079.218 | 9,440,078.881 | +0.3370 | 17,334 | 17,334 | 1,165.238 | 1,165.238 | 24 | 8 |

## 9. What this verification does not show

* It does not show that the BDG2 files are free of errors; they are hashed and used as published.
* It does not make the communities representative of family flats or of any registered housing society: they are groups of whole-building meters, mostly student residence halls (section 7), and this verification does not change that.
* It does not verify the weather columns, the forecasting models, their accuracy, the anomaly events, the tariff costs or the recommendations. Those are layer 4 or derived from layer 3 and are documented in `docs/society/RESULTS.md`.
* The cleaning thresholds are rules chosen for this project and documented in `docs/society/10_raw_data_verification.md`; the independent pipeline checks that they were applied as written, not that they are the best possible rules.
* In `subset` mode the SHA-256 of the full 174 MB electricity file is not re-checked (only the hash of the extracted subset and of the official metadata file). Run with the full files, or with `--check-subset`, for that.

## 10. All checks

| # | Scope | Check | Result | Detail |
|---:|---|---|---|---|
| 1 | raw | `integrity.sha256.data/metadata/metadata.csv`: SHA-256 of data/metadata/metadata.csv equals the recorded value | PASS | expected 992d0b29f24f96ad..., found 992d0b29f24f96ad... |
| 2 | raw | `integrity.sha256.data/weather/weather.csv`: SHA-256 of data/weather/weather.csv equals the recorded value | PASS | expected a8189f1c6acdf3b9..., found a8189f1c6acdf3b9... |
| 3 | raw | `integrity.sha256.data/meters/raw/electricity.csv`: SHA-256 of data/meters/raw/electricity.csv equals the recorded value | PASS | expected 039d909d8981e2d6..., found 039d909d8981e2d6... |
| 4 | raw | `integrity.sha256.LICENSE`: SHA-256 of LICENSE equals the recorded value | PASS | expected 1df42bd84afc40e6..., found 1df42bd84afc40e6... |
| 5 | raw | `integrity.sha256.README.md`: SHA-256 of README.md equals the recorded value | PASS | expected 7f2a1539a17c3183..., found 7f2a1539a17c3183... |
| 6 | raw | `raw.grid`: Raw readings sit on one complete hourly grid (sorted, unique, 1-hour steps) | PASS | 17,544 hours, 2016-01-01 00:00:00 to 2017-12-31 23:00:00 |
| 7 | raw | `integrity.subset_equals_full`: The shipped raw subset equals the full official electricity file, value by value, for every column it contains | PASS | 149 columns, 17,544 rows |
| 8 | sites | `sites.accepted_match`: Sites accepted by the independent screening equal the communities in the application's catalogue | PASS | independent ['bull', 'eagle', 'fox', 'hog', 'peacock', 'rat', 'robin']; application ['bull', 'eagle', 'fox', 'hog', 'peacock', 'rat', 'robin'] |
| 9 | bull | `bull.selection.kept_buildings`: Buildings kept by the independent selection equal the application's buildings.csv | PASS | independent 16, application 16; only independent: []; only application: [] |
| 10 | bull | `bull.selection.excluded_meters`: Candidate meters rejected by the 95 % rule equal the application's excluded_meters.csv | PASS | independent ['Bull_lodging_Anibal', 'Bull_lodging_Danielle', 'Bull_lodging_Terence'], application ['Bull_lodging_Anibal', 'Bull_lodging_Danielle', 'Bull_lodging_Terence'] |
| 11 | bull | `bull.selection.building_codes`: Building codes follow the documented rule (site prefix, source ids sorted) | PASS |  |
| 12 | bull | `bull.buildings.metadata`: Each kept building is of the selected primary use on the site, with floor area and sub-use equal to the BDG2 metadata | PASS |  |
| 13 | bull | `bull.grid.complete`: Processed hourly grid equals the raw grid: unique, regular 1-hour steps, no missing timestamp | PASS | 17,544 hours, 2016-01-01 00:00:00 to 2017-12-31 23:00:00 |
| 14 | bull | `bull.meters.unaltered`: No stored (cleaned) value differs from the raw reading of the same hour by more than the 3-decimal rounding | PASS | 0 of 275,243 stored meter values differ |
| 15 | bull | `bull.meters.cleaned_equals_independent`: Application's cleaned meters equal the independently cleaned meters (same valid hours, same values) | PASS | 16 meters identical in missing pattern and values |
| 16 | bull | `bull.meters.removal_counts`: Per-rule removal counts (missing, negative, zero, stuck, spike, valid) equal the application's cleaning report | PASS | no difference |
| 17 | bull | `bull.invalid.none_left`: The processed meters contain no negative, zero, stuck (>= 48 identical) or spike (> 4 x p99.5) reading | PASS | negative 0, zero 0, stuck 0, spike 0 |
| 18 | bull | `bull.aggregate.total_equals_independent`: Application's community demand equals the independent sum of the cleaned meters, hour by hour | PASS | largest hourly difference 0.00010 kWh (allowed 0.0085 from 3-decimal storage); missing-hour pattern identical: True |
| 19 | bull | `bull.aggregate.no_partial_sums`: The processed community demand is missing in exactly the hours where any kept meter is missing (never a partial sum) | PASS | 16,862 hours with every meter valid |
| 20 | bull | `bull.aggregate.n_valid_meters`: n_valid_meters equals the number of non-missing meters in each hour | PASS |  |
| 21 | bull | `bull.aggregate.valid_hours`: Valid community hours and the 94 % rule agree with the application's cleaning report | PASS | independent 16,862 h (0.9611), application 16,862 h |
| 22 | bull | `bull.spec.rules_match`: Thresholds recorded in the application's cleaning report equal this script's SPEC | PASS |  |
| 23 | eagle | `eagle.selection.kept_buildings`: Buildings kept by the independent selection equal the application's buildings.csv | PASS | independent 8, application 8; only independent: []; only application: [] |
| 24 | eagle | `eagle.selection.excluded_meters`: Candidate meters rejected by the 95 % rule equal the application's excluded_meters.csv | PASS | independent ['Eagle_lodging_Blake', 'Eagle_lodging_Garland'], application ['Eagle_lodging_Blake', 'Eagle_lodging_Garland'] |
| 25 | eagle | `eagle.selection.building_codes`: Building codes follow the documented rule (site prefix, source ids sorted) | PASS |  |
| 26 | eagle | `eagle.buildings.metadata`: Each kept building is of the selected primary use on the site, with floor area and sub-use equal to the BDG2 metadata | PASS |  |
| 27 | eagle | `eagle.grid.complete`: Processed hourly grid equals the raw grid: unique, regular 1-hour steps, no missing timestamp | PASS | 17,544 hours, 2016-01-01 00:00:00 to 2017-12-31 23:00:00 |
| 28 | eagle | `eagle.meters.unaltered`: No stored (cleaned) value differs from the raw reading of the same hour by more than the 3-decimal rounding | PASS | 0 of 137,878 stored meter values differ |
| 29 | eagle | `eagle.meters.cleaned_equals_independent`: Application's cleaned meters equal the independently cleaned meters (same valid hours, same values) | PASS | 8 meters identical in missing pattern and values |
| 30 | eagle | `eagle.meters.removal_counts`: Per-rule removal counts (missing, negative, zero, stuck, spike, valid) equal the application's cleaning report | PASS | no difference |
| 31 | eagle | `eagle.invalid.none_left`: The processed meters contain no negative, zero, stuck (>= 48 identical) or spike (> 4 x p99.5) reading | PASS | negative 0, zero 0, stuck 0, spike 0 |
| 32 | eagle | `eagle.aggregate.total_equals_independent`: Application's community demand equals the independent sum of the cleaned meters, hour by hour | PASS | largest hourly difference 0.00050 kWh (allowed 0.0045 from 3-decimal storage); missing-hour pattern identical: True |
| 33 | eagle | `eagle.aggregate.no_partial_sums`: The processed community demand is missing in exactly the hours where any kept meter is missing (never a partial sum) | PASS | 16,704 hours with every meter valid |
| 34 | eagle | `eagle.aggregate.n_valid_meters`: n_valid_meters equals the number of non-missing meters in each hour | PASS |  |
| 35 | eagle | `eagle.aggregate.valid_hours`: Valid community hours and the 94 % rule agree with the application's cleaning report | PASS | independent 16,704 h (0.9521), application 16,704 h |
| 36 | eagle | `eagle.spec.rules_match`: Thresholds recorded in the application's cleaning report equal this script's SPEC | PASS |  |
| 37 | fox | `fox.selection.kept_buildings`: Buildings kept by the independent selection equal the application's buildings.csv | PASS | independent 11, application 11; only independent: []; only application: [] |
| 38 | fox | `fox.selection.excluded_meters`: Candidate meters rejected by the 95 % rule equal the application's excluded_meters.csv | PASS | independent ['Fox_lodging_Warren'], application ['Fox_lodging_Warren'] |
| 39 | fox | `fox.selection.building_codes`: Building codes follow the documented rule (site prefix, source ids sorted) | PASS |  |
| 40 | fox | `fox.buildings.metadata`: Each kept building is of the selected primary use on the site, with floor area and sub-use equal to the BDG2 metadata | PASS |  |
| 41 | fox | `fox.grid.complete`: Processed hourly grid equals the raw grid: unique, regular 1-hour steps, no missing timestamp | PASS | 17,544 hours, 2016-01-01 00:00:00 to 2017-12-31 23:00:00 |
| 42 | fox | `fox.meters.unaltered`: No stored (cleaned) value differs from the raw reading of the same hour by more than the 3-decimal rounding | PASS | 0 of 192,885 stored meter values differ |
| 43 | fox | `fox.meters.cleaned_equals_independent`: Application's cleaned meters equal the independently cleaned meters (same valid hours, same values) | PASS | 11 meters identical in missing pattern and values |
| 44 | fox | `fox.meters.removal_counts`: Per-rule removal counts (missing, negative, zero, stuck, spike, valid) equal the application's cleaning report | PASS | no difference |
| 45 | fox | `fox.invalid.none_left`: The processed meters contain no negative, zero, stuck (>= 48 identical) or spike (> 4 x p99.5) reading | PASS | negative 0, zero 0, stuck 0, spike 0 |
| 46 | fox | `fox.aggregate.total_equals_independent`: Application's community demand equals the independent sum of the cleaned meters, hour by hour | PASS | largest hourly difference 0.00000 kWh (allowed 0.0060 from 3-decimal storage); missing-hour pattern identical: True |
| 47 | fox | `fox.aggregate.no_partial_sums`: The processed community demand is missing in exactly the hours where any kept meter is missing (never a partial sum) | PASS | 17,486 hours with every meter valid |
| 48 | fox | `fox.aggregate.n_valid_meters`: n_valid_meters equals the number of non-missing meters in each hour | PASS |  |
| 49 | fox | `fox.aggregate.valid_hours`: Valid community hours and the 94 % rule agree with the application's cleaning report | PASS | independent 17,486 h (0.9967), application 17,486 h |
| 50 | fox | `fox.spec.rules_match`: Thresholds recorded in the application's cleaning report equal this script's SPEC | PASS |  |
| 51 | hog | `hog.selection.kept_buildings`: Buildings kept by the independent selection equal the application's buildings.csv | PASS | independent 10, application 10; only independent: []; only application: [] |
| 52 | hog | `hog.selection.excluded_meters`: Candidate meters rejected by the 95 % rule equal the application's excluded_meters.csv | PASS | independent ['Hog_lodging_Edgar'], application ['Hog_lodging_Edgar'] |
| 53 | hog | `hog.selection.building_codes`: Building codes follow the documented rule (site prefix, source ids sorted) | PASS |  |
| 54 | hog | `hog.buildings.metadata`: Each kept building is of the selected primary use on the site, with floor area and sub-use equal to the BDG2 metadata | PASS |  |
| 55 | hog | `hog.grid.complete`: Processed hourly grid equals the raw grid: unique, regular 1-hour steps, no missing timestamp | PASS | 17,544 hours, 2016-01-01 00:00:00 to 2017-12-31 23:00:00 |
| 56 | hog | `hog.meters.unaltered`: No stored (cleaned) value differs from the raw reading of the same hour by more than the 3-decimal rounding | PASS | 0 of 174,945 stored meter values differ |
| 57 | hog | `hog.meters.cleaned_equals_independent`: Application's cleaned meters equal the independently cleaned meters (same valid hours, same values) | PASS | 10 meters identical in missing pattern and values |
| 58 | hog | `hog.meters.removal_counts`: Per-rule removal counts (missing, negative, zero, stuck, spike, valid) equal the application's cleaning report | PASS | no difference |
| 59 | hog | `hog.invalid.none_left`: The processed meters contain no negative, zero, stuck (>= 48 identical) or spike (> 4 x p99.5) reading | PASS | negative 0, zero 0, stuck 0, spike 0 |
| 60 | hog | `hog.aggregate.total_equals_independent`: Application's community demand equals the independent sum of the cleaned meters, hour by hour | PASS | largest hourly difference 0.00050 kWh (allowed 0.0055 from 3-decimal storage); missing-hour pattern identical: True |
| 61 | hog | `hog.aggregate.no_partial_sums`: The processed community demand is missing in exactly the hours where any kept meter is missing (never a partial sum) | PASS | 17,051 hours with every meter valid |
| 62 | hog | `hog.aggregate.n_valid_meters`: n_valid_meters equals the number of non-missing meters in each hour | PASS |  |
| 63 | hog | `hog.aggregate.valid_hours`: Valid community hours and the 94 % rule agree with the application's cleaning report | PASS | independent 17,051 h (0.9719), application 17,051 h |
| 64 | hog | `hog.spec.rules_match`: Thresholds recorded in the application's cleaning report equal this script's SPEC | PASS |  |
| 65 | peacock | `peacock.selection.kept_buildings`: Buildings kept by the independent selection equal the application's buildings.csv | PASS | independent 11, application 11; only independent: []; only application: [] |
| 66 | peacock | `peacock.selection.excluded_meters`: Candidate meters rejected by the 95 % rule equal the application's excluded_meters.csv | PASS | independent [], application [] |
| 67 | peacock | `peacock.selection.building_codes`: Building codes follow the documented rule (site prefix, source ids sorted) | PASS |  |
| 68 | peacock | `peacock.buildings.metadata`: Each kept building is of the selected primary use on the site, with floor area and sub-use equal to the BDG2 metadata | PASS |  |
| 69 | peacock | `peacock.grid.complete`: Processed hourly grid equals the raw grid: unique, regular 1-hour steps, no missing timestamp | PASS | 17,544 hours, 2016-01-01 00:00:00 to 2017-12-31 23:00:00 |
| 70 | peacock | `peacock.meters.unaltered`: No stored (cleaned) value differs from the raw reading of the same hour by more than the 3-decimal rounding | PASS | 0 of 192,691 stored meter values differ |
| 71 | peacock | `peacock.meters.cleaned_equals_independent`: Application's cleaned meters equal the independently cleaned meters (same valid hours, same values) | PASS | 11 meters identical in missing pattern and values |
| 72 | peacock | `peacock.meters.removal_counts`: Per-rule removal counts (missing, negative, zero, stuck, spike, valid) equal the application's cleaning report | PASS | no difference |
| 73 | peacock | `peacock.invalid.none_left`: The processed meters contain no negative, zero, stuck (>= 48 identical) or spike (> 4 x p99.5) reading | PASS | negative 0, zero 0, stuck 0, spike 0 |
| 74 | peacock | `peacock.aggregate.total_equals_independent`: Application's community demand equals the independent sum of the cleaned meters, hour by hour | PASS | largest hourly difference 0.00050 kWh (allowed 0.0060 from 3-decimal storage); missing-hour pattern identical: True |
| 75 | peacock | `peacock.aggregate.no_partial_sums`: The processed community demand is missing in exactly the hours where any kept meter is missing (never a partial sum) | PASS | 17,393 hours with every meter valid |
| 76 | peacock | `peacock.aggregate.n_valid_meters`: n_valid_meters equals the number of non-missing meters in each hour | PASS |  |
| 77 | peacock | `peacock.aggregate.valid_hours`: Valid community hours and the 94 % rule agree with the application's cleaning report | PASS | independent 17,393 h (0.9914), application 17,393 h |
| 78 | peacock | `peacock.spec.rules_match`: Thresholds recorded in the application's cleaning report equal this script's SPEC | PASS |  |
| 79 | rat | `rat.selection.kept_buildings`: Buildings kept by the independent selection equal the application's buildings.csv | PASS | independent 9, application 9; only independent: []; only application: [] |
| 80 | rat | `rat.selection.excluded_meters`: Candidate meters rejected by the 95 % rule equal the application's excluded_meters.csv | PASS | independent ['Rat_lodging_Lakisha', 'Rat_lodging_Lucille'], application ['Rat_lodging_Lakisha', 'Rat_lodging_Lucille'] |
| 81 | rat | `rat.selection.building_codes`: Building codes follow the documented rule (site prefix, source ids sorted) | PASS |  |
| 82 | rat | `rat.buildings.metadata`: Each kept building is of the selected primary use on the site, with floor area and sub-use equal to the BDG2 metadata | PASS |  |
| 83 | rat | `rat.grid.complete`: Processed hourly grid equals the raw grid: unique, regular 1-hour steps, no missing timestamp | PASS | 17,544 hours, 2016-01-01 00:00:00 to 2017-12-31 23:00:00 |
| 84 | rat | `rat.meters.unaltered`: No stored (cleaned) value differs from the raw reading of the same hour by more than the 3-decimal rounding | PASS | 0 of 156,645 stored meter values differ |
| 85 | rat | `rat.meters.cleaned_equals_independent`: Application's cleaned meters equal the independently cleaned meters (same valid hours, same values) | PASS | 9 meters identical in missing pattern and values |
| 86 | rat | `rat.meters.removal_counts`: Per-rule removal counts (missing, negative, zero, stuck, spike, valid) equal the application's cleaning report | PASS | no difference |
| 87 | rat | `rat.invalid.none_left`: The processed meters contain no negative, zero, stuck (>= 48 identical) or spike (> 4 x p99.5) reading | PASS | negative 0, zero 0, stuck 0, spike 0 |
| 88 | rat | `rat.aggregate.total_equals_independent`: Application's community demand equals the independent sum of the cleaned meters, hour by hour | PASS | largest hourly difference 0.00000 kWh (allowed 0.0050 from 3-decimal storage); missing-hour pattern identical: True |
| 89 | rat | `rat.aggregate.no_partial_sums`: The processed community demand is missing in exactly the hours where any kept meter is missing (never a partial sum) | PASS | 16,620 hours with every meter valid |
| 90 | rat | `rat.aggregate.n_valid_meters`: n_valid_meters equals the number of non-missing meters in each hour | PASS |  |
| 91 | rat | `rat.aggregate.valid_hours`: Valid community hours and the 94 % rule agree with the application's cleaning report | PASS | independent 16,620 h (0.9473), application 16,620 h |
| 92 | rat | `rat.spec.rules_match`: Thresholds recorded in the application's cleaning report equal this script's SPEC | PASS |  |
| 93 | robin | `robin.selection.kept_buildings`: Buildings kept by the independent selection equal the application's buildings.csv | PASS | independent 8, application 8; only independent: []; only application: [] |
| 94 | robin | `robin.selection.excluded_meters`: Candidate meters rejected by the 95 % rule equal the application's excluded_meters.csv | PASS | independent ['Robin_lodging_Armand', 'Robin_lodging_Donna'], application ['Robin_lodging_Armand', 'Robin_lodging_Donna'] |
| 95 | robin | `robin.selection.building_codes`: Building codes follow the documented rule (site prefix, source ids sorted) | PASS |  |
| 96 | robin | `robin.buildings.metadata`: Each kept building is of the selected primary use on the site, with floor area and sub-use equal to the BDG2 metadata | PASS |  |
| 97 | robin | `robin.grid.complete`: Processed hourly grid equals the raw grid: unique, regular 1-hour steps, no missing timestamp | PASS | 17,544 hours, 2016-01-01 00:00:00 to 2017-12-31 23:00:00 |
| 98 | robin | `robin.meters.unaltered`: No stored (cleaned) value differs from the raw reading of the same hour by more than the 3-decimal rounding | PASS | 0 of 139,422 stored meter values differ |
| 99 | robin | `robin.meters.cleaned_equals_independent`: Application's cleaned meters equal the independently cleaned meters (same valid hours, same values) | PASS | 8 meters identical in missing pattern and values |
| 100 | robin | `robin.meters.removal_counts`: Per-rule removal counts (missing, negative, zero, stuck, spike, valid) equal the application's cleaning report | PASS | no difference |
| 101 | robin | `robin.invalid.none_left`: The processed meters contain no negative, zero, stuck (>= 48 identical) or spike (> 4 x p99.5) reading | PASS | negative 0, zero 0, stuck 0, spike 0 |
| 102 | robin | `robin.aggregate.total_equals_independent`: Application's community demand equals the independent sum of the cleaned meters, hour by hour | PASS | largest hourly difference 0.00050 kWh (allowed 0.0045 from 3-decimal storage); missing-hour pattern identical: True |
| 103 | robin | `robin.aggregate.no_partial_sums`: The processed community demand is missing in exactly the hours where any kept meter is missing (never a partial sum) | PASS | 17,334 hours with every meter valid |
| 104 | robin | `robin.aggregate.n_valid_meters`: n_valid_meters equals the number of non-missing meters in each hour | PASS |  |
| 105 | robin | `robin.aggregate.valid_hours`: Valid community hours and the 94 % rule agree with the application's cleaning report | PASS | independent 17,334 h (0.9880), application 17,334 h |
| 106 | robin | `robin.spec.rules_match`: Thresholds recorded in the application's cleaning report equal this script's SPEC | PASS |  |
| 107 | bull | `bull.api.totals`: API overview totals (hours, valid hours, energy, mean, peak, peak hour) equal the independent community demand | PASS | energy API 32,549,761.910 vs independent 32,549,761.910 kWh (diff +0.0002, allowed 143.33); valid hours 16,862 vs 16,862; peak 4,841.960 vs 4,841.960 kW at 2017-10-03 10:00:00 |
| 108 | bull | `bull.api.monthly`: API monthly energy and valid hours equal the independent monthly sums for every calendar month | PASS | 24 months compared; differing months: none |
| 109 | bull | `bull.api.buildings`: API building energy, valid hours and peak equal the independent per-meter figures for every building (admin view) | PASS | 16 buildings compared, largest energy difference 0.0001 kWh; differing: none |
| 110 | eagle | `eagle.api.totals`: API overview totals (hours, valid hours, energy, mean, peak, peak hour) equal the independent community demand | PASS | energy API 9,289,115.977 vs independent 9,289,115.984 kWh (diff -0.0072, allowed 75.17); valid hours 16,704 vs 16,704; peak 907.685 vs 907.685 kW at 2016-02-15 01:00:00 |
| 111 | eagle | `eagle.api.monthly`: API monthly energy and valid hours equal the independent monthly sums for every calendar month | PASS | 24 months compared; differing months: none |
| 112 | eagle | `eagle.api.buildings`: API building energy, valid hours and peak equal the independent per-meter figures for every building (admin view) | PASS | 8 buildings compared, largest energy difference 1.3746 kWh; differing: none |
| 113 | fox | `fox.api.totals`: API overview totals (hours, valid hours, energy, mean, peak, peak hour) equal the independent community demand | PASS | energy API 26,464,352.430 vs independent 26,464,352.430 kWh (diff +0.0000, allowed 104.92); valid hours 17,486 vs 17,486; peak 2,283.160 vs 2,283.160 kW at 2016-09-11 21:00:00 |
| 114 | fox | `fox.api.monthly`: API monthly energy and valid hours equal the independent monthly sums for every calendar month | PASS | 24 months compared; differing months: none |
| 115 | fox | `fox.api.buildings`: API building energy, valid hours and peak equal the independent per-meter figures for every building (admin view) | PASS | 11 buildings compared, largest energy difference 0.0000 kWh; differing: none |
| 116 | hog | `hog.api.totals`: API overview totals (hours, valid hours, energy, mean, peak, peak hour) equal the independent community demand | PASS | energy API 29,804,910.654 vs independent 29,804,910.649 kWh (diff +0.0054, allowed 93.78); valid hours 17,051 vs 17,051; peak 2,917.163 vs 2,917.163 kW at 2017-08-30 18:00:00 |
| 117 | hog | `hog.api.monthly`: API monthly energy and valid hours equal the independent monthly sums for every calendar month | PASS | 24 months compared; differing months: none |
| 118 | hog | `hog.api.buildings`: API building energy, valid hours and peak equal the independent per-meter figures for every building (admin view) | PASS | 10 buildings compared, largest energy difference 0.0020 kWh; differing: none |
| 119 | peacock | `peacock.api.totals`: API overview totals (hours, valid hours, energy, mean, peak, peak hour) equal the independent community demand | PASS | energy API 15,596,896.757 vs independent 15,596,896.740 kWh (diff +0.0166, allowed 104.36); valid hours 17,393 vs 17,393; peak 1,338.578 vs 1,338.578 kW at 2016-09-10 19:00:00 |
| 120 | peacock | `peacock.api.monthly`: API monthly energy and valid hours equal the independent monthly sums for every calendar month | PASS | 24 months compared; differing months: none |
| 121 | peacock | `peacock.api.buildings`: API building energy, valid hours and peak equal the independent per-meter figures for every building (admin view) | PASS | 11 buildings compared, largest energy difference 0.0594 kWh; differing: none |
| 122 | rat | `rat.api.totals`: API overview totals (hours, valid hours, energy, mean, peak, peak hour) equal the independent community demand | PASS | energy API 8,328,445.710 vs independent 8,328,445.710 kWh (diff +0.0000, allowed 83.10); valid hours 16,620 vs 16,620; peak 938.380 vs 938.380 kW at 2016-07-25 15:00:00 |
| 123 | rat | `rat.api.monthly`: API monthly energy and valid hours equal the independent monthly sums for every calendar month | PASS | 24 months compared; differing months: none |
| 124 | rat | `rat.api.buildings`: API building energy, valid hours and peak equal the independent per-meter figures for every building (admin view) | PASS | 9 buildings compared, largest energy difference 0.0000 kWh; differing: none |
| 125 | robin | `robin.api.totals`: API overview totals (hours, valid hours, energy, mean, peak, peak hour) equal the independent community demand | PASS | energy API 9,440,079.218 vs independent 9,440,078.881 kWh (diff +0.3370, allowed 78.00); valid hours 17,334 vs 17,334; peak 1,165.238 vs 1,165.238 kW at 2016-01-19 19:00:00 |
| 126 | robin | `robin.api.monthly`: API monthly energy and valid hours equal the independent monthly sums for every calendar month | PASS | 24 months compared; differing months: none |
| 127 | robin | `robin.api.buildings`: API building energy, valid hours and peak equal the independent per-meter figures for every building (admin view) | PASS | 8 buildings compared, largest energy difference 0.1927 kWh; differing: none |
