# subject-trajectory-export

A wt-platform workflow that produces the **full trajectory dataset** for a subject
group as a **downloadable file** (parquet + CSV), for use in external tools such as R.

It is a trimmed variant of the stock **Subject Tracking** workflow. It keeps the
trajectory build, an NSD chart and lightweight per-subject summary tiles, and it
**removes the home-range (ETD) calculation and all map rendering** — the parts that
make large, multi-year runs slow or time out.

## Why this exists

The stock Subject Tracking workflow times out on big jobs (e.g. the whole ATE group
across several years) because of the elliptical time-density (ETD) home-range step,
and it produces a dashboard rather than a downloadable data file. This variant drops
ETD so it runs fast at scale, and adds file export so the trajectory table can be
pulled into R.

## What it outputs

- **`trajectories` (parquet)** — the full segment-level trajectory table, with geometry.
  One row per movement segment, per subject.
- **`trajectory_stats` (CSV)** — the same table without geometry, for R/Excel. Columns:
  `subject_name, subject_subtype, subject_sex, segment_start, segment_end,
  dist_meters` (step length), `timespan_seconds, speed_kmhr, nsd, extra__is_night`.
- **Dashboard** — an NSD chart plus per-subject summary tiles (mean/max speed, number
  of locations, night/day ratio, total distance, total time). No maps, no home range.

## Key settings (in the run form)

- **Subject group** and **time range** — the animals and period.
- **Trajectory segment filter** — e.g. `max_speed_kmhr: 8`, `max_time_secs: 12000`.
- **Grouping** — group by `subject_name` (and/or a monthly temporal grouper) as needed.

To restrict to specific animals (the GUI filters by group, not by individual), create
a subject group for them in EarthRanger and point the workflow at it.

## How it was built

`spec.yaml` was derived from the released `subject-tracking` spec
(`ecoscope-platform` 2.16.1) by:

1. Removing the entire **Time Density Map** (ETD) task group and its dashboard widget.
2. Removing the two **ecomap** chains (trajectory speed map, night/day map), the speed
   classification, and the base-map definitions.
3. Re-pointing `split_subject_traj_groups` at `map_subject_sex` (the full trajectory
   frame) now that the speed-classification step is gone.
4. Adding three export tasks: `persist_df` (parquet) of the full trajectory frame,
   `subset_columns` to select the movement metrics, and `persist_df` (CSV) of that.
5. Trimming the dashboard to the summary tiles + NSD chart.

Everything kept is reused verbatim from the released spec, so the retained wiring is
known-good.

## Repo contents

This repo holds the **source** for the workflow. The runnable package is *generated*
from `spec.yaml` by `wt-compiler` (see below) — it is not committed here.

```
spec.yaml          the workflow definition (the thing you edit)
metadata.yaml      name / category / description shown on the platform
layout.json        dashboard tile arrangement
test-cases.yaml    named configs used by CI / local test
pixi.toml          brings in wt-compiler + defines the `compile` task   <- was missing
Makefile           same compile step for a global wt-compiler install
README.md · LICENSE
```
