# Atlanta Metro Census Tract Master File — Methodology

All steps below are at **Census Tract level** (not ZIP Code). Every dataset joins to the Census Tract layer using **TractGeoID** — the 11-character Census Tract GEOID, always stored as text/string, zero-padded. This field type discipline was the single most common source of join failures throughout this project and should be enforced at every step.

**Open question, unresolved:** the true target vintage year is inconsistently referenced across sources as 2010, 2011, or 2012. Most work targeted 2012; a later cross-check against a related study suggested 2010. The target year is to be confirmed before final variable vintages are locked in.

---

## 1. Building Footprints — Atlanta (Government, 2012)

**Source:** Atlanta Esri REST Service, Structure Footprints layer, 2012 vintage, City of Atlanta extent only

**Steps:**
1. Project to NAD83 StatePlane Georgia West FIPS 1002 (US Feet)
2. **Spatial Join** — direction matters:
   - ❌ First attempt: Target = Census Tracts, Join Features = Buildings, "Join one to one" → returned `Join_Count = 0` for every row
   - ✅ Diagnosed via **Select Layer By Location** (Input = Census Tracts, Relationship = Intersect, Selecting Features = Buildings) — confirmed the spatial relationship itself was valid, ruling out a data problem
   - ✅ Working setup: **Target Features = Buildings**, **Join Features = Census Tracts**, Match Option = Intersects → tags every building with `TractGeoID`
3. **Summary Statistics** — Case Field = `TractGeoID`; Statistics Fields = building area → SUM, MEAN, MAX; count of buildings per tract
4. Join summary table back to the Census Tract master via `TractGeoID`

