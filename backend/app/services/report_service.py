"""Report templates (saved filter sets) + report history (a log of every
generation, template-based or ad-hoc). Neither stores a generated file --
see app/models/report.py for why. Every function here is thin; the actual
export rendering stays in app/api/reports.py, which is the single caller of
the Metric Engine functions (get_visible_audits_query/compute_summary) --
this module never re-derives a number.
"""
from typing import Optional

from sqlalchemy.orm import Session

from app.models.report import ReportHistory, ReportTemplate
from app.models.user import User


class TemplateNotFoundError(Exception):
    pass


def create_template(
    db: Session, *, name: str, description: Optional[str], filters: dict, creator: User
) -> ReportTemplate:
    template = ReportTemplate(name=name, description=description, filters=filters, created_by_id=creator.id)
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


def list_templates(db: Session) -> list[ReportTemplate]:
    return db.query(ReportTemplate).order_by(ReportTemplate.name).all()


def get_template(db: Session, template_id: int) -> Optional[ReportTemplate]:
    return db.query(ReportTemplate).filter(ReportTemplate.id == template_id).first()


def delete_template(db: Session, *, template: ReportTemplate, actor: User) -> None:
    if actor.role != "Admin" and template.created_by_id != actor.id:
        raise PermissionError("Only the creator or an Admin can delete this template")
    db.delete(template)
    db.commit()


def record_history(
    db: Session,
    *,
    name: str,
    template_id: Optional[int],
    filters_used: dict,
    format: str,
    generated_by: User,
    status: str = "completed",
    error: Optional[str] = None,
    regenerated_from_id: Optional[int] = None,
) -> ReportHistory:
    entry = ReportHistory(
        name=name,
        template_id=template_id,
        filters_used=filters_used,
        format=format,
        status=status,
        error=error,
        generated_by_id=generated_by.id,
        regenerated_from_id=regenerated_from_id,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def list_history(db: Session, *, skip: int = 0, limit: int = 50) -> list[ReportHistory]:
    limit = max(1, min(limit, 200))
    return (
        db.query(ReportHistory)
        .order_by(ReportHistory.id.desc())
        .offset(max(0, skip))
        .limit(limit)
        .all()
    )


def get_history(db: Session, history_id: int) -> Optional[ReportHistory]:
    return db.query(ReportHistory).filter(ReportHistory.id == history_id).first()
