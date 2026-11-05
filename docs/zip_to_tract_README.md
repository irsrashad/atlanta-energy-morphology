# ZIP-to-tract energy comparison

Compares ZIP-level energy estimates, redistributed to census tracts, with the
tract-level model estimates. The code in `src/zip_to_tract.py` reproduces the
lost original analysis; `Workings_Transparent.xlsx` is the ground truth and the
tests check every row against its `Step5_Final_Comparison` sheet.

The "ZIP-to-tract table" used throughout is a table that says what share of each ZIP's population lives in each tract.

## Inputs (data/raw/tables, not tracked by git)

- `highEE_FullData.xlsx`, `lowEE_FullData.xlsx`: ZIP estimates in `RF_ZCTA_Estimates`
  (`predictedRF_train`, `predictedRF_cv_train`, `predictedmatlab_train`, `actual`),
  tract estimates in `censusEstimates` (`RFnewCensus_RF`, `RFnewCensus_cv`, `matlabnewCens`).
  Neither sheet holds ids. ZIP ids (`ZCTA`) come from `ZipCode Coordinates` (high) / `Coordinates` (low);
  tract ids (`Census`, stored as floats) plus lat/lon come from `Census Coordinates` (high) / `testCoordinates` (low).
  All are row-aligned with the estimate sheets.
- `ga_zip_tract_equivalence.csv`: ProximityOne equivalence table, used as the ZIP-to-tract table for the first run (2,483 rows, 196 ZIPs, 1,539 tracts).
  `Pct` is a 0-1 fraction that sums to 1.0 within each ZIP.
- `Workings_Transparent.xlsx`: reference workbook used only by the tests.

## Method

1. ZIP and tract ids are read as text and zero-padded to 5 and 11 characters (float tract ids go through int64 first). Nothing needed padding in this data.
2. ZIP energy from **all 196 ZIPs (both clusters)** is inner-joined once to the ZIP-to-tract table, each energy column is
   multiplied by `Pct` (population-weighted areal interpolation), and summed by tract. This
   aggregation is done before the per-cluster tract join. It matches `Workings_Transparent.xlsx` (Step4 has all 1,539 tracts);
   a strictly per-cluster aggregation loses tract 13063040606, a LOW-list tract fed by two HIGH-cluster ZIPs.
3. Each cluster's tract estimates (HIGH from highEE, LOW from lowEE) are inner-joined to that aggregate on TractGeoID.
4. Delta = ZIP sum - tract estimate; PctDelta = Delta / tract estimate * 100; exceedance = Delta > 0.
   Mapping: predictedRF_train -> RFnewCensus_RF, predictedRF_cv_train -> RFnewCensus_cv, predictedmatlab_train -> matlabnewCens.
5. Agreement tier on abs(PctDelta): 0-10 Very Low, 10-20 Low, 20-30 Moderate, 30-40 High, over 40 Very High.
   If the tract estimate is <= 0 the tier is N/A and PctDelta is left blank; exceedance is still computed.

Result: 66 matched tracts (17 HIGH, 49 LOW). Exceedance 11 / 16 / 44 (RF Train / RF CV / MATLAB).

### Tier edge convention

Both conventions were tested against the workbook's Agreement columns: upper-inclusive bands `(lo, hi]` and
lower-inclusive bands `[lo, hi)` each give 0 mismatches over 66 tracts x 3 models, because no tract falls exactly on
an edge. It does not matter for this data. The code uses `(lo, hi]` (exactly 10% is Very Low).

## Caveats

- MATLAB estimates are unreliable: 34 of the 66 tract estimates are negative. They are kept and flagged
  (`Matlab_Note`, tier N/A) but should not be used for cross-scale conclusions without a note.
  MATLAB mean PctDelta is dominated by tracts with tiny positive estimates.
- The 10% agreement bands and the HIGH/LOW cluster labels are analyst choices, not standards.
- The weighting assumes the ZIP-to-tract table population shares are a fair proxy for how ZIP energy is spread over tracts.

