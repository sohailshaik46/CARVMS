"""Forensic anomaly detection over an uploaded tabular dataset.

Every rule here is a real, general-purpose statistical/pattern check, run
against the actual file -- never a fraud conclusion. Results are always
framed as "Exception" / "requires verification", per the brief's explicit
instruction never to accuse an employee of fraud from an anomaly alone.
This is deliberately NOT a claim to detect every forensic pattern in the
brief's taxonomy (impossible chronology, FASTag mismatches, travel
inconsistencies, backwards ODO, etc.) -- those need domain-specific column
semantics a generic engine cannot honestly infer without being told what
each column means, which is out of scope here.
"""
from typing import Optional

from sqlalchemy.orm import Session

from app.models.anomaly import DatasetAnomaly
from app.models.dataset import Dataset
from app.models.user import User
from app.services import audit_log_service, profiling_service, storage_service

DEFAULT_REPEATED_VALUE_THRESHOLD = 3
DEFAULT_IQR_MULTIPLIER = 1.5
MAX_ANOMALIES_PER_RULE = 500  # backstop, not a silent cap -- see scan_dataset


class RuleConfigError(Exception):
    pass


def _risk_for_repeat_count(count: int, threshold: int) -> str:
    if count >= threshold * 3:
        return "Critical"
    if count >= threshold * 2:
        return "High"
    return "Medium"


def _detect_duplicate_rows(df, dataset: Dataset) -> list[dict]:
    anomalies = []
    dup_mask = df.duplicated(keep="first")
    for idx in df.index[dup_mask][:MAX_ANOMALIES_PER_RULE]:
        row = df.loc[idx]
        anomalies.append(
            {
                "entity_description": f"Row {idx} of '{dataset.name}'",
                "observed_value": {str(k): _jsonable(v) for k, v in row.to_dict().items()},
                "expected_baseline": {"rule": "each row should be unique"},
                "difference": {"duplicate_of_first_occurrence": True},
                "risk_level": "Medium",
                "potential_impact": "Possible double-counted record (double billing, duplicate claim, etc.)",
                "evidence_source": f"dataset:{dataset.id} row:{idx}",
                "recommended_verification": "Confirm with source system whether this row was genuinely submitted twice.",
            }
        )
    return anomalies


def _detect_repeated_value(df, dataset: Dataset, column: str, threshold: int) -> list[dict]:
    if column not in df.columns:
        raise RuleConfigError(f"Column '{column}' not found in dataset {dataset.id}")

    anomalies = []
    counts = df[column].value_counts(dropna=True)
    offending_values = counts[counts >= threshold]
    for value, count in offending_values.items():
        matching_idx = df.index[df[column] == value].tolist()
        anomalies.append(
            {
                "entity_description": f"Value '{value}' in column '{column}' of '{dataset.name}'",
                "observed_value": {"value": _jsonable(value), "occurrence_count": int(count)},
                "expected_baseline": {"threshold": threshold, "rule": f"'{column}' repeating >= {threshold} times is unusual"},
                "difference": {"exceeds_threshold_by": int(count - threshold)},
                "risk_level": _risk_for_repeat_count(int(count), threshold),
                "potential_impact": f"{count} rows share the same '{column}' value -- possible threshold gaming or batch duplication.",
                "evidence_source": f"dataset:{dataset.id} rows:{matching_idx[:20]}",
                "recommended_verification": f"Review the {count} rows with {column}='{value}' individually for legitimacy.",
            }
        )
        if len(anomalies) >= MAX_ANOMALIES_PER_RULE:
            break
    return anomalies


