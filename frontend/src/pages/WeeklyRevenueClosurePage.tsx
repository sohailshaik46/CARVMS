import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card, CardBody, CardHeader, KpiCard } from '../components/ui/Card'
import { TextField } from '../components/ui/Field'
import { EmptyState, ErrorBanner, Spinner } from '../components/ui/Feedback'
import { HeroBanner } from '../components/ui/HeroBanner'
import { ChartIcon, ReceiptIcon, TrophyIcon, UsersIcon } from '../components/ui/Icons'
import { LedgerStackIllustration } from '../components/ui/Illustrations'
import { Modal } from '../components/ui/Modal'
import { Select } from '../components/ui/Select'
import { Tooltip } from '../components/ui/Tooltip'
import { useToast } from '../components/ui/ToastProvider'
import { apiErrorMessage } from '../lib/api'
import { approveContactChangeRequest, listContactChangeRequests, rejectContactChangeRequest } from '../lib/resources/delayedCash'
import {
  activateDefaultRule,
  closeBatch,
  deleteBatch,
  downloadBatchExport,
  downloadCaseResponseEvidence,
  getActionTaken,
  getBatchCentersBreakdown,
  getBatchSummary,
  getCaseIncidents,
  getCaseResponses,
  getCentersActivity,
  getReviewQueue,
  listBatches,
  revokeBillIncidentReview,
  listCenterPenalties,
  listNoRemarkIncidents,
  listRolePenalties,
  markNoRemarkReceived,
  notifyIncident,
  publishLinksForBatch,
  reviewBillIncident,
  uploadBatch,
} from '../lib/resources/weeklyRevenueClosure'
import {
  downloadAutoValidationExport,
  listWrcAutoValidation,
  overrideWrcResponse,
  reevaluateAllWrc,
  reevaluateWrcResponse,
} from '../lib/resources/autoValidation'
import type {
  AutoValidationBucket,
  AutoValidationResponse,
  ContactChangeRequest,
  WeeklyRevenueClosureBatch,
  WrcBatchPublishResult,
  WrcBillIncident,
  WrcCenterBreakdown,
  WrcIncidentType,
  WrcUploadResult,
} from '../lib/types'

type Tab = 'batches' | 'review-queue' | 'auto-validation' | 'action-taken' | 'centers-activity' | 'notifications'
const TAB_VALUES: Tab[] = ['batches', 'review-queue', 'auto-validation', 'action-taken', 'centers-activity', 'notifications']

function formatPct(rate: string): string {
  return `${(Number(rate) * 100).toFixed(2)}%`
}

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
}

const TYPE_LABELS: Record<string, string> = {
  bill_pending: 'Bill Pending',
  daily_report_not_sent: 'Daily Report not sent',
  no_billing_no_daily_report: 'No Billing / No Daily Report',
}

const INCIDENT_TYPE_TOOLTIPS: Record<string, string> = {
  bill_pending: 'The center had bills still pending for that day -- the most common incident type, and the only one Cluster Manager escalation counts in the "not considered" section.',
  daily_report_not_sent: "The center didn't submit its daily report for that day at all.",
  no_billing_no_daily_report: 'Neither a bill nor a daily report was submitted for that day -- the more serious combination of the two incident types above.',
}

/** Beside the week/batch filter in both Review Queue and Action Taken --
 * lists only centers actually present in whatever's already been filtered
 * down (the selected week/batch), never every center in the system, so
 * picking one always jumps to real rows instead of an empty result.
 * Mirrors DelayedCashBillingPage.tsx's identical component exactly. */
function CenterFilterSelect({
  items,
  value,
  onChange,
}: {
  items: { centre_code: string; centre_name: string }[]
  value: string | 'all'
  onChange: (value: string | 'all') => void
}) {
  const centers = Array.from(new Map(items.map((i) => [i.centre_code, i.centre_name])).entries()).sort((a, b) =>
    a[0].localeCompare(b[0]),
  )

  return (
    <Tooltip text="Search/jump to one center -- only lists centers with a row in the currently selected week or batch above.">
      <Select className="w-56 text-sm" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="all">Search centers…</option>
        {centers.map(([code, name]) => (
          <option key={code} value={code}>
            {code} -- {name}
          </option>
        ))}
      </Select>
    </Tooltip>
  )
}

/** Weekly Revenue Closure -- a deliberately separate engine from Delayed
 * Cash Billing (different formula: flat 6.25% per delinquent center per
 * week, escalating to Cluster Manager and, in the "no remark" section
 * only, Zonal Manager too). See
 * docs/CARVMS_WEEKLY_REVENUE_CLOSURE_FORMULA_ANALYSIS.md for the proof
 * this was built against -- never change the formula here without
 * re-reading that doc. */