## Known issue: only 66 of 174 study tracts are matched

There are 175 study-tract rows in the two workbooks (174 unique; tract 13089021909 is in both clusters and is not among the 66).
Of the 109 study-tract rows absent from the ZIP-to-tract table, 106 have a lat/lon centroid inside a study ZIP.
The ZIP-to-tract table is on 2020-vintage tract IDs while the model's tract IDs are 2010. Checked against the 2010 Georgia tract
layer (1,969 tracts): 1,004 of the table's 1,539 tract IDs (65%) do not exist in 2010, covering 63% of its ZIP-tract
rows. All 174 study tracts, including the 108 absent from the ZIP-to-tract table, do exist in the 2010 layer. The non-2010 IDs
cluster in the fast-growing counties (Fulton, Gwinnett, Cobb, DeKalb, Henry) where tracts were split after 2010.
The 66 matches are therefore the tracts whose ID did not change between censuses, which is probably not a random
sample of the 174, so the disagreement reported here may not describe the whole study area.
Tests 12 and 13 print these diagnostic numbers.

## Outputs

- `data/processed/zip_to_tract_comparison.csv` (combined), `..._high.csv`, `..._low.csv`, `zip_to_tract_summary.csv`
- `docs/figures/`: `agreement_tiers.png`, `exceedance.png`, `zip_vs_tract_scatter.png` (log axes; tracts with estimate <= 0 excluded and counted in each panel title), `pctdelta_histogram.png` (values beyond -100/+200 shown in end bins)

## Rerun

```
python -m src.zip_to_tract
python -m pytest -v
```

Run from the repo root with the project virtual environment. Tests skip if the raw inputs are missing.

## Run with the Census 2010 relationship file

The workbook reproduction above is the faithful record of the original analysis. As a second, separate run, the same
pipeline can use the Census Bureau's 2010 ZCTA-to-tract relationship file
(https://www2.census.gov/geo/docs/maps-data/data/rel/zcta_tract_rel_10.txt, saved as
`data/raw/tables/census_rel_2010/zcta_tract_rel_10.txt`, not tracked by git). It is used because the model's tract
ids are 2010 tracts, while the first ZIP-to-tract table appears to be 2020 vintage (only 66 of 174 study tracts match).

- Pct = POPPT / ZPOP (2010 population of the ZCTA-tract part over the ZCTA population), a 0-1 fraction that sums to 1.0 for all 196 study ZIPs.
- Only the 196 study ZIPs are kept (1,802 rows, 998 tracts); everything downstream is the same code path as the default run.
- Run: `python -m src.zip_to_tract --crosswalk census2010`. Outputs carry a `_census2010` suffix
  (`zip_to_tract_comparison_census2010.csv`, `_high`, `_low`, `zip_to_tract_summary_census2010.csv`, and four charts in `docs/figures/`). The default outputs are not touched. (The command-line flag is still called `--crosswalk`.)
- Tract 13089021909 is in both clusters' tract-estimate lists (the HIGH and LOW models give different estimates). Both rows are kept, so the result has 175 rows = 174 unique tracts (HIGH 50, LOW 125).

Headline results (175 rows): exceedance RF Train 45, RF CV 55, MATLAB 116; mean PctDelta RF Train -16.3%, RF CV -4.2%;
median -52.5% and -38.7%. MATLAB has 75 non-positive tract estimates (tier N/A), so it remains unreliable.
For the 66 rows that both ZIP-to-tract tables match, ZIP_RF_sum correlates 0.990 between them and the median absolute PctDelta_RF difference is 1.6 points;
on those 66 rows the 2010 run gives RF Train mean -42.1% / median -55.1%, close to the workbook's -42.6% / -55.5%.
The 109 newly covered rows are more favourable (RF Train mean -0.6%, median -46.9%; exceedance 34 of 109), so the earlier
66-tract result is directionally consistent but understates exceedance. These numbers are printed by `test_c10_g_side_by_side`.
