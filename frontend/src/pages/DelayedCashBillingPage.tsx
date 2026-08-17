import { useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { TextField } from '../components/ui/Field'
import { EmptyState, ErrorBanner, Spinner } from '../components/ui/Feedback'
import { HeroBanner } from '../components/ui/HeroBanner'
import { LedgerStackIllustration } from '../components/ui/Illustrations'
import { Modal } from '../components/ui/Modal'
import { Select } from '../components/ui/Select'
import { useToast } from '../components/ui/ToastProvider'
import { apiErrorMessage } from '../lib/api'
import {
  activateDefaultRule,
  approveContactChangeRequest,
  deleteBatch,
  downloadBatchExport,
  downloadCaseResponseEvidence,
  getActionTaken,
  getCaseResponses,
  getCentersActivity,
  getReviewQueue,
  listBatches,
  listCenterPenalties,
  listContactChangeRequests,
  notifyBill,
  publishBatch,
  rejectContactChangeRequest,
  reviewBill,
  uploadBatch,
} from '../lib/resources/delayedCash'
import type {
  BatchPublishResult,
  BillReviewDecision,
  ContactChangeRequest,
  DelayedCashBill,
  DelayedCashUploadBatch,
  UploadBatchResult,
} from '../lib/types'

type Tab = 'batches' | 'review-queue' | 'action-taken' | 'centers-activity' | 'notifications'
const TAB_VALUES: Tab[] = ['batches', 'review-queue', 'action-taken', 'centers-activity', 'notifications']

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
  const [isUploadOpen, setIsUploadOpen] = useState(false)
  const [selectedBatchId, setSelectedBatchId] = useState<number | null>(null)
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
                    <thead className="text-xs uppercase text-slate-500">
                      <tr>
                        <th className="py-2 pr-4">Period</th>
                        <th className="py-2 pr-4">Source File</th>
                        <th className="py-2 pr-4">Status</th>
                        <th className="py-2 pr-4">Uploaded</th>
                        <th className="py-2 pr-4">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800">
                      {batches.map((batch) => (
                        <tr key={batch.id} className="hover:bg-slate-800">
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
                              <button
                                className="text-xs font-medium text-brand-600 hover:text-brand-400"
                                onClick={() => setSelectedBatchId(batch.id)}
                              >
                                View centers
                              </button>
                              <button
                                className="text-xs font-medium text-brand-600 hover:text-brand-400 disabled:opacity-50"
                                disabled={publishMutation.isPending}
                                onClick={() => publishMutation.mutate(batch.id)}
                              >
                                {batch.status === 'published' ? 'Re-publish links' : 'Publish links'}
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
            <BatchCenterPenalties batchId={selectedBatchId} onClose={() => setSelectedBatchId(null)} />
          )}
        </>
      )}

      {tab === 'review-queue' && <ReviewQueueTab />}
      {tab === 'action-taken' && <ActionTakenTab />}
      {tab === 'centers-activity' && <CentersActivityTab />}
      {tab === 'notifications' && <ContactChangeNotificationsTab />}

      {isUploadOpen && (
        <UploadBatchModal
          onClose={() => setIsUploadOpen(false)}
          onUploaded={(result) => {
            queryClient.invalidateQueries({ queryKey: ['dcb-batches'] })
            setIsUploadOpen(false)
            setSelectedBatchId(result.batch.id)
            if (result.skipped_rows.length > 0) {
              showToast(`Uploaded with ${result.skipped_rows.length} row(s) skipped -- see the report below`, 'error')
            } else {
              showToast(`Uploaded ${result.center_penalties.length} center(s), ${result.center_penalties.reduce((sum, cp) => sum + cp.total_bills, 0)} bill(s)`)
            }
          }}
        />
      )}

      {publishResult && <PublishResultModal result={publishResult} onClose={() => setPublishResult(null)} />}

      {batchToDelete && (
        <Modal title="Delete this batch?" onClose={() => setBatchToDelete(null)}>
          <div className="space-y-4">
            <p className="text-sm text-slate-300">
              This permanently deletes <span className="font-medium text-slate-100">{batchToDelete.source_filename}</span>{' '}
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

const REVIEW_STATUS_OPTIONS: { key: 'unreviewed' | 'needs_more_detail' | 'needs_proof'; label: string }[] = [
  { key: 'unreviewed', label: 'Never Reviewed' },
  { key: 'needs_more_detail', label: 'Needs More Detail' },
  { key: 'needs_proof', label: 'Needs Proof' },
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

function ReviewQueueTab() {
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [lastLink, setLastLink] = useState<{ centre_code: string; response_url: string } | null>(null)
  const [monthFilter, setMonthFilter] = useState<string | 'all'>('all')
  const [statusFilter, setStatusFilter] = useState<'unreviewed' | 'needs_more_detail' | 'needs_proof' | 'all'>('all')

  const { data: allBills, isLoading, error } = useQuery({ queryKey: ['dcb-review-queue'], queryFn: getReviewQueue })

  // Distinct months present, newest first -- derived from the bills
  // actually in the queue, never a fixed calendar range.
  const monthOptions = Array.from(new Set(allBills?.map((b) => monthKey(b.bill_date)) ?? [])).sort().reverse()

  const billsForMonth = allBills?.filter((b) => monthFilter === 'all' || monthKey(b.bill_date) === monthFilter)

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

  const bills = billsForMonth?.filter((b) => statusFilter === 'all' || statusOf(b) === statusFilter)

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

  const decisions: { key: BillReviewDecision; label: string }[] = [
    { key: 'considered', label: 'Considered' },
    { key: 'not_considered', label: 'Not Considered' },
    { key: 'needs_more_detail', label: 'Need More Detail' },
    { key: 'needs_proof', label: 'Need Proof' },
  ]

  return (
    <div className="space-y-4">
      {lastLink && (
        <div className="flex items-center justify-between rounded-md border border-amber-800 bg-amber-500/10 px-3 py-2 text-sm">
          <span className="text-amber-300">
            Response link for <strong>{lastLink.centre_code}</strong>: no automatic email yet (no center email list
            configured) -- copy and send manually: <span className="text-xs">{lastLink.response_url}</span>
          </span>
          <div className="flex shrink-0 gap-2">
            <button className="text-xs font-medium text-brand-600 hover:text-brand-400" onClick={() => copyLink(lastLink.response_url)}>
              Copy
            </button>
            <button className="text-xs font-medium text-slate-500 hover:text-slate-200" onClick={() => setLastLink(null)}>
              Dismiss
            </button>
          </div>
        </div>
      )}

      <Card>
        <CardHeader
          title="Bills Awaiting a Decision"
          actions={
            <Select className="w-56 text-sm" value={monthFilter} onChange={(e) => setMonthFilter(e.target.value)}>
              <option value="all">All months</option>
              {monthOptions.map((key) => (
                <option key={key} value={key}>
                  {monthLabel(key)}
                </option>
              ))}
            </Select>
          }
        />
        <CardBody>
          <div className="mb-4 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setStatusFilter('all')}
              className={`rounded-full border px-3 py-1 text-xs font-medium ${
                statusFilter === 'all'
                  ? 'border-vigilance-500 bg-vigilance-500/15 text-vigilance-300'
                  : 'border-slate-700 text-slate-400 hover:bg-slate-800'
              }`}
            >
              All ({billsForMonth?.length ?? 0})
            </button>
            {REVIEW_STATUS_OPTIONS.map((opt) => (
              <button
                key={opt.key}
                type="button"
                onClick={() => setStatusFilter(opt.key)}
                className={`rounded-full border px-3 py-1 text-xs font-medium ${
                  statusFilter === opt.key
                    ? 'border-vigilance-500 bg-vigilance-500/15 text-vigilance-300'
                    : 'border-slate-700 text-slate-400 hover:bg-slate-800'
                }`}
              >
                {opt.label} ({countsByStatus[opt.key]})
              </button>
            ))}
          </div>

          {isLoading && <Spinner />}
          {error && <ErrorBanner message={apiErrorMessage(error)} />}
          {bills && bills.length === 0 && (
            <EmptyState
              title="Nothing pending review"
              hint={
                statusFilter === 'all' && monthFilter === 'all'
                  ? 'Every bill has a terminal considered/not-considered verdict.'
                  : 'No bills match this selection.'
              }
            />
          )}
          {bills && bills.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs uppercase text-slate-500">
                  <tr>
                    <th className="py-2 pr-4">Center</th>
                    <th className="py-2 pr-4">Sales Bill</th>
                    <th className="py-2 pr-4">Delay (days)</th>
                    <th className="py-2 pr-4">Penalty</th>
                    <th className="py-2 pr-4">Current Status</th>
                    <th className="py-2 pr-4">Decision</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {bills.map((bill) => (
                    <tr key={bill.id}>
                      <td className="py-2 pr-4">
                        {bill.centre_code}
                        <div className="text-xs text-slate-500">{bill.centre_name}</div>
                      </td>
                      <td className="py-2 pr-4">{bill.sales_bill}</td>
                      <td className="py-2 pr-4">{bill.calculated_day_difference}</td>
                      <td className="py-2 pr-4 font-medium">{formatMoney(bill.calculated_penalty)}</td>
                      <td className="py-2 pr-4">
                        {bill.considered ? <Badge tone="status">{bill.considered}</Badge> : <span className="text-xs text-slate-500">Not yet reviewed</span>}
                      </td>
                      <td className="py-2 pr-4">
                        <div className="flex flex-wrap gap-1">
                          {decisions.map((d) => (
                            <button
                              key={d.key}
                              disabled={reviewMutation.isPending}
                              className="rounded-md border border-slate-700 px-2 py-1 text-xs font-medium text-slate-400 hover:bg-slate-800 disabled:opacity-50"
                              onClick={() => reviewMutation.mutate({ billId: bill.id, decision: d.key })}
                            >
                              {d.label}
                            </button>
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
          className="w-full rounded-md border border-slate-700 bg-void-950 px-2 py-1 text-xs text-slate-200 placeholder:text-slate-600"
          rows={2}
          placeholder="Type what you need from this center..."
          value={comment}
          onChange={(e) => setComment(e.target.value)}
        />
      )}
      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled={notifyMutation.isPending || (needsComment && !comment.trim())}
          className="rounded-md border border-vigilance-700 px-2 py-1 text-xs font-medium text-vigilance-400 hover:bg-vigilance-900/40 disabled:opacity-40"
          onClick={() => notifyMutation.mutate()}
        >
          ✉ {needsComment ? 'Send' : 'Notify Center'}
        </button>
        {lastResult && (
          <span className={`text-xs ${lastResult.sent ? 'text-neon-400' : 'text-amber-400'}`}>
            {lastResult.sent ? 'Sent' : lastResult.reason}
          </span>
        )}
      </div>
    </div>
  )
}

function ActionTakenTab() {
  const { data: bills, isLoading, error } = useQuery({ queryKey: ['dcb-action-taken'], queryFn: () => getActionTaken() })

  return (
    <Card>
      <CardHeader title="Decisions Already Made" />
      <CardBody>
        {isLoading && <Spinner />}
        {error && <ErrorBanner message={apiErrorMessage(error)} />}
        {bills && bills.length === 0 && (
          <EmptyState title="No decisions yet" hint="Considered/Not Considered verdicts will show up here as you review bills." />
        )}
        {bills && bills.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase text-slate-500">
                <tr>
                  <th className="py-2 pr-4">Center</th>
                  <th className="py-2 pr-4">Sales Bill</th>
                  <th className="py-2 pr-4">Penalty</th>
                  <th className="py-2 pr-4">Decision</th>
                  <th className="py-2 pr-4">Decided</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {bills.map((bill: DelayedCashBill) => (
                  <tr key={bill.id}>
                    <td className="py-2 pr-4">
                      {bill.centre_code}
                      <div className="text-xs text-slate-500">{bill.centre_name}</div>
                    </td>
                    <td className="py-2 pr-4">{bill.sales_bill}</td>
                    <td className="py-2 pr-4 font-medium">{formatMoney(bill.calculated_penalty)}</td>
                    <td className="py-2 pr-4">
                      {bill.considered && <Badge tone="status">{bill.considered}</Badge>}
                      <RemarksAndProofDropdown centerPenaltyId={bill.center_penalty_id} />
                      <NotifyCenterControl bill={bill} />
                    </td>
                    <td className="py-2 pr-4 text-xs text-slate-500">
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
        <p className="mb-4 text-xs text-slate-500">
          Every time a center manager opened or submitted through the response portal -- including centers that
          only browsed and never submitted anything.
        </p>
        {isLoading && <Spinner />}
        {error && <ErrorBanner message={apiErrorMessage(error)} />}
        {activity && activity.length === 0 && <EmptyState title="No activity yet" hint="Nothing has been opened via the response portal yet." />}
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
                    <td className="py-2 pr-4 text-xs text-slate-500">
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
        <p className="mb-4 text-xs text-slate-500">
          A center manager's name/NPID/email from a response submission is never written to the Org Master
          automatically -- approve here to apply it, or reject to leave the record unchanged.
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

function BatchCenterPenalties({ batchId, onClose }: { batchId: number; onClose: () => void }) {
  const { showToast } = useToast()
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
          <div className="flex items-center gap-3">
            <Button variant="secondary" isLoading={exportMutation.isPending} onClick={() => exportMutation.mutate()}>
              Export Workbook
            </Button>
            <button onClick={onClose} className="text-xs font-medium text-slate-500 hover:text-slate-200">
              Close
            </button>
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
              <thead className="text-xs uppercase text-slate-500">
                <tr>
                  <th className="py-2 pr-4">Center Code</th>
                  <th className="py-2 pr-4">Center Name</th>
                  <th className="py-2 pr-4">Bills</th>
                  <th className="py-2 pr-4">Calculated Penalty</th>
                  <th className="py-2 pr-4">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {data.map((cp) => (
                  <tr key={cp.id}>
                    <td className="py-2 pr-4">{cp.centre_code}</td>
                    <td className="py-2 pr-4">{cp.centre_name}</td>
                    <td className="py-2 pr-4">{cp.total_bills}</td>
                    <td className="py-2 pr-4 font-medium">{formatMoney(cp.calculated_penalty)}</td>
                    <td className="py-2 pr-4">
                      <Badge tone="status">{cp.penalty_status}</Badge>
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
          <label className="mb-1 block text-sm font-medium text-slate-400">Delayed Cash Bills Data workbook (.xlsx)</label>
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

function PublishResultModal({ result, onClose }: { result: BatchPublishResult; onClose: () => void }) {
  const { showToast } = useToast()
  const singleLinkUrl = `${window.location.origin}/respond/delayed-cash`

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
                <tr key={link.center_penalty_id}>
                  <td className="py-2 pr-4">
                    {link.centre_code}
                    <div className="text-xs text-slate-500">{link.centre_name}</div>
                  </td>
                  <td className="max-w-xs truncate py-2 pr-4 text-xs text-slate-500">{link.response_url}</td>
                  <td className="py-2 pr-4">
                    <button
                      className="text-xs font-medium text-brand-600 hover:text-brand-400"
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
        <div className="flex justify-end">
          <Button type="button" variant="secondary" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
    </Modal>
  )
}
