"""Covariate-labeling tasks: label a (geo)dataframe with Google Earth Engine covariates.

Two registered tasks wrap the Ecoscope GEE labeling primitives so a workflow can
attach earth-observation covariates to an existing frame (e.g. trajectory
segments):

- ``label_with_static_image``              -> covariate(s) from a single GEE
                                              image (e.g. elevation from a DEM).
- ``label_with_temporal_image_collection`` -> a time-matched covariate from an
                                              image collection (e.g. NDVI per
                                              segment).

Both route through ``eetools.chunk_gdf``, which processes the features in
batches so large jobs don't exceed Earth Engine's per-request quota/memory
limits (the canonical pattern from the Ecoscope "Module 6 - GEE" notebook).
Each returns the input frame with the covariate column(s) appended. Heavy GEE
imports happen inside the task bodies so importing this module for the registry
scan stays light -- mirroring ecoscope's own ``_earthengine`` tasks.
"""

from __future__ import annotations

from typing import Annotated, Optional

from ecoscope.platform.annotations import AnyGeoDataFrame
from ecoscope.platform.connections import EarthEngineClient
from pydantic import Field
from wt_registry import register

# Region reducers offered to the run form. 'mean' gives one scalar per feature
# (best for line/polygon segments); 'toList' returns the raw pixel value(s).
_ALLOWED_REDUCERS = {
    "mean",
    "median",
    "mode",
    "min",
    "max",
    "sum",
    "stdDev",
    "first",
    "toList",
}


def _build_reducer(name: str):
    """Turn a reducer name (e.g. 'mean') into a validated ee.Reducer."""
    import ee

    if name not in _ALLOWED_REDUCERS:
        raise ValueError(
            f"reducer must be one of {sorted(_ALLOWED_REDUCERS)}, got {name!r}"
        )
    return getattr(ee.Reducer, name)()


def _label_gdf_with_img_robust(gdf, img, region_reducer, scale=500.0):
    """Sample a static image per feature, keeping EVERY input row.

    ecoscope's ``label_gdf_with_img`` uses ``reduceRegions``, which silently
    drops features that do not overlap the image and then rebuilds a frame on
    the original index -- a length mismatch when any feature is over no-data
    (e.g. line segments crossing water on a DEM). This maps ``reduceRegion``
    over the features 1:1, so a feature with no data becomes NaN instead of
    vanishing.
    """
    import ee
    import pandas as pd

    in_fc = ee.FeatureCollection(gdf[["geometry"]].__geo_interface__)

    def feat_func(feat):
        return feat.set(
            "img_vals",
            img.reduceRegion(
                reducer=region_reducer, geometry=feat.geometry(), scale=scale
            ),
        )

    out_fc = in_fc.map(feat_func)
    raw = out_fc.reduceColumns(ee.Reducer.toList(1), ["img_vals"]).get("list").getInfo()

    def _norm(r):
        if isinstance(r, list):
            return r[0] if r else {}
        return r if isinstance(r, dict) else {}

    dicts = [_norm(r) for r in (raw or [])]
    return pd.DataFrame(dicts, index=gdf.index)


@register(tags=["io"])
def label_with_static_image(
    client: EarthEngineClient,
    df: Annotated[
        AnyGeoDataFrame,
        Field(
            description="The (geo)dataframe to label. Must carry geometry.",
            exclude=True,
        ),
    ],
    image_id: Annotated[
        str,
        Field(
            description="Full Earth Engine image asset ID (a path, not a band name), e.g. 'USGS/SRTMGL1_003'."
        ),
    ] = "USGS/SRTMGL1_003",
    bands: Annotated[
        Optional[list[str]],
        Field(
            description="Image bands to sample, e.g. ['elevation']. Leave empty to use all bands."
        ),
    ] = None,
    reducer: Annotated[
        str,
        Field(
            description="Region reducer per feature (mean, median, mode, min, max, sum, stdDev, first, toList)."
        ),
    ] = "mean",
    scale: Annotated[
        float,
        Field(
            description="Sampling scale in metres; the image's native resolution is a good default."
        ),
    ] = 500.0,
    df_chunk_size: Annotated[
        int,
        Field(
            description="Features sampled per Earth Engine request. Lower it if you hit GEE quota/memory limits."
        ),
    ] = 5000,
    column_prefix: Annotated[
        Optional[str],
        Field(
            description="Optional prefix for the new covariate column(s), to avoid name clashes."
        ),
    ] = None,
) -> AnyGeoDataFrame:
    """Label each feature with values sampled from a single GEE image.

    Samples the image per feature via ``eetools.chunk_gdf`` (features with no
    data under them come back as NaN). Returns the
    input frame with one new column per sampled band appended (optionally
    prefixed). Note: derived images (e.g. slope from a DEM) aren't expressible
    through ``image_id`` alone -- point ``image_id`` at a pre-computed asset, or
    we add a dedicated task for those.
    """
    import ee
    from ecoscope.io import eetools

    img = ee.Image(image_id)
    if bands:
        img = img.select(bands)

    labels = eetools.chunk_gdf(
        gdf=df[["geometry"]],
        label_func=_label_gdf_with_img_robust,
        label_func_kwargs={
            "img": img,
            "region_reducer": _build_reducer(reducer),
            "scale": scale,
        },
        df_chunk_size=df_chunk_size,
        max_workers=1,  # single worker to stay within EE quotas
    )
    if labels is None:
        return df
    if column_prefix:
        labels = labels.add_prefix(column_prefix)
    return df.join(labels)


