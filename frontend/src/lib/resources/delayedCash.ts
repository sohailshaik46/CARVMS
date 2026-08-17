import { api } from '../api'
import type {
  BatchPublishResult,
  BillNotifyResult,
  BillReviewDecision,
  BillReviewResult,
  ContactChangeRequest,
  DcbBatchSummary,
  DcbCaseResponse,
  DcbCenterBreakdown,
  DcbCenterActivity,
  DelayedCashBill,
  DelayedCashCenterPenalty,
  DelayedCashRule,
  DelayedCashUploadBatch,
  UploadBatchResult,
} from '../types'

// ---------- rule governance ----------

export async function getActiveRule(): Promise<DelayedCashRule | null> {
  try {
    const { data } = await api.get<DelayedCashRule>('/delayed-cash/rules/active')
    return data
  } catch (err) {
    if ((err as { response?: { status?: number } })?.response?.status === 404) return null
    throw err
  }
}

export async function activateDefaultRule(): Promise<DelayedCashRule> {
  const { data } = await api.post<DelayedCashRule>('/delayed-cash/rules/activate-default')
  return data
}

// ---------- export ----------

export async function downloadBatchExport(batchId: number): Promise<void> {
  const response = await api.get(`/delayed-cash/batches/${batchId}/export.xlsx`, { responseType: 'blob' })
  const blob = new Blob([response.data], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  })
  const objectUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = objectUrl
  a.download = `delayed-cash-batch-${batchId}-penalty.xlsx`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(objectUrl)
}

export async function listBatches(): Promise<DelayedCashUploadBatch[]> {
  const { data } = await api.get<DelayedCashUploadBatch[]>('/delayed-cash/batches')
  return data
}

export async function getBatch(batchId: number): Promise<DelayedCashUploadBatch> {
  const { data } = await api.get<DelayedCashUploadBatch>(`/delayed-cash/batches/${batchId}`)
  return data
}

export async function deleteBatch(batchId: number): Promise<void> {
  await api.delete(`/delayed-cash/batches/${batchId}`)
}

export async function getBatchSummary(batchId: number): Promise<DcbBatchSummary> {
  const { data } = await api.get<DcbBatchSummary>(`/delayed-cash/batches/${batchId}/summary`)
  return data
}

export async function getBatchCentersBreakdown(batchId: number): Promise<DcbCenterBreakdown[]> {
  const { data } = await api.get<DcbCenterBreakdown[]>(`/delayed-cash/batches/${batchId}/centers-breakdown`)
  return data
}

export async function uploadBatch(
  file: File,
  periodStart: string,
  periodEnd: string,
): Promise<UploadBatchResult> {
  const form = new FormData()
  form.append('period_start', periodStart)
  form.append('period_end', periodEnd)
  form.append('file', file)
  const { data } = await api.post<UploadBatchResult>('/delayed-cash/batches/upload', form)
  return data
}

export async function publishBatch(batchId: number): Promise<BatchPublishResult> {
  const { data } = await api.post<BatchPublishResult>(`/delayed-cash/batches/${batchId}/publish`)
  return data
}

// Read-only counterpart to publishBatch above -- fetches whichever links
// already exist for this batch WITHOUT minting/invalidating anything, so
// looking up a link to copy never re-publishes (and never breaks a link
// already shared with a center).
export async function getPublishedLinks(batchId: number): Promise<BatchPublishResult> {
  const { data } = await api.get<BatchPublishResult>(`/delayed-cash/batches/${batchId}/links`)
  return data
}

export async function listCenterPenalties(batchId?: number): Promise<DelayedCashCenterPenalty[]> {
  const { data } = await api.get<DelayedCashCenterPenalty[]>('/delayed-cash/center-penalties', {
    params: batchId != null ? { batch_id: batchId } : undefined,
  })
  return data
}

// ---------- per-bill review queue ----------

export async function getReviewQueue(): Promise<DelayedCashBill[]> {
  const { data } = await api.get<DelayedCashBill[]>('/delayed-cash/bills/review-queue')
  return data
}

export async function getActionTaken(batchId?: number): Promise<DelayedCashBill[]> {
  const { data } = await api.get<DelayedCashBill[]>('/delayed-cash/bills/action-taken', {
    params: batchId != null ? { batch_id: batchId } : undefined,
  })
  return data
}

// ---------- submitted remarks + evidence (shown under the review queue) ----------

export async function getCaseResponses(centerPenaltyId: number): Promise<DcbCaseResponse[]> {
  const { data } = await api.get<DcbCaseResponse[]>(`/delayed-cash/center-penalties/${centerPenaltyId}/responses`)
  return data
}

export async function downloadCaseResponseEvidence(responseId: number, filename: string): Promise<void> {
  const response = await api.get(`/delayed-cash/case-responses/${responseId}/evidence`, { responseType: 'blob' })
  const blob = new Blob([response.data])
  const objectUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = objectUrl
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(objectUrl)
}

// ---------- Centers Activity ----------

export async function getCentersActivity(batchId?: number): Promise<DcbCenterActivity[]> {
  const { data } = await api.get<DcbCenterActivity[]>('/delayed-cash/centers-activity', {
    params: batchId != null ? { batch_id: batchId } : undefined,
  })
  return data
}

export async function listBillsForCenterPenalty(centerPenaltyId: number): Promise<DelayedCashBill[]> {
  const { data } = await api.get<DelayedCashBill[]>(`/delayed-cash/center-penalties/${centerPenaltyId}/bills`)
  return data
}

export async function reviewBill(billId: number, decision: BillReviewDecision): Promise<BillReviewResult> {
  const { data } = await api.post<BillReviewResult>(`/delayed-cash/bills/${billId}/review`, { decision })
  return data
}

// Undoes a mistaken Considered/Not Considered/Needs More Detail/Needs
// Proof click -- moves the bill back into the Review Queue. 400s if the
// bill's verdict came from the uploaded workbook itself rather than an
// actual review click (nothing to undo there).
export async function revokeBillReview(billId: number): Promise<DelayedCashBill> {
  const { data } = await api.post<DelayedCashBill>(`/delayed-cash/bills/${billId}/revoke-review`)
  return data
}

export async function notifyBill(billId: number, comment?: string): Promise<BillNotifyResult> {
  const { data } = await api.post<BillNotifyResult>(`/delayed-cash/bills/${billId}/notify`, { comment })
  return data
}

// ---------- Org Master contact-change notifications ----------

export async function listContactChangeRequests(status?: 'pending' | 'approved' | 'rejected'): Promise<ContactChangeRequest[]> {
  const { data } = await api.get<ContactChangeRequest[]>('/org/contact-change-requests', {
    params: status ? { status } : undefined,
  })
  return data
}

export async function approveContactChangeRequest(requestId: number): Promise<ContactChangeRequest> {
  const { data } = await api.post<ContactChangeRequest>(`/org/contact-change-requests/${requestId}/approve`)
  return data
}

export async function rejectContactChangeRequest(requestId: number): Promise<ContactChangeRequest> {
  const { data } = await api.post<ContactChangeRequest>(`/org/contact-change-requests/${requestId}/reject`)
  return data
}
