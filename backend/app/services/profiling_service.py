"""Real data profiling for tabular uploads (CSV/Excel) only. Every number
this module returns is computed from the actual file -- nothing here is a
placeholder or an estimate. Non-tabular uploads (PDF/Word/PPT/image) never
reach this module; see dataset_service.py.
"""
from dataclasses import dataclass, field

import pandas as pd

from app.models.org import OrgDimension
from sqlalchemy.orm import Session


@dataclass
class ColumnProfile:
    name: str
    inferred_type: str
    null_rate: float
    mapped_dimension: str | None


@dataclass
class ProfileResult:
    row_count: int
    column_count: int
    duplicate_row_count: int
    quality_score: float
    columns: list[ColumnProfile] = field(default_factory=list)


_DTYPE_MAP = {
    "int64": "integer",
    "Int64": "integer",
    "float64": "float",
    "bool": "boolean",
    "datetime64[ns]": "datetime",
    "object": "string",
}


def _normalize(name: str) -> str:
    return name.strip().lower().replace(" ", "_").replace("-", "_")


def load_dataframe(absolute_path: str, source_type: str) -> pd.DataFrame:
    if source_type == "csv":
        return pd.read_csv(absolute_path)
    if source_type == "excel":
        return pd.read_excel(absolute_path)
    raise ValueError(f"'{source_type}' is not a profilable source type")


def profile_dataframe(df: pd.DataFrame, db: Session) -> ProfileResult:
    row_count = len(df)
    column_count = len(df.columns)
    duplicate_row_count = int(df.duplicated().sum())

    known_dimension_keys = {
        _normalize(d.key): d.key for d in db.query(OrgDimension).all()
    }

    columns: list[ColumnProfile] = []
    null_rates: list[float] = []
    for col in df.columns:
        series = df[col]
        null_rate = float(series.isna().mean()) if row_count > 0 else 0.0
        null_rates.append(null_rate)
        inferred_type = _DTYPE_MAP.get(str(series.dtype), "string")
        mapped_dimension = known_dimension_keys.get(_normalize(str(col)))
        columns.append(
            ColumnProfile(
                name=str(col),
                inferred_type=inferred_type,
                null_rate=round(null_rate, 4),
                mapped_dimension=mapped_dimension,
            )
        )

    avg_null_rate = sum(null_rates) / len(null_rates) if null_rates else 0.0
    dup_fraction = (duplicate_row_count / row_count) if row_count > 0 else 0.0
    quality_score = round(100 * max(0.0, (1 - avg_null_rate) * (1 - dup_fraction)), 2)

    return ProfileResult(
        row_count=row_count,
        column_count=column_count,
        duplicate_row_count=duplicate_row_count,
        quality_score=quality_score,
        columns=columns,
    )
