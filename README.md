# Covariate Labelling

A workflow that labels a subject **trajectory** dataframe with **Google Earth Engine
covariates**.

It builds the trajectory from EarthRanger, joins Earth Engine covariates onto each
trajectory segment by time and location, and exports the labeled table. It applies both
covariate-labeling methods: a **static image** (elevation) and a **temporal image
collection** (NDVI).

## Pipeline

```
EarthRanger pull -> relocations -> trajectory -> label: static image + temporal collection (GEE) -> export (parquet + CSV)
```

The output is the trajectory table with the covariate column(s) appended:
`trajectories.parquet` (with geometry) and `trajectory_stats.csv` (tabular, for downstream
applications). Each segment gains an `elevation` column (static) and an `NDVI` column
(temporal).

## Run form

- **Static image ID** — the Earth Engine image asset path sampled for the static covariate.
  Default `USGS/SRTMGL1_003` (SRTM elevation). Editable.
- **Image collection ID** — the Earth Engine ImageCollection asset path sampled for the
  temporal covariate. Default `MODIS/061/MYD13A1`. Editable.
- **Image stack** — how many extra images to include on **each side** of the temporally
  closest image. `0` (default) = only the single closest image, i.e. one covariate value per
  segment. `2` = the 2 images before + the closest + the 2 after, which returns several rows
  per segment.

All three are Earth Engine **asset paths**, not band names (a common mistake: entering
`NDVI` as the collection fails, because `NDVI` is a band, not a collection).

## Which band gets sampled

A collection or image usually has **many bands** (MYD13A1, for example, has `NDVI`, `EVI`,
quality layers, reflectance bands). Leaving the band unset samples them all — a column each.
To keep the output clean the workflow pins the band per labeler: `elevation` for the static
image, `NDVI` for the temporal collection. To sample a different band (or change the reducer
or scale), edit the pinned `bands` / `reducer` for that step in `spec.yaml`.

## Notes on the output

- **Raw MODIS scaling.** MODIS NDVI is stored as an integer scaled by `0.0001` (e.g. `1792`
  = `0.1792`). Multiply by `0.0001` downstream to get true NDVI.
- **Nulls.** A segment is null for a covariate when it has no data at that location/time —
  NDVI where no image falls close enough in time to the segment, or elevation where a segment
  crosses water. Widening the image stack fills more temporal gaps.

## The two methods (tasks)

Two registered tasks implement the two covariate-labeling methods, both wrapping Ecoscope's
Earth Engine helpers via `chunk_gdf` (batched to stay within Earth Engine limits):

- `label_with_static_image` — samples a single GEE image (Method 1). Sampled per segment so
  segments over no-data come back as null rather than dropped.
- `label_with_temporal_image_collection` — samples a time-matched image collection (Method 2).
