# UI and UX improvements

This records what was changed in the interface during the upgrade, why, and how it was checked. It also says what was **not** changed, because the delivered interface already had a consistent design and the brief was to keep the project's identity.

## 1. Starting point and approach

The baseline (the delivered project before this upgrade) already had a coherent visual system: IBM Plex Sans (served from the package, no external font request), a teal accent, a left navigation with two groups (*Residential society* and *System*), white cards on a pale background, a coloured notice component (info, warning), a Chart/Table toggle and zoom controls on time-series charts, and honest labels (for example "An estimate, not a bill", "Historical data 2016 to 2017"). Compare `docs/screenshots/baseline/desktop__cost.png` with `docs/screenshots/final/desktop__cost.png`.

So the upgrade was **targeted, not a re-skin**: the baseline was probed page by page (see [`FINAL_FEATURE_AUDIT.md`](FINAL_FEATURE_AUDIT.md)), problems and gaps were fixed, and new capability was added in the existing style. Colours, type, spacing tokens, icons and layout were kept so existing users, documents and screenshots stay recognisable.

## 2. Changes

### 2.1 Things a user could not do or see before

| Change | Why | Where | Checked by |
|---|---|---|---|
| **Compare communities** page (menu entry, four horizontal bar charts and an all-figures table: energy per m², load factor, peak per m², 24 h forecast error as % of average demand; selected community highlighted; a note that sites differ in climate, size and years) | A manager comparing seven communities had to open each in turn, and raw kWh cannot be compared across different sizes | `pages/society/CompareCommunitiesPage.tsx` | `verify_new_rr7.log`, `newfeatures.test.tsx`, crawl at three widths |
| **Tariff manager** on *Cost and peaks*: add a tariff from a bill (flat or peak/off-peak, any offered currency, fixed daily charge), live rate preview, use, delete; field errors shown beside the field | The only tariff was a placeholder, so cost could never reflect a real bill | `PeaksCostPage.tsx`, `lib/tariff.ts` | `verify_tariff_rr7.log` (13 of 13), `lib/tariff.test.ts` |
| **Load-duration curve** and **distribution of demand** on the *Peak demand* tab | The shape of peak demand was only a summary table | `PeaksCostPage.tsx` | crawl, `newfeatures.test.tsx` |
| **Forecast error analysis** (average bias, mean absolute error against the baseline, median and 95th-percentile error, share of hours inside the 80 % band, error histogram, error by hour of day, the largest errors) | Accuracy was one number; a manager needs to know *when* the forecast is wrong | `SocietyForecastPage.tsx` | `verify_functional.log`, `newfeatures.test.tsx` |
| Window title follows the page ("Cost and peaks · EnergiQ AI", "Page not found · EnergiQ AI") | Every tab and history entry said the same thing | `lib/pageTitle.ts` | `verify_routing.log`; the crawl records 16 distinct titles |

### 2.2 Things that were misleading

| Change | Where | Checked by |
|---|---|---|
| The peak-forecast evaluation printed "[object Object]" for the model and baseline names; names now shown | *Cost and peaks, Peak demand* | BUGS_FIXED A1 |
| The note under *Model comparison* could contradict the table in 8 of 35 community-and-horizon cases; it now says which model is deployed and how the best learned model did, in plain words, and the cross-validation error of baselines is shown too | *Forecasting* | BUGS_FIXED A2; `modelChoice.test.ts`; `verify_model_choice.log` |
| "Models not installed" for five of seven communities; all seven now forecast live | *Forecasting*, *Overview* | BUGS_FIXED A3 |
| A stale "Invalid e-mail or password" stayed next to a new validation message | Sign-in | BUGS_FIXED A4 |
| Rupee amounts grouped the international way (1,234,567); Indian grouping (12,34,567) for INR | all money fields | `lib/format.ts`; unit test; `verify_tariff_rr7.log` ("₹2,31,26,989") |

### 2.3 Charts

