from typing import Optional

from pydantic import BaseModel


class DcbSummaryOut(BaseModel):
    total_batches: int
    total_bills: int
    considered: int
    not_considered: int
    needs_more_detail: int
    needs_proof: int
    unreviewed: int
    non_compliance_rate: Optional[float]
    total_validated_penalty: float


class WrcSummaryOut(BaseModel):
    total_batches: int
    total_incidents: int
    considered: int
    not_considered: int
    unreviewed: int
    non_compliance_rate: Optional[float]
    total_center_penalty: float
    total_role_penalty: float


class ClusterBreakdownItem(BaseModel):
    cluster: str
    non_compliant_center_count: int


class ZoneBreakdownItem(BaseModel):
    zone: str
    non_compliant_center_count: int


class RepeatedCenterOut(BaseModel):
    centre_code: str
    centre_name: str
    violation_count: int


class DashboardSummaryOut(BaseModel):
    dcb: DcbSummaryOut
    wrc: WrcSummaryOut
    cluster_breakdown: list[ClusterBreakdownItem]
    zone_breakdown: list[ZoneBreakdownItem]
    repeated_centers: list[RepeatedCenterOut]
    repeated_centers_truncated: bool
