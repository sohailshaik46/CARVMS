import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card, CardBody, CardHeader, KpiCard } from '../components/ui/Card'
import { Combobox } from '../components/ui/Combobox'
import { TextField } from '../components/ui/Field'
import { EmptyState, ErrorBanner, Spinner } from '../components/ui/Feedback'
import { HeroBanner } from '../components/ui/HeroBanner'
import { ChartIcon, ReceiptIcon, UsersIcon } from '../components/ui/Icons'
import { LedgerStackIllustration } from '../components/ui/Illustrations'
import { Modal } from '../components/ui/Modal'
import { Select } from '../components/ui/Select'
import { Tooltip } from '../components/ui/Tooltip'
import { useToast } from '../components/ui/ToastProvider'
import { apiErrorMessage } from '../lib/api'
import {
  activateDefaultRule,
  approveContactChangeRequest,
  deleteBatch,
  downloadBatchExport,
  downloadCaseResponseEvidence,
  getActionTaken,
  getBatchCentersBreakdown,
  getBatchSummary,
  getCaseResponses,
  getCentersActivity,
  getReviewQueue,
  listBatches,
  listBillsForCenterPenalty,
  listCenterPenalties,
  listContactChangeRequests,
  notifyBill,
  publishBatch,
  pullDcbFromRemote,
  pushDcbToRemote,
  rejectContactChangeRequest,
  revokeBillReview,
  reviewBill,
  uploadBatch,
} from '../lib/resources/delayedCash'
import {
  downloadAutoValidationExport,
  listDcbAutoValidation,
  overrideDcbResponse,
  reevaluateAllDcb,
  reevaluateDcbResponse,
} from '../lib/resources/autoValidation'
import { RemoteSyncCard, type RemoteSyncSummary } from '../components/ui/RemoteSyncCard'
import type {
  AutoValidationBucket,
  AutoValidationResponse,
  BatchPublishResult,
  BillReviewDecision,
  ContactChangeRequest,
  DcbCenterBreakdown,
  DcbRemoteSyncReport,
  DelayedCashBill,
  DelayedCashUploadBatch,
  UploadBatchResult,
} from '../lib/types'

function dcbReportToSummary(report: DcbRemoteSyncReport): RemoteSyncSummary {
  return {
    created: report.rules_created + report.batches_created + report.bills_created + report.center_penalties_created,
    updated: report.rules_updated + report.batches_updated + report.bills_updated + report.center_penalties_updated,
    unchanged:
      report.rules_unchanged + report.batches_unchanged + report.bills_unchanged + report.center_penalties_unchanged,
    changedList: report.changed_summary,
  }
}

function RemoteSyncCardForDcb() {
  return (
    <RemoteSyncCard
      title="Data Sync with Render"
      whatIsThisTooltip="Manual only -- nothing here ever runs automatically. Push sends THIS computer's Delayed Cash Billing data (batches, bills, review decisions, response links) up to Render; Pull brings Render's down to this computer. Neither ever deletes anything, and neither ever overwrites a response link already emailed to a center or a review decision already made -- those only ever get filled in if the receiving side has none yet. Each button previews the exact changes first (writes nothing); a second click actually applies them."
      pushLabel="Push to Render"
      pushDescription="Send this computer's Delayed Cash Billing data up to the live Render database."
      pullLabel="Pull from Render"
      pullDescription="Bring Render's live Delayed Cash Billing data down to this computer."
      onPreviewPush={() => pushDcbToRemote(false).then(dcbReportToSummary)}
      onApplyPush={() => pushDcbToRemote(true).then(dcbReportToSummary)}
      onPreviewPull={() => pullDcbFromRemote(false).then(dcbReportToSummary)}
      onApplyPull={() => pullDcbFromRemote(true).then(dcbReportToSummary)}
    />
  )
}

type Tab = 'batches' | 'review-queue' | 'auto-validation' | 'action-taken' | 'centers-activity' | 'notifications'
const TAB_VALUES: Tab[] = ['batches', 'review-queue', 'auto-validation', 'action-taken', 'centers-activity', 'notifications']

function formatMoney(value: string): string {
  return `₹${Number(value).toLocaleString('en-IN')}`
}

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
}

