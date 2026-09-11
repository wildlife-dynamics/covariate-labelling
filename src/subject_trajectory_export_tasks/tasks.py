"""Custom tasks for the subject-trajectory-export workflow.

Currently one task: `group_plot_filename`, which builds a human-readable,
per-group HTML filename so persisted plots are named after the group (e.g.
`Esposito_net_square_displacement.html`) instead of a content hash.

Core ecoscope-platform has no string-returning "first value per group" task
(`dataframe_column_first_unique` is typed to return an int), so this small task
fills that gap — analogous to how create-vcf-basemap ships its own tasks.
"""

from __future__ import annotations

import re
from typing import Annotated

from ecoscope.platform.annotations import AnyDataFrame
from pydantic import Field
from wt_registry import register


def _safe(label: str) -> str:
    """Make a string safe to use as a filename component."""
    label = re.sub(r"[^A-Za-z0-9._-]+", "_", label).strip("_")
    return label or "group"


@register()
def group_plot_filename(
    df: Annotated[
        AnyDataFrame,
        Field(description="A single split group's dataframe.", exclude=True),
    ],
    column_name: Annotated[
        str,
        Field(description="Column that identifies the group, e.g. 'subject_name'."),
    ],
    suffix: Annotated[
        str,
        Field(
            description=(
                "Text appended after the group label, including the extension, "
                "e.g. 'net_square_displacement.html'."
            )
        ),
    ],
) -> Annotated[
    str,
    Field(
        description="Filesystem-safe filename, e.g. 'Esposito_net_square_displacement.html'."
    ),
]:
    """Build a per-group filename from a grouping column.

    If the group holds a single value in ``column_name`` (e.g. grouped by
    subject), that value becomes the label; if it holds many (e.g. an ungrouped
    "all subjects" run), the label is ``all``. The label is sanitised for
    filesystem safety and joined to ``suffix`` with an underscore.
    """
    values = df[column_name].dropna().astype(str).unique().tolist()
    label = values[0] if len(values) == 1 else "all"
    return f"{_safe(label)}_{suffix}"