**Result / limitation:** Matched 216 of 1,970 tracts (city extent doesn't cover the full metro study area). Of those 216, only **22 overlap with the 174 HIGH/LOW energy-study tracts** — too small a sample for building-morphology-vs-energy conclusions on its own.

---

## 2. Building Footprints — Microsoft (2018–2020)

**Source:** Microsoft US Building Footprints, Georgia statewide GeoJSON

**Steps:**
1. GeoJSON was ~1GB — too slow/error-prone to convert via ArcGIS Pro or QGIS's "Save As" directly. Faster alternatives: `ogr2ogr` command-line conversion, or loading the GeoJSON directly into ArcGIS Pro without converting first
2. Checked the `capture_dates_range` field distribution — confirmed Georgia falls inside Microsoft's 2018–2020 recapture tier; **no genuine 2012 subset exists** for this dataset (filtering by date would return zero or near-zero usable rows)
3. Project to NAD83 StatePlane Georgia West FIPS 1002 (US Feet)
4. Same Spatial Join pattern as Atlanta footprints (Buildings = Target, Census Tracts = Join Features, Intersects)
5. Summary Statistics (Case Field = `TractGeoID`; area → SUM, MEAN) → renamed to `microsoft_sum_area`, `microsoft_mean_area`

**QC comparison against Atlanta 2012 data:**
1. Joined both sources' tract-level sums on `TractGeoID`
2. `PctDiff_bldg = (microsoft_sum_area − sum_buildi) / sum_buildi × 100`
3. Identified and excluded **15 tracts** with implausibly tiny Atlanta-side values (e.g., 63 sq ft for an entire tract) — a sign of incomplete building coverage at the tract edge, not real data
4. Remaining 201 tracts: **median difference +13.7%, IQR +3.5% to +27.5%** — a moderate, fairly consistent offset, supporting use of Microsoft data as a supplement despite the vintage gap

---

## 3. Distance to CBD

**Source:** Atlanta CBD boundary polygon (provided with the study data)

**Steps:**
1. **Feature To Point** — Input = CBD polygon, Output = `CBD_centroid`, **"Inside" option checked** (guarantees the point falls within the actual polygon, important since the CBD shape is irregular/concave)
2. **Feature To Point** — Input = Census Tract polygons, Output = `tract_centroids`, "Inside" checked (same reasoning; also required because Near on raw polygons behaves incorrectly — see Section 4)
3. **Near** — Input Features = `tract_centroids`, Near Features = `CBD_centroid`, Method = Planar, Distance Unit = US Survey Feet → `NEAR_DIST`
4. Renamed `NEAR_DIST` → `Dist_CBD_ft`
5. Joined back to master via `TractGeoID` (carried over automatically from Feature To Point)

**Methodological note:** Euclidean/straight-line distance was used deliberately, not Network Analyst street-distance. This is consistent with monocentric city model conventions in urban economics, and the existing signal is already strong (High EE tracts ~11.6 mi from CBD vs. Low EE ~31.2 mi) — the added setup time to build a clean, topologically correct road network for Network Analyst was judged not worth the likely marginal improvement, especially since network routing for straight distance does **not** require speed/velocity assumptions (only time-based travel routing does) — the real cost is verifying road topology.

---

## 4. Distance to MARTA Rail Station

**Source:** MARTA Rail Stations point layer

**Steps:**
1. Project to NAD83 StatePlane Georgia West FIPS 1002 (US Feet)
2. ❌ First attempt: **Near** run with Input Features = Census Tract **polygons** directly → returned distance = 0 for every row
   - **Root cause:** Near measures distance to a polygon's boundary/edge. Any MARTA station physically located *inside* a tract registers as distance 0 to that polygon — and since stations are often inside their containing tract, this produced widespread zeros
3. ✅ Fix: reused `tract_centroids` (from the CBD step) as Input Features instead of raw polygons
4. **Near** — Input Features = `tract_centroids`, Near Features = MARTA Rail Stations, Method = Planar, Distance Unit = US Survey Feet, custom Field Names set (Feature ID → `station_fid`, Distance → `station_dist`)
5. Confirmed fix worked: real, varied distance values instead of all zeros
6. Renamed/used as `Dist_MARTA_Rail_ft`

**General rule established:** any Near-tool distance calculation must run on **centroid points**, never raw polygons, or it will silently return 0 for any near-feature located inside the polygon.

---

## 5. Walkability Index (NatWalkInd) + Street Intersection Density (D3b)

**Source:** EPA Smart Location Database, standalone National Walkability Index download (v3.0), Census Block Group level

**Important distinction:** this standalone file's own "D4a" field means *predicted carpool commute share*, **not** distance to transit — a naming collision with the full SLD's D4a. It was **not used**; the project's own MARTA Near-based distance calculation (Section 4) served as the transit-distance variable instead.

**Steps:**
1. Add Walkability Index shapefile, project to NAD83 StatePlane Georgia West
2. **Select Layer By Location** to narrow to the study area — first attempt used the full 1,970-row Georgia master tract layer as the selecting boundary, which pulled in ~5,711 block groups (essentially the whole state, since that master layer itself spans well beyond the 174-tract study area). Decision made to proceed at full Georgia scale rather than re-narrow, since the join step naturally excludes non-matching rows anyway
3. Export selection → `walkability_atlanta`
4. **Field Calculator:** `TractGeoID = !GEOID10![:11]` (Python — slices the 12-digit Block Group GEOID down to the 11-digit Tract GEOID)
5. **Summary Statistics** — Case Field = `TractGeoID`; Statistics = `NatWalkInd` → MEAN, `D3b` → MEAN → `natwalkind_tract_stats`
6. **Add Join** to master on `TractGeoID`:
   - ❌ First attempt: 0 matches. Diagnosed as a field type mismatch — the master file's join field (`census_code`) was stored as **Double** (numeric), while the walkability table's `TractGeoID` was **Text**
   - ✅ Fix: created a proper text field on the master (`TractGeoID_txt = str(int(!census_code!))`), rejoined on that
7. Renamed `MEAN_NatWalkInd` → `NatWalkInd_tract`, `MEAN_D3b` → `D3b_tract`

**What D3b actually measures:** weighted count of pedestrian-oriented street intersections per square mile. Weighted so 4-way intersections count more than 3-way "T" junctions; auto-oriented intersections (highway interchanges) are explicitly excluded since they're irrelevant to walking. High D3b = fine-grained walkable grid (short blocks); low D3b = sparse suburban layout (cul-de-sacs, long blocks).

---

## 6. Arterial Road Density

**Source:** Initially Georgia statewide roads (2019, primary/secondary only); replaced with **TIGER 2012 Primary/Secondary Roads** (Georgia) to better match the target vintage

**Getting the correct TIGER year:** census.gov's shapefile tool requires selecting **Year** first, which populates the **Layer Type** dropdown — then Roads → Primary and Secondary Roads → Submit. TIGER offers year-specific files back through the archive; both 2012 and 2013 vintages exist for Georgia specifically.

**Steps:**
1. Project to NAD83 StatePlane Georgia West
2. Clip to Census Tract extent (optional, speeds up processing)
3. **Summarize Within** — Input Polygons = Census Tract layer, Input Summary Features = roads layer, Summary Field = `Shape_Length` → SUM → `tract_road_summary` (gives `sum_Shape_Length` per tract)
4. **Field Calculator:** `Arterial_Rd_Density = !sum_Shape_Length! / !Shape_Area!`
   - ❌ Hit `ZeroDivisionError` — diagnosed as the density field being created as **Long (integer)** type, which silently truncates small decimal area values to 0
   - ✅ Fix: recreated the field as **Double/Float** type
5. Optional unit conversion to miles per square mile: `(sum_Shape_Length / 5280) / (Shape_Area / 27878400)`

**Interpretation:** this measures **arterial/highway accessibility** specifically (primary/secondary roads only, no local streets) — it complements D3b (which measures the fine-grained local pedestrian grid) rather than duplicating it.

---

## 7. Air Quality

**Source:** Regional air quality model output, 12km grid resolution, delivered as a point table (columns: `GEOID10`, `longitude`, `latitude`, `Lambert_X`, `LAMBERT_Y`, `date`, plus O3/CO/NO/NO2/SO2/CH2O/PM10/PM2.5 and PM2.5 sub-components), single date snapshot

**Steps (spatial join performed by the research team):**
1. Nearest-point one-to-one spatial join — since the 12km grid doesn't align with 1–3km Census Tract boundaries, not every tract contains a grid point, so nearest-point matching was used instead of a strict spatial containment join
2. Output confirmed `Join_Count = 1` for every row — a clean, correctly-executed 1:1 nearest match

**Verification performed:**
1. Checked `column`/`row` fields plus `Lambert_X`/`LAMBERT_Y` spacing — confirmed **perfectly even 12,000-unit (12km) steps**, proving this is raster-derived gridded model output, not real monitoring stations (real station networks would never produce such regular spacing)
2. Counted unique underlying grid values: only **138 unique AQ points behind 1,000 tracts** — on average ~7 tracts share an identical value, with one extreme case of 66 tracts sharing the same value

**Methodology assessment:** nearest-point join is a legitimate, defensible method — not an error. **Zonal Statistics** was discussed as a more rigorous alternative (area-weighted blending for tracts straddling two grid cells), but since most Census Tracts are smaller than a single 12km cell, the two methods would return identical results for the majority of tracts. The 138-unique-value resolution ceiling is a property of the source data, not fixable by changing the join method. Interpolation was explicitly ruled out as inappropriate — the grid already has full, gap-free coverage, so there's nothing to estimate; interpolation is for filling genuinely missing values, not reassigning existing ones.

**Integration into master file:** done via Python/pandas (not ArcGIS Add Join) — `GEOID10` converted to zero-padded 11-character text before merging on `TractGeoID`.

---

## 8. Remote Sensing Rasters — NDVI, Impervious Surface, Land Surface Temperature, Leaf Area Index

### 8a. Sourcing — Impervious Surface & Tree Canopy Cover (via MRLC.gov)

1. On the MRLC data viewer, the dataset tree has two relevant sections:
   - **Annual NLCD** — continuous yearly series (1985–2025), needs a year selector/slider once opened
   - **Legacy NLCD** — discrete standalone releases (2001, 2006, 2011, 2016...)
2. Selected: Annual NLCD → **Fractional Impervious Surface**; NLCD Tree Canopy → **CONUS Tree Canopy** (CONUS = the 48 contiguous states — correct choice; PR/HI/AK are separate, irrelevant options)
3. **Data Download panel:** Method = Rectangle, Download Contents = GeoTIFF, set the year slider, enter a Latitude/Longitude bounding box, provide contact details
4. ❌ First bounding box attempt was drawn too small and clipped part of the study area
5. ✅ Redone with a generous Atlanta Metro buffer: Latitude 33.10–34.20, Longitude −85.00 to −83.60 (a full-Georgia fallback box of Latitude 30.35–35.05, Longitude −85.65 to −80.75 was also identified as a safer, larger alternative)
6. **Year ambiguity:** initially downloaded 2012-vintage files; after finding that a related study referenced 2010, switched to the 2010-vintage files instead — this is tied to the broader unresolved year question and should be confirmed before finalizing

### 8b. Sourcing — NDVI & Land Surface Temperature & Leaf Area Index (via USGS EarthExplorer)

1. ❌ First dataset selection error: **"Landsat 8-9 OLI/TIRS C2 L2"** was selected, which produced "No Results Found" for any 2010–2012 search — Landsat 8 didn't launch until February 2013, so no data exists for that mission in the target years
2. ✅ Corrected dataset: **"Landsat 4-5 TM C2 L1"** for NDVI (the mission actually operating in 2010–2012)
3. For **Land Surface Temperature specifically**, use **"Landsat 4-5 TM C2 L2"** (Level-2, not Level-1) — Level-2 includes a pre-calculated Surface Temperature (ST) band, avoiding manual thermal band math
4. ❌ Location filter error: initially left at the full State of Georgia extent, producing 844 pages / 84,389 results — far too broad
5. ✅ Fix: narrow to Atlanta specifically via place-name search ("Atlanta, GA") in the Search Criteria tab, or by entering Atlanta's Landsat WRS-2 Path/Row directly (approximately Path 019, Row 036) under Additional Criteria
6. Scene selection criteria: prioritize summer months (June–August) for the strongest vegetation signal; choose the lowest cloud cover; visually confirm via thumbnail that clouds aren't sitting directly over the Atlanta study area before downloading

### 8c. Processing all 4 rasters — same pattern

1. Add each raster to ArcGIS Pro, confirm/set CRS
2. **Zonal Statistics as Table** — Input Zone = Census Tract layer, Zone Field = `TractGeoID`, Input Raster = the variable raster, Statistic = MEAN, Output = `[variable]_tract_stats`
   - The Batch option (right-click the tool → Batch) allows queuing all 4 raster runs at once instead of reopening the tool manually each time
3. ❌ **Add Join repeatedly failed (0 matches)** for these outputs — root causes identified:
   - Zonal Statistics as Table does not reliably preserve the zone field's name — it can output a generic `VALUE` field, or retain the raw source field name (e.g., `GEOID10_1`) instead of `TractGeoID`
   - Shapefile text fields can carry hidden trailing whitespace (fixed-width storage padding), which breaks exact-match joins even when values look visually identical
   - Separately, a `Calculate Field` operation threw **"Failed to write value ... to output field GEOID"** — diagnosed as the `GEOID` field's defined text length being too short to hold an 11-character value
4. ✅ **Resolution:** abandoned ArcGIS Add Join for these 4 variables. Each Zonal Statistics table was exported to Excel and joined into the master file using **Python/pandas** instead, explicitly casting the zone field to a zero-padded 11-character text string before merging. This worked cleanly on the first attempt, with zero duplicate keys and no join failures.

**Final coverage:** NDVI, Impervious Surface, and LST matched 655 of 1,970 tracts (82 of the 174 energy-study tracts). LAI matched a smaller 426 tracts (62 of 174 energy-study tracts) — expected, since LAI is only meaningful over vegetated pixels and returns no value for water, dense urban cores, etc.

---

## 9. General Recurring Issues (apply across nearly every step above)

- **TractGeoID field type mismatches** (Double vs. Text, or Long silently truncating decimals) caused the large majority of "0 matches" join failures throughout this project. Always verify both sides of a join share the same field type before troubleshooting further.
- **Spatial Join direction matters** — which layer is Target Features vs. Join Features determines whether "Join one to one" succeeds or silently returns 0 matches with no error message.
- **Near tool requires centroid points, never raw polygons**, for any meaningful point-distance calculation — running it on polygons returns 0 for any near-feature located inside that polygon.
- **Shapefile's 10-character field name limit** caused repeated ambiguity when interpreting old vs. new fields as the master file grew (e.g., `census_cod` vs. a full `census_code`).
- **Large GeoJSON files (~1GB+)** caused slowdowns/errors converting to shapefile in both ArcGIS Pro and QGIS — `ogr2ogr` command-line conversion, or loading GeoJSON directly into ArcGIS Pro without converting, were faster workarounds.
- **Select Layer By Location** is a useful simpler diagnostic when a Spatial Join's result is suspicious — it tests the raw spatial relationship independent of Spatial Join's own settings (one-to-one, field merge rules, etc.).