export function WeeklyRevenueClosurePage() {
  // Deep-linkable via ?tab=... -- see DelayedCashBillingPage's identical
  // pattern; the Dashboard's KPI boxes route straight into the tab a
  // number actually comes from.
  const [searchParams] = useSearchParams()
  const initialTab = TAB_VALUES.find((t) => t === searchParams.get('tab')) ?? 'batches'
  const [tab, setTab] = useState<Tab>(initialTab)
  // See DelayedCashBillingPage's identical comment -- a KPI card within
  // this same page (the batch dashboard's "Considered" box, etc.)
  // navigates via "?tab=..." too, but the pathname doesn't change, so this
  // component never remounts; re-sync whenever the URL's tab param changes.
  useEffect(() => {
    const fromUrl = TAB_VALUES.find((t) => t === searchParams.get('tab'))
    if (fromUrl) setTab(fromUrl)
  }, [searchParams])
  const [isUploadOpen, setIsUploadOpen] = useState(false)
  const [selectedBatchId, setSelectedBatchId] = useState<number | null>(null)
  const [centersBatchId, setCentersBatchId] = useState<number | null>(null)
  const [publishResult, setPublishResult] = useState<WrcBatchPublishResult | null>(null)
  const [batchToDelete, setBatchToDelete] = useState<WeeklyRevenueClosureBatch | null>(null)
  const queryClient = useQueryClient()
  const { showToast } = useToast()

  const { data: batches, isLoading, error } = useQuery({ queryKey: ['wrc-batches'], queryFn: listBatches })

  // Same query key the Notifications tab itself uses below -- shares the
  // cache. Powers the pending-count badge on the tab label.
  const { data: pendingContactChanges } = useQuery({
    queryKey: ['wrc-contact-change-requests'],
    queryFn: () => listContactChangeRequests('pending'),
  })

  const publishMutation = useMutation({
    mutationFn: (batchId: number) => publishLinksForBatch(batchId),
    onSuccess: (result) => setPublishResult(result),
    onError: (err) => showToast(apiErrorMessage(err, 'Could not publish links'), 'error'),
  })

  const deleteMutation = useMutation({
    mutationFn: (batchId: number) => deleteBatch(batchId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['wrc-batches'] })
      showToast(`Deleted "${batchToDelete?.week_label}" and all its incidents/penalties/responses`)
      setBatchToDelete(null)
    },
    onError: (err) => showToast(apiErrorMessage(err, 'Delete failed'), 'error'),
  })

  const TABS: { key: Tab; label: string }[] = [
    { key: 'batches', label: 'Batches' },
    { key: 'review-queue', label: 'Review Queue' },
    { key: 'auto-validation', label: 'Auto Validation' },
    { key: 'action-taken', label: 'Action Taken' },
    { key: 'centers-activity', label: 'Centers Activity' },
    { key: 'notifications', label: 'Notifications' },
  ]

  return (
    <div className="space-y-6">
      <HeroBanner
        illustration={<LedgerStackIllustration className="h-full w-full" />}
        kicker="Revenue Vigilance"
        title="Weekly Revenue Closure"
        actions={
          tab === 'batches' ? <Button onClick={() => setIsUploadOpen(true)}>Upload Closure Pending List</Button> : undefined
        }
      />

      <div className="flex gap-1 border-b border-slate-200 dark:border-slate-700">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`relative px-3 py-2 text-sm font-medium ${
              tab === t.key
                ? 'border-b-2 border-brand-600 text-brand-700 dark:border-neon-500 dark:text-neon-400'
                : 'text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200'
            }`}
          >
            {t.label}
            {t.key === 'notifications' && !!pendingContactChanges?.length && (
              <span className="ml-1.5 inline-flex min-w-[1.25rem] items-center justify-center rounded-full bg-brand-600 px-1.5 py-0.5 text-[10px] font-semibold text-white dark:bg-neon-500 dark:text-void-950">
                {pendingContactChanges.length}
              </span>
            )}
          </button>
        ))}
      </div>

      {tab === 'batches' && (
        <>
          <Card>
            <CardHeader title="Batches" />
            <CardBody>
              {isLoading && <Spinner />}
              {error && <ErrorBanner message={apiErrorMessage(error)} />}
              {batches && batches.length === 0 && (
                <EmptyState title="No batches uploaded yet" hint="Upload a weekly closure pending list to get started." />
              )}
              {batches && batches.length > 0 && (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="text-xs uppercase text-slate-500 dark:text-slate-400">
                      <tr>
                        <th className="py-2 pr-4">Week</th>
                        <th className="py-2 pr-4">Period</th>
                        <th className="py-2 pr-4">Status</th>
                        <th className="py-2 pr-4">Created</th>
                        <th className="py-2 pr-4">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
                      {batches.map((batch) => (
                        <tr key={batch.id} className="hover:bg-slate-100 dark:hover:bg-slate-700">
                          <td className="py-2 pr-4 font-medium">{batch.week_label}</td>
                          <td className="py-2 pr-4">
                            {formatDate(batch.period_start)} – {formatDate(batch.period_end)}
                          </td>
                          <td className="py-2 pr-4">
                            <Badge tone="status">{batch.status}</Badge>
                          </td>
                          <td className="py-2 pr-4">{formatDate(batch.created_at)}</td>
                          <td className="py-2 pr-4">
                            <div className="flex flex-wrap gap-2">
                              <Tooltip text="Opens this week's KPI dashboard -- total incidents, considered/not-considered counts, center penalties, and Cluster/Zonal Manager escalation.">
                                <button
                                  className="text-xs font-medium text-np-calming-blue hover:text-np-deep-blue dark:text-neon-blue-400 dark:hover:text-neon-blue-300"
                                  onClick={() => {
                                    // Mutually exclusive with "View centers" below -- see the
                                    // identical comment in DelayedCashBillingPage.tsx for why:
                                    // without clearing the other panel's id, both cards stack
                                    // and Dashboard (rendered first) hides that anything changed.
                                    setCentersBatchId(null)
                                    setSelectedBatchId(batch.id)
                                  }}
                                >
                                  View dashboard
                                </button>
                              </Tooltip>
                              <Tooltip text="Opens the centers in this batch with their zone/cluster, plus each center's all-time repeat-non-compliance count and considered/not-considered history.">
                                <button
                                  className="text-xs font-medium text-np-calming-blue hover:text-np-deep-blue dark:text-neon-blue-400 dark:hover:text-neon-blue-300"
                                  onClick={() => {
                                    setSelectedBatchId(null)
                                    setCentersBatchId(batch.id)
                                  }}
                                >
                                  View centers
                                </button>
                              </Tooltip>
                              <Tooltip text="Generates a response link for every center with an incident in this batch, and shows the full list so you can share or email them.">
                                <button
                                  className="text-xs font-medium text-brand-600 hover:text-brand-700 dark:text-vigilance-400 dark:hover:text-neon-400"
                                  disabled={publishMutation.isPending}
                                  onClick={() => publishMutation.mutate(batch.id)}
                                >
                                  Publish links
                                </button>
                              </Tooltip>
                              <Tooltip text="Permanently deletes this batch and everything computed from it -- incidents, penalties, cases, submitted responses, and evidence files. Cannot be undone; asks for confirmation first.">
                                <button
                                  className="text-xs font-medium text-red-600 hover:text-red-700 dark:text-neon-pink-400 dark:hover:text-neon-pink-300"
                                  onClick={() => setBatchToDelete(batch)}
                                >
                                  Delete
                                </button>
                              </Tooltip>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardBody>
          </Card>

          {selectedBatchId != null && (
            <BatchDashboard
              batchId={selectedBatchId}
              onClose={() => setSelectedBatchId(null)}
              onSwitchBatch={setSelectedBatchId}
            />
          )}
          {centersBatchId != null && (
            <WrcCentersBreakdown
              batchId={centersBatchId}
              onClose={() => setCentersBatchId(null)}
              onSwitchBatch={setCentersBatchId}
            />
          )}
        </>
      )}

      {tab === 'review-queue' && <ReviewQueueTab />}
      {tab === 'auto-validation' && <WrcAutoValidationTab />}
      {tab === 'action-taken' && <ActionTakenTab />}
      {tab === 'centers-activity' && <CentersActivityTab />}
      {tab === 'notifications' && <WrcContactChangeNotificationsTab />}

      {publishResult && <PublishResultModal result={publishResult} onClose={() => setPublishResult(null)} />}

      {batchToDelete && (
        <Modal title="Delete this batch?" onClose={() => setBatchToDelete(null)}>
          <div className="space-y-4">
            <p className="text-sm text-slate-600 dark:text-slate-300">
              This permanently deletes <span className="font-medium text-slate-800 dark:text-slate-100">{batchToDelete.week_label}</span>{' '}
              ({formatDate(batchToDelete.period_start)} – {formatDate(batchToDelete.period_end)}) along with every
              incident, center/role penalty, response-portal link, submitted response and evidence file, and activity
              record tied to it. This cannot be undone -- you can re-upload a corrected file afterwards.
            </p>
            <ErrorBanner message="This action is irreversible." />
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setBatchToDelete(null)}>
                Cancel
              </Button>
              <Button
                variant="danger"
                isLoading={deleteMutation.isPending}
                onClick={() => deleteMutation.mutate(batchToDelete.id)}
              >
                Delete batch
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {isUploadOpen && (
        <UploadBatchModal
          onClose={() => setIsUploadOpen(false)}
          onUploaded={(result) => {
            // Deliberately does NOT close the modal (see UploadBatchModal
            // below) -- it switches to its own result view (skipped-rows
            // table, out-of-period count, etc.) and stays open until the
            // user clicks "Done" themselves, so that view is actually
            // seen rather than instantly unmounted.
            queryClient.invalidateQueries({ queryKey: ['wrc-batches'] })
            setSelectedBatchId(result.batch.id)
            const outOfPeriodNote =
              result.out_of_period_row_count > 0
                ? ` ${result.out_of_period_row_count} row(s) outside this batch's own dates were ignored (already covered by a prior week's upload).`
                : ''
            if (result.skipped_rows.length > 0) {
              showToast(`Uploaded with ${result.skipped_rows.length} row(s) skipped -- see the report below.${outOfPeriodNote}`, 'error')
            } else {
              showToast(
                `Ingested ${result.incidents_ingested} incident(s); ${result.excess_billed_row_count} Excess billed row(s) counted (out of scope for penalty).${outOfPeriodNote}`,
              )
            }
          }}
        />
      )}
    </div>
  )
}

function BatchDashboard({
  batchId,
  onClose,
  onSwitchBatch,
}: {
  batchId: number
  onClose: () => void
  onSwitchBatch: (batchId: number) => void
}) {
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [showNoRemark, setShowNoRemark] = useState(false)

  // Shares the Batches tab's own query -- so the picker below doesn't cost
  // a second request and always lists the exact same batches shown there.
  const { data: batches } = useQuery({ queryKey: ['wrc-batches'], queryFn: listBatches })

  const { data: summary, isLoading, error } = useQuery({
    queryKey: ['wrc-batch-summary', batchId],
    queryFn: () => getBatchSummary(batchId),
  })
  const { data: centerPenalties } = useQuery({
    queryKey: ['wrc-center-penalties', batchId],
    queryFn: () => listCenterPenalties(batchId),
  })
  const { data: rolePenalties } = useQuery({
    queryKey: ['wrc-role-penalties', batchId],
    queryFn: () => listRolePenalties(batchId),
  })

  const closeMutation = useMutation({
    mutationFn: () => closeBatch(batchId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['wrc-batch-summary', batchId] })
      queryClient.invalidateQueries({ queryKey: ['wrc-center-penalties', batchId] })
      queryClient.invalidateQueries({ queryKey: ['wrc-role-penalties', batchId] })
      queryClient.invalidateQueries({ queryKey: ['wrc-batches'] })
      showToast('Batch closed -- penalties computed')
    },
    onError: (err) => showToast(apiErrorMessage(err, 'Could not close batch'), 'error'),
  })

  const exportMutation = useMutation({
    mutationFn: () => downloadBatchExport(batchId, summary?.batch.week_label ?? `batch-${batchId}`),
    onError: (err) => showToast(apiErrorMessage(err, 'Export failed'), 'error'),
  })

  return (
    <Card>
      <CardHeader
        title={summary ? `${summary.batch.week_label} -- Dashboard` : `Batch #${batchId} -- Dashboard`}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Tooltip text="Switch this dashboard to a different week without closing it -- picks up right where you are, no need to go back to the Batches tab first.">
              <Select
                className="w-56 text-sm"
                value={String(batchId)}
                onChange={(e) => onSwitchBatch(Number(e.target.value))}
              >
                {batches?.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.week_label}
                  </option>
                ))}
              </Select>
            </Tooltip>
            <Tooltip text="Downloads this week's full Data + Penalty workbook as an Excel file, in the same 3-sheet shape as the proven reference workbook.">
              <Button variant="secondary" isLoading={exportMutation.isPending} onClick={() => exportMutation.mutate()}>
                Export Workbook
              </Button>
            </Tooltip>
            <Tooltip text="Computes every center's penalty and every Cluster/Zonal Manager's escalation from each incident's current decision. Safe to click again later if a decision changes -- it recomputes from scratch every time, never adds on top of a previous run.">
              <Button isLoading={closeMutation.isPending} onClick={() => closeMutation.mutate()}>
                {summary?.batch.status === 'closed' ? 'Recompute (close again)' : 'Close Batch'}
              </Button>
            </Tooltip>
            <Tooltip text="Hides this dashboard and returns to the batches list -- doesn't change any data.">
              <button onClick={onClose} className="text-xs font-medium text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200">
                Close panel
              </button>
            </Tooltip>
          </div>
        }
      />
      <CardBody className="space-y-6">
        {isLoading && <Spinner />}
        {error && <ErrorBanner message={apiErrorMessage(error)} />}
        {summary && (
          <>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <KpiCard
                label="Total Incidents"
                value={<span className="inline-flex items-center gap-2"><ReceiptIcon className="h-5 w-5 text-slate-500 dark:text-vigilance-400" />{summary.total_incidents}</span>}
                tooltip="Every remark-received incident uploaded for this week, regardless of review status. Click to see them in the Review Queue."
                to={`/weekly-revenue-closure?tab=review-queue&batch=${batchId}`}
              />
              <KpiCard
                label="Pending Review"
                value={summary.pending_review_count}
                hint="Awaiting Vigilance verdict"
                tooltip="Incidents that still need a Considered/Not Considered decision -- click to open them in the Review Queue, pre-filtered to this week."
                to={`/weekly-revenue-closure?tab=review-queue&batch=${batchId}`}
              />
              <KpiCard
                label="Considered"
                value={summary.considered_count}
                hint="Accepted exception -- no penalty"
                tooltip="Incidents Vigilance marked Considered -- click to see them in Action Taken, pre-filtered to this week and this decision."
                to={`/weekly-revenue-closure?tab=action-taken&batch=${batchId}&decision=considered`}
              />
              <KpiCard
                label="Not Considered"
                value={summary.not_considered_count}
                hint="Feeds the flat penalty"
                tooltip="Incidents Vigilance marked Not Considered -- click to see them in Action Taken, pre-filtered to this week and this decision."
                to={`/weekly-revenue-closure?tab=action-taken&batch=${batchId}&decision=not_considered`}
              />
              <KpiCard
                label="No-Remark Centers"
                value={summary.no_remark_center_count}
                hint="Never responded"
                tooltip="Centers that never submitted any remark at all for this week -- click to see which centers, and how many times each. A separate, harsher section from 'Not Considered', which still escalates to both Cluster and Zonal Manager."
                onCardClick={() => setShowNoRemark(true)}
              />
              <KpiCard
                label="Centers Penalized"
                value={<span className="inline-flex items-center gap-2"><UsersIcon className="h-5 w-5 text-slate-500 dark:text-vigilance-400" />{summary.centers_penalized}</span>}
                tooltip="How many distinct centers have at least one penalty (Not Considered or No-Remark) computed for this week -- see the Center Penalties table below."
              />
              <KpiCard
                label="Total Center Penalty Rate"
                value={<span className="inline-flex items-center gap-2"><ChartIcon className="h-5 w-5 text-slate-500 dark:text-vigilance-400" />{formatPct(summary.total_center_penalty_rate)}</span>}
                hint="Sum of flat 6.25% rates, not a rupee amount"
                tooltip="Adds up every center's penalty rate (6.25% each, flat, never scaled by incident count) -- a rate total, not a rupee figure."
              />
              <KpiCard
                label="Total Role Escalation Rate"
                value={<span className="inline-flex items-center gap-2"><TrophyIcon className="h-5 w-5 text-slate-500 dark:text-vigilance-400" />{formatPct(summary.total_role_penalty_rate)}</span>}
                hint="Cluster/Zonal Manager escalation, summed"
                tooltip="Adds up every Cluster/Zonal Manager escalation this week -- rate x count of distinct centers under them with a qualifying incident."
              />
            </div>

            <div>
              <h4 className="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-200">Center Penalties</h4>
              {centerPenalties && centerPenalties.length === 0 && (
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  None yet -- close the batch to compute penalties from reviewed incidents.
                </p>
              )}
              {centerPenalties && centerPenalties.length > 0 && (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="text-xs uppercase text-slate-500 dark:text-slate-400">
                      <tr>
                        <th className="py-2 pr-4">Center</th>
                        <th className="py-2 pr-4">Center Manager</th>
                        <th className="py-2 pr-4">Not Considered</th>
                        <th className="py-2 pr-4">No Remark</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
                      {centerPenalties.map((cp) => (
                        <tr key={cp.id}>
                          <td className="py-2 pr-4">
                            {cp.centre_code}
                            <div className="text-xs text-slate-500 dark:text-slate-400">{cp.centre_name}</div>
                          </td>
                          <td className="py-2 pr-4">{cp.center_manager ?? '—'}</td>
                          <td className="py-2 pr-4 font-medium">{formatPct(cp.not_considered_penalty)}</td>
                          <td className="py-2 pr-4 font-medium">{formatPct(cp.no_remark_penalty)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <div>
              <h4 className="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-200">Cluster / Zonal Manager Escalation</h4>
              {rolePenalties && rolePenalties.length === 0 && (
                <p className="text-xs text-slate-500 dark:text-slate-400">None yet -- close the batch to compute escalations.</p>
              )}
              {rolePenalties && rolePenalties.length > 0 && (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="text-xs uppercase text-slate-500 dark:text-slate-400">
                      <tr>
                        <th className="py-2 pr-4">Role</th>
                        <th className="py-2 pr-4">Name</th>
                        <th className="py-2 pr-4">Section</th>
                        <th className="py-2 pr-4">Distinct Centers</th>
                        <th className="py-2 pr-4">Penalty</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
                      {rolePenalties.map((rp) => (
                        <tr key={rp.id}>
                          <td className="py-2 pr-4">{rp.role === 'cluster_manager' ? 'Cluster Manager' : 'Zonal Manager'}</td>
                          <td className="py-2 pr-4">{rp.person_name}</td>
                          <td className="py-2 pr-4">
                            <Badge tone="status">{rp.section === 'not_considered' ? 'Not Considered' : 'No Remark'}</Badge>
                          </td>
                          <td className="py-2 pr-4">{rp.distinct_center_count}</td>
                          <td className="py-2 pr-4 font-medium">{formatPct(rp.penalty_amount)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </>
        )}
      </CardBody>
      {showNoRemark && <NoRemarkCentersModal batchId={batchId} onClose={() => setShowNoRemark(false)} />}
    </Card>
  )
}

function NoRemarkCentersModal({ batchId, onClose }: { batchId: number; onClose: () => void }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['wrc-no-remark-incidents', batchId],
    queryFn: () => listNoRemarkIncidents(batchId),
  })

  return (
    <Modal title="Centers That Never Responded This Week" onClose={onClose} wide>
      <div className="space-y-3">
        <p className="text-xs text-slate-500 dark:text-slate-400">
          Every center with zero remarks submitted for this week, by incident type, with how many times each type
          occurred -- informational only, the penalty itself is flat per center per section, never scaled by count.
        </p>
        {isLoading && <Spinner />}
        {error && <ErrorBanner message={apiErrorMessage(error)} />}
        {data && data.length === 0 && <EmptyState title="No centers in this bucket" hint="Every center submitted at least one remark this week." />}
        {data && data.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase text-slate-500 dark:text-slate-400">
                <tr>
                  <th className="py-2 pr-4">Center</th>
                  <th className="py-2 pr-4">Incident Type</th>
                  <th className="py-2 pr-4">Count</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
                {data.map((n) => (
                  <tr key={n.id}>
                    <td className="py-2 pr-4">
                      {n.centre_code}
                      <div className="text-xs text-slate-500 dark:text-slate-400">{n.centre_name}</div>
                    </td>
                    <td className="py-2 pr-4">{TYPE_LABELS[n.incident_type] ?? n.incident_type}</td>
                    <td className="py-2 pr-4">{n.incident_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Modal>
  )
}

interface WrcRollupRow {
  key: string
  centerCount: number
  thisBatchIncidents: number
  allTimeConsidered: number
  allTimeNotConsidered: number
  repeatCentersCount: number
  centers: WrcCenterBreakdown[]
  repeatCenters: WrcCenterBreakdown[]
}

/** Aggregates a list of per-center breakdown rows into one rollup row per
 * distinct key (cluster/zone/zonal manager) -- "Unknown" groups centers
 * whose source incident rows never carried that column, rather than
 * dropping them. Keeps the actual matching rows (not just their counts) so
 * a rollup number can drill into exactly which centers make it up -- see
 * RollupSection's onDrill. */
function rollupBreakdown(rows: WrcCenterBreakdown[], keyFn: (r: WrcCenterBreakdown) => string): WrcRollupRow[] {
  const groups = new Map<string, WrcRollupRow>()
  for (const r of rows) {
    const key = keyFn(r) || 'Unknown'
    const g = groups.get(key) ?? {
      key, centerCount: 0, thisBatchIncidents: 0, allTimeConsidered: 0, allTimeNotConsidered: 0,
      repeatCentersCount: 0, centers: [], repeatCenters: [],
    }
    g.centerCount += 1
    g.thisBatchIncidents += r.this_batch_incident_count
    g.allTimeConsidered += r.all_time_considered_count
    g.allTimeNotConsidered += r.all_time_not_considered_count
    g.centers.push(r)
    if (r.all_time_batch_count > 1) {
      g.repeatCentersCount += 1
      g.repeatCenters.push(r)
    }
    groups.set(key, g)
  }
  return Array.from(groups.values()).sort((a, b) => b.thisBatchIncidents - a.thisBatchIncidents)
}

/** A clickable rollup count -- opens the drilldown modal listing exactly
 * which centers make up this number, instead of leaving it as a dead-end
 * figure. `count` of 0 stays plain text (nothing to drill into). */
function WrcDrillableCount({
  count,
  label,
  centers,
  onDrill,
}: {
  count: number
  label: string
  centers: WrcCenterBreakdown[]
  onDrill: (label: string, centers: WrcCenterBreakdown[]) => void
}) {
  if (count === 0) return <span className="text-slate-400 dark:text-slate-500">0</span>
  return (
    <button type="button" onClick={() => onDrill(label, centers)} className="font-medium text-np-calming-blue hover:underline">
      {count}
    </button>
  )
}

/** Lists exactly which centers make up a clicked rollup number. */
function WrcCenterDrilldownModal({
  label,
  centers,
  onClose,
}: {
  label: string
  centers: WrcCenterBreakdown[]
  onClose: () => void
}) {
  return (
    <Modal title={label} onClose={onClose} wide>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-xs uppercase text-slate-500 dark:text-slate-400">
            <tr>
              <th className="py-2 pr-4">Center</th>
              <th className="py-2 pr-4">Zone</th>
              <th className="py-2 pr-4">Cluster</th>
              <th className="py-2 pr-4">Zonal Manager</th>
              <th className="py-2 pr-4">This Week's Incidents</th>
              <th className="py-2 pr-4">All-Time Weeks Flagged</th>
              <th className="py-2 pr-4">All-Time Considered</th>
              <th className="py-2 pr-4">All-Time Not Considered</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
            {centers.map((c) => (
              <tr key={c.centre_code}>
                <td className="py-2 pr-4">
                  {c.centre_code}
                  <div className="text-xs text-slate-500 dark:text-slate-400">{c.centre_name}</div>
                </td>
                <td className="py-2 pr-4">{c.zone ?? <span className="text-slate-400 dark:text-slate-500">Unknown</span>}</td>
                <td className="py-2 pr-4">{c.cluster ?? <span className="text-slate-400 dark:text-slate-500">Unknown</span>}</td>
                <td className="py-2 pr-4">{c.zonal_manager ?? <span className="text-slate-400 dark:text-slate-500">Unknown</span>}</td>
                <td className="py-2 pr-4">{c.this_batch_incident_count}</td>
                <td className="py-2 pr-4">{c.all_time_batch_count}</td>
                <td className="py-2 pr-4">{c.all_time_considered_count}</td>
                <td className="py-2 pr-4">{c.all_time_not_considered_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Modal>
  )
}

function WrcCentersBreakdown({
  batchId,
  onClose,
  onSwitchBatch,
}: {
  batchId: number
  onClose: () => void
  onSwitchBatch: (batchId: number) => void
}) {
  const { showToast } = useToast()
  const { data: batches } = useQuery({ queryKey: ['wrc-batches'], queryFn: listBatches })
  const { data, isLoading, error } = useQuery({
    queryKey: ['wrc-centers-breakdown', batchId],
    queryFn: () => getBatchCentersBreakdown(batchId),
  })

  const byCluster = data ? rollupBreakdown(data, (r) => r.cluster ?? 'Unknown') : []
  const byZone = data ? rollupBreakdown(data, (r) => r.zone ?? 'Unknown') : []
  const byZonalManager = data ? rollupBreakdown(data, (r) => r.zonal_manager ?? 'Unknown') : []
  const [drilldown, setDrilldown] = useState<{ label: string; centers: WrcCenterBreakdown[] } | null>(null)
  const handleDrill = (label: string, drillCenters: WrcCenterBreakdown[]) => setDrilldown({ label, centers: drillCenters })

  return (
    <Card>
      <CardHeader
        title="Centers -- Cluster / Zone / Repeat Non-Compliance"
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Tooltip text="Switch this list to a different week without closing it -- picks up right where you are, no need to go back to the Batches tab first.">
              <Select
                className="w-56 text-sm"
                value={String(batchId)}
                onChange={(e) => onSwitchBatch(Number(e.target.value))}
              >
                {batches?.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.week_label}
                  </option>
                ))}
              </Select>
            </Tooltip>
            <Tooltip text="Hides this list and returns to the batches list -- doesn't change any data.">
              <button onClick={onClose} className="text-xs font-medium text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200">
                Close panel
              </button>
            </Tooltip>
          </div>
        }
      />
      <CardBody className="space-y-6">
        {isLoading && <Spinner />}
        {error && <ErrorBanner message={apiErrorMessage(error)} />}
        {data && data.length === 0 && <EmptyState title="No centers in this batch" />}
        {data && data.length > 0 && (
          <>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              "All-time" counts look across every week uploaded so far, not just this one -- "Repeat" means a center
              that has shown up with an incident in more than one week to date.
            </p>

            <RollupSection title="By Cluster" rows={byCluster} onDrill={handleDrill} />
            <RollupSection title="By Zone" rows={byZone} onDrill={handleDrill} />
            <RollupSection title="By Zonal Manager" rows={byZonalManager} onDrill={handleDrill} />

            <div>
              <h4 className="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-200">All Centers in This Batch</h4>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="text-xs uppercase text-slate-500 dark:text-slate-400">
                    <tr>
                      <th className="py-2 pr-4">Center</th>
                      <th className="py-2 pr-4">Zone</th>
                      <th className="py-2 pr-4">Cluster</th>
                      <th className="py-2 pr-4">Zonal Manager</th>
                      <th className="py-2 pr-4">This Week</th>
                      <th className="py-2 pr-4">Link</th>
                      <th className="py-2 pr-4">All-Time Weeks Flagged</th>
                      <th className="py-2 pr-4">All-Time Considered</th>
                      <th className="py-2 pr-4">All-Time Not Considered</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
                    {data.map((r) => (
                      <tr key={r.centre_code}>
                        <td className="py-2 pr-4">
                          {r.centre_code}
                          <div className="text-xs text-slate-500 dark:text-slate-400">{r.centre_name}</div>
                        </td>
                        <td className="py-2 pr-4">{r.zone ?? <span className="text-slate-400 dark:text-slate-500">Unknown</span>}</td>
                        <td className="py-2 pr-4">{r.cluster ?? <span className="text-slate-400 dark:text-slate-500">Unknown</span>}</td>
                        <td className="py-2 pr-4">{r.zonal_manager ?? <span className="text-slate-400 dark:text-slate-500">Unknown</span>}</td>
                        <td className="py-2 pr-4">
                          {r.this_batch_considered_count > 0 && (
                            <Badge tone="status">{`${r.this_batch_considered_count} considered`}</Badge>
                          )}{' '}
                          {r.this_batch_not_considered_count > 0 && (
                            <Badge tone="status">{`${r.this_batch_not_considered_count} not considered`}</Badge>
                          )}{' '}
                          {r.this_batch_pending_count > 0 && (
                            <span className="text-xs text-slate-500 dark:text-slate-400">{r.this_batch_pending_count} pending</span>
                          )}
                        </td>
                        <td className="py-2 pr-4">
                          {r.response_token ? (
                            <Tooltip text="Copies this center's own response-portal link -- read-only, doesn't mint or invalidate anything.">
                              <button
                                type="button"
                                className="text-xs font-medium text-np-calming-blue hover:text-np-deep-blue dark:text-neon-blue-400 dark:hover:text-neon-blue-300"
                                onClick={() => {
                                  const url = `${window.location.origin}/respond/weekly-revenue/${r.response_token}`
                                  navigator.clipboard.writeText(url).then(() => showToast('Link copied'))
                                }}
                              >
                                Copy link
                              </button>
                            </Tooltip>
                          ) : (
                            <span className="text-xs text-slate-400 dark:text-slate-500">—</span>
                          )}
                        </td>
                        <td className="py-2 pr-4">
                          <Tooltip text="How many distinct weeks (batches) this center has had at least one incident, all-time -- more than 1 means a repeat.">
                            <span className={r.all_time_batch_count > 1 ? 'font-medium text-amber-700 dark:text-amber-400' : ''}>
                              {r.all_time_batch_count}
                            </span>
                          </Tooltip>
                        </td>
                        <td className="py-2 pr-4">{r.all_time_considered_count}</td>
                        <td className="py-2 pr-4">{r.all_time_not_considered_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
      </CardBody>
      {drilldown && (
        <WrcCenterDrilldownModal label={drilldown.label} centers={drilldown.centers} onClose={() => setDrilldown(null)} />
      )}
    </Card>
  )
}

function RollupSection({
  title,
  rows,
  onDrill,
}: {
  title: string
  rows: WrcRollupRow[]
  onDrill: (label: string, centers: WrcCenterBreakdown[]) => void
}) {
  if (rows.length === 0) return null
  const dimension = title.replace('By ', '')
  return (
    <div>
      <h4 className="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-200">{title}</h4>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-xs uppercase text-slate-500 dark:text-slate-400">
            <tr>
              <th className="py-2 pr-4">{dimension}</th>
              <th className="py-2 pr-4">
                <Tooltip text={`How many distinct centers fall under this ${dimension.toLowerCase()}. Click a row's Center count to see which ones.`}>
                  <span className="cursor-help underline decoration-dotted">Centers</span>
                </Tooltip>
              </th>
              <th className="py-2 pr-4">
                <Tooltip text="How many incidents in THIS week/batch belong to centers under this row -- click to see them.">
                  <span className="cursor-help underline decoration-dotted">This Week's Incidents</span>
                </Tooltip>
              </th>
              <th className="py-2 pr-4">
                <Tooltip text="Centers under this row that have appeared in more than one week all-time -- a genuine repeat, not just multiple incidents in one week. Click to see which centers.">
                  <span className="cursor-help underline decoration-dotted">Repeat Centers</span>
                </Tooltip>
              </th>
              <th className="py-2 pr-4">
                <Tooltip text="All-time count of incidents under this row's centers marked Considered -- click to see which centers.">
                  <span className="cursor-help underline decoration-dotted">All-Time Considered</span>
                </Tooltip>
              </th>
              <th className="py-2 pr-4">
                <Tooltip text="All-time count of incidents under this row's centers marked Not Considered -- click to see which centers.">
                  <span className="cursor-help underline decoration-dotted">All-Time Not Considered</span>
                </Tooltip>
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
            {rows.map((r) => (
              <tr key={r.key}>
                <td className="py-2 pr-4 font-medium">{r.key}</td>
                <td className="py-2 pr-4">
                  <WrcDrillableCount count={r.centerCount} label={`${dimension}: ${r.key} -- all centers`} centers={r.centers} onDrill={onDrill} />
                </td>
                <td className="py-2 pr-4">{r.thisBatchIncidents}</td>
                <td className="py-2 pr-4">
                  <WrcDrillableCount count={r.repeatCentersCount} label={`${dimension}: ${r.key} -- repeat centers`} centers={r.repeatCenters} onDrill={onDrill} />
                </td>
                <td className="py-2 pr-4">
                  <WrcDrillableCount
                    count={r.allTimeConsidered}
                    label={`${dimension}: ${r.key} -- centers with an all-time Considered incident`}
                    centers={r.centers.filter((c) => c.all_time_considered_count > 0)}
                    onDrill={onDrill}
                  />
                </td>
                <td className="py-2 pr-4">
                  <WrcDrillableCount
                    count={r.allTimeNotConsidered}
                    label={`${dimension}: ${r.key} -- centers with an all-time Not Considered incident`}
                    centers={r.centers.filter((c) => c.all_time_not_considered_count > 0)}
                    onDrill={onDrill}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

const INCIDENT_TYPE_OPTIONS = Object.keys(TYPE_LABELS) as WrcIncidentType[]

function ReviewQueueTab() {
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [searchParams] = useSearchParams()
  // Pre-selected when arriving from a KPI card's "?batch=" link (e.g. the
  // batch dashboard's "Total Incidents" / "Pending Review" boxes) --
  // otherwise defaults to "all weeks", same as before.
  const batchParam = searchParams.get('batch')
  const [remarksDraft, setRemarksDraft] = useState<Record<number, string>>({})
  const [weekFilter, setWeekFilter] = useState<number | 'all'>(batchParam ? Number(batchParam) : 'all')
  const [typeFilter, setTypeFilter] = useState<WrcIncidentType | 'all'>('all')
  const [centerFilter, setCenterFilter] = useState<string | 'all'>('all')

  const { data: batches } = useQuery({ queryKey: ['wrc-batches'], queryFn: listBatches })
  const {
    data: incidentsForWeek,
    isLoading,
    error,
  } = useQuery({
    queryKey: ['wrc-review-queue', weekFilter],
    queryFn: () => getReviewQueue(weekFilter === 'all' ? undefined : weekFilter),
  })

  // Counts reflect the selected week (or all weeks) BEFORE the type
  // filter narrows the list further -- so the pill labels always show
  // "how many of each type exist right now", not just what's visible.
  const countsByType = INCIDENT_TYPE_OPTIONS.reduce(
    (acc, type) => {
      acc[type] = incidentsForWeek?.filter((i) => i.mis_final_remark === type).length ?? 0
      return acc
    },
    {} as Record<WrcIncidentType, number>,
  )

  const incidents = incidentsForWeek
    ?.filter((i) => typeFilter === 'all' || i.mis_final_remark === typeFilter)
    .filter((i) => centerFilter === 'all' || i.centre_code === centerFilter)

  const reviewMutation = useMutation({
    mutationFn: ({ id, decision, centerRemarks }: { id: number; decision: 'considered' | 'not_considered'; centerRemarks?: string }) =>
      reviewBillIncident(id, decision, centerRemarks),
    onSuccess: (_result, { decision }) => {
      queryClient.invalidateQueries({ queryKey: ['wrc-review-queue'] })
      showToast(`Marked "${decision.replace(/_/g, ' ')}"`)
    },
    onError: (err) => showToast(apiErrorMessage(err, 'Could not save that decision'), 'error'),
  })

  const noRemarkMutation = useMutation({
    mutationFn: (id: number) => markNoRemarkReceived(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['wrc-review-queue'] })
      showToast('Moved to "Remarks Not Received"')
    },
    onError: (err) => showToast(apiErrorMessage(err, 'Could not update'), 'error'),
  })

  return (
    <Card>
      <CardHeader
        title="Incidents Awaiting a Vigilance Verdict"
        actions={
          <div className="flex flex-wrap gap-2">
            <Select
              className="w-56 text-sm"
              value={weekFilter === 'all' ? 'all' : String(weekFilter)}
              onChange={(e) => setWeekFilter(e.target.value === 'all' ? 'all' : Number(e.target.value))}
            >
              <option value="all">All weeks</option>
              {batches?.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.week_label}
                </option>
              ))}
            </Select>
            <CenterFilterSelect items={incidentsForWeek ?? []} value={centerFilter} onChange={setCenterFilter} />
          </div>
        }
      />
      <CardBody>
        <div className="mb-4 flex flex-wrap gap-2">
          <Tooltip text="Every incident awaiting a decision for the selected week (or all weeks).">
            <button
              type="button"
              onClick={() => setTypeFilter('all')}
              className={`rounded-full border px-3 py-1 text-xs font-medium ${
                typeFilter === 'all'
                  ? 'border-brand-600 bg-brand-50 text-brand-700 dark:border-vigilance-500 dark:bg-vigilance-500/15 dark:text-vigilance-300'
                  : 'border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700'
              }`}
            >
              All ({incidentsForWeek?.length ?? 0})
            </button>
          </Tooltip>
          {INCIDENT_TYPE_OPTIONS.map((type) => (
            <Tooltip key={type} text={INCIDENT_TYPE_TOOLTIPS[type]}>
              <button
                type="button"
                onClick={() => setTypeFilter(type)}
                className={`rounded-full border px-3 py-1 text-xs font-medium ${
                  typeFilter === type
                    ? 'border-brand-600 bg-brand-50 text-brand-700 dark:border-vigilance-500 dark:bg-vigilance-500/15 dark:text-vigilance-300'
                    : 'border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700'
                }`}
              >
                {TYPE_LABELS[type]} ({countsByType[type]})
              </button>
            </Tooltip>
          ))}
        </div>

        {isLoading && <Spinner />}
        {error && <ErrorBanner message={apiErrorMessage(error)} />}
        {incidents && incidents.length === 0 && (
          <EmptyState
            title="Nothing pending review"
            hint={
              typeFilter === 'all'
                ? 'Every remark-received incident has a terminal verdict.'
                : 'No incidents of this type are pending review for this selection.'
            }
          />
        )}
        {incidents && incidents.length > 0 && (
          <div className="space-y-3">
            {incidents.map((incident) => (
              <div key={incident.id} className="rounded-md border border-slate-200 dark:border-slate-700 p-3">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-medium text-slate-800 dark:text-slate-100">
                      {incident.centre_code} <span className="text-slate-500 dark:text-slate-400">-- {incident.centre_name}</span>
                    </p>
                    <p className="text-xs text-slate-500 dark:text-slate-400">
                      {formatDate(incident.incident_date)} · {TYPE_LABELS[incident.mis_final_remark] ?? incident.mis_final_remark}
                      {incident.cluster && <> · Cluster: {incident.cluster}</>}
                      {incident.center_manager && <> · {incident.center_manager}</>}
                    </p>
                    {incident.raw_remark && (
                      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Raw remark: "{incident.raw_remark}"</p>
                    )}
                  </div>
                </div>
                <TextField
                  className="mt-2"
                  placeholder="Center remarks / Vigilance notes (optional)"
                  value={remarksDraft[incident.id] ?? incident.center_remarks ?? ''}
                  onChange={(e) => setRemarksDraft((prev) => ({ ...prev, [incident.id]: e.target.value }))}
                />
                <div className="mt-2 flex flex-wrap gap-2">
                  <Tooltip text="Accepts the center's explanation as a valid exception -- this incident will NOT count toward the center's flat 6.25% penalty for this week.">
                    <button
                      disabled={reviewMutation.isPending}
                      className="rounded-md border border-green-300 bg-green-50 px-2 py-1 text-xs font-medium text-green-700 hover:bg-green-100 dark:border-green-800 dark:bg-green-500/10 dark:text-green-300 dark:hover:bg-green-500/20 disabled:opacity-50"
                      onClick={() =>
                        reviewMutation.mutate({ id: incident.id, decision: 'considered', centerRemarks: remarksDraft[incident.id] })
                      }
                    >
                      Considered
                    </button>
                  </Tooltip>
                  <Tooltip text="Rejects the center's explanation -- this incident WILL count toward the center's flat 6.25% penalty for this week, once the batch is closed.">
                    <button
                      disabled={reviewMutation.isPending}
                      className="rounded-md border border-red-300 bg-red-50 px-2 py-1 text-xs font-medium text-red-700 hover:bg-red-100 dark:border-red-800 dark:bg-red-500/10 dark:text-red-300 dark:hover:bg-red-500/20 disabled:opacity-50"
                      onClick={() =>
                        reviewMutation.mutate({ id: incident.id, decision: 'not_considered', centerRemarks: remarksDraft[incident.id] })
                      }
                    >
                      Not Considered
                    </button>
                  </Tooltip>
                  <Tooltip text='Moves this incident out of the review queue and into the "Remarks Not Received" bucket -- use this when the center never responded at all. That bucket escalates to both Cluster and Zonal Manager, harsher than a plain Not Considered.'>
                    <button
                      disabled={noRemarkMutation.isPending}
                      className="rounded-md border border-slate-200 dark:border-slate-700 px-2 py-1 text-xs font-medium text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 disabled:opacity-50"
                      onClick={() => noRemarkMutation.mutate(incident.id)}
                    >
                      Mark No Remark Received
                    </button>
                  </Tooltip>
                </div>
                <RemarksAndProofDropdown caseId={incident.case_id} />
                <NotifyCenterControl incident={incident} />
              </div>
            ))}
          </div>
        )}
      </CardBody>
    </Card>
  )
}

/** A collapsed-by-default dropdown showing the center's submitted remarks
 * + proof for this incident's case, mirroring DCB's RemarksAndProofDropdown
 * exactly. Fetches lazily, only once opened. */
function RemarksAndProofDropdown({ caseId }: { caseId: number | null }) {
  const [isOpen, setIsOpen] = useState(false)
  const { showToast } = useToast()
  const { data, isLoading, error } = useQuery({
    queryKey: ['wrc-case-responses', caseId],
    queryFn: () => getCaseResponses(caseId as number),
    enabled: isOpen && caseId != null,
  })

  const downloadMutation = useMutation({
    mutationFn: ({ responseId, filename }: { responseId: number; filename: string }) =>
      downloadCaseResponseEvidence(responseId, filename),
    onError: (err) => showToast(apiErrorMessage(err, 'Download failed'), 'error'),
  })

  if (caseId == null) return null

  return (
    <div className="mt-2">
      <button
        type="button"
        className="text-xs font-medium text-slate-500 hover:text-np-teal dark:text-vigilance-400 dark:hover:text-neon-400"
        onClick={() => setIsOpen((o) => !o)}
      >
        {isOpen ? '▲ Hide' : '▼ Show'} center remarks &amp; proof
      </button>
      {isOpen && (
        <div className="mt-1 max-w-md space-y-2 rounded-md border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-void-950 p-2">
          {isLoading && <Spinner />}
          {error && <ErrorBanner message={apiErrorMessage(error)} />}
          {data && data.length === 0 && <p className="text-xs text-slate-500 dark:text-slate-400">No remarks submitted yet.</p>}
          {data?.map((r) => (
            <div key={r.id} className="rounded border border-slate-200 dark:border-slate-700 p-2 text-xs">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium text-slate-700 dark:text-slate-200">
                  {r.responder_name} <span className="text-slate-500 dark:text-slate-400">({r.responder_npid})</span>
                </span>
                <span className="shrink-0 text-slate-500 dark:text-slate-400">{formatDate(r.submitted_at)}</span>
              </div>
              <p className="mt-1 whitespace-pre-wrap text-slate-500 dark:text-slate-400">{r.reason}</p>
              <button
                type="button"
                disabled={downloadMutation.isPending}
                className="mt-1 font-medium text-slate-500 hover:text-np-teal dark:text-vigilance-400 dark:hover:text-neon-400 disabled:opacity-50"
                onClick={() => downloadMutation.mutate({ responseId: r.id, filename: r.evidence_original_filename })}
              >
                ⬇ Download proof ({r.evidence_original_filename})
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/** Sits below an incident's decision buttons once a decision exists --
 * mirrors DCB's NotifyCenterControl, simplified to WRC's real decision
 * model (considered/not_considered only, always a fixed notice). */
function NotifyCenterControl({ incident }: { incident: WrcBillIncident }) {
  const { showToast } = useToast()
  const [lastResult, setLastResult] = useState<{ sent: boolean; reason: string | null } | null>(null)

  const notifyMutation = useMutation({
    mutationFn: () => notifyIncident(incident.id),
    onSuccess: (result) => {
      setLastResult(result)
      showToast(result.sent ? 'Center notified by email' : (result.reason ?? 'Could not send that email'), result.sent ? undefined : 'error')
    },
    onError: (err) => showToast(apiErrorMessage(err, 'Could not send that email'), 'error'),
  })

  if (!incident.considered) return null

  return (
    <div className="mt-2 flex items-center gap-2">
      <Tooltip text="Emails the center to let them know this incident's decision has been recorded -- purely informational, doesn't change the decision itself.">
        <button
          type="button"
          disabled={notifyMutation.isPending}
          className="rounded-md border border-np-teal/40 px-2 py-1 text-xs font-medium text-np-teal hover:bg-np-teal/10 dark:border-vigilance-700 dark:text-vigilance-400 dark:hover:bg-vigilance-900/40 disabled:opacity-40"
          onClick={() => notifyMutation.mutate()}
        >
          ✉ Notify Center
        </button>
      </Tooltip>
      {lastResult && (
        <span className={`text-xs ${lastResult.sent ? 'text-np-teal dark:text-neon-400' : 'text-amber-700 dark:text-amber-400'}`}>
          {lastResult.sent ? 'Sent' : lastResult.reason}
        </span>
      )}
    </div>
  )
}

const WRC_AUTO_BUCKET_LABELS: Record<AutoValidationBucket, string> = {
  considered: 'Considered',
  not_considered: 'Not Considered',
  manual_check: 'Manual Check',
}

const WRC_AUTO_BUCKET_TOOLTIPS: Record<AutoValidationBucket, string> = {
  considered: 'Remarks the rules matched to a "considered" category, with the keyword that matched -- shown here as a suggestion only. Vigilance still confirms the real decision in the Review Queue.',
  not_considered: 'Remarks the rules matched to a "not considered" category, with the reason that would be given to the center -- advisory only, nothing is sent or finalized automatically.',
  manual_check: 'Remarks that matched no rule, or matched conflicting rules on both sides -- these need a human read before you decide.',
}

/** Every incident tied to one case, with the same considered/not-considered
 * buttons the Review Queue uses -- mirrors DcbBillsToReverify in
 * DelayedCashBillingPage.tsx exactly, adapted for WRC's 2-decision model
 * (no needs_more_detail/needs_proof stage here). */
function WrcIncidentsToReverify({ caseId }: { caseId: number }) {
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const { data: incidents, isLoading, error } = useQuery({
    queryKey: ['wrc-incidents-for-case', caseId],
    queryFn: () => getCaseIncidents(caseId),
  })

  const reviewMutation = useMutation({
    mutationFn: ({ id, decision }: { id: number; decision: 'considered' | 'not_considered' }) =>
      reviewBillIncident(id, decision),
    onSuccess: (_result, { decision }) => {
      queryClient.invalidateQueries({ queryKey: ['wrc-incidents-for-case', caseId] })
      queryClient.invalidateQueries({ queryKey: ['wrc-review-queue'] })
      queryClient.invalidateQueries({ queryKey: ['wrc-action-taken'] })
      showToast(`Marked "${decision.replace(/_/g, ' ')}"`)
    },
    onError: (err) => showToast(apiErrorMessage(err, 'Could not save that decision'), 'error'),
  })

  return (
    <div className="mt-2 rounded-md border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-void-950 p-2">
      {isLoading && <Spinner />}
      {error && <ErrorBanner message={apiErrorMessage(error)} />}
      {incidents && incidents.length === 0 && <p className="text-xs text-slate-500 dark:text-slate-400">No incidents found for this case.</p>}
      {incidents && incidents.length > 0 && (
        <div className="space-y-2">
          {incidents.map((incident) => (
            <div key={incident.id} className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 dark:border-slate-700 pb-2 text-xs last:border-0 last:pb-0">
              <div>
                <span className="font-medium text-slate-700 dark:text-slate-200">{formatDate(incident.incident_date)}</span>{' '}
                <span className="text-slate-500 dark:text-slate-400">{TYPE_LABELS[incident.mis_final_remark] ?? incident.mis_final_remark}</span>
                {incident.considered && (
                  <span className="ml-2">
                    <Badge tone="status">{incident.considered}</Badge>
                  </span>
                )}
              </div>
              <div className="flex flex-wrap gap-1">
                <button
                  disabled={reviewMutation.isPending}
                  className="rounded-md border border-slate-200 dark:border-slate-700 px-2 py-1 font-medium text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 disabled:opacity-50"
                  onClick={() => reviewMutation.mutate({ id: incident.id, decision: 'considered' })}
                >
                  Considered
                </button>
                <button
                  disabled={reviewMutation.isPending}
                  className="rounded-md border border-slate-200 dark:border-slate-700 px-2 py-1 font-medium text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 disabled:opacity-50"
                  onClick={() => reviewMutation.mutate({ id: incident.id, decision: 'not_considered' })}
                >
                  Not Considered
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function WrcAutoValidationOverrideControl({ response }: { response: AutoValidationResponse }) {
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [isOpen, setIsOpen] = useState(false)
  const [note, setNote] = useState('')

  const overrideMutation = useMutation({
    mutationFn: (bucket: AutoValidationBucket) => overrideWrcResponse(response.id, bucket, note || undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['wrc-auto-validation'] })
      showToast('Override saved')
      setIsOpen(false)
      setNote('')
    },
    onError: (err) => showToast(apiErrorMessage(err, 'Could not save override'), 'error'),
  })

  return (
    <div className="mt-1">
      <Tooltip text="Lets you set the bucket yourself instead of the auto-validation result -- the original auto result is kept for reporting, and your override is recorded with your name and an optional note.">
        <button
          type="button"
          className="text-xs font-medium text-slate-500 hover:text-np-teal dark:text-vigilance-400 dark:hover:text-neon-400"
          onClick={() => setIsOpen((o) => !o)}
        >
          {isOpen ? '▲ Hide override' : '✎ Override'}
        </button>
      </Tooltip>
      {isOpen && (
        <div className="mt-1 max-w-xs space-y-1">
          <textarea
            className="w-full rounded-md border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-void-950 px-2 py-1 text-xs text-slate-700 dark:text-slate-200"
            rows={2}
            placeholder="Why are you overriding the auto-validation result? (optional)"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <div className="flex gap-1">
            {(['considered', 'not_considered', 'manual_check'] as AutoValidationBucket[]).map((bucket) => (
              <Tooltip key={bucket} text={`Sets this response's official bucket to "${WRC_AUTO_BUCKET_LABELS[bucket]}".`}>
                <button
                  disabled={overrideMutation.isPending}
                  className="rounded-md border border-slate-200 dark:border-slate-700 px-2 py-1 text-xs font-medium text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 disabled:opacity-50"
                  onClick={() => overrideMutation.mutate(bucket)}
                >
                  {WRC_AUTO_BUCKET_LABELS[bucket]}
                </button>
              </Tooltip>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function WrcAutoValidationTab() {
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [bucketFilter, setBucketFilter] = useState<AutoValidationBucket | 'all'>('all')
  const [expandedId, setExpandedId] = useState<number | null>(null)

  const { data: responses, isLoading, error } = useQuery({
    queryKey: ['wrc-auto-validation'],
    queryFn: () => listWrcAutoValidation(),
  })

  const filtered = responses?.filter((r) => bucketFilter === 'all' || r.effective_bucket === bucketFilter)

  const countsByBucket = (['considered', 'not_considered', 'manual_check'] as AutoValidationBucket[]).reduce(
    (acc, bucket) => {
      acc[bucket] = responses?.filter((r) => r.effective_bucket === bucket).length ?? 0
      return acc
    },
    {} as Record<AutoValidationBucket, number>,
  )

  const reevaluateAllMutation = useMutation({
    mutationFn: () => reevaluateAllWrc(),
    onSuccess: (results) => {
      queryClient.invalidateQueries({ queryKey: ['wrc-auto-validation'] })
      showToast(`Re-ran auto-validation on ${results.length} response(s)`)
    },
    onError: (err) => showToast(apiErrorMessage(err, 'Could not re-run auto-validation'), 'error'),
  })

  const reevaluateOneMutation = useMutation({
    mutationFn: (responseId: number) => reevaluateWrcResponse(responseId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['wrc-auto-validation'] })
      showToast('Re-evaluated')
    },
    onError: (err) => showToast(apiErrorMessage(err, 'Could not re-evaluate'), 'error'),
  })

  const exportMutation = useMutation({
    mutationFn: () => downloadAutoValidationExport(),
    onError: (err) => showToast(apiErrorMessage(err, 'Export failed'), 'error'),
  })

  return (
    <Card>
      <CardHeader
        title="Auto Validation"
        actions={
          <div className="flex gap-2">
            <Tooltip text="Downloads an Excel workbook of every auto-validated remark for both DCB and WRC -- a raw list plus center/zone/cluster rollups, with a repeat-instance count for recurring excuses.">
              <Button variant="secondary" isLoading={exportMutation.isPending} onClick={() => exportMutation.mutate()}>
                Download Report (DCB + WRC)
              </Button>
            </Tooltip>
            <Tooltip text="Re-evaluates every response that hasn't been manually overridden, against the current Auto Validation Rules -- use this after you add or edit a rule so past submissions reflect it too.">
              <Button
                variant="secondary"
                isLoading={reevaluateAllMutation.isPending}
                onClick={() => reevaluateAllMutation.mutate()}
              >
                Re-run All
              </Button>
            </Tooltip>
          </div>
        }
      />
      <CardBody>
        <p className="mb-4 text-xs text-slate-500 dark:text-slate-400">
          Every submitted remark is matched against the keyword rules under Auto Validation Rules -- Considered /
          Not Considered / Manual Check. This is advisory only: it never sets the incident's real decision or
          changes the penalty. Use the buttons below to reverify and confirm the actual decision in the Review
          Queue.
        </p>
        <div className="mb-4 flex flex-wrap gap-2">
          <Tooltip text="Every response that has been auto-validated so far, in any bucket.">
            <button
              type="button"
              onClick={() => setBucketFilter('all')}
              className={`rounded-full border px-3 py-1 text-xs font-medium ${
                bucketFilter === 'all'
                  ? 'border-brand-600 bg-brand-50 text-brand-700 dark:border-vigilance-500 dark:bg-vigilance-500/15 dark:text-vigilance-300'
                  : 'border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700'
              }`}
            >
              All ({responses?.length ?? 0})
            </button>
          </Tooltip>
          {(['considered', 'not_considered', 'manual_check'] as AutoValidationBucket[]).map((bucket) => (
            <Tooltip key={bucket} text={WRC_AUTO_BUCKET_TOOLTIPS[bucket]}>
              <button
                type="button"
                onClick={() => setBucketFilter(bucket)}
                className={`rounded-full border px-3 py-1 text-xs font-medium ${
                  bucketFilter === bucket
                    ? 'border-brand-600 bg-brand-50 text-brand-700 dark:border-vigilance-500 dark:bg-vigilance-500/15 dark:text-vigilance-300'
                    : 'border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700'
                }`}
              >
                {WRC_AUTO_BUCKET_LABELS[bucket]} ({countsByBucket[bucket]})
              </button>
            </Tooltip>
          ))}
        </div>

        {isLoading && <Spinner />}
        {error && <ErrorBanner message={apiErrorMessage(error)} />}
        {filtered && filtered.length === 0 && (
          <EmptyState title="Nothing auto-validated yet" hint="This fills in as centers submit responses through the portal." />
        )}
        {filtered && filtered.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase text-slate-500 dark:text-slate-400">
                <tr>
                  <th className="py-2 pr-4">Center</th>
                  <th className="py-2 pr-4">Remark</th>
                  <th className="py-2 pr-4">Category</th>
                  <th className="py-2 pr-4">Decision</th>
                  <th className="py-2 pr-4">Submitted</th>
                  <th className="py-2 pr-4">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
                {filtered.map((r) => (
                  <tr key={r.id}>
                    <td className="py-2 pr-4">
                      {r.centre_code}
                      <div className="text-xs text-slate-500 dark:text-slate-400">{r.centre_name}</div>
                    </td>
                    <td className="max-w-xs py-2 pr-4 text-xs text-slate-600 dark:text-slate-300">{r.reason}</td>
                    <td className="py-2 pr-4 text-xs">
                      {r.auto_category ?? <span className="text-slate-500 dark:text-slate-400">(no rule matched)</span>}
                      {r.auto_matched_keyword && (
                        <div className="text-slate-500 dark:text-slate-400">matched "{r.auto_matched_keyword}"</div>
                      )}
                    </td>
                    <td className="py-2 pr-4">
                      {r.effective_bucket && <Badge tone="status">{r.effective_bucket}</Badge>}
                      {r.admin_override_bucket && (
                        <div className="mt-1 text-xs text-amber-700 dark:text-amber-400">
                          overridden from {r.auto_bucket} by {r.admin_override_by_name}
                        </div>
                      )}
                      {r.auto_reason && !r.admin_override_bucket && (
                        <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">{r.auto_reason}</div>
                      )}
                    </td>
                    <td className="py-2 pr-4 text-xs text-slate-500 dark:text-slate-400">{formatDate(r.submitted_at)}</td>
                    <td className="py-2 pr-4">
                      <div className="flex flex-wrap gap-2">
                        <Tooltip text="Opens every incident this response covers, right here, with the real Considered/Not Considered buttons -- so you can confirm the actual decision without leaving this tab.">
                          <button
                            type="button"
                            className="text-xs font-medium text-slate-500 hover:text-np-teal dark:text-vigilance-400 dark:hover:text-neon-400"
                            onClick={() => setExpandedId(expandedId === r.id ? null : r.id)}
                          >
                            {expandedId === r.id ? '▲ Hide' : '▼ Reverify'} incidents
                          </button>
                        </Tooltip>
                        <Tooltip text="Re-evaluates just this one response against the current Auto Validation Rules -- useful right after you edit a rule.">
                          <button
                            type="button"
                            disabled={reevaluateOneMutation.isPending}
                            className="text-xs font-medium text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200 disabled:opacity-50"
                            onClick={() => reevaluateOneMutation.mutate(r.id)}
                          >
                            Re-run
                          </button>
                        </Tooltip>
                      </div>
                      <WrcAutoValidationOverrideControl response={r} />
                      {expandedId === r.id && <WrcIncidentsToReverify caseId={r.case_or_penalty_id} />}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardBody>
    </Card>
  )
}

function ActionTakenTab() {
  const [searchParams] = useSearchParams()
  const batchParam = searchParams.get('batch')
  const decisionParam = searchParams.get('decision')
  const [weekFilter, setWeekFilter] = useState<number | 'all'>(batchParam ? Number(batchParam) : 'all')
  const [decisionFilter, setDecisionFilter] = useState<'all' | 'considered' | 'not_considered'>(
    decisionParam === 'considered' || decisionParam === 'not_considered' ? decisionParam : 'all',
  )
  const [centerFilter, setCenterFilter] = useState<string | 'all'>('all')

  const queryClient = useQueryClient()
  const { showToast } = useToast()

  const { data: batches } = useQuery({ queryKey: ['wrc-batches'], queryFn: listBatches })
  const { data: incidentsForWeek, isLoading, error } = useQuery({
    queryKey: ['wrc-action-taken', weekFilter],
    queryFn: () => getActionTaken(weekFilter === 'all' ? undefined : weekFilter),
  })

  const revokeMutation = useMutation({
    mutationFn: (incidentId: number) => revokeBillIncidentReview(incidentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['wrc-action-taken'] })
      queryClient.invalidateQueries({ queryKey: ['wrc-review-queue'] })
      showToast('Decision revoked -- back in the Review Queue')
    },
    onError: (err) => showToast(apiErrorMessage(err, 'Could not revoke this decision'), 'error'),
  })

  const incidents = incidentsForWeek
    ?.filter((i) => decisionFilter === 'all' || i.considered === decisionFilter)
    .filter((i) => centerFilter === 'all' || i.centre_code === centerFilter)

  return (
    <Card>
      <CardHeader
        title="Decisions Already Made"
        actions={
          <div className="flex flex-wrap gap-2">
            <Select
              className="w-56 text-sm"
              value={weekFilter === 'all' ? 'all' : String(weekFilter)}
              onChange={(e) => setWeekFilter(e.target.value === 'all' ? 'all' : Number(e.target.value))}
            >
              <option value="all">All weeks</option>
              {batches?.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.week_label}
                </option>
              ))}
            </Select>
            <CenterFilterSelect items={incidentsForWeek ?? []} value={centerFilter} onChange={setCenterFilter} />
          </div>
        }
      />
      <CardBody>
        <div className="mb-4 flex flex-wrap gap-2">
          {(['all', 'considered', 'not_considered'] as const).map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => setDecisionFilter(d)}
              className={`rounded-full border px-3 py-1 text-xs font-medium ${
                decisionFilter === d
                  ? 'border-brand-600 bg-brand-50 text-brand-700 dark:border-vigilance-500 dark:bg-vigilance-500/15 dark:text-vigilance-300'
                  : 'border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700'
              }`}
            >
              {d === 'all' ? 'All' : d === 'considered' ? 'Considered' : 'Not Considered'} (
              {d === 'all'
                ? incidentsForWeek?.length ?? 0
                : incidentsForWeek?.filter((i) => i.considered === d).length ?? 0}
              )
            </button>
          ))}
        </div>

        {isLoading && <Spinner />}
        {error && <ErrorBanner message={apiErrorMessage(error)} />}
        {incidents && incidents.length === 0 && (
          <EmptyState title="No decisions yet" hint="Considered/Not Considered verdicts will show up here as you review incidents." />
        )}
        {incidents && incidents.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase text-slate-500 dark:text-slate-400">
                <tr>
                  <th className="py-2 pr-4">Center</th>
                  <th className="py-2 pr-4">Incident</th>
                  <th className="py-2 pr-4">Decision</th>
                  <th className="py-2 pr-4">Decided</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
                {incidents.map((incident) => (
                  <tr key={incident.id}>
                    <td className="py-2 pr-4">
                      {incident.centre_code}
                      <div className="text-xs text-slate-500 dark:text-slate-400">{incident.centre_name}</div>
                    </td>
                    <td className="py-2 pr-4">
                      {formatDate(incident.incident_date)} · {TYPE_LABELS[incident.mis_final_remark] ?? incident.mis_final_remark}
                    </td>
                    <td className="py-2 pr-4">
                      {incident.considered && <Badge tone="status">{incident.considered}</Badge>}
                      {incident.reviewed_at && (
                        <Tooltip text="Undoes this decision if it was clicked by mistake -- moves the incident back into the Review Queue with no verdict, so you can decide again. Doesn't touch the incident's data, only the decision.">
                          <button
                            type="button"
                            className="ml-2 text-xs font-medium text-red-600 hover:text-red-700 disabled:opacity-50 dark:text-neon-pink-400 dark:hover:text-neon-pink-300"
                            disabled={revokeMutation.isPending}
                            onClick={() => revokeMutation.mutate(incident.id)}
                          >
                            Revoke
                          </button>
                        </Tooltip>
                      )}
                      <RemarksAndProofDropdown caseId={incident.case_id} />
                      <NotifyCenterControl incident={incident} />
                    </td>
                    <td className="py-2 pr-4 text-xs text-slate-500 dark:text-slate-400">
                      {incident.reviewed_at ? formatDate(incident.reviewed_at) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardBody>
    </Card>
  )
}

function CentersActivityTab() {
  const { data: activity, isLoading, error } = useQuery({
    queryKey: ['wrc-centers-activity'],
    queryFn: () => getCentersActivity(),
  })

  return (
    <Card>
      <CardHeader title="Centers Activity" />
      <CardBody>
        {isLoading && <Spinner />}
        {error && <ErrorBanner message={apiErrorMessage(error)} />}
        {activity && activity.length === 0 && (
          <EmptyState title="No activity yet" hint="Every time a center opens or submits through the public portal, it shows up here." />
        )}
        {activity && activity.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase text-slate-500 dark:text-slate-400">
                <tr>
                  <th className="py-2 pr-4">Center</th>
                  <th className="py-2 pr-4">Event</th>
                  <th className="py-2 pr-4">When</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
                {activity.map((a) => (
                  <tr key={a.id}>
                    <td className="py-2 pr-4">
                      {a.centre_code}
                      {a.centre_name && <div className="text-xs text-slate-500 dark:text-slate-400">{a.centre_name}</div>}
                    </td>
                    <td className="py-2 pr-4">
                      <Badge tone="status">{a.event_type}</Badge>
                    </td>
                    <td className="py-2 pr-4 text-xs text-slate-500 dark:text-slate-400">{new Date(a.occurred_at).toLocaleString('en-IN')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardBody>
    </Card>
  )
}

function WrcContactChangeNotificationsTab() {
  const queryClient = useQueryClient()
  const { showToast } = useToast()

  const { data: requests, isLoading, error } = useQuery({
    queryKey: ['wrc-contact-change-requests'],
    queryFn: () => listContactChangeRequests('pending'),
  })

  const approveMutation = useMutation({
    mutationFn: (id: number) => approveContactChangeRequest(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['wrc-contact-change-requests'] })
      showToast('Approved -- Org Master updated')
    },
    onError: (err) => showToast(apiErrorMessage(err, 'Could not approve'), 'error'),
  })

  const rejectMutation = useMutation({
    mutationFn: (id: number) => rejectContactChangeRequest(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['wrc-contact-change-requests'] })
      showToast('Rejected -- no change made')
    },
    onError: (err) => showToast(apiErrorMessage(err, 'Could not reject'), 'error'),
  })

  return (
    <Card>
      <CardHeader title="Pending Center Manager Contact Changes" />
      <CardBody>
        <p className="mb-4 text-xs text-slate-500 dark:text-slate-400">
          Shared across Delayed Cash Billing and Weekly Revenue Closure -- a center manager's name/NPID/email from
          any response submission is never written to the Org Master automatically -- approve here to apply it,
          or reject to leave the record unchanged.
        </p>
        {isLoading && <Spinner />}
        {error && <ErrorBanner message={apiErrorMessage(error)} />}
        {requests && requests.length === 0 && <EmptyState title="No pending contact changes" />}
        {requests && requests.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase text-slate-500 dark:text-slate-400">
                <tr>
                  <th className="py-2 pr-4">Center Code</th>
                  <th className="py-2 pr-4">Proposed Name</th>
                  <th className="py-2 pr-4">Proposed NPID</th>
                  <th className="py-2 pr-4">Proposed Email</th>
                  <th className="py-2 pr-4">Source</th>
                  <th className="py-2 pr-4">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
                {requests.map((r: ContactChangeRequest) => (
                  <tr key={r.id}>
                    <td className="py-2 pr-4">
                      {r.centre_code_hint}
                      {r.org_node_id == null && (
                        <div className="text-xs text-red-600">No matching center in Org Hierarchy</div>
                      )}
                    </td>
                    <td className="py-2 pr-4">{r.proposed_manager_name ?? '—'}</td>
                    <td className="py-2 pr-4">{r.proposed_manager_npid ?? '—'}</td>
                    <td className="py-2 pr-4">{r.proposed_manager_email ?? '—'}</td>
                    <td className="py-2 pr-4 text-xs text-slate-500 dark:text-slate-400">{r.source}</td>
                    <td className="py-2 pr-4">
                      <div className="flex gap-2">
                        <button
                          disabled={approveMutation.isPending || r.org_node_id == null}
                          className="text-xs font-medium text-brand-600 hover:text-brand-700 dark:text-neon-400 dark:hover:text-neon-300 disabled:opacity-50"
                          onClick={() => approveMutation.mutate(r.id)}
                          title={r.org_node_id == null ? 'Fix the center in Org Hierarchy first' : undefined}
                        >
                          Approve
                        </button>
                        <button
                          disabled={rejectMutation.isPending}
                          className="text-xs font-medium text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200 disabled:opacity-50"
                          onClick={() => rejectMutation.mutate(r.id)}
                        >
                          Reject
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardBody>
    </Card>
  )
}

function PublishResultModal({
  result,
  onClose,
  mode = 'published',
}: {
  result: WrcBatchPublishResult
  onClose: () => void
  mode?: 'published' | 'view'
}) {
  const { showToast } = useToast()
  const singleLinkUrl = `${window.location.origin}/respond/weekly-revenue`

  function copy(url: string) {
    navigator.clipboard.writeText(url).then(() => showToast('Link copied'))
  }

  return (
    <Modal
      title={mode === 'view' ? `Batch #${result.batch_id} -- Response Links` : `Batch #${result.batch_id} -- Published Response Links`}
      onClose={onClose}
      wide
    >
      <div className="space-y-4">
        {result.links.length === 0 ? (
          <EmptyState
            title="No links published yet"
            hint="Use Publish links on this batch first -- once minted, they'll appear here to view and copy without re-publishing."
          />
        ) : (
          <>
            <div className="rounded-md border border-brand-200 bg-brand-50 p-3 dark:border-vigilance-600/30 dark:bg-vigilance-500/5">
              <p className="text-xs font-semibold uppercase tracking-wide text-brand-600 dark:text-vigilance-400">
                One link for every center
              </p>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                Send this single URL in one email to everyone -- each center manager picks their own center from a
                dropdown when they open it, and can only respond for that center.
              </p>
              <div className="mt-2 flex items-center gap-2">
                <code className="flex-1 truncate rounded border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-void-950 px-2 py-1.5 text-xs text-slate-600 dark:text-slate-300">
                  {singleLinkUrl}
                </code>
                <Button type="button" variant="secondary" onClick={() => copy(singleLinkUrl)}>
                  Copy
                </Button>
              </div>
            </div>

            <p className="text-xs text-slate-500 dark:text-slate-400">
              {mode === 'view'
                ? "Viewing the links already published for this batch -- these are read-only, so nothing was re-minted or invalidated by opening this. Use \"Publish links\" instead if you need fresh tokens."
                : 'Individual per-center links (still work if you prefer sending separately). Publishing again always mints fresh tokens, invalidating these links.'}
            </p>
            <div className="max-h-96 overflow-y-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs uppercase text-slate-500 dark:text-slate-400">
                  <tr>
                    <th className="py-2 pr-4">Center</th>
                    <th className="py-2 pr-4">Response Link</th>
                    <th className="py-2 pr-4"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
                  {result.links.map((link) => (
                    <tr key={link.case_id}>
                      <td className="py-2 pr-4">
                        {link.centre_code}
                        <div className="text-xs text-slate-500 dark:text-slate-400">{link.centre_name}</div>
                      </td>
                      <td className="max-w-xs truncate py-2 pr-4 text-xs text-slate-500 dark:text-slate-400">{link.response_url}</td>
                      <td className="py-2 pr-4">
                        <button className="text-xs font-medium text-np-calming-blue hover:text-np-deep-blue dark:text-neon-blue-400 dark:hover:text-neon-blue-300" onClick={() => copy(link.response_url)}>
                          Copy
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
        <div className="flex justify-end">
          <Button type="button" variant="secondary" onClick={onClose}>
            Done
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function UploadBatchModal({
  onClose,
  onUploaded,
}: {
  onClose: () => void
  onUploaded: (result: WrcUploadResult) => void
}) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [periodStart, setPeriodStart] = useState('')
  const [periodEnd, setPeriodEnd] = useState('')
  const [weekLabel, setWeekLabel] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<WrcUploadResult | null>(null)
  const { showToast } = useToast()

  const mutation = useMutation({
    mutationFn: (file: File) => uploadBatch(file, periodStart, periodEnd, weekLabel),
    onSuccess: (uploadResult) => {
      setResult(uploadResult)
      onUploaded(uploadResult)
    },
    onError: (err) => setError(apiErrorMessage(err, 'Upload failed')),
  })

  const activateRuleMutation = useMutation({
    mutationFn: () => activateDefaultRule(),
    onSuccess: () => {
      setError(null)
      showToast('Default rule activated -- try uploading again')
    },
    onError: (err) => setError(apiErrorMessage(err, 'Could not activate the default rule')),
  })

  const needsRule = !!error && error.toLowerCase().includes('no approved')

  function handleSubmit() {
    setError(null)
    if (!periodStart || !periodEnd || !weekLabel.trim()) {
      setError('Choose a period start, period end, and week label (e.g. "Week 2")')
      return
    }
    const file = fileInputRef.current?.files?.[0]
    if (!file) {
      setError('Choose the closure pending list workbook first')
      return
    }
    mutation.mutate(file)
  }

  return (
    <Modal title="Upload Weekly Closure Pending List" onClose={onClose} wide>
      <div className="space-y-4">
        {error && (
          <div className="space-y-2">
            <ErrorBanner message={error} />
            {needsRule && (
              <Button
                type="button"
                variant="secondary"
                isLoading={activateRuleMutation.isPending}
                onClick={() => activateRuleMutation.mutate()}
              >
                Activate default rule (6.25% flat penalty)
              </Button>
            )}
          </div>
        )}
        {!result && (
          <>
            <div className="grid grid-cols-3 gap-3">
              <TextField id="wrc-period-start" label="Period start" type="date" value={periodStart} onChange={(e) => setPeriodStart(e.target.value)} />
              <TextField id="wrc-period-end" label="Period end" type="date" value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} />
              <TextField id="wrc-week-label" label="Week label" placeholder="e.g. Week 2" value={weekLabel} onChange={(e) => setWeekLabel(e.target.value)} />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-500 dark:text-slate-400">Closure pending list workbook (.xlsx)</label>
              <input ref={fileInputRef} type="file" accept=".xlsx,.xlsm" className="block w-full text-sm" />
            </div>
          </>
        )}

        {result && (
          <div className="rounded-md border border-emerald-300 bg-emerald-50 p-3 dark:border-emerald-800 dark:bg-emerald-500/10">
            <p className="text-sm text-emerald-800 dark:text-emerald-200">
              <span className="font-semibold">{result.incidents_ingested}</span> incident(s) ingested for{' '}
              <span className="font-semibold">{result.batch.week_label}</span>.
            </p>
            <p className="mt-1 text-xs text-emerald-700 dark:text-emerald-300">
              {result.excess_billed_row_count} "Excess billed" row(s) counted but out of scope for penalty.
              {result.out_of_period_row_count > 0 && (
                <>
                  {' '}
                  {result.out_of_period_row_count} row(s) fell outside this batch's own dates and were ignored --
                  already covered by a prior week's upload.
                </>
              )}
            </p>
          </div>
        )}

        {result && result.skipped_rows.length > 0 && (
          <div className="rounded-md border border-amber-300 bg-amber-50 p-3 dark:border-amber-800 dark:bg-amber-500/10">
            <p className="mb-2 text-xs font-semibold text-amber-700 dark:text-amber-300">
              {result.skipped_rows.length} row(s) skipped -- never silently dropped, review below:
            </p>
            <div className="max-h-40 overflow-y-auto">
              <table className="w-full text-left text-xs">
                <thead className="text-amber-700 dark:text-amber-300">
                  <tr>
                    <th className="pr-3">Row</th>
                    <th>Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {result.skipped_rows.map((row) => (
                    <tr key={row.row_number}>
                      <td className="pr-3">{row.row_number}</td>
                      <td>{row.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            {result ? 'Done' : 'Cancel'}
          </Button>
          {!result && (
            <Button type="button" isLoading={mutation.isPending} onClick={handleSubmit}>
              Upload
            </Button>
          )}
        </div>
      </div>
    </Modal>
  )
}
