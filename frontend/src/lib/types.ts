// Mirrors backend/app/schemas/*.py exactly. If a field is renamed on the
// backend, it must be renamed here too -- there is no transformation layer.

export const ROLES = [
  'Admin',
  'Auditor',
  'Finance',
  'Center Manager',
  'Cluster Manager',
  'Zonal Manager',
  'Half Country Manager',
] as const
export type Role = (typeof ROLES)[number]

export interface UserOut {
  id: number
  username: string
  email: string
  role: Role
  is_active: boolean
  phone_number: string | null
}

export interface UserAdminOut extends UserOut {
  org_node_id: number | null
  created_at: string
  updated_at: string
}

export interface Token {
  access_token: string
  token_type: string
}

// ---------- Org hierarchy ----------

export interface OrgDimension {
  id: number
  key: string
  label: string
  sort_order: number
}

export interface OrgNode {
  id: number
  dimension_id: number
  parent_id: number | null
  name: string
  external_code: string | null
  is_active: boolean
}

export interface OrgNodePath {
  id: number
  name: string
  dimension_key: string
}

export interface OrgNodeWithPath extends OrgNode {
  path: OrgNodePath[]
}

// Everything about one center in a single flattened shape -- powers the
// "open a center, see everything" lookup. See backend org_service.
// CenterDetail for the full reasoning (each ancestor's own manager_* is
// that level's manager -- a cluster's manager_name IS the Cluster
// Manager's name, per the Centers Master sheet's own convention).
export interface CenterDetail {
  center_code: string
  center_name: string
  is_active: boolean
  center_manager_name: string | null
  center_manager_npid: string | null
  center_manager_email: string | null
  center_manager_phone: string | null
  cluster_manager_name: string | null
  cluster_manager_email: string | null
  cluster_manager_phone: string | null
  zone_name: string | null
  zonal_manager_name: string | null
  zonal_manager_email: string | null
  zonal_manager_phone: string | null
  half_country_head: string | null
}

// ---------- Dashboard / Metrics ----------
// Rewritten 2026-08-14 to compute from Delayed Cash Billing (DCB) + Weekly
// Revenue Closure (WRC) data -- the Audits/Findings domain this used to
// summarize was deleted per explicit user request.

export interface DashboardFilters {
  period_from?: string
  period_to?: string
}

export interface DcbSummary {
  total_batches: number
  total_bills: number
  considered: number
  not_considered: number
  needs_more_detail: number
  needs_proof: number
  unreviewed: number
  non_compliance_rate: number | null
  total_validated_penalty: number
}

export interface WrcSummary {
  total_batches: number
  total_incidents: number
  considered: number
  not_considered: number
  unreviewed: number
  non_compliance_rate: number | null
  total_center_penalty: number
  total_role_penalty: number
}

export interface ClusterBreakdownItem {
  cluster: string
  non_compliant_center_count: number
}

export interface ZoneBreakdownItem {
  zone: string
  non_compliant_center_count: number
}

export interface RepeatedCenter {
  centre_code: string
  centre_name: string
  violation_count: number
}

export interface DashboardSummary {
  dcb: DcbSummary
  wrc: WrcSummary
  cluster_breakdown: ClusterBreakdownItem[]
  zone_breakdown: ZoneBreakdownItem[]
  repeated_centers: RepeatedCenter[]
  repeated_centers_truncated: boolean
}

// ---------- Report templates / history ----------

export const REPORT_FORMATS = ['csv', 'xlsx', 'pdf', 'docx', 'pptx'] as const
export type ReportFormat = (typeof REPORT_FORMATS)[number]

export interface ReportTemplate {
  id: number
  name: string
  description: string | null
  filters: DashboardFilters
  created_by_id: number
  created_at: string
  updated_at: string
}

export interface ReportHistoryEntry {
  id: number
  name: string
  template_id: number | null
  filters_used: DashboardFilters
  format: ReportFormat
  status: 'completed' | 'failed'
  error: string | null
  generated_by_id: number
  generated_at: string
  regenerated_from_id: number | null
}

// ---------- Global search ----------

