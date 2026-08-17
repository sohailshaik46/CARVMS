import { useRef, useState } from 'react'
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
  getBatchSummary,
  getCaseResponses,
  getCentersActivity,
  getReviewQueue,
  listBatches,
  listCenterPenalties,
  listRolePenalties,
  markNoRemarkReceived,
  notifyIncident,
  publishLinksForBatch,
  reviewBillIncident,
  uploadBatch,
} from '../lib/resources/weeklyRevenueClosure'
import type {
  ContactChangeRequest,
  WeeklyRevenueClosureBatch,
  WrcBatchPublishResult,
  WrcBillIncident,
  WrcIncidentType,
  WrcUploadResult,
} from '../lib/types'

type Tab = 'batches' | 'review-queue' | 'action-taken' | 'centers-activity' | 'notifications'
const TAB_VALUES: Tab[] = ['batches', 'review-queue', 'action-taken', 'centers-activity', 'notifications']

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
  const [isUploadOpen, setIsUploadOpen] = useState(false)
  const [selectedBatchId, setSelectedBatchId] = useState<number | null>(null)
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

      <div className="flex gap-1 border-b border-slate-800">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`relative px-3 py-2 text-sm font-medium ${
              tab === t.key
                ? 'border-b-2 border-brand-600 text-brand-300'
                : 'text-slate-500 hover:text-slate-200'
            }`}
          >
            {t.label}
            {t.key === 'notifications' && !!pendingContactChanges?.length && (
              <span className="ml-1.5 inline-flex min-w-[1.25rem] items-center justify-center rounded-full bg-neon-500 px-1.5 py-0.5 text-[10px] font-semibold text-void-950">
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
                    <thead className="text-xs uppercase text-slate-500">
                      <tr>
                        <th className="py-2 pr-4">Week</th>
                        <th className="py-2 pr-4">Period</th>
                        <th className="py-2 pr-4">Status</th>
                        <th className="py-2 pr-4">Created</th>
                        <th className="py-2 pr-4">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800">
                      {batches.map((batch) => (
                        <tr key={batch.id} className="hover:bg-slate-800">
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
                              <button
                                className="text-xs font-medium text-brand-600 hover:text-brand-400"
                                onClick={() => setSelectedBatchId(batch.id)}
                              >
                                View dashboard
                              </button>
                              <button
                                className="text-xs font-medium text-vigilance-400 hover:text-neon-400"
                                disabled={publishMutation.isPending}
                                onClick={() => publishMutation.mutate(batch.id)}
                              >
                                Publish links
                              </button>
                              <button
                                className="text-xs font-medium text-red-500 hover:text-red-400"
                                onClick={() => setBatchToDelete(batch)}
                              >
                                Delete
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

          {selectedBatchId != null && (
            <BatchDashboard batchId={selectedBatchId} onClose={() => setSelectedBatchId(null)} />
          )}
        </>
      )}

      {tab === 'review-queue' && <ReviewQueueTab />}
      {tab === 'action-taken' && <ActionTakenTab />}
      {tab === 'centers-activity' && <CentersActivityTab />}
      {tab === 'notifications' && <WrcContactChangeNotificationsTab />}

      {publishResult && <PublishResultModal result={publishResult} onClose={() => setPublishResult(null)} />}

      {batchToDelete && (
        <Modal title="Delete this batch?" onClose={() => setBatchToDelete(null)}>
          <div className="space-y-4">
            <p className="text-sm text-slate-300">
              This permanently deletes <span className="font-medium text-slate-100">{batchToDelete.week_label}</span>{' '}
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
            queryClient.invalidateQueries({ queryKey: ['wrc-batches'] })
            setIsUploadOpen(false)
            setSelectedBatchId(result.batch.id)
            if (result.skipped_rows.length > 0) {
              showToast(`Uploaded with ${result.skipped_rows.length} row(s) skipped -- see the report below`, 'error')
            } else {
              showToast(
                `Ingested ${result.incidents_ingested} incident(s); ${result.excess_billed_row_count} Excess billed row(s) counted (out of scope for penalty)`,
              )
            }
          }}
        />
      )}
    </div>
  )
}

