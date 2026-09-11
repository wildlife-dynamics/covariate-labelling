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

After you compile, a new directory appears:
`ecoscope-workflows-subject-trajectory-export-workflow/` — **that** is the runnable
package (its own `pixi.toml`, `pyproject.toml`, `Dockerfile`, generated DAG code, etc.).
Commit it and deploy/publish it the same way as other wt workflows.

## Compile it (required — this is what produces the runnable workflow)

### Option A — local, no global install (matches `pixi run -e compile ...`)

The included `pixi.toml` provides the compiler in a `compile` environment:

```console
pixi run -e compile compile
```

That runs:

```
wt-compiler compile --spec=spec.yaml --pkg-name-prefix=ecoscope-workflows \
  --results-env-var=ECOSCOPE_WORKFLOWS_RESULTS --variant=gcp --clobber
```

Use `pixi run -e compile compile-install` to also build the generated package's
runnable environment locally.

> If the compile step errors about `dot`/graphviz, run `dot -c` once (graphviz is
> already a dependency of the `compile` environment), then re-run.

### Option B — global wt-compiler + make

```console
pixi global install -c https://prefix.dev/ecoscope-workflows -c conda-forge \
  wt-compiler --run-post-link-scripts
pixi self-update
make compile
```

## Note: this repo could not be compiled where it was generated

The compile step needs `wt-compiler` and the `ecoscope-workflows` package channel,
which weren't available in the environment that wrote this repo — so the generated
package is produced by **you** running one of the commands above on a machine with
pixi and channel access. Everything needed for that command is in this repo.

## Export step — tasks used

The export uses core `ecoscope-platform` tasks only, so no custom extension
packages are required:

- **`persist_df`** — writes the full trajectory frame to `trajectories.parquet`
  (with geometry) and the tabular frame to `trajectory_stats.csv`. Validated by the
  compiler.
- **`map_columns`** (`drop_columns: [geometry]`) — produces the clean tabular frame
  for the CSV. This replaced an earlier `subset_columns` step, which is **not** a core
  task (it lives in a custom extension) and failed compilation.

## Custom task — per-group plot filenames

The NSD plot is named after its group (e.g. `Esposito_net_square_displacement.html`,
or `all_net_square_displacement.html` when ungrouped) instead of a content hash. Core
`ecoscope-platform` can't produce a per-group string filename, so this workflow ships a
small task, exactly like `create-vcf-basemap` ships its own:

```
tasks-pkg/
  pyproject.toml                         # registers the task via wt_registry entry-point
  src/subject_trajectory_export_tasks/
    tasks.py                             # @register() def group_plot_filename(...)
```

It is wired in through `spec.yaml requirements:` as an **editable pypi path**
dependency, so the compiler discovers it and the runtime env installs it — no channel
publishing needed:

```yaml
- name: subject-trajectory-export-tasks
  path: /Users/la/pgaff/bull_movement/subject-trajectory-export/tasks-pkg
  editable: true
```

**Important:** `PyPIRequirement.path` must be **absolute**. If you move this repo (or
build it on another machine), update that `path` in `spec.yaml` and recompile. The task
labels the file by `subject_name` when a group has one subject, and `all` when it has
many (the ungrouped case). If you group by month, every month's subjects are "many", so
those files would all label `all` — say so and I'll switch the label source to the
grouper key.

## Still worth a glance after compile

- **`layout.json`** widget ordering — the `widget_id` values are best-effort (6 tiles
  then the NSD chart). Adjust after compile if the dashboard ordering looks off.
- If compilation warns it **skipped post-link scripts** and later can't find `dot`,
  run `pixi config set --local run-post-link-scripts insecure` once, then re-compile.