export const SEARCHABLE_TYPES = ['delayed_cash_bill', 'wrc_incident', 'org_node', 'report_template'] as const
export type SearchableType = (typeof SEARCHABLE_TYPES)[number]

export interface SearchResultItem {
  entity_type: SearchableType
  id: number
  title: string
  subtitle?: string | null
  parent_id?: number | null
}

export interface SearchResponse {
  query: string
  results: Partial<Record<SearchableType, SearchResultItem[]>>
  total: number
}

// ---------- Dashboard layouts ----------
// The configurable "which KPI boxes are visible" concept doesn't apply
// anymore -- the rebuilt Dashboard has a fixed set of sections (DCB/WRC
// summary, cluster/zone breakdown, repeat violators, pending tasks). A
// saved layout is now just a saved default period filter.

export interface DashboardLayoutConfig {
  default_filters: DashboardFilters
}

export interface DashboardLayout {
  id: number
  name: string
  description: string | null
  config: DashboardLayoutConfig
  is_shared: boolean
  owner_id: number
  created_at: string
  updated_at: string
}

// ---------- Center performance scoring ----------

export const CENTER_SCORE_COMPONENTS = ['non_compliance_rate', 'repeat_violations', 'outstanding_penalty', 'unresolved_cases'] as const
export type CenterScoreComponent = (typeof CENTER_SCORE_COMPONENTS)[number]

export const COMPONENT_LABELS: Record<CenterScoreComponent, string> = {
  non_compliance_rate: 'Non-Compliance Rate',
  repeat_violations: 'Repeat SOP Violations',
  outstanding_penalty: 'Outstanding Penalty',
  unresolved_cases: 'Unresolved Cases',
}

export interface CenterScoringWeight {
  id: number
  component_key: CenterScoreComponent
  weight: number
  updated_by_id: number | null
  updated_at: string
}

export interface ComponentScore {
  raw: number | null
  normalized: number | null
}

export interface CenterRanking {
  rank: number
  centre_code: string
  centre_name: string
  case_count: number
  components: Partial<Record<CenterScoreComponent, ComponentScore>>
  composite_score: number | null
}

// ---------- Email integration (Gmail OAuth) ----------

export interface EmailProviderInfo {
  provider: string
  configured: boolean
}

export interface EmailConnectAuthorization {
  authorization_url: string
}

export interface EmailConnectionStatus {
  connected: boolean
  provider: string | null
  scope: string | null
  connected_at: string | null
  // False for a connection made before the send permission was requested
  // -- reconnect to grant it; Google won't add it to an old token.
  can_send: boolean
}

// ---------- User preferences (Settings: Appearance/Dashboard/Notifications/Security) ----------

export type ThemeName = 'light' | 'dark'

export interface DashboardConfig {
  visible_kpis: string[]
}

export interface NotificationPrefs {
  email_on_new_case: boolean
  email_on_decision: boolean
  email_on_escalation: boolean
  [key: string]: boolean
}

export interface SecuritySettings {
  session_timeout_minutes: number
  [key: string]: number
}

export interface UserPreferences {
  theme: ThemeName
  dashboard_config: DashboardConfig
  notification_prefs: NotificationPrefs
  security_settings: SecuritySettings
}

export interface UserPreferencesUpdate {
  theme?: ThemeName
  dashboard_config?: DashboardConfig
  notification_prefs?: NotificationPrefs
  security_settings?: SecuritySettings
}

// ---------- Delayed Cash Billing: public response portal ----------

export type TatStatus = 'within_window' | 'overdue' | 'unknown'

export interface PublicBillSummary {
  sales_bill: string
  bill_date: string
  calculated_day_difference: number
  calculated_penalty: string
  considered: BillReviewDecision | null
}

export interface PublicDelayedCashCase {
  centre_code: string
  centre_name: string
  period_start: string
  period_end: string
  total_bills: number
  calculated_penalty: string
  tat_status: TatStatus
  deadline: string | null
  already_responded: boolean
  bills: PublicBillSummary[]
}

export interface DelayedCashCaseResponseSubmission {
  responder_name: string
  responder_npid: string
  responder_email: string
  reason: string
  selected_center_code?: string
  selected_center_name?: string
}