@register(tags=["io"])
def label_with_temporal_image_collection(
    client: EarthEngineClient,
    df: Annotated[
        AnyGeoDataFrame,
        Field(
            description="The (geo)dataframe to label. Must carry geometry and the time column below.",
            exclude=True,
        ),
    ],
    image_collection_id: Annotated[
        str,
        Field(
            description="Full Earth Engine ImageCollection asset ID (a path, NOT a band name), e.g. 'MODIS/061/MYD13A1'."
        ),
    ] = "MODIS/061/MYD13A1",
    time_column: Annotated[
        str,
        Field(
            description="Datetime column used to pick the temporally closest image(s), e.g. 'segment_start'."
        ),
    ] = "segment_start",
    bands: Annotated[
        Optional[list[str]],
        Field(
            description="Band name(s) within the collection to sample, e.g. ['NDVI']. Leave empty for all bands."
        ),
    ] = ["NDVI"],  # noqa: B006
    image_stack: Annotated[
        int,
        Field(
            description="How many extra images to pull on each side of the image closest in time to a segment. 0 (default) uses only that single closest image -- one covariate value per segment. Higher values average a window of images around the segment's time (and can add rows)."
        ),
    ] = 0,
    reducer: Annotated[
        str,
        Field(
            description="Region reducer per feature (mean, median, mode, min, max, sum, stdDev, first, toList)."
        ),
    ] = "mean",
    scale: Annotated[
        float,
        Field(description="Sampling scale in metres."),
    ] = 500.0,
    df_chunk_size: Annotated[
        int,
        Field(
            description="Features sampled per Earth Engine request. Lower it if you hit GEE quota/memory limits."
        ),
    ] = 5000,
    column_prefix: Annotated[
        Optional[str],
        Field(description="Optional prefix for the new covariate column(s)."),
    ] = None,
) -> AnyGeoDataFrame:
    """Label each feature with a time-matched value from a GEE image collection.

    Wraps ``eetools.label_gdf_with_temporal_image_collection_by_feature`` via
    ``eetools.chunk_gdf``. With ``n_before = n_after = 0`` each feature gets the
    single temporally closest image, so the result has one row per input row
    plus an ``img_date`` column and one column per sampled band. Widening the
    window (n_before/n_after > 0) returns a *stack* -- multiple rows per feature
    -- which multiplies the frame.
    """
    import ee
    from ecoscope.io import eetools

    coll = ee.ImageCollection(image_collection_id)
    if bands:
        coll = coll.select(bands)

    labels = eetools.chunk_gdf(
        gdf=df[[time_column, "geometry"]],
        label_func=eetools.label_gdf_with_temporal_image_collection_by_feature,
        label_func_kwargs={
            "img_coll": coll,
            "time_col_name": time_column,
            "n_before": image_stack,
            "n_after": image_stack,
            "n": "images",
            "region_reducer": _build_reducer(reducer),
            "scale": scale,
        },
        df_chunk_size=df_chunk_size,
        max_workers=1,  # single worker to stay within EE quotas
    )
    if labels is None:
        return df
    if column_prefix:
        rename = {c: f"{column_prefix}{c}" for c in labels.columns if c != "img_date"}
        labels = labels.rename(columns=rename)
    return df.join(labels)
