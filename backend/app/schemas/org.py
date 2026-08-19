from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class OrgDimensionOut(BaseModel):
    id: int
    key: str
    label: str
    sort_order: int

    model_config = {"from_attributes": True}


class OrgDimensionCreate(BaseModel):
    key: str = Field(min_length=1, max_length=50, pattern=r"^[a-z0-9_]+$")
    label: str = Field(min_length=1, max_length=100)
    sort_order: int = 0


class OrgNodeOut(BaseModel):
    id: int
    dimension_id: int
    parent_id: Optional[int]
    name: str
    external_code: Optional[str]
    is_active: bool
    manager_name: Optional[str]
    manager_email: Optional[str]
    manager_phone: Optional[str]
    manager_npid: Optional[str]

    model_config = {"from_attributes": True}


class OrgNodeCreate(BaseModel):
    dimension_id: int
    parent_id: Optional[int] = None
    name: str = Field(min_length=1, max_length=200)
    external_code: Optional[str] = None


class OrgNodeUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    external_code: Optional[str] = None
    is_active: Optional[bool] = None
    manager_name: Optional[str] = None
    manager_email: Optional[str] = None
    manager_phone: Optional[str] = None
    manager_npid: Optional[str] = None


class OrgNodePathEntry(BaseModel):
    id: int
    name: str
    dimension_key: str


class OrgNodeWithPath(OrgNodeOut):
    path: list[OrgNodePathEntry]


class SkippedRowOut(BaseModel):
    row_number: int
    reason: str


class DataConflictOut(BaseModel):
    description: str


class SyncReportOut(BaseModel):
    total_rows: int
    half_countries_created: int
    zones_created: int
    clusters_created: int
    centers_created: int
    centers_updated: int
    skipped: list[SkippedRowOut]
    conflicts: list[DataConflictOut]


class DirectoryReportOut(BaseModel):
    total_rows: int
    centers_created: int
    centers_updated: int
    skipped: list[SkippedRowOut]


class EmailSyncReportOut(BaseModel):
    total_rows: int
    updated: int
    unchanged: int
    skipped: list[SkippedRowOut]


class CenterDirectoryEntry(BaseModel):
    code: str
    name: str


class ContactChangeRequestOut(BaseModel):
    """A center manager's self-reported name/NPID/email, proposed but not
    yet applied to the OrgNode -- see OrgNodeContactChangeRequest. Approving
    calls org_service.update_node(); rejecting just closes the notification
    with no data change."""

    id: int
    org_node_id: Optional[int]
    centre_code_hint: str
    proposed_manager_name: Optional[str]
    proposed_manager_npid: Optional[str]
    proposed_manager_email: Optional[str]
    source: str
    status: str
    created_at: datetime
    reviewed_at: Optional[datetime]

    model_config = {"from_attributes": True}