export interface DelayedCashCaseResponseOut {
  id: number
  responder_name: string
  responder_npid: string
  responder_email: string | null
  reason: string
  evidence_original_filename: string
  submitted_at: string
  was_within_tat: TatStatus | null
  selected_center_code: string | null
  selected_center_name: string | null
}

export interface CenterDirectoryEntry {
  code: string
  name: string
}

export interface RemoteSyncReport {
  dimensions_created: number
  dimensions_updated: number
  dimensions_unchanged: number
  nodes_created: number
  nodes_updated: number
  nodes_unchanged: number
  changed_node_names: string[]
  committed: boolean
}

export interface DcbRemoteSyncReport {
  rules_created: number
  rules_updated: number
  rules_unchanged: number
  batches_created: number
  batches_updated: number
  batches_unchanged: number
  bills_created: number
  bills_updated: number
  bills_unchanged: number
  center_penalties_created: number
  center_penalties_updated: number
  center_penalties_unchanged: number
  changed_summary: string[]
  committed: boolean
}

export interface WrcRemoteSyncReport {
  rules_created: number
  rules_updated: number
  rules_unchanged: number
  batches_created: number
  batches_updated: number
  batches_unchanged: number
  bill_incidents_created: number
  bill_incidents_updated: number
  bill_incidents_unchanged: number
  no_remark_incidents_created: number
  no_remark_incidents_updated: number
  no_remark_incidents_unchanged: number
  center_penalties_created: number
  center_penalties_updated: number
  center_penalties_unchanged: number
  role_penalties_created: number
  role_penalties_updated: number
  role_penalties_unchanged: number
  center_cases_created: number
  center_cases_updated: number
  center_cases_unchanged: number
  changed_summary: string[]
  committed: boolean
}

// Single shared response link -- same shape as PublicDelayedCashCase, plus
// the case's own id (needed to submit against it without a token).
export interface PublicOpenDelayedCashCase extends PublicDelayedCashCase {
  id: number
}

// ---------- Delayed Cash Billing: Vigilance-facing upload/publish pipeline ----------

export type DcbPenaltyStatus = 'published' | 'validated' | 'awaiting_cap_input' | 'capped'
export type DcbBatchStatus = 'uploaded' | 'published' | 'closed'

export interface DelayedCashCenterPenalty {
  id: number
  batch_id: number
  centre_code: string
  centre_name: string
  total_bills: number
  calculated_penalty: string
  validated_penalty: string | null
  monthly_cap_amount: string | null
  final_penalty: string | null
  penalty_status: DcbPenaltyStatus
  created_at: string
  response_token: string | null
  response_token_expires_at: string | null
}

export interface DelayedCashUploadBatch {
  id: number
  period_start: string
  period_end: string
  source_filename: string
  status: DcbBatchStatus
  uploaded_at: string
}

export interface DelayedCashRule {
  id: number
  rule_version: string
  rate_per_day: string
  monthly_cap_percentage: string
  status: string
  effective_from: string
}

export interface SkippedBillRow {
  row_number: number
  reason: string
}

export interface UploadBatchResult {
  batch: DelayedCashUploadBatch
  center_penalties: DelayedCashCenterPenalty[]
  out_of_period_row_count: number
  skipped_rows: SkippedBillRow[]
}

export interface DcbBatchSummary {
  batch: DelayedCashUploadBatch
  total_bills: number
  pending_review_count: number
  considered_count: number
  not_considered_count: number
  needs_more_detail_count: number
  needs_proof_count: number
  centers_in_batch: number
  total_calculated_penalty: string
  total_validated_penalty: string
}

export interface DcbCenterBreakdown {
  centre_code: string
  centre_name: string
  zone: string | null
  cluster: string | null
  this_batch_bill_count: number
  this_batch_considered_count: number
  this_batch_not_considered_count: number
  this_batch_pending_count: number
  all_time_batch_count: number
  all_time_considered_count: number
  all_time_not_considered_count: number
}

export interface ResponseLinkDetail {
  center_penalty_id: number
  centre_code: string
  centre_name: string
  response_token: string
  response_url: string
  expires_at: string
}

