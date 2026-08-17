"""Dataset-vs-dataset reconciliation. Compares two already-uploaded tabular
datasets on a chosen key column and reports matched/mismatched/missing/extra
rows. Real pandas comparison against the actual files -- nothing here is
estimated or sampled without saying so (see MAX_EXAMPLES truncation notes).
"""
from typing import Optional

from sqlalchemy.orm import Session

from app.models.dataset import PROFILABLE_SOURCE_TYPES, Dataset
from app.models.reconciliation import Reconciliation
from app.models.user import User
from app.services import audit_log_service, profiling_service, storage_service

MAX_EXAMPLES = 200


class NotProfilableError(Exception):
    pass


class ColumnNotFoundError(Exception):
    pass


def _load(dataset: Dataset):
    if dataset.source_type not in PROFILABLE_SOURCE_TYPES:
        raise NotProfilableError(
            f"Dataset {dataset.id} ('{dataset.name}') is a '{dataset.source_type}' file -- "
            "reconciliation only works on tabular (csv/excel) datasets"
        )
    abs_path = storage_service.absolute_path_for(dataset.storage_path)
    return profiling_service.load_dataframe(abs_path, dataset.source_type)


def run_reconciliation(
    db: Session,
    *,
    dataset_a: Dataset,
    dataset_b: Dataset,
    key_column_a: str,
    key_column_b: str,
    compare_columns: Optional[list[str]],
    actor: User,
) -> Reconciliation:
    """Raises NotProfilableError/ColumnNotFoundError directly for bad input
    (wrong file type, unknown column) -- those are clean 400s with no
    wasted DB row, same pattern as dataset upload rejecting an unsupported
    extension before creating anything. Only a genuinely unexpected failure
    during the comparison itself gets caught and persisted as a 'failed'
    Reconciliation row (mirrors dataset_service's profiling_error pattern).
    """
    df_a = _load(dataset_a)
    df_b = _load(dataset_b)

    if key_column_a not in df_a.columns:
        raise ColumnNotFoundError(f"'{key_column_a}' not found in dataset {dataset_a.id}")
    if key_column_b not in df_b.columns:
        raise ColumnNotFoundError(f"'{key_column_b}' not found in dataset {dataset_b.id}")

    shared_columns = compare_columns or [
        c for c in df_a.columns if c in df_b.columns and c not in (key_column_a, key_column_b)
    ]
    missing_shared = [c for c in shared_columns if c not in df_a.columns or c not in df_b.columns]
    if missing_shared:
        raise ColumnNotFoundError(f"compare_columns {missing_shared} are not present in both datasets")

    recon = Reconciliation(
        dataset_a_id=dataset_a.id,
        dataset_b_id=dataset_b.id,
        key_column_a=key_column_a,
        key_column_b=key_column_b,
        compare_columns=compare_columns,
        status="completed",
        run_by_id=actor.id,
    )

    try:
        df_a = df_a.set_index(df_a[key_column_a].astype(str))
        df_b = df_b.set_index(df_b[key_column_b].astype(str))

        keys_a = set(df_a.index)
        keys_b = set(df_b.index)

        missing_in_b = sorted(keys_a - keys_b)
        extra_in_b = sorted(keys_b - keys_a)
        common_keys = sorted(keys_a & keys_b)

        matched_keys = []
        mismatched_examples = []
        for key in common_keys:
            row_a = df_a.loc[key]
            row_b = df_b.loc[key]
            diffs = {}
            for col in shared_columns:
                val_a = row_a[col]
                val_b = row_b[col]
                # NaN != NaN in pandas; treat two NaNs as equal for this purpose.
                both_nan = _is_missing(val_a) and _is_missing(val_b)
                if not both_nan and val_a != val_b:
                    diffs[col] = {"a": _jsonable(val_a), "b": _jsonable(val_b)}
            if diffs:
                if len(mismatched_examples) < MAX_EXAMPLES:
                    mismatched_examples.append({"key": key, "diffs": diffs})
            else:
                matched_keys.append(key)

        recon.matched_count = len(matched_keys)
        recon.mismatched_count = len(common_keys) - len(matched_keys)
        recon.missing_in_b_count = len(missing_in_b)
        recon.extra_in_b_count = len(extra_in_b)
        recon.details_json = {
            "compared_columns": shared_columns,
            "mismatched_examples": mismatched_examples,
            "mismatched_examples_truncated": recon.mismatched_count > len(mismatched_examples),
            "missing_in_b_examples": missing_in_b[:MAX_EXAMPLES],
            "missing_in_b_truncated": len(missing_in_b) > MAX_EXAMPLES,
            "extra_in_b_examples": extra_in_b[:MAX_EXAMPLES],
            "extra_in_b_truncated": len(extra_in_b) > MAX_EXAMPLES,
        }
    except Exception as exc:  # noqa: BLE001 -- a bad column/file is a data problem, not a bug
        recon.status = "failed"
        recon.error = str(exc)[:500]

    db.add(recon)
    db.flush()

    audit_log_service.record(
        db,
        actor=actor,
        action="reconciliation.run",
        entity_type="Reconciliation",
        entity_id=recon.id,
        after={
            "dataset_a_id": dataset_a.id,
            "dataset_b_id": dataset_b.id,
            "status": recon.status,
            "matched_count": recon.matched_count,
            "mismatched_count": recon.mismatched_count,
        },
    )
    db.commit()
    db.refresh(recon)
    return recon


def _is_missing(value) -> bool:
    try:
        import pandas as pd

        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _jsonable(value):
    if _is_missing(value):
        return None
    if hasattr(value, "item"):  # numpy scalar
        return value.item()
    return value


def get_reconciliation(db: Session, recon_id: int) -> Optional[Reconciliation]:
    return db.query(Reconciliation).filter(Reconciliation.id == recon_id).first()


def list_reconciliations(db: Session, *, dataset_id: Optional[int] = None) -> list[Reconciliation]:
    query = db.query(Reconciliation)
    if dataset_id is not None:
        query = query.filter(
            (Reconciliation.dataset_a_id == dataset_id) | (Reconciliation.dataset_b_id == dataset_id)
        )
    return query.order_by(Reconciliation.id.desc()).all()