export function DelayedCashBillingPage() {
  // Deep-linkable via ?tab=... -- the Dashboard's KPI boxes route straight
  // into the tab a number actually comes from (e.g. "Bills Awaiting
  // Review" -> ?tab=review-queue) instead of just landing on Batches.
  const [searchParams] = useSearchParams()
  const initialTab = TAB_VALUES.find((t) => t === searchParams.get('tab')) ?? 'batches'
  const [tab, setTab] = useState<Tab>(initialTab)
  // A KPI card *within this same page* (e.g. the batch dashboard's
  // "Considered" box) navigates via `?tab=...` too, but since the pathname
  // doesn't change, this component never remounts -- `useState(initialTab)`
  // alone would silently miss it. Re-sync whenever the URL's own tab
  // param changes, without fighting manual tab-bar clicks (those never
  // touch the URL, so this effect stays quiet unless a link does).
  useEffect(() => {
    const fromUrl = TAB_VALUES.find((t) => t === searchParams.get('tab'))
    if (fromUrl) setTab(fromUrl)
  }, [searchParams])
  const [isUploadOpen, setIsUploadOpen] = useState(false)
  const [selectedBatchId, setSelectedBatchId] = useState<number | null>(null)
  const [dashboardBatchId, setDashboardBatchId] = useState<number | null>(null)
  const [publishResult, setPublishResult] = useState<BatchPublishResult | null>(null)
  const [batchToDelete, setBatchToDelete] = useState<DelayedCashUploadBatch | null>(null)
  const queryClient = useQueryClient()
  const { showToast } = useToast()

  const { data: batches, isLoading, error } = useQuery({ queryKey: ['dcb-batches'], queryFn: listBatches })

  // Same query key the Notifications tab itself uses below -- shares the
  // cache, so this doesn't cost a second request. Powers the pending-count
  // badge on the tab label.
  const { data: pendingContactChanges } = useQuery({
    queryKey: ['dcb-contact-change-requests'],
    queryFn: () => listContactChangeRequests('pending'),
  })

  const publishMutation = useMutation({
    mutationFn: (batchId: number) => publishBatch(batchId),
    onSuccess: (result) => {
      setPublishResult(result)
      queryClient.invalidateQueries({ queryKey: ['dcb-batches'] })
      showToast(`Published ${result.links.length} response link(s)`)
    },
    onError: (err) => showToast(apiErrorMessage(err, 'Publish failed'), 'error'),
  })

  const downloadMutation = useMutation({
    mutationFn: (batchId: number) => downloadBatchExport(batchId),
    onError: (err) => showToast(apiErrorMessage(err, 'Download failed'), 'error'),
  })

  const deleteMutation = useMutation({
    mutationFn: (batchId: number) => deleteBatch(batchId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dcb-batches'] })
      showToast(`Deleted "${batchToDelete?.source_filename}" and all its bills/penalties/responses`)
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
        kicker="Billing Vigilance"
        title="Delayed Cash Billing"
        actions={
          tab === 'batches' ? <Button onClick={() => setIsUploadOpen(true)}>Upload Delayed Cash Bills Data</Button> : undefined
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
                : 'text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200'
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

      <RemoteSyncCardForDcb />

      {tab === 'batches' && (
        <>
          <Card>
            <CardHeader title="Upload Batches" />
            <CardBody>
              {isLoading && <Spinner />}
              {error && <ErrorBanner message={apiErrorMessage(error)} />}
              {batches && batches.length === 0 && (
                <EmptyState title="No batches uploaded yet" hint="Upload the Delayed Cash Bills Data workbook to get started." />
              )}
              {batches && batches.length > 0 && (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="text-xs uppercase text-slate-500 dark:text-slate-400">
                      <tr>
                        <th className="py-2 pr-4">Period</th>
                        <th className="py-2 pr-4">Source File</th>
                        <th className="py-2 pr-4">Status</th>
                        <th className="py-2 pr-4">Uploaded</th>
                        <th className="py-2 pr-4">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
                      {batches.map((batch) => (
                        <tr key={batch.id} className="hover:bg-slate-50 dark:hover:bg-slate-700">
                          <td className="py-2 pr-4">
                            {formatDate(batch.period_start)} – {formatDate(batch.period_end)}
                          </td>
                          <td className="py-2 pr-4">{batch.source_filename}</td>
                          <td className="py-2 pr-4">
                            <Badge tone="status">{batch.status}</Badge>
                          </td>
                          <td className="py-2 pr-4">{formatDate(batch.uploaded_at)}</td>
                          <td className="py-2 pr-4">
                            <div className="flex gap-2">
                              <Tooltip text="Opens this batch's KPI dashboard -- total bills, decision breakdown, and a zone/cluster view of every center in it.">
                                <button
                                  className="text-xs font-medium text-np-calming-blue hover:text-np-deep-blue dark:text-neon-blue-400 dark:hover:text-neon-blue-300"
                                  onClick={() => {
                                    // Mutually exclusive with "View centers" below -- without
                                    // clearing the other panel's id first, clicking this while
                                    // that one's already open just stacks both cards, and since
                                    // Dashboard renders first, it visually looks like nothing
                                    // happened until you scroll past it.
                                    setSelectedBatchId(null)
                                    setDashboardBatchId(batch.id)
                                  }}
                                >
                                  Dashboard
                                </button>
                              </Tooltip>
                              <Tooltip text="Opens every center in this batch with its total bills and calculated penalty.">
                                <button
                                  className="text-xs font-medium text-np-calming-blue hover:text-np-deep-blue dark:text-neon-blue-400 dark:hover:text-neon-blue-300"
                                  onClick={() => {
                                    setDashboardBatchId(null)
                                    setSelectedBatchId(batch.id)
                                  }}
                                >
                                  View centers
                                </button>
                              </Tooltip>
                              <Tooltip text="Generates a response link for every center with a bill in this batch, and shows the full list so you can share or email them.">
                                <button
                                  className="text-xs font-medium text-brand-600 hover:text-brand-700 dark:text-neon-400 dark:hover:text-neon-300 disabled:opacity-50"
                                  disabled={publishMutation.isPending}
                                  onClick={() => publishMutation.mutate(batch.id)}
                                >
                                  {batch.status === 'published' ? 'Re-publish links' : 'Publish links'}
                                </button>
                              </Tooltip>
                              <Tooltip text="Downloads this batch's full Data + Penalty workbook as an Excel file, regenerated fresh from its current bills and penalties.">
                                <button
                                  className="text-xs font-medium text-np-calming-blue hover:text-np-deep-blue dark:text-neon-blue-400 dark:hover:text-neon-blue-300 disabled:opacity-50"
                                  disabled={downloadMutation.isPending}
                                  onClick={() => downloadMutation.mutate(batch.id)}
                                >
                                  Download
                                </button>
                              </Tooltip>
                              <Tooltip text="Permanently deletes this batch and everything computed from it -- bills, penalties, responses, and evidence files. Cannot be undone; asks for confirmation first.">
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

          {dashboardBatchId != null && (
            <DcbBatchDashboard
              batchId={dashboardBatchId}
              onClose={() => setDashboardBatchId(null)}
              onSwitchBatch={setDashboardBatchId}
            />
          )}
          {selectedBatchId != null && (
            <BatchCenterPenalties
              batchId={selectedBatchId}
              onClose={() => setSelectedBatchId(null)}
              onSwitchBatch={setSelectedBatchId}
            />
          )}
        </>
      )}

      {tab === 'review-queue' && <ReviewQueueTab />}
      {tab === 'auto-validation' && <AutoValidationTab />}
      {tab === 'action-taken' && <ActionTakenTab />}
      {tab === 'centers-activity' && <CentersActivityTab />}
      {tab === 'notifications' && <ContactChangeNotificationsTab />}

      {isUploadOpen && (
        <UploadBatchModal
          onClose={() => setIsUploadOpen(false)}
          onUploaded={(result) => {
            // Deliberately does NOT close the modal (see UploadBatchModal
            // below) -- it switches to its own result view and stays open
            // until the user clicks "Done" themselves, so that view is
            // actually seen rather than instantly unmounted.
            queryClient.invalidateQueries({ queryKey: ['dcb-batches'] })
            setSelectedBatchId(result.batch.id)
            const outOfPeriodNote =
              result.out_of_period_row_count > 0
                ? ` ${result.out_of_period_row_count} row(s) outside this batch's own dates were ignored (already covered by a prior week's upload).`
                : ''
            if (result.skipped_rows.length > 0) {
              showToast(`Uploaded with ${result.skipped_rows.length} row(s) skipped -- see the report below.${outOfPeriodNote}`, 'error')
            } else {
              showToast(
                `Uploaded ${result.center_penalties.length} center(s), ${result.center_penalties.reduce((sum, cp) => sum + cp.total_bills, 0)} bill(s).${outOfPeriodNote}`,
              )
            }
          }}
        />
      )}

      {publishResult && <PublishResultModal result={publishResult} onClose={() => setPublishResult(null)} />}

      {batchToDelete && (
        <Modal title="Delete this batch?" onClose={() => setBatchToDelete(null)}>
          <div className="space-y-4">
            <p className="text-sm text-slate-600 dark:text-slate-300">
              This permanently deletes <span className="font-medium text-slate-900 dark:text-slate-100">{batchToDelete.source_filename}</span>{' '}
              ({formatDate(batchToDelete.period_start)} – {formatDate(batchToDelete.period_end)}) along with every bill,
              center penalty, response-portal link, submitted response and evidence file, and activity record tied to
              it. This cannot be undone -- you can re-upload a corrected file afterwards.
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
    </div>
  )
}

const REVIEW_STATUS_OPTIONS: { key: 'unreviewed' | 'needs_more_detail' | 'needs_proof'; label: string; tooltip: string }[] = [
  { key: 'unreviewed', label: 'Never Reviewed', tooltip: 'No decision has been made on this bill yet.' },
  {
    key: 'needs_more_detail',
    label: 'Needs More Detail',
    tooltip: 'Vigilance asked the center to follow up with more information -- awaiting their next response.',
  },
  {
    key: 'needs_proof',
    label: 'Needs Proof',
    tooltip: 'Vigilance asked the center for supporting evidence specifically -- awaiting their next response.',
  },
]

/** "YYYY-MM" -> "July 2026", built from a bill's own bill_date so it never
 * depends on which upload batch a bill happened to arrive in (a single
 * calendar month can span more than one batch). */
function monthKey(dateStr: string): string {
  return dateStr.slice(0, 7)
}

function monthLabel(key: string): string {
  const [year, month] = key.split('-').map(Number)
  return new Date(year, month - 1, 1).toLocaleDateString('en-IN', { month: 'long', year: 'numeric' })
}

/** Beside the month/batch filter in both Review Queue and Action Taken --
 * lists only centers actually present in whatever's already been filtered
 * down (the selected month/batch), never every center in the system, so
 * picking one always jumps to real rows instead of an empty result. */
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
  const options = centers.map(([code, name]) => ({ value: code, label: `${code} -- ${name}`, searchText: name }))

  return (
    <Tooltip text="Search/jump to one center by code or name (type any part, e.g. just the number) -- only lists centers with a row in the currently selected month or batch above.">
      <Combobox
        className="w-56 text-sm"
        placeholder="Search centers…"
        value={value === 'all' ? '' : value}
        onChange={(v) => onChange(v === '' ? 'all' : v)}
        options={options}
      />
    </Tooltip>
  )
}

function ReviewQueueTab() {
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [searchParams] = useSearchParams()
  // A "?batch=" link (e.g. from the batch dashboard's "Total Incidents" /
  // "Pending Review" boxes) scopes the list to that batch specifically --
  // there's no server-side batch filter for this endpoint (a bill's own
  // month is the honest grouping key, since a batch can straddle months),
  // so this is applied client-side, on top of whatever month is selected.
  const batchParam = searchParams.get('batch') ? Number(searchParams.get('batch')) : null
  const [lastLink, setLastLink] = useState<{ centre_code: string; response_url: string } | null>(null)
  const [monthFilter, setMonthFilter] = useState<string | 'all'>('all')
  const [statusFilter, setStatusFilter] = useState<'unreviewed' | 'needs_more_detail' | 'needs_proof' | 'all'>('all')
  const [centerFilter, setCenterFilter] = useState<string | 'all'>('all')

  const { data: allBills, isLoading, error } = useQuery({ queryKey: ['dcb-review-queue'], queryFn: getReviewQueue })

  const billsForBatch = batchParam ? allBills?.filter((b) => b.batch_id === batchParam) : allBills

  // Distinct months present, newest first -- derived from the bills
  // actually in the queue, never a fixed calendar range.
  const monthOptions = Array.from(new Set(billsForBatch?.map((b) => monthKey(b.bill_date)) ?? [])).sort().reverse()

  const billsForMonth = billsForBatch?.filter((b) => monthFilter === 'all' || monthKey(b.bill_date) === monthFilter)

  function statusOf(bill: DelayedCashBill): 'unreviewed' | 'needs_more_detail' | 'needs_proof' {
    if (bill.considered === 'needs_more_detail' || bill.considered === 'needs_proof') return bill.considered
    return 'unreviewed'
  }

  const countsByStatus = REVIEW_STATUS_OPTIONS.reduce(
    (acc, opt) => {
      acc[opt.key] = billsForMonth?.filter((b) => statusOf(b) === opt.key).length ?? 0
      return acc
    },
    {} as Record<'unreviewed' | 'needs_more_detail' | 'needs_proof', number>,
  )

  const bills = billsForMonth
    ?.filter((b) => statusFilter === 'all' || statusOf(b) === statusFilter)
    .filter((b) => centerFilter === 'all' || b.centre_code === centerFilter)

  const reviewMutation = useMutation({
    mutationFn: ({ billId, decision }: { billId: number; decision: BillReviewDecision }) => reviewBill(billId, decision),
    onSuccess: (result, { decision }) => {
      queryClient.invalidateQueries({ queryKey: ['dcb-review-queue'] })
      if (result.response_link) {
        setLastLink({ centre_code: result.bill.centre_code, response_url: result.response_link.response_url })
        showToast(`Marked "${decision.replace(/_/g, ' ')}" -- a fresh response link is ready to copy below`)
      } else {
        showToast(`Marked "${decision.replace(/_/g, ' ')}"`)
      }
    },
    onError: (err) => showToast(apiErrorMessage(err, 'Could not save that decision'), 'error'),
  })

  function copyLink(url: string) {
    navigator.clipboard.writeText(url).then(() => showToast('Link copied'))
  }

  const decisions: { key: BillReviewDecision; label: string; tooltip: string }[] = [
    {
      key: 'considered',
      label: 'Considered',
      tooltip: 'Accepts the center\'s explanation as a valid exception -- excluded from this center\'s validated penalty.',
    },
    {
      key: 'not_considered',
      label: 'Not Considered',
      tooltip: "Rejects the center's explanation -- this bill's penalty (day_difference x rate) counts toward the center's validated penalty.",
    },
    {
      key: 'needs_more_detail',
      label: 'Need More Detail',
      tooltip: 'Kicks the case back to the center for a follow-up -- not a financial decision yet. Mints a fresh response link automatically.',
    },
    {
      key: 'needs_proof',
      label: 'Need Proof',
      tooltip: 'Same as "Need More Detail", specifically asking the center for supporting evidence before a decision can be made.',
    },
  ]

  return (
    <div className="space-y-4">
      {lastLink && (
        <div className="flex items-center justify-between rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm dark:border-amber-800 dark:bg-amber-500/10">
          <span className="text-amber-800 dark:text-amber-300">
            Response link for <strong>{lastLink.centre_code}</strong>: no automatic email yet (no center email list
            configured) -- copy and send manually: <span className="text-xs">{lastLink.response_url}</span>
          </span>
          <div className="flex shrink-0 gap-2">
            <button className="text-xs font-medium text-np-calming-blue hover:text-np-deep-blue dark:text-neon-blue-400 dark:hover:text-neon-blue-300" onClick={() => copyLink(lastLink.response_url)}>
              Copy
            </button>
            <button className="text-xs font-medium text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200" onClick={() => setLastLink(null)}>
              Dismiss
            </button>
          </div>
        </div>
      )}

      <Card>
        <CardHeader
          title="Bills Awaiting a Decision"
          actions={
            <div className="flex flex-wrap gap-2">
              <Select className="w-56 text-sm" value={monthFilter} onChange={(e) => setMonthFilter(e.target.value)}>
                <option value="all">All months</option>
                {monthOptions.map((key) => (
                  <option key={key} value={key}>
                    {monthLabel(key)}
                  </option>
                ))}
              </Select>
              <CenterFilterSelect items={billsForMonth ?? []} value={centerFilter} onChange={setCenterFilter} />
            </div>
          }
        />
        <CardBody>
          <div className="mb-4 flex flex-wrap gap-2">
            <Tooltip text="Every bill still awaiting a decision for the selected month (or all months).">
              <button
                type="button"
                onClick={() => setStatusFilter('all')}
                className={`rounded-full border px-3 py-1 text-xs font-medium ${
                  statusFilter === 'all'
                    ? 'border-brand-200 bg-brand-50 text-brand-700 dark:border-vigilance-500 dark:bg-vigilance-500/15 dark:text-vigilance-300'
                    : 'border-slate-300 text-slate-500 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-400 dark:hover:bg-slate-700'
                }`}
              >
                All ({billsForMonth?.length ?? 0})
              </button>
            </Tooltip>
            {REVIEW_STATUS_OPTIONS.map((opt) => (
              <Tooltip key={opt.key} text={opt.tooltip}>
                <button
                  type="button"
                  onClick={() => setStatusFilter(opt.key)}
                  className={`rounded-full border px-3 py-1 text-xs font-medium ${
                    statusFilter === opt.key
                      ? 'border-brand-200 bg-brand-50 text-brand-700 dark:border-vigilance-500 dark:bg-vigilance-500/15 dark:text-vigilance-300'
                      : 'border-slate-300 text-slate-500 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-400 dark:hover:bg-slate-700'
                  }`}
                >
                  {opt.label} ({countsByStatus[opt.key]})
                </button>
              </Tooltip>
            ))}
          </div>

          {isLoading && <Spinner />}
          {error && <ErrorBanner message={apiErrorMessage(error)} />}
          {bills && bills.length === 0 && (
            <EmptyState
              title="Nothing pending review"
              hint={
                statusFilter === 'all' && monthFilter === 'all' && centerFilter === 'all'
                  ? 'Every bill has a terminal considered/not-considered verdict.'
                  : 'No bills match this selection.'
              }
            />
          )}
          {bills && bills.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs uppercase text-slate-500 dark:text-slate-400">
                  <tr>
                    <th className="py-2 pr-4">Center</th>
                    <th className="py-2 pr-4">Sales Bill</th>
                    <th className="py-2 pr-4">Delay (days)</th>
                    <th className="py-2 pr-4">Penalty</th>
                    <th className="py-2 pr-4">Current Status</th>
                    <th className="py-2 pr-4">Decision</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
                  {bills.map((bill) => (
                    <tr key={bill.id}>
                      <td className="py-2 pr-4">
                        {bill.centre_code}
                        <div className="text-xs text-slate-500 dark:text-slate-400">{bill.centre_name}</div>
                      </td>
                      <td className="py-2 pr-4">{bill.sales_bill}</td>
                      <td className="py-2 pr-4">{bill.calculated_day_difference}</td>
                      <td className="py-2 pr-4 font-medium">{formatMoney(bill.calculated_penalty)}</td>
                      <td className="py-2 pr-4">
                        {bill.considered ? <Badge tone="status">{bill.considered}</Badge> : <span className="text-xs text-slate-500 dark:text-slate-400">Not yet reviewed</span>}
                      </td>
                      <td className="py-2 pr-4">
                        <div className="flex flex-wrap gap-1">
                          {decisions.map((d) => (
                            <Tooltip key={d.key} text={d.tooltip}>
                              <button
                                disabled={reviewMutation.isPending}
                                className="rounded-md border border-slate-300 px-2 py-1 text-xs font-medium text-slate-500 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:text-slate-400 dark:hover:bg-slate-700"
                                onClick={() => reviewMutation.mutate({ billId: bill.id, decision: d.key })}
                              >
                                {d.label}
                              </button>
                            </Tooltip>
                          ))}
                        </div>
                        <RemarksAndProofDropdown centerPenaltyId={bill.center_penalty_id} />
                        <NotifyCenterControl bill={bill} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardBody>
      </Card>
    </div>
  )
}

/** A collapsed-by-default dropdown, shown just below a bill's decision
 * buttons -- the center's submitted remark text plus a download link for
 * whatever proof they attached, so Vigilance can read/verify both before
 * deciding. Fetches lazily (only once opened), since most rows in a large
 * queue are never expanded. */
function RemarksAndProofDropdown({ centerPenaltyId }: { centerPenaltyId: number | null }) {
  const [isOpen, setIsOpen] = useState(false)
  const { showToast } = useToast()
  const { data, isLoading, error } = useQuery({
    queryKey: ['dcb-case-responses', centerPenaltyId],
    queryFn: () => getCaseResponses(centerPenaltyId as number),
    enabled: isOpen && centerPenaltyId != null,
  })

  const downloadMutation = useMutation({
    mutationFn: ({ responseId, filename }: { responseId: number; filename: string }) =>
      downloadCaseResponseEvidence(responseId, filename),
    onError: (err) => showToast(apiErrorMessage(err, 'Download failed'), 'error'),
  })

  if (centerPenaltyId == null) return null

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
        <div className="mt-1 max-w-md space-y-2 rounded-md border border-slate-200 bg-slate-50 p-2 dark:border-slate-700 dark:bg-void-950">
          {isLoading && <Spinner />}
          {error && <ErrorBanner message={apiErrorMessage(error)} />}
          {data && data.length === 0 && <p className="text-xs text-slate-500 dark:text-slate-400">No remarks submitted yet.</p>}
          {data?.map((r) => (
            <div key={r.id} className="rounded border border-slate-200 p-2 text-xs dark:border-slate-700">
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
                onClick={() =>
                  downloadMutation.mutate({ responseId: r.id, filename: r.evidence_original_filename })
                }
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

/** Sits below a bill's decision buttons once a decision exists.
 * Considered/Not Considered: one "Notify Center" button, no comment.
 * Needs More Detail/Needs Proof: a remark textarea + Send button --
 * Vigilance's typed remark plus a fresh response link go out together. */
function NotifyCenterControl({ bill }: { bill: DelayedCashBill }) {
  const { showToast } = useToast()
  const [comment, setComment] = useState('')
  const [lastResult, setLastResult] = useState<{ sent: boolean; reason: string | null } | null>(null)
  const needsComment = bill.considered === 'needs_more_detail' || bill.considered === 'needs_proof'

  const notifyMutation = useMutation({
    mutationFn: () => notifyBill(bill.id, needsComment ? comment : undefined),
    onSuccess: (result) => {
      setLastResult(result)
      if (result.sent) {
        showToast('Center notified by email')
        setComment('')
      } else {
        showToast(result.reason ?? 'Could not send that email', 'error')
      }
    },
    onError: (err) => showToast(apiErrorMessage(err, 'Could not send that email'), 'error'),
  })

  if (!bill.considered) return null

  return (
    <div className="mt-2 max-w-md space-y-1">
      {needsComment && (
        <textarea
          className="w-full rounded-md border border-slate-300 bg-white px-2 py-1 text-xs text-slate-800 placeholder:text-slate-400 dark:border-slate-700 dark:bg-void-950 dark:text-slate-200 dark:placeholder:text-slate-600"
          rows={2}
          placeholder="Type what you need from this center..."
          value={comment}
          onChange={(e) => setComment(e.target.value)}
        />
      )}
      <div className="flex items-center gap-2">
        <Tooltip
          text={
            needsComment
              ? "Emails the center your typed remark plus a fresh response link, so they know exactly what more you need."
              : "Emails the center to let them know this bill's decision has been recorded -- purely informational, doesn't change the decision itself."
          }
        >
          <button
            type="button"
            disabled={notifyMutation.isPending || (needsComment && !comment.trim())}
            className="rounded-md border border-np-teal/40 px-2 py-1 text-xs font-medium text-np-teal hover:bg-np-teal/10 disabled:opacity-40 dark:border-vigilance-700 dark:text-vigilance-400 dark:hover:bg-vigilance-900/40"
            onClick={() => notifyMutation.mutate()}
          >
            ✉ {needsComment ? 'Send' : 'Notify Center'}
          </button>
        </Tooltip>
        {lastResult && (
          <span className={`text-xs ${lastResult.sent ? 'text-np-teal dark:text-neon-400' : 'text-amber-600 dark:text-amber-400'}`}>
            {lastResult.sent ? 'Sent' : lastResult.reason}
          </span>
        )}
      </div>
    </div>
  )
}

const AUTO_BUCKET_LABELS: Record<AutoValidationBucket, string> = {
  considered: 'Considered',
  not_considered: 'Not Considered',
  manual_check: 'Manual Check',
}

const AUTO_BUCKET_TOOLTIPS: Record<AutoValidationBucket, string> = {
  considered: 'Remarks the rules matched to a "considered" category, with the keyword that matched -- shown here as a suggestion only. Vigilance still confirms the real decision in the Review Queue.',
  not_considered: 'Remarks the rules matched to a "not considered" category, with the reason that would be given to the center -- advisory only, nothing is sent or finalized automatically.',
  manual_check: 'Remarks that matched no rule, or matched conflicting rules on both sides -- these need a human read before you decide.',
}

/** Every bill tied to one case, with the SAME decision buttons the Review
 * Queue uses -- this is the "click the auto-validation remark to open the
 * relevant bills and reverify" surface, expanded inline rather than
 * navigating away so Vigilance keeps the auto-validation context on
 * screen while deciding. */
function DcbBillsToReverify({ centerPenaltyId }: { centerPenaltyId: number }) {
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const { data: bills, isLoading, error } = useQuery({
    queryKey: ['dcb-bills-for-center-penalty', centerPenaltyId],
    queryFn: () => listBillsForCenterPenalty(centerPenaltyId),
  })

  const reviewMutation = useMutation({
    mutationFn: ({ billId, decision }: { billId: number; decision: BillReviewDecision }) => reviewBill(billId, decision),
    onSuccess: (_result, { decision }) => {
      queryClient.invalidateQueries({ queryKey: ['dcb-bills-for-center-penalty', centerPenaltyId] })
      queryClient.invalidateQueries({ queryKey: ['dcb-review-queue'] })
      queryClient.invalidateQueries({ queryKey: ['dcb-action-taken'] })
      showToast(`Marked "${decision.replace(/_/g, ' ')}"`)
    },
    onError: (err) => showToast(apiErrorMessage(err, 'Could not save that decision'), 'error'),
  })

  const decisions: { key: BillReviewDecision; label: string; tooltip: string }[] = [
    {
      key: 'considered',
      label: 'Considered',
      tooltip: 'Accepts the center\'s explanation as a valid exception -- excluded from this center\'s validated penalty.',
    },
    {
      key: 'not_considered',
      label: 'Not Considered',
      tooltip: "Rejects the center's explanation -- this bill's penalty (day_difference x rate) counts toward the center's validated penalty.",
    },
    {
      key: 'needs_more_detail',
      label: 'Need More Detail',
      tooltip: 'Kicks the case back to the center for a follow-up -- not a financial decision yet. Mints a fresh response link automatically.',
    },
    {
      key: 'needs_proof',
      label: 'Need Proof',
      tooltip: 'Same as "Need More Detail", specifically asking the center for supporting evidence before a decision can be made.',
    },
  ]

  return (
    <div className="mt-2 rounded-md border border-slate-200 bg-slate-50 p-2 dark:border-slate-700 dark:bg-void-950">
      {isLoading && <Spinner />}
      {error && <ErrorBanner message={apiErrorMessage(error)} />}
      {bills && bills.length === 0 && <p className="text-xs text-slate-500 dark:text-slate-400">No bills found for this case.</p>}
      {bills && bills.length > 0 && (
        <div className="space-y-2">
          {bills.map((bill) => (
            <div key={bill.id} className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 pb-2 text-xs last:border-0 last:pb-0 dark:border-slate-700">
              <div>
                <span className="font-medium text-slate-700 dark:text-slate-200">{bill.sales_bill}</span>{' '}
                <span className="text-slate-500 dark:text-slate-400">
                  {formatDate(bill.bill_date)} · {formatMoney(bill.calculated_penalty)}
                </span>
                {bill.considered && (
                  <span className="ml-2">
                    <Badge tone="status">{bill.considered}</Badge>
                  </span>
                )}
              </div>
              <div className="flex flex-wrap gap-1">
                {decisions.map((d) => (
                  <Tooltip key={d.key} text={d.tooltip}>
                    <button
                      disabled={reviewMutation.isPending}
                      className="rounded-md border border-slate-300 px-2 py-1 font-medium text-slate-500 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:text-slate-400 dark:hover:bg-slate-700"
                      onClick={() => reviewMutation.mutate({ billId: bill.id, decision: d.key })}
                    >
                      {d.label}
                    </button>
                  </Tooltip>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function AutoValidationOverrideControl({ response }: { response: AutoValidationResponse }) {
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [isOpen, setIsOpen] = useState(false)
  const [note, setNote] = useState('')

  const overrideMutation = useMutation({
    mutationFn: (bucket: AutoValidationBucket) => overrideDcbResponse(response.id, bucket, note || undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dcb-auto-validation'] })
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
            className="w-full rounded-md border border-slate-300 bg-white px-2 py-1 text-xs text-slate-800 dark:border-slate-700 dark:bg-void-950 dark:text-slate-200"
            rows={2}
            placeholder="Why are you overriding the auto-validation result? (optional)"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <div className="flex gap-1">
            {(['considered', 'not_considered', 'manual_check'] as AutoValidationBucket[]).map((bucket) => (
              <Tooltip key={bucket} text={`Sets this response's official bucket to "${AUTO_BUCKET_LABELS[bucket]}".`}>
                <button
                  disabled={overrideMutation.isPending}
                  className="rounded-md border border-slate-300 px-2 py-1 text-xs font-medium text-slate-500 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:text-slate-400 dark:hover:bg-slate-700"
                  onClick={() => overrideMutation.mutate(bucket)}
                >
                  {AUTO_BUCKET_LABELS[bucket]}
                </button>
              </Tooltip>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function AutoValidationTab() {
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [bucketFilter, setBucketFilter] = useState<AutoValidationBucket | 'all'>('all')
  const [expandedId, setExpandedId] = useState<number | null>(null)

  const { data: responses, isLoading, error } = useQuery({
    queryKey: ['dcb-auto-validation'],
    queryFn: () => listDcbAutoValidation(),
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
    mutationFn: () => reevaluateAllDcb(),
    onSuccess: (results) => {
      queryClient.invalidateQueries({ queryKey: ['dcb-auto-validation'] })
      showToast(`Re-ran auto-validation on ${results.length} response(s)`)
    },
    onError: (err) => showToast(apiErrorMessage(err, 'Could not re-run auto-validation'), 'error'),
  })

  const reevaluateOneMutation = useMutation({
    mutationFn: (responseId: number) => reevaluateDcbResponse(responseId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dcb-auto-validation'] })
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
          Not Considered / Manual Check. This is advisory only: it never sets the bill's real decision or changes
          the penalty. Use the buttons below to reverify and confirm the actual decision in the Review Queue.
        </p>
        <div className="mb-4 flex flex-wrap gap-2">
          <Tooltip text="Every response that has been auto-validated so far, in any bucket.">
            <button
              type="button"
              onClick={() => setBucketFilter('all')}
              className={`rounded-full border px-3 py-1 text-xs font-medium ${
                bucketFilter === 'all'
                  ? 'border-brand-200 bg-brand-50 text-brand-700 dark:border-vigilance-500 dark:bg-vigilance-500/15 dark:text-vigilance-300'
                  : 'border-slate-300 text-slate-500 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-400 dark:hover:bg-slate-700'
              }`}
            >
              All ({responses?.length ?? 0})
            </button>
          </Tooltip>
          {(['considered', 'not_considered', 'manual_check'] as AutoValidationBucket[]).map((bucket) => (
            <Tooltip key={bucket} text={AUTO_BUCKET_TOOLTIPS[bucket]}>
              <button
                type="button"
                onClick={() => setBucketFilter(bucket)}
                className={`rounded-full border px-3 py-1 text-xs font-medium ${
                  bucketFilter === bucket
                    ? 'border-brand-200 bg-brand-50 text-brand-700 dark:border-vigilance-500 dark:bg-vigilance-500/15 dark:text-vigilance-300'
                    : 'border-slate-300 text-slate-500 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-400 dark:hover:bg-slate-700'
                }`}
              >
                {AUTO_BUCKET_LABELS[bucket]} ({countsByBucket[bucket]})
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
                        <div className="mt-1 text-xs text-amber-600 dark:text-amber-400">
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
                        <Tooltip text="Opens every bill this response covers, right here, with the real Considered/Not Considered buttons -- so you can confirm the actual decision without leaving this tab.">
                          <button
                            type="button"
                            className="text-xs font-medium text-slate-500 hover:text-np-teal dark:text-vigilance-400 dark:hover:text-neon-400"
                            onClick={() => setExpandedId(expandedId === r.id ? null : r.id)}
                          >
                            {expandedId === r.id ? '▲ Hide' : '▼ Reverify'} bills
                          </button>
                        </Tooltip>
                        <Tooltip text="Re-evaluates just this one response against the current Auto Validation Rules -- useful right after you edit a rule.">
                          <button
                            type="button"
                            disabled={reevaluateOneMutation.isPending}
                            className="text-xs font-medium text-slate-500 hover:text-slate-800 disabled:opacity-50 dark:text-slate-400 dark:hover:text-slate-200"
                            onClick={() => reevaluateOneMutation.mutate(r.id)}
                          >
                            Re-run
                          </button>
                        </Tooltip>
                      </div>
                      <AutoValidationOverrideControl response={r} />
                      {expandedId === r.id && <DcbBillsToReverify centerPenaltyId={r.case_or_penalty_id} />}
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
  const [batchFilter, setBatchFilter] = useState<number | 'all'>(batchParam ? Number(batchParam) : 'all')
  const [decisionFilter, setDecisionFilter] = useState<'all' | 'considered' | 'not_considered'>(
    decisionParam === 'considered' || decisionParam === 'not_considered' ? decisionParam : 'all',
  )
  const [centerFilter, setCenterFilter] = useState<string | 'all'>('all')
  const queryClient = useQueryClient()
  const { showToast } = useToast()

  const { data: batches } = useQuery({ queryKey: ['dcb-batches'], queryFn: listBatches })
  const { data: billsForBatch, isLoading, error } = useQuery({
    queryKey: ['dcb-action-taken', batchFilter],
    queryFn: () => getActionTaken(batchFilter === 'all' ? undefined : batchFilter),
  })

  const revokeMutation = useMutation({
    mutationFn: (billId: number) => revokeBillReview(billId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dcb-action-taken'] })
      queryClient.invalidateQueries({ queryKey: ['dcb-review-queue'] })
      showToast('Decision revoked -- back in the Review Queue')
    },
    onError: (err) => showToast(apiErrorMessage(err, 'Could not revoke this decision'), 'error'),
  })

  const bills = billsForBatch
    ?.filter((b) => decisionFilter === 'all' || b.considered === decisionFilter)
    .filter((b) => centerFilter === 'all' || b.centre_code === centerFilter)

  return (
    <Card>
      <CardHeader
        title="Decisions Already Made"
        actions={
          <div className="flex flex-wrap gap-2">
            <Select
              className="w-56 text-sm"
              value={batchFilter === 'all' ? 'all' : String(batchFilter)}
              onChange={(e) => setBatchFilter(e.target.value === 'all' ? 'all' : Number(e.target.value))}
            >
              <option value="all">All batches</option>
              {batches?.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.source_filename}
                </option>
              ))}
            </Select>
            <CenterFilterSelect items={billsForBatch ?? []} value={centerFilter} onChange={setCenterFilter} />
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
                  ? 'border-brand-200 bg-brand-50 text-brand-700 dark:border-vigilance-500 dark:bg-vigilance-500/15 dark:text-vigilance-300'
                  : 'border-slate-300 text-slate-500 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-400 dark:hover:bg-slate-700'
              }`}
            >
              {d === 'all' ? 'All' : d === 'considered' ? 'Considered' : 'Not Considered'} (
              {d === 'all' ? billsForBatch?.length ?? 0 : billsForBatch?.filter((b) => b.considered === d).length ?? 0}
              )
            </button>
          ))}
        </div>

        {isLoading && <Spinner />}
        {error && <ErrorBanner message={apiErrorMessage(error)} />}
        {bills && bills.length === 0 && (
          <EmptyState title="No decisions yet" hint="Considered/Not Considered verdicts will show up here as you review bills." />
        )}
        {bills && bills.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase text-slate-500 dark:text-slate-400">
                <tr>
                  <th className="py-2 pr-4">Center</th>
                  <th className="py-2 pr-4">Sales Bill</th>
                  <th className="py-2 pr-4">Penalty</th>
                  <th className="py-2 pr-4">Decision</th>
                  <th className="py-2 pr-4">Decided</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
                {bills.map((bill: DelayedCashBill) => (
                  <tr key={bill.id}>
                    <td className="py-2 pr-4">
                      {bill.centre_code}
                      <div className="text-xs text-slate-500 dark:text-slate-400">{bill.centre_name}</div>
                    </td>
                    <td className="py-2 pr-4">{bill.sales_bill}</td>
                    <td className="py-2 pr-4 font-medium">{formatMoney(bill.calculated_penalty)}</td>
                    <td className="py-2 pr-4">
                      {bill.considered && <Badge tone="status">{bill.considered}</Badge>}
                      {bill.reviewed_at && (
                        <Tooltip text="Undoes this decision if it was clicked by mistake -- moves the bill back into the Review Queue with no verdict, so you can decide again. Doesn't touch the bill's data, only the decision.">
                          <button
                            type="button"
                            className="ml-2 text-xs font-medium text-red-600 hover:text-red-700 disabled:opacity-50 dark:text-neon-pink-400 dark:hover:text-neon-pink-300"
                            disabled={revokeMutation.isPending}
                            onClick={() => revokeMutation.mutate(bill.id)}
                          >
                            Revoke
                          </button>
                        </Tooltip>
                      )}
                      <RemarksAndProofDropdown centerPenaltyId={bill.center_penalty_id} />
                      <NotifyCenterControl bill={bill} />
                    </td>
                    <td className="py-2 pr-4 text-xs text-slate-500 dark:text-slate-400">
                      {bill.reviewed_at ? formatDate(bill.reviewed_at) : '—'}
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
    queryKey: ['dcb-centers-activity'],
    queryFn: () => getCentersActivity(),
  })

  return (
    <Card>
      <CardHeader title="Centers Activity" />
      <CardBody>
        <p className="mb-4 text-xs text-slate-500 dark:text-slate-400">
          Every time a center manager opened or submitted through the response portal -- including centers that
          only browsed and never submitted anything.
        </p>
        {isLoading && <Spinner />}
        {error && <ErrorBanner message={apiErrorMessage(error)} />}
        {activity && activity.length === 0 && <EmptyState title="No activity yet" hint="Nothing has been opened via the response portal yet." />}
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
                    <td className="py-2 pr-4 text-xs text-slate-500 dark:text-slate-400">
                      {new Date(a.occurred_at).toLocaleString('en-IN')}
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

function ContactChangeNotificationsTab() {
  const queryClient = useQueryClient()
  const { showToast } = useToast()

  const { data: requests, isLoading, error } = useQuery({
    queryKey: ['dcb-contact-change-requests'],
    queryFn: () => listContactChangeRequests('pending'),
  })

  const approveMutation = useMutation({
    mutationFn: (id: number) => approveContactChangeRequest(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dcb-contact-change-requests'] })
      showToast('Approved -- Org Master updated')
    },
    onError: (err) => showToast(apiErrorMessage(err, 'Could not approve'), 'error'),
  })

  const rejectMutation = useMutation({
    mutationFn: (id: number) => rejectContactChangeRequest(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dcb-contact-change-requests'] })
      showToast('Rejected -- no change made')
    },
    onError: (err) => showToast(apiErrorMessage(err, 'Could not reject'), 'error'),
  })

  return (
    <Card>
      <CardHeader title="Pending Center Manager Contact Changes" />
      <CardBody>
        <p className="mb-4 text-xs text-slate-500 dark:text-slate-400">
          A center manager's name/NPID/email from a response submission is never written to the Org Master
          automatically -- approve here to apply it, or reject to leave the record unchanged.
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
                        <div className="text-xs text-red-600 dark:text-red-400">No matching center in Org Hierarchy</div>
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
                          className="text-xs font-medium text-brand-600 hover:text-brand-700 disabled:opacity-50 dark:text-neon-400 dark:hover:text-neon-300"
                          onClick={() => approveMutation.mutate(r.id)}
                          title={r.org_node_id == null ? 'Fix the center in Org Hierarchy first' : undefined}
                        >
                          Approve
                        </button>
                        <button
                          disabled={rejectMutation.isPending}
                          className="text-xs font-medium text-slate-500 hover:text-slate-800 disabled:opacity-50 dark:text-slate-400 dark:hover:text-slate-200"
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

interface DcbRollupRow {
  key: string
  centerCount: number
  thisBatchBills: number
  allTimeConsidered: number
  allTimeNotConsidered: number
  repeatCentersCount: number
  centers: DcbCenterBreakdown[]
  repeatCenters: DcbCenterBreakdown[]
}

/** Aggregates a list of per-center breakdown rows into one rollup row per
 * distinct key (zone/cluster/etc) -- "Unknown" groups centers whose Org
 * Master link hasn't been placed in that dimension yet, rather than
 * dropping them silently. Keeps the actual matching rows (not just their
 * counts) so a rollup number can drill into exactly which centers make it
 * up -- see DcbRollupSection's onDrill. */
function rollupDcbBreakdown(rows: DcbCenterBreakdown[], keyFn: (r: DcbCenterBreakdown) => string): DcbRollupRow[] {
  const groups = new Map<string, DcbRollupRow>()
  for (const r of rows) {
    const key = keyFn(r) || 'Unknown'
    const g = groups.get(key) ?? {
      key, centerCount: 0, thisBatchBills: 0, allTimeConsidered: 0, allTimeNotConsidered: 0,
      repeatCentersCount: 0, centers: [], repeatCenters: [],
    }
    g.centerCount += 1
    g.thisBatchBills += r.this_batch_bill_count
    g.allTimeConsidered += r.all_time_considered_count
    g.allTimeNotConsidered += r.all_time_not_considered_count
    g.centers.push(r)
    if (r.all_time_batch_count > 1) {
      g.repeatCentersCount += 1
      g.repeatCenters.push(r)
    }
    groups.set(key, g)
  }
  return Array.from(groups.values()).sort((a, b) => b.thisBatchBills - a.thisBatchBills)
}

/** A clickable rollup count -- opens the drilldown modal listing exactly
 * which centers make up this number, instead of leaving it as a dead-end
 * figure. `count` of 0 stays plain text (nothing to drill into). */
function DrillableCount({
  count,
  label,
  centers,
  onDrill,
}: {
  count: number
  label: string
  centers: DcbCenterBreakdown[]
  onDrill: (label: string, centers: DcbCenterBreakdown[]) => void
}) {
  if (count === 0) return <span className="text-slate-400 dark:text-slate-500">0</span>
  return (
    <button
      type="button"
      onClick={() => onDrill(label, centers)}
      className="font-medium text-np-calming-blue hover:underline"
    >
      {count}
    </button>
  )
}

function DcbRollupSection({
  title,
  rows,
  onDrill,
}: {
  title: string
  rows: DcbRollupRow[]
  onDrill: (label: string, centers: DcbCenterBreakdown[]) => void
}) {
  if (rows.length === 0) return null
  const dimension = title.replace('By ', '')
  return (
    <div>
      <h4 className="mb-2 text-sm font-semibold text-slate-800 dark:text-slate-200">{title}</h4>
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
                <Tooltip text="How many bills in THIS batch belong to centers under this row -- click to see them.">
                  <span className="cursor-help underline decoration-dotted">This Batch's Bills</span>
                </Tooltip>
              </th>
              <th className="py-2 pr-4">
                <Tooltip text="Centers under this row that have appeared in more than one upload batch all-time -- a genuine repeat, not just multiple bills in one batch. Click to see which centers.">
                  <span className="cursor-help underline decoration-dotted">Repeat Centers</span>
                </Tooltip>
              </th>
              <th className="py-2 pr-4">
                <Tooltip text="All-time count of bills under this row's centers marked Considered -- click to see which centers.">
                  <span className="cursor-help underline decoration-dotted">All-Time Considered</span>
                </Tooltip>
              </th>
              <th className="py-2 pr-4">
                <Tooltip text="All-time count of bills under this row's centers marked Not Considered -- click to see which centers.">
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
                  <DrillableCount count={r.centerCount} label={`${dimension}: ${r.key} -- all centers`} centers={r.centers} onDrill={onDrill} />
                </td>
                <td className="py-2 pr-4">{r.thisBatchBills}</td>
                <td className="py-2 pr-4">
                  <DrillableCount count={r.repeatCentersCount} label={`${dimension}: ${r.key} -- repeat centers`} centers={r.repeatCenters} onDrill={onDrill} />
                </td>
                <td className="py-2 pr-4">
                  <DrillableCount
                    count={r.allTimeConsidered}
                    label={`${dimension}: ${r.key} -- centers with an all-time Considered bill`}
                    centers={r.centers.filter((c) => c.all_time_considered_count > 0)}
                    onDrill={onDrill}
                  />
                </td>
                <td className="py-2 pr-4">
                  <DrillableCount
                    count={r.allTimeNotConsidered}
                    label={`${dimension}: ${r.key} -- centers with an all-time Not Considered bill`}
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

/** Lists exactly which centers make up a clicked rollup number. */
function CenterDrilldownModal({
  label,
  centers,
  onClose,
}: {
  label: string
  centers: DcbCenterBreakdown[]
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
              <th className="py-2 pr-4">This Batch's Bills</th>
              <th className="py-2 pr-4">All-Time Batches Flagged</th>
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
                <td className="py-2 pr-4">{c.this_batch_bill_count}</td>
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

function DcbBatchDashboard({
  batchId,
  onClose,
  onSwitchBatch,
}: {
  batchId: number
  onClose: () => void
  onSwitchBatch: (batchId: number) => void
}) {
  const { showToast } = useToast()

  // Shares the Batches tab's own query -- so the picker below doesn't cost
  // a second request and always lists the exact same batches shown there.
  const { data: batches } = useQuery({ queryKey: ['dcb-batches'], queryFn: listBatches })

  const { data: summary, isLoading, error } = useQuery({
    queryKey: ['dcb-batch-summary', batchId],
    queryFn: () => getBatchSummary(batchId),
  })
  const { data: centers } = useQuery({
    queryKey: ['dcb-centers-breakdown', batchId],
    queryFn: () => getBatchCentersBreakdown(batchId),
  })

  const exportMutation = useMutation({
    mutationFn: () => downloadBatchExport(batchId),
    onError: (err) => showToast(apiErrorMessage(err, 'Export failed'), 'error'),
  })

  const byZone = centers ? rollupDcbBreakdown(centers, (r) => r.zone ?? 'Unknown') : []
  const byCluster = centers ? rollupDcbBreakdown(centers, (r) => r.cluster ?? 'Unknown') : []
  const unresolvedCount = centers?.filter((r) => !r.zone && !r.cluster).length ?? 0
  const [drilldown, setDrilldown] = useState<{ label: string; centers: DcbCenterBreakdown[] } | null>(null)
  const handleDrill = (label: string, drillCenters: DcbCenterBreakdown[]) => setDrilldown({ label, centers: drillCenters })

  return (
    <Card>
      <CardHeader
        title={summary ? `Batch #${batchId} -- Dashboard` : `Batch #${batchId} -- Dashboard`}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Tooltip text="Switch this dashboard to a different batch without closing it -- picks up right where you are, no need to go back to the Batches tab first.">
              <Select
                className="w-64 text-sm"
                value={String(batchId)}
                onChange={(e) => onSwitchBatch(Number(e.target.value))}
              >
                {batches?.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.source_filename}
                  </option>
                ))}
              </Select>
            </Tooltip>
            <Tooltip text="Downloads this batch's full Data + Penalty workbook as an Excel file.">
              <Button variant="secondary" isLoading={exportMutation.isPending} onClick={() => exportMutation.mutate()}>
                Export Workbook
              </Button>
            </Tooltip>
            <Tooltip text="Hides this dashboard and returns to the batches list -- doesn't change any data.">
              <button onClick={onClose} className="text-xs font-medium text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200">
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
                label="Total Bills"
                value={<span className="inline-flex items-center gap-2"><ReceiptIcon className="h-5 w-5 text-slate-500 dark:text-vigilance-400" />{summary.total_bills}</span>}
                tooltip="Every bill uploaded for this batch, regardless of review status."
                to={`/delayed-cash?tab=review-queue&batch=${batchId}`}
              />
              <KpiCard
                label="Pending Review"
                value={summary.pending_review_count}
                hint="No terminal verdict yet"
                tooltip="Bills without a Considered/Not Considered verdict yet (includes Needs More Detail/Needs Proof) -- click to open the Review Queue, pre-filtered to this batch."
                to={`/delayed-cash?tab=review-queue&batch=${batchId}`}
              />
              <KpiCard
                label="Considered"
                value={summary.considered_count}
                hint="Accepted exception"
                tooltip="Bills Vigilance marked Considered -- click to see them in Action Taken, pre-filtered to this batch and this decision."
                to={`/delayed-cash?tab=action-taken&batch=${batchId}&decision=considered`}
              />
              <KpiCard
                label="Not Considered"
                value={summary.not_considered_count}
                hint="Feeds validated penalty"
                tooltip="Bills Vigilance marked Not Considered -- click to see them in Action Taken, pre-filtered to this batch and this decision."
                to={`/delayed-cash?tab=action-taken&batch=${batchId}&decision=not_considered`}
              />
              <KpiCard
                label="Needs More Detail"
                value={summary.needs_more_detail_count}
                tooltip="Vigilance kicked these back to the center for a follow-up -- not a financial decision yet."
                to={`/delayed-cash?tab=review-queue&batch=${batchId}`}
              />
              <KpiCard
                label="Needs Proof"
                value={summary.needs_proof_count}
                tooltip="Vigilance asked the center for supporting evidence specifically -- not a financial decision yet."
                to={`/delayed-cash?tab=review-queue&batch=${batchId}`}
              />
              <KpiCard
                label="Centers in Batch"
                value={<span className="inline-flex items-center gap-2"><UsersIcon className="h-5 w-5 text-slate-500 dark:text-vigilance-400" />{summary.centers_in_batch}</span>}
                tooltip="How many distinct centers have a bill in this batch."
              />
              <KpiCard
                label="Total Calculated Penalty"
                value={<span className="inline-flex items-center gap-2"><ChartIcon className="h-5 w-5 text-slate-500 dark:text-vigilance-400" />{formatMoney(summary.total_calculated_penalty)}</span>}
                hint="Every bill, unfiltered by remark"
                tooltip="Sum of day_difference x rate across every bill in this batch, before any remark is reviewed -- the publishing-stage total, per the proven formula."
              />
            </div>

            <div>
              <div className="mb-2 flex items-center justify-between">
                <h4 className="text-sm font-semibold text-slate-800 dark:text-slate-200">Centers -- Zone / Cluster / Repeat Non-Compliance</h4>
              </div>
              {centers && unresolvedCount > 0 && (
                <p className="mb-3 text-xs text-amber-600 dark:text-amber-400">
                  {unresolvedCount} of {centers.length} center(s) in this batch have no zone/cluster on record in the
                  Org Master yet -- shown as "Unknown". Run the Centers Master sync (Org Hierarchy) to fix.
                </p>
              )}
              {centers && centers.length > 0 && (
                <div className="space-y-6">
                  <DcbRollupSection title="By Zone" rows={byZone} onDrill={handleDrill} />
                  <DcbRollupSection title="By Cluster" rows={byCluster} onDrill={handleDrill} />
                  <div>
                    <h4 className="mb-2 text-sm font-semibold text-slate-800 dark:text-slate-200">All Centers in This Batch</h4>
                    <div className="overflow-x-auto">
                      <table className="w-full text-left text-sm">
                        <thead className="text-xs uppercase text-slate-500 dark:text-slate-400">
                          <tr>
                            <th className="py-2 pr-4">Center</th>
                            <th className="py-2 pr-4">Zone</th>
                            <th className="py-2 pr-4">Cluster</th>
                            <th className="py-2 pr-4">This Batch</th>
                            <th className="py-2 pr-4">All-Time Batches Flagged</th>
                            <th className="py-2 pr-4">All-Time Considered</th>
                            <th className="py-2 pr-4">All-Time Not Considered</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
                          {centers.map((r) => (
                            <tr key={r.centre_code}>
                              <td className="py-2 pr-4">
                                {r.centre_code}
                                <div className="text-xs text-slate-500 dark:text-slate-400">{r.centre_name}</div>
                              </td>
                              <td className="py-2 pr-4">{r.zone ?? <span className="text-slate-500 dark:text-slate-400">Unknown</span>}</td>
                              <td className="py-2 pr-4">{r.cluster ?? <span className="text-slate-500 dark:text-slate-400">Unknown</span>}</td>
                              <td className="py-2 pr-4">
                                {r.this_batch_considered_count > 0 && <Badge tone="status">{`${r.this_batch_considered_count} considered`}</Badge>}{' '}
                                {r.this_batch_not_considered_count > 0 && <Badge tone="status">{`${r.this_batch_not_considered_count} not considered`}</Badge>}{' '}
                                {r.this_batch_pending_count > 0 && (
                                  <span className="text-xs text-slate-500 dark:text-slate-400">{r.this_batch_pending_count} pending</span>
                                )}
                              </td>
                              <td className="py-2 pr-4">
                                <Tooltip text="How many distinct batches this center has had at least one bill in, all-time -- more than 1 means a repeat.">
                                  <span className={r.all_time_batch_count > 1 ? 'font-medium text-amber-600 dark:text-amber-400' : ''}>
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
                </div>
              )}
            </div>
          </>
        )}
      </CardBody>
      {drilldown && (
        <CenterDrilldownModal label={drilldown.label} centers={drilldown.centers} onClose={() => setDrilldown(null)} />
      )}
    </Card>
  )
}

function BatchCenterPenalties({
  batchId,
  onClose,
  onSwitchBatch,
}: {
  batchId: number
  onClose: () => void
  onSwitchBatch: (batchId: number) => void
}) {
  const { showToast } = useToast()
  const { data: batches } = useQuery({ queryKey: ['dcb-batches'], queryFn: listBatches })
  const { data, isLoading, error } = useQuery({
    queryKey: ['dcb-center-penalties', batchId],
    queryFn: () => listCenterPenalties(batchId),
  })

  const exportMutation = useMutation({
    mutationFn: () => downloadBatchExport(batchId),
    onError: (err) => showToast(apiErrorMessage(err, 'Export failed'), 'error'),
  })

  return (
    <Card>
      <CardHeader
        title={`Batch #${batchId} -- Center Penalties`}
        actions={
          <div className="flex flex-wrap items-center gap-3">
            <Tooltip text="Switch this list to a different batch without closing it -- picks up right where you are, no need to go back to the Batches tab first.">
              <Select
                className="w-64 text-sm"
                value={String(batchId)}
                onChange={(e) => onSwitchBatch(Number(e.target.value))}
              >
                {batches?.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.source_filename}
                  </option>
                ))}
              </Select>
            </Tooltip>
            <Tooltip text="Downloads this batch's full Data + Penalty workbook as an Excel file, reproducing the reference format exactly.">
              <Button variant="secondary" isLoading={exportMutation.isPending} onClick={() => exportMutation.mutate()}>
                Export Workbook
              </Button>
            </Tooltip>
            <Tooltip text="Hides this center list and returns to the batches list -- doesn't change any data.">
              <button onClick={onClose} className="text-xs font-medium text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200">
                Close
              </button>
            </Tooltip>
          </div>
        }
      />
      <CardBody>
        {isLoading && <Spinner />}
        {error && <ErrorBanner message={apiErrorMessage(error)} />}
        {data && data.length === 0 && <EmptyState title="No centers in this batch" />}
        {data && data.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase text-slate-500 dark:text-slate-400">
                <tr>
                  <th className="py-2 pr-4">Center Code</th>
                  <th className="py-2 pr-4">Center Name</th>
                  <th className="py-2 pr-4">Bills</th>
                  <th className="py-2 pr-4">Calculated Penalty</th>
                  <th className="py-2 pr-4">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
                {data.map((cp) => (
                  <tr key={cp.id}>
                    <td className="py-2 pr-4">{cp.centre_code}</td>
                    <td className="py-2 pr-4">{cp.centre_name}</td>
                    <td className="py-2 pr-4">{cp.total_bills}</td>
                    <td className="py-2 pr-4 font-medium">{formatMoney(cp.calculated_penalty)}</td>
                    <td className="py-2 pr-4">
                      <div className="flex items-center gap-2">
                        <Badge tone="status">{cp.penalty_status}</Badge>
                        {cp.response_token && (
                          <Tooltip text="Copies this center's own response-portal link -- read-only, doesn't mint or invalidate anything.">
                            <button
                              type="button"
                              className="text-xs font-medium text-np-calming-blue hover:text-np-deep-blue dark:text-neon-blue-400 dark:hover:text-neon-blue-300"
                              onClick={() => {
                                const url = `${window.location.origin}/respond/delayed-cash/${cp.response_token}`
                                navigator.clipboard.writeText(url).then(() => showToast('Link copied'))
                              }}
                            >
                              Copy link
                            </button>
                          </Tooltip>
                        )}
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

function UploadBatchModal({
  onClose,
  onUploaded,
}: {
  onClose: () => void
  onUploaded: (result: UploadBatchResult) => void
}) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [periodStart, setPeriodStart] = useState('')
  const [periodEnd, setPeriodEnd] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<UploadBatchResult | null>(null)
  const { showToast } = useToast()

  const mutation = useMutation({
    mutationFn: (file: File) => uploadBatch(file, periodStart, periodEnd),
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
    if (!periodStart || !periodEnd) {
      setError('Choose both a period start and end date')
      return
    }
    const file = fileInputRef.current?.files?.[0]
    if (!file) {
      setError('Choose the Delayed Cash Bills Data workbook first')
      return
    }
    mutation.mutate(file)
  }

  return (
    <Modal title="Upload Delayed Cash Bills Data" onClose={onClose} wide>
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
                Activate default rule (₹100/day, 6.25% monthly cap)
              </Button>
            )}
          </div>
        )}
        {!result && (
          <>
            <div className="grid grid-cols-2 gap-3">
              <TextField
                id="dcb-period-start"
                label="Period start"
                type="date"
                value={periodStart}
                onChange={(e) => setPeriodStart(e.target.value)}
              />
              <TextField
                id="dcb-period-end"
                label="Period end"
                type="date"
                value={periodEnd}
                onChange={(e) => setPeriodEnd(e.target.value)}
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-600 dark:text-slate-400">Delayed Cash Bills Data workbook (.xlsx)</label>
              <input ref={fileInputRef} type="file" accept=".xlsx,.xlsm" className="block w-full text-sm" />
            </div>
          </>
        )}

        {result && (
          <div className="rounded-md border border-emerald-300 bg-emerald-50 p-3 dark:border-emerald-800 dark:bg-emerald-500/10">
            <p className="text-sm text-emerald-800 dark:text-emerald-200">
              <span className="font-semibold">{result.center_penalties.length}</span> center(s),{' '}
              <span className="font-semibold">{result.center_penalties.reduce((sum, cp) => sum + cp.total_bills, 0)}</span> bill(s) ingested.
            </p>
            {result.out_of_period_row_count > 0 && (
              <p className="mt-1 text-xs text-emerald-700 dark:text-emerald-300">
                {result.out_of_period_row_count} row(s) fell outside this batch's own dates and were ignored --
                already covered by a prior week's upload.
              </p>
            )}
          </div>
        )}

        {result && result.skipped_rows.length > 0 && (
          <div className="rounded-md border border-amber-300 bg-amber-50 p-3 dark:border-amber-800 dark:bg-amber-500/10">
            <p className="mb-2 text-xs font-semibold text-amber-800 dark:text-amber-300">
              {result.skipped_rows.length} row(s) skipped -- never silently dropped, review below:
            </p>
            <div className="max-h-40 overflow-y-auto">
              <table className="w-full text-left text-xs">
                <thead className="text-amber-800 dark:text-amber-300">
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

function PublishResultModal({
  result,
  onClose,
  mode = 'published',
}: {
  result: BatchPublishResult
  onClose: () => void
  mode?: 'published' | 'view'
}) {
  const { showToast } = useToast()
  const singleLinkUrl = `${window.location.origin}/respond/delayed-cash`

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
                <code className="flex-1 truncate rounded border border-slate-200 bg-slate-50 px-2 py-1.5 text-xs text-slate-600 dark:border-slate-700 dark:bg-void-950 dark:text-slate-300">
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
                    <tr key={link.center_penalty_id}>
                      <td className="py-2 pr-4">
                        {link.centre_code}
                        <div className="text-xs text-slate-500 dark:text-slate-400">{link.centre_name}</div>
                      </td>
                      <td className="max-w-xs truncate py-2 pr-4 text-xs text-slate-500 dark:text-slate-400">{link.response_url}</td>
                      <td className="py-2 pr-4">
                        <button
                          className="text-xs font-medium text-np-calming-blue hover:text-np-deep-blue dark:text-neon-blue-400 dark:hover:text-neon-blue-300"
                          onClick={() => copy(link.response_url)}
                        >
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
            Close
          </Button>
        </div>
      </div>
    </Modal>
  )
}