| Change | Why |
|---|---|
| The tariff preview starts at zero | It auto-zoomed to 7.4 to 8.6, which made a flat tariff look volatile |
| Unit labels shortened (`INR/kWh`) and axis titles added to the horizontal bar charts | A unit was clipped; bars had no axis title |
| Load-duration x axis ticks every 10 % | Ticks were irregular |
| Long labels given room (`yWidth` 170) in the model-comparison chart | Labels were truncated |
| Comparison table: shorter headers, cells that do not wrap | "Period" wrapped over four lines |

**Chart rules applied to every chart, and where each was verified**

| Rule | Result |
|---|---|
| Title, axis titles, units | All 18 charts on the 7 pages that have charts have a title, tick labels and at least one axis title (`docs/final_verification/logs/hover_check.log`; for the Buildings comparison chart the script resolved a control label, and the card's title "Building comparison" was confirmed in the page headings) |
| Legend where more than one series | Present (for example measured, forecast and 80 % range on the overview) |
| Hover values | A tooltip with the value and its unit appeared on all 18 charts when the mouse crossed the plot (`hover_check.log`), with no console message |
| A table alternative | Chart/Table toggle on every time-series chart; table view row counts checked (717 rows on Consumption) |
| Empty data | An explanatory message in place of an empty frame (for example the Facilities page for communities without separate meters; "No explanation for this horizon" where the selected method is a baseline) |
| Responsive | No horizontal page overflow at 1440, 820 and 390 px (48 of 48 visits) |
| Only data that exist | No solar, renewable or carbon chart: there are no such data |

### 2.4 Tables and forms

* A table wider than its container scrolls sideways inside a **focusable, named region with a visible focus ring**, so a keyboard or screen-reader user can reach all columns (it could not be reached before).
* The Reports table's empty header cell (the download column) now has a visually hidden "Download" header.
* Forms say what is wrong beside the field (sign-in, registration, tariff).
* Destructive actions ask first and name what will be removed (deleting a society, deleting a tariff).

## 3. Accessibility

* **axe-core** with the WCAG 2.0/2.1 A and AA rules plus best-practice rules: **0 violations** on the 15 signed-in routes at desktop and phone width and on the sign-in page at desktop width (31 scans, `docs/final_verification/logs/a11y_scan.log`). Automated scanners find roughly a third of accessibility problems; this is a necessary check, not a certificate.
* Keyboard: visible focus outline on controls (`:focus-visible`), radio groups focus through their hidden inputs, tables reachable (above), one `h1` per page (the crawl records exactly one for each route).
* Colour is not the only carrier of meaning in the places checked: notices carry an icon and a title; chart series are named in the legend, and on the overview the measured line is solid and the forecast dashed.
* Motion: `prefers-reduced-motion` is honoured.
* Language attribute and viewport are set.

## 4. Responsive behaviour

Three widths were crawled after the last code change: 1440 px (desktop), 820 px (tablet) and 390 px (phone). On the phone the menu collapses behind a button, charts fill the width, tables scroll inside their region, and the page itself does not scroll sideways. See `docs/screenshots/final/` (`desktop__*`, `tablet__*`, `mobile__*`).

## 5. Images

The interface uses **no photographs or stock pictures**, and none were added. For an energy-management tool the charts, tables and icons are the content; decorative images would add files with licence questions and nothing a user could act on. The logo and icons are inline vector graphics. Screenshots of the application are documentation, not part of the interface.

## 6. Not done, on purpose or for lack of a way to test

* No dark theme and no language other than English.
* Tested in Chromium only. Firefox, Safari, and real phones and tablets were not available; the 820 px and 390 px runs use Chromium's viewport emulation.
* No manual screen-reader session (NVDA, VoiceOver); only the automated scan and a keyboard-reachability review of the table region.
* No user study. The audit judges whether controls work and are honest, not whether they are liked.
* Windows high-contrast mode and Windows text scaling were not tested.