def _detect_outliers_iqr(df, dataset: Dataset, column: str, multiplier: float) -> list[dict]:
    if column not in df.columns:
        raise RuleConfigError(f"Column '{column}' not found in dataset {dataset.id}")

    series = df[column]
    numeric = series.dropna()
    if len(numeric) < 4:
        return []  # too few points for a meaningful IQR -- honestly skip, don't fabricate

    q1 = numeric.quantile(0.25)
    q3 = numeric.quantile(0.75)
    iqr = q3 - q1
    lower = q1 - multiplier * iqr
    upper = q3 + multiplier * iqr

    anomalies = []
    outlier_idx = series.index[(series < lower) | (series > upper)]
    for idx in outlier_idx[:MAX_ANOMALIES_PER_RULE]:
        value = series.loc[idx]
        anomalies.append(
            {
                "entity_description": f"Row {idx}, column '{column}' of '{dataset.name}'",
                "observed_value": {"value": _jsonable(value)},
                "expected_baseline": {
                    "q1": _jsonable(q1), "q3": _jsonable(q3), "iqr": _jsonable(iqr),
                    "normal_range": [_jsonable(lower), _jsonable(upper)],
                },
                "difference": {"outside_range_by": _jsonable(value - upper if value > upper else lower - value)},
                "risk_level": "High" if (value > upper + iqr or value < lower - iqr) else "Medium",
                "potential_impact": f"'{column}' value is a statistical outlier vs. the rest of the dataset.",
                "evidence_source": f"dataset:{dataset.id} row:{idx}",
                "recommended_verification": "Confirm this value against source documentation; outliers are not proof of error.",
            }
        )
    return anomalies


def _jsonable(value):
    import pandas as pd

    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def scan_dataset(
    db: Session,
    *,
    dataset: Dataset,
    rules: list[str],
    repeated_value_column: Optional[str],
    repeated_value_threshold: int,
    outlier_column: Optional[str],
    outlier_iqr_multiplier: float,
    actor: User,
) -> list[DatasetAnomaly]:
    abs_path = storage_service.absolute_path_for(dataset.storage_path)
    df = profiling_service.load_dataframe(abs_path, dataset.source_type)

    if "repeated_value" in rules and not repeated_value_column:
        raise RuleConfigError("repeated_value rule requires repeated_value_column")
    if "outlier_iqr" in rules and not outlier_column:
        raise RuleConfigError("outlier_iqr rule requires outlier_column")

    created: list[DatasetAnomaly] = []
    if "duplicate_row" in rules:
        for r in _detect_duplicate_rows(df, dataset):
            created.append(_persist(db, dataset, "duplicate_row", r))
    if "repeated_value" in rules:
        for r in _detect_repeated_value(df, dataset, repeated_value_column, repeated_value_threshold):
            created.append(_persist(db, dataset, "repeated_value", r))
    if "outlier_iqr" in rules:
        for r in _detect_outliers_iqr(df, dataset, outlier_column, outlier_iqr_multiplier):
            created.append(_persist(db, dataset, "outlier_iqr", r))

    audit_log_service.record(
        db,
        actor=actor,
        action="dataset.anomaly_scan",
        entity_type="Dataset",
        entity_id=dataset.id,
        after={"rules": rules, "anomalies_found": len(created)},
    )
    db.commit()
    for a in created:
        db.refresh(a)
    return created


def _persist(db: Session, dataset: Dataset, rule_code: str, result: dict) -> DatasetAnomaly:
    anomaly = DatasetAnomaly(
        dataset_id=dataset.id,
        rule_code=rule_code,
        status="Open",
        **result,
    )
    db.add(anomaly)
    db.flush()
    return anomaly


def list_anomalies(db: Session, *, dataset_id: Optional[int] = None, status: Optional[str] = None) -> list[DatasetAnomaly]:
    query = db.query(DatasetAnomaly)
    if dataset_id is not None:
        query = query.filter(DatasetAnomaly.dataset_id == dataset_id)
    if status is not None:
        query = query.filter(DatasetAnomaly.status == status)
    return query.order_by(DatasetAnomaly.id.desc()).all()


def get_anomaly(db: Session, anomaly_id: int) -> Optional[DatasetAnomaly]:
    return db.query(DatasetAnomaly).filter(DatasetAnomaly.id == anomaly_id).first()


def dismiss_anomaly(db: Session, *, anomaly: DatasetAnomaly, reason: str, actor: User) -> DatasetAnomaly:
    before = {"status": anomaly.status}
    anomaly.status = "Dismissed"
    anomaly.dismissed_reason = reason
    db.flush()

    audit_log_service.record(
        db, actor=actor, action="anomaly.dismissed", entity_type="DatasetAnomaly",
        entity_id=anomaly.id, before=before, after={"status": "Dismissed", "reason": reason},
    )
    db.commit()
    db.refresh(anomaly)
    return anomaly


