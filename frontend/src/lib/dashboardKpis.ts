import type { DashboardSummary } from './types'

const currency = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })
const percent = (v: number | null) => (v === null ? '—' : `${v}%`)

/** Everything DashboardPage needs to render one KPI card, decoupled from
 * whether/where it renders -- the single source of truth both DashboardPage
 * (render loop) and Settings' Appearance/Dashboard tab (show/hide + reorder
 * picker) key off of. `key` must match the values a UserPreference's
 * dashboard_config.visible_kpis can contain (see
 * app/models/user_preference.py's DEFAULT_DASHBOARD_CONFIG on the backend). */
export interface DashboardKpiDef {
  key: string
  label: string
  to: string
  value: (data: DashboardSummary) => string | number
  hint?: (data: DashboardSummary) => string | undefined
}

export const DASHBOARD_KPIS: DashboardKpiDef[] = [
  {
    key: 'dcb_non_compliance_rate',
    label: 'DCB Non-Compliance Rate',
    to: '/delayed-cash?tab=action-taken',
    value: (d) => percent(d.dcb.non_compliance_rate),
    hint: (d) => `${d.dcb.not_considered} of ${d.dcb.considered + d.dcb.not_considered} reviewed bills`,
  },
  {
    key: 'wrc_non_compliance_rate',
    label: 'WRC Non-Compliance Rate',
    to: '/weekly-revenue-closure?tab=action-taken',
    value: (d) => percent(d.wrc.non_compliance_rate),
    hint: (d) => `${d.wrc.not_considered} of ${d.wrc.considered + d.wrc.not_considered} reviewed incidents`,
  },
  {
    key: 'dcb_validated_penalty',
    label: 'DCB Validated Penalty',
    to: '/delayed-cash?tab=batches',
    value: (d) => currency.format(d.dcb.total_validated_penalty),
  },
  {
    key: 'wrc_penalty',
    label: 'WRC Penalty (Center + Role)',
    to: '/weekly-revenue-closure?tab=batches',
    value: (d) => currency.format(d.wrc.total_center_penalty + d.wrc.total_role_penalty),
  },
  {
    key: 'dcb_awaiting_review',
    label: 'DCB Bills Awaiting Review',
    to: '/delayed-cash?tab=review-queue',
    value: (d) => d.dcb.unreviewed + d.dcb.needs_more_detail + d.dcb.needs_proof,
  },
  {
    key: 'wrc_awaiting_review',
    label: 'WRC Incidents Awaiting Review',
    to: '/weekly-revenue-closure?tab=review-queue',
    value: (d) => d.wrc.unreviewed,
  },
  {
    key: 'repeat_violators',
    label: 'Repeat SOP Violators',
    to: '/center-rankings',
    value: (d) => d.repeated_centers.length,
    hint: (d) => (d.repeated_centers_truncated ? `showing top ${d.repeated_centers.length}` : undefined),
  },
  {
    key: 'zones_with_non_compliance',
    label: 'Zones with Non-Compliance',
    to: '/center-rankings',
    value: (d) => d.zone_breakdown.length,
  },
]

export const DEFAULT_VISIBLE_KPIS: string[] = DASHBOARD_KPIS.map((k) => k.key)

/** Resolves a stored visible_kpis list against the current catalog: keeps
 * the user's chosen subset and order, dropping any key that no longer
 * exists in the catalog. Deliberately does NOT auto-add catalog keys the
 * list doesn't mention -- a key missing from the list means the user
 * hid it (see Settings' Dashboard tab), and re-adding it here would make
 * hiding a KPI impossible to make stick. A KPI added in a future release
 * simply doesn't appear until the user opts into it from Settings' own
 * "Hidden" section, same as any other currently-hidden KPI. */
export function resolveVisibleKpis(stored: string[] | undefined): DashboardKpiDef[] {
  const byKey = new Map(DASHBOARD_KPIS.map((k) => [k.key, k]))
  const list = stored ?? DEFAULT_VISIBLE_KPIS
  return list.map((key) => byKey.get(key)).filter((k): k is DashboardKpiDef => !!k)
}