function BatchDashboard({ batchId, onClose }: { batchId: number; onClose: () => void }) {
  const queryClient = useQueryClient()
  const { showToast } = useToast()

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
          <div className="flex gap-2">
            <Button variant="secondary" isLoading={exportMutation.isPending} onClick={() => exportMutation.mutate()}>
              Export Workbook
            </Button>
            <Button isLoading={closeMutation.isPending} onClick={() => closeMutation.mutate()}>
              {summary?.batch.status === 'closed' ? 'Recompute (close again)' : 'Close Batch'}
            </Button>
            <button onClick={onClose} className="text-xs font-medium text-slate-500 hover:text-slate-200">
              Close panel
            </button>
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
                value={<span className="inline-flex items-center gap-2"><ReceiptIcon className="h-5 w-5 text-vigilance-400" />{summary.total_incidents}</span>}
              />
              <KpiCard label="Pending Review" value={summary.pending_review_count} hint="Awaiting Vigilance verdict" />
              <KpiCard label="Considered" value={summary.considered_count} hint="Accepted exception -- no penalty" />
              <KpiCard label="Not Considered" value={summary.not_considered_count} hint="Feeds the flat penalty" />
              <KpiCard label="No-Remark Centers" value={summary.no_remark_center_count} hint="Never responded" />
              <KpiCard
                label="Centers Penalized"
                value={<span className="inline-flex items-center gap-2"><UsersIcon className="h-5 w-5 text-vigilance-400" />{summary.centers_penalized}</span>}
              />
              <KpiCard
                label="Total Center Penalty Rate"
                value={<span className="inline-flex items-center gap-2"><ChartIcon className="h-5 w-5 text-vigilance-400" />{formatPct(summary.total_center_penalty_rate)}</span>}
                hint="Sum of flat 6.25% rates, not a rupee amount"
              />
              <KpiCard
                label="Total Role Escalation Rate"
                value={<span className="inline-flex items-center gap-2"><TrophyIcon className="h-5 w-5 text-vigilance-400" />{formatPct(summary.total_role_penalty_rate)}</span>}
                hint="Cluster/Zonal Manager escalation, summed"
              />
            </div>

            <div>
              <h4 className="mb-2 text-sm font-semibold text-slate-200">Center Penalties</h4>
              {centerPenalties && centerPenalties.length === 0 && (
                <p className="text-xs text-slate-500">
                  None yet -- close the batch to compute penalties from reviewed incidents.
                </p>
              )}
              {centerPenalties && centerPenalties.length > 0 && (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="text-xs uppercase text-slate-500">
                      <tr>
                        <th className="py-2 pr-4">Center</th>
                        <th className="py-2 pr-4">Center Manager</th>
                        <th className="py-2 pr-4">Not Considered</th>
                        <th className="py-2 pr-4">No Remark</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800">
                      {centerPenalties.map((cp) => (
                        <tr key={cp.id}>
                          <td className="py-2 pr-4">
                            {cp.centre_code}
                            <div className="text-xs text-slate-500">{cp.centre_name}</div>
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
              <h4 className="mb-2 text-sm font-semibold text-slate-200">Cluster / Zonal Manager Escalation</h4>
              {rolePenalties && rolePenalties.length === 0 && (
                <p className="text-xs text-slate-500">None yet -- close the batch to compute escalations.</p>
              )}
              {rolePenalties && rolePenalties.length > 0 && (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="text-xs uppercase text-slate-500">
                      <tr>
                        <th className="py-2 pr-4">Role</th>
                        <th className="py-2 pr-4">Name</th>
                        <th className="py-2 pr-4">Section</th>
                        <th className="py-2 pr-4">Distinct Centers</th>
                        <th className="py-2 pr-4">Penalty</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800">
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
    </Card>
  )
}

const INCIDENT_TYPE_OPTIONS = Object.keys(TYPE_LABELS) as WrcIncidentType[]

function ReviewQueueTab() {
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [remarksDraft, setRemarksDraft] = useState<Record<number, string>>({})
  const [weekFilter, setWeekFilter] = useState<number | 'all'>('all')
  const [typeFilter, setTypeFilter] = useState<WrcIncidentType | 'all'>('all')

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

  const incidents = incidentsForWeek?.filter((i) => typeFilter === 'all' || i.mis_final_remark === typeFilter)

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
        }
      />
      <CardBody>
        <div className="mb-4 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setTypeFilter('all')}
            className={`rounded-full border px-3 py-1 text-xs font-medium ${
              typeFilter === 'all'
                ? 'border-vigilance-500 bg-vigilance-500/15 text-vigilance-300'
                : 'border-slate-700 text-slate-400 hover:bg-slate-800'
            }`}
          >
            All ({incidentsForWeek?.length ?? 0})
          </button>
          {INCIDENT_TYPE_OPTIONS.map((type) => (
            <button
              key={type}
              type="button"
              onClick={() => setTypeFilter(type)}
              className={`rounded-full border px-3 py-1 text-xs font-medium ${
                typeFilter === type
                  ? 'border-vigilance-500 bg-vigilance-500/15 text-vigilance-300'
                  : 'border-slate-700 text-slate-400 hover:bg-slate-800'
              }`}
            >
              {TYPE_LABELS[type]} ({countsByType[type]})
            </button>
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
              <div key={incident.id} className="rounded-md border border-slate-800 p-3">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-medium text-slate-100">
                      {incident.centre_code} <span className="text-slate-500">-- {incident.centre_name}</span>
                    </p>
                    <p className="text-xs text-slate-500">
                      {formatDate(incident.incident_date)} · {TYPE_LABELS[incident.mis_final_remark] ?? incident.mis_final_remark}
                      {incident.cluster && <> · Cluster: {incident.cluster}</>}
                      {incident.center_manager && <> · {incident.center_manager}</>}
                    </p>
                    {incident.raw_remark && (
                      <p className="mt-1 text-xs text-slate-400">Raw remark: "{incident.raw_remark}"</p>
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
                  <button
                    disabled={reviewMutation.isPending}
                    className="rounded-md border border-green-800 bg-green-500/10 px-2 py-1 text-xs font-medium text-green-300 hover:bg-green-500/20 disabled:opacity-50"
                    onClick={() =>
                      reviewMutation.mutate({ id: incident.id, decision: 'considered', centerRemarks: remarksDraft[incident.id] })
                    }
                  >
                    Considered
                  </button>
                  <button
                    disabled={reviewMutation.isPending}
                    className="rounded-md border border-red-800 bg-red-500/10 px-2 py-1 text-xs font-medium text-red-300 hover:bg-red-500/20 disabled:opacity-50"
                    onClick={() =>
                      reviewMutation.mutate({ id: incident.id, decision: 'not_considered', centerRemarks: remarksDraft[incident.id] })
                    }
                  >
                    Not Considered
                  </button>
                  <button
                    disabled={noRemarkMutation.isPending}
                    className="rounded-md border border-slate-700 px-2 py-1 text-xs font-medium text-slate-400 hover:bg-slate-800 disabled:opacity-50"
                    onClick={() => noRemarkMutation.mutate(incident.id)}
                  >
                    Mark No Remark Received
                  </button>
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
        className="text-xs font-medium text-vigilance-400 hover:text-neon-400"
        onClick={() => setIsOpen((o) => !o)}
      >
        {isOpen ? '▲ Hide' : '▼ Show'} center remarks &amp; proof
      </button>
      {isOpen && (
        <div className="mt-1 max-w-md space-y-2 rounded-md border border-slate-800 bg-void-950 p-2">
          {isLoading && <Spinner />}
          {error && <ErrorBanner message={apiErrorMessage(error)} />}
          {data && data.length === 0 && <p className="text-xs text-slate-500">No remarks submitted yet.</p>}
          {data?.map((r) => (
            <div key={r.id} className="rounded border border-slate-800 p-2 text-xs">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium text-slate-200">
                  {r.responder_name} <span className="text-slate-500">({r.responder_npid})</span>
                </span>
                <span className="shrink-0 text-slate-500">{formatDate(r.submitted_at)}</span>
              </div>
              <p className="mt-1 whitespace-pre-wrap text-slate-400">{r.reason}</p>
              <button
                type="button"
                disabled={downloadMutation.isPending}
                className="mt-1 font-medium text-vigilance-400 hover:text-neon-400 disabled:opacity-50"
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
      <button
        type="button"
        disabled={notifyMutation.isPending}
        className="rounded-md border border-vigilance-700 px-2 py-1 text-xs font-medium text-vigilance-400 hover:bg-vigilance-900/40 disabled:opacity-40"
        onClick={() => notifyMutation.mutate()}
      >
        ✉ Notify Center
      </button>
      {lastResult && (
        <span className={`text-xs ${lastResult.sent ? 'text-neon-400' : 'text-amber-400'}`}>
          {lastResult.sent ? 'Sent' : lastResult.reason}
        </span>
      )}
    </div>
  )
}

function ActionTakenTab() {
  const { data: incidents, isLoading, error } = useQuery({ queryKey: ['wrc-action-taken'], queryFn: () => getActionTaken() })

  return (
    <Card>
      <CardHeader title="Decisions Already Made" />
      <CardBody>
        {isLoading && <Spinner />}
        {error && <ErrorBanner message={apiErrorMessage(error)} />}
        {incidents && incidents.length === 0 && (
          <EmptyState title="No decisions yet" hint="Considered/Not Considered verdicts will show up here as you review incidents." />
        )}
        {incidents && incidents.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase text-slate-500">
                <tr>
                  <th className="py-2 pr-4">Center</th>
                  <th className="py-2 pr-4">Incident</th>
                  <th className="py-2 pr-4">Decision</th>
                  <th className="py-2 pr-4">Decided</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {incidents.map((incident) => (
                  <tr key={incident.id}>
                    <td className="py-2 pr-4">
                      {incident.centre_code}
                      <div className="text-xs text-slate-500">{incident.centre_name}</div>
                    </td>
                    <td className="py-2 pr-4">
                      {formatDate(incident.incident_date)} · {TYPE_LABELS[incident.mis_final_remark] ?? incident.mis_final_remark}
                    </td>
                    <td className="py-2 pr-4">
                      {incident.considered && <Badge tone="status">{incident.considered}</Badge>}
                      <RemarksAndProofDropdown caseId={incident.case_id} />
                      <NotifyCenterControl incident={incident} />
                    </td>
                    <td className="py-2 pr-4 text-xs text-slate-500">
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
              <thead className="text-xs uppercase text-slate-500">
                <tr>
                  <th className="py-2 pr-4">Center</th>
                  <th className="py-2 pr-4">Event</th>
                  <th className="py-2 pr-4">When</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {activity.map((a) => (
                  <tr key={a.id}>
                    <td className="py-2 pr-4">
                      {a.centre_code}
                      {a.centre_name && <div className="text-xs text-slate-500">{a.centre_name}</div>}
                    </td>
                    <td className="py-2 pr-4">
                      <Badge tone="status">{a.event_type}</Badge>
                    </td>
                    <td className="py-2 pr-4 text-xs text-slate-500">{new Date(a.occurred_at).toLocaleString('en-IN')}</td>
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
        <p className="mb-4 text-xs text-slate-500">
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
              <thead className="text-xs uppercase text-slate-500">
                <tr>
                  <th className="py-2 pr-4">Center Code</th>
                  <th className="py-2 pr-4">Proposed Name</th>
                  <th className="py-2 pr-4">Proposed NPID</th>
                  <th className="py-2 pr-4">Proposed Email</th>
                  <th className="py-2 pr-4">Source</th>
                  <th className="py-2 pr-4">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
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
                    <td className="py-2 pr-4 text-xs text-slate-500">{r.source}</td>
                    <td className="py-2 pr-4">
                      <div className="flex gap-2">
                        <button
                          disabled={approveMutation.isPending || r.org_node_id == null}
                          className="text-xs font-medium text-brand-600 hover:text-brand-400 disabled:opacity-50"
                          onClick={() => approveMutation.mutate(r.id)}
                          title={r.org_node_id == null ? 'Fix the center in Org Hierarchy first' : undefined}
                        >
                          Approve
                        </button>
                        <button
                          disabled={rejectMutation.isPending}
                          className="text-xs font-medium text-slate-500 hover:text-slate-200 disabled:opacity-50"
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

function PublishResultModal({ result, onClose }: { result: WrcBatchPublishResult; onClose: () => void }) {
  const { showToast } = useToast()
  const singleLinkUrl = `${window.location.origin}/respond/weekly-revenue`

  function copy(url: string) {
    navigator.clipboard.writeText(url).then(() => showToast('Link copied'))
  }

  return (
    <Modal title={`Batch #${result.batch_id} -- Published Response Links`} onClose={onClose} wide>
      <div className="space-y-4">
        <div className="rounded-md border border-vigilance-600/30 bg-vigilance-500/5 p-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-vigilance-400">
            One link for every center
          </p>
          <p className="mt-1 text-xs text-slate-400">
            Send this single URL in one email to everyone -- each center manager picks their own center from a
            dropdown when they open it, and can only respond for that center.
          </p>
          <div className="mt-2 flex items-center gap-2">
            <code className="flex-1 truncate rounded border border-slate-800 bg-void-950 px-2 py-1.5 text-xs text-slate-300">
              {singleLinkUrl}
            </code>
            <Button type="button" variant="secondary" onClick={() => copy(singleLinkUrl)}>
              Copy
            </Button>
          </div>
        </div>

        <p className="text-xs text-slate-500">
          Individual per-center links (still work if you prefer sending separately). Publishing again always
          mints fresh tokens, invalidating these links.
        </p>
        <div className="max-h-96 overflow-y-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase text-slate-500">
              <tr>
                <th className="py-2 pr-4">Center</th>
                <th className="py-2 pr-4">Response Link</th>
                <th className="py-2 pr-4"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {result.links.map((link) => (
                <tr key={link.case_id}>
                  <td className="py-2 pr-4">
                    {link.centre_code}
                    <div className="text-xs text-slate-500">{link.centre_name}</div>
                  </td>
                  <td className="max-w-xs truncate py-2 pr-4 text-xs text-slate-500">{link.response_url}</td>
                  <td className="py-2 pr-4">
                    <button className="text-xs font-medium text-brand-600 hover:text-brand-400" onClick={() => copy(link.response_url)}>
                      Copy
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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
        <div className="grid grid-cols-3 gap-3">
          <TextField id="wrc-period-start" label="Period start" type="date" value={periodStart} onChange={(e) => setPeriodStart(e.target.value)} />
          <TextField id="wrc-period-end" label="Period end" type="date" value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} />
          <TextField id="wrc-week-label" label="Week label" placeholder="e.g. Week 2" value={weekLabel} onChange={(e) => setWeekLabel(e.target.value)} />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-slate-400">Closure pending list workbook (.xlsx)</label>
          <input ref={fileInputRef} type="file" accept=".xlsx,.xlsm" className="block w-full text-sm" />
        </div>

        {result && result.skipped_rows.length > 0 && (
          <div className="rounded-md border border-amber-800 bg-amber-500/10 p-3">
            <p className="mb-2 text-xs font-semibold text-amber-300">
              {result.skipped_rows.length} row(s) skipped -- never silently dropped, review below:
            </p>
            <div className="max-h-40 overflow-y-auto">
              <table className="w-full text-left text-xs">
                <thead className="text-amber-300">
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