export interface BatchPublishResult {
  batch_id: number
  links: ResponseLinkDetail[]
}

// ---------- Delayed Cash Billing: per-bill review queue ----------

export type BillReviewDecision = 'considered' | 'not_considered' | 'needs_more_detail' | 'needs_proof'

export interface DelayedCashBill {
  id: number
  batch_id: number
  centre_code: string
  centre_name: string
  sales_bill: string
  bill_date: string
  calculated_day_difference: number
  calculated_penalty: string
  considered: BillReviewDecision | null
  reviewed_at: string | null
  center_penalty_id: number | null
}

export interface BillReviewResult {
  bill: DelayedCashBill
  response_link: ResponseLinkDetail | null
}

export interface BillNotifyResult {
  sent: boolean
  reason: string | null
}

// ---------- Delayed Cash Billing: submitted remarks + Centers Activity ----------

export interface DcbCaseResponse {
  id: number
  responder_name: string
  responder_npid: string
  responder_email: string | null
  reason: string
  evidence_original_filename: string
  submitted_at: string
  was_within_tat: 'within_window' | 'overdue' | null
  selected_center_code: string | null
  selected_center_name: string | null
}

export type DcbActivityEventType = 'opened' | 'submitted'

export interface DcbCenterActivity {
  id: number
  centre_code: string
  centre_name: string | null
  center_penalty_id: number | null
  event_type: DcbActivityEventType
  occurred_at: string
}

// ---------- Org Master contact-change notifications ----------

export type ContactChangeStatus = 'pending' | 'approved' | 'rejected'

export interface ContactChangeRequest {
  id: number
  org_node_id: number | null
  centre_code_hint: string
  proposed_manager_name: string | null
  proposed_manager_npid: string | null
  proposed_manager_email: string | null
  source: string
  status: ContactChangeStatus
  created_at: string
  reviewed_at: string | null
}

// ---------- Weekly Revenue Closure -- a separate engine from Delayed Cash
// Billing, own formula (flat 6.25% per delinquent center, escalating to
// Cluster/Zonal Manager), own role hierarchy (Center + Cluster Manager
// penalties apply here). See CARVMS_WEEKLY_REVENUE_CLOSURE_FORMULA_ANALYSIS.md ----------

export type WrcBatchStatus = 'open' | 'closed'
export type WrcIncidentType = 'bill_pending' | 'daily_report_not_sent' | 'no_billing_no_daily_report'
export type WrcConsidered = 'considered' | 'not_considered'

export interface WrcRule {
  id: number
  rule_version: string
  penalty_rate: string
  status: string
  effective_from: string
}

export interface WeeklyRevenueClosureBatch {
  id: number
  period_start: string
  period_end: string
  week_label: string
  status: WrcBatchStatus
  created_at: string
}

export interface WrcSkippedRow {
  row_number: number
  reason: string
}

export interface WrcUploadResult {
  batch: WeeklyRevenueClosureBatch
  incidents_ingested: number
  excess_billed_row_count: number
  // Rows whose own Date fell outside this batch's period -- the source
  // file repeatedly turns out to still carry a prior week's rows too;
  // those are excluded rather than double-counted against the wrong week.
  out_of_period_row_count: number
  skipped_rows: WrcSkippedRow[]
}

export interface WrcBillIncident {
  id: number
  batch_id: number
  centre_code: string
  centre_name: string
  zone: string | null
  cluster: string | null
  zonal_manager: string | null
  center_manager: string | null
  center_manager_npid: string | null
  incident_date: string
  mis_final_remark: WrcIncidentType
  raw_remark: string | null
  center_remarks: string | null
  penalty_remarks: string | null
  considered: WrcConsidered | null
  reviewed_at: string | null
  case_id: number | null
}

export interface WrcNoRemarkIncident {
  id: number
  batch_id: number
  centre_code: string
  centre_name: string
  incident_type: WrcIncidentType
  incident_count: number
}

export interface WrcCenterPenalty {
  id: number
  batch_id: number
  centre_code: string
  centre_name: string
  center_manager: string | null
  center_manager_npid: string | null
  not_considered_penalty: string
  no_remark_penalty: string
}

export interface WrcRolePenalty {
  id: number
  batch_id: number
  role: 'cluster_manager' | 'zonal_manager'
  section: 'not_considered' | 'no_remark'
  person_name: string
  person_npid: string | null
  distinct_center_count: number
  penalty_amount: string
}

export interface WrcCloseBatchResult {
  batch: WeeklyRevenueClosureBatch
  center_penalties: WrcCenterPenalty[]
  role_penalties: WrcRolePenalty[]
}

export interface WrcBatchSummary {
  batch: WeeklyRevenueClosureBatch
  total_incidents: number
  pending_review_count: number
  considered_count: number
  not_considered_count: number
  no_remark_center_count: number
  centers_penalized: number
  total_center_penalty_rate: string
  total_role_penalty_rate: string
}

export interface WrcCenterBreakdown {
  centre_code: string
  centre_name: string
  zone: string | null
  cluster: string | null
  zonal_manager: string | null
  this_batch_incident_count: number
  this_batch_considered_count: number
  this_batch_not_considered_count: number
  this_batch_pending_count: number
  all_time_batch_count: number
  all_time_considered_count: number
  all_time_not_considered_count: number
  response_token: string | null
  response_token_expires_at: string | null
}

// ---------- Weekly Revenue Closure: response portal (mirrors DCB's) ----------

export interface WrcResponseLinkDetail {
  case_id: number
  centre_code: string
  centre_name: string
  response_token: string
  response_url: string
  expires_at: string
}

export interface WrcBatchPublishResult {
  batch_id: number
  links: WrcResponseLinkDetail[]
}

export interface WrcPublicIncidentSummary {
  incident_date: string
  mis_final_remark: WrcIncidentType
  raw_remark: string | null
  considered: WrcConsidered | null
}

export interface WrcPublicCase {
  centre_code: string
  centre_name: string
  period_start: string
  period_end: string
  week_label: string
  pending_incident_count: number
  tat_status: TatStatus
  deadline: string | null
  already_responded: boolean
  incidents: WrcPublicIncidentSummary[]
}

export interface WrcPublicOpenCase extends WrcPublicCase {
  id: number
}

export interface WrcCaseResponse {
  id: number
  responder_name: string
  responder_npid: string
  responder_email: string | null
  reason: string
  evidence_original_filename: string
  submitted_at: string
  was_within_tat: string | null
  selected_center_code: string | null
  selected_center_name: string | null
}

export interface WrcCenterActivity {
  id: number
  centre_code: string
  centre_name: string | null
  case_id: number | null
  event_type: DcbActivityEventType
  occurred_at: string
}

export interface WrcIncidentNotifyResult {
  sent: boolean
  reason: string | null
}

// ---------- Auto Validation -- advisory-only remark classification, shared
// vocabulary across DCB + WRC. See backend/app/services/auto_validation_service.py
// for the full design: this NEVER sets a bill/incident's real `considered`
// decision -- Vigilance's own Review Queue click remains the only thing
// that's ever official. ----------

export type AutoValidationBucket = 'considered' | 'not_considered' | 'manual_check'

export interface AutoValidationRule {
  id: number
  bucket: 'considered' | 'not_considered'
  category: string
  keyword_phrase: string
  decision_label: string
  reason: string | null
  notes: string | null
  applies_to: 'both' | 'dcb' | 'wrc'
  is_active: boolean
  created_at: string
}

export interface AutoValidationResponse {
  id: number
  engine: 'dcb' | 'wrc'
  case_or_penalty_id: number
  batch_id: number
  centre_code: string
  centre_name: string
  reason: string
  submitted_at: string
  auto_bucket: AutoValidationBucket | null
  auto_category: string | null
  auto_matched_keyword: string | null
  auto_decision_label: string | null
  auto_reason: string | null
  auto_evaluated_at: string | null
  admin_override_bucket: AutoValidationBucket | null
  admin_override_by_name: string | null
  admin_override_at: string | null
  admin_override_note: string | null
  effective_bucket: AutoValidationBucket | null
}
