import { api, TOKEN_STORAGE_KEY } from '../api'
import type {
  WrcBatchPublishResult,
  WrcBatchSummary,
  WrcBillIncident,
  WrcCaseResponse,
  WrcCenterActivity,
  WrcCenterBreakdown,
  WrcCenterPenalty,
  WrcCloseBatchResult,
  WrcIncidentNotifyResult,
  WrcNoRemarkIncident,
  WrcResponseLinkDetail,
  WrcRolePenalty,
  WrcRule,
  WeeklyRevenueClosureBatch,
  WrcUploadResult,
} from '../types'

// ---------- rule governance ----------

export async function getActiveRule(): Promise<WrcRule | null> {
  try {
    const { data } = await api.get<WrcRule>('/weekly-revenue-closure/rules/active')
    return data
  } catch (err) {
    if ((err as { response?: { status?: number } })?.response?.status === 404) return null
    throw err
  }
}

export async function activateDefaultRule(): Promise<WrcRule> {
  const { data } = await api.post<WrcRule>('/weekly-revenue-closure/rules/activate-default')
  return data
}

export async function listBatches(): Promise<WeeklyRevenueClosureBatch[]> {
  const { data } = await api.get<WeeklyRevenueClosureBatch[]>('/weekly-revenue-closure/batches')
  return data
}

export async function getBatch(batchId: number): Promise<WeeklyRevenueClosureBatch> {
  const { data } = await api.get<WeeklyRevenueClosureBatch>(`/weekly-revenue-closure/batches/${batchId}`)
  return data
}

export async function getBatchSummary(batchId: number): Promise<WrcBatchSummary> {
  const { data } = await api.get<WrcBatchSummary>(`/weekly-revenue-closure/batches/${batchId}/summary`)
  return data
}

export async function deleteBatch(batchId: number): Promise<void> {
  await api.delete(`/weekly-revenue-closure/batches/${batchId}`)
}

export async function getCaseIncidents(caseId: number): Promise<WrcBillIncident[]> {
  const { data } = await api.get<WrcBillIncident[]>(`/weekly-revenue-closure/cases/${caseId}/incidents`)
  return data
}

export async function uploadBatch(
  file: File,
  periodStart: string,
  periodEnd: string,
  weekLabel: string,
): Promise<WrcUploadResult> {
  const form = new FormData()
  form.append('period_start', periodStart)
  form.append('period_end', periodEnd)
  form.append('week_label', weekLabel)
  form.append('file', file)
  const { data } = await api.post<WrcUploadResult>('/weekly-revenue-closure/batches/upload', form)
  return data
}

export async function closeBatch(batchId: number): Promise<WrcCloseBatchResult> {
  const { data } = await api.post<WrcCloseBatchResult>(`/weekly-revenue-closure/batches/${batchId}/close`)
  return data
}

export async function listCenterPenalties(batchId: number): Promise<WrcCenterPenalty[]> {
  const { data } = await api.get<WrcCenterPenalty[]>(`/weekly-revenue-closure/batches/${batchId}/center-penalties`)
  return data
}

export async function listRolePenalties(batchId: number): Promise<WrcRolePenalty[]> {
  const { data } = await api.get<WrcRolePenalty[]>(`/weekly-revenue-closure/batches/${batchId}/role-penalties`)
  return data
}

export async function listNoRemarkIncidents(batchId: number): Promise<WrcNoRemarkIncident[]> {
  const { data } = await api.get<WrcNoRemarkIncident[]>(`/weekly-revenue-closure/batches/${batchId}/no-remark-incidents`)
  return data
}

export async function getBatchCentersBreakdown(batchId: number): Promise<WrcCenterBreakdown[]> {
  const { data } = await api.get<WrcCenterBreakdown[]>(`/weekly-revenue-closure/batches/${batchId}/centers-breakdown`)
  return data
}

// ---------- per-incident review queue ----------

export async function getReviewQueue(batchId?: number): Promise<WrcBillIncident[]> {
  const { data } = await api.get<WrcBillIncident[]>('/weekly-revenue-closure/bills/review-queue', {
    params: batchId != null ? { batch_id: batchId } : undefined,
  })
  return data
}

export async function reviewBillIncident(
  incidentId: number,
  decision: 'considered' | 'not_considered',
  centerRemarks?: string,
): Promise<WrcBillIncident> {
  const { data } = await api.post<WrcBillIncident>(`/weekly-revenue-closure/bills/${incidentId}/review`, {
    decision,
    center_remarks: centerRemarks,
  })
  return data
}

// Undoes a mistaken Considered/Not Considered click -- moves the incident
// back into the Review Queue. 400s if the incident's verdict came from
// the uploaded workbook itself rather than an actual review click.
export async function revokeBillIncidentReview(incidentId: number): Promise<WrcBillIncident> {
  const { data } = await api.post<WrcBillIncident>(`/weekly-revenue-closure/bills/${incidentId}/revoke-review`)
  return data
}

export async function markNoRemarkReceived(incidentId: number): Promise<WrcNoRemarkIncident> {
  const { data } = await api.post<WrcNoRemarkIncident>(
    `/weekly-revenue-closure/bills/${incidentId}/mark-no-remark-received`,
  )
  return data
}

export async function getActionTaken(batchId?: number): Promise<WrcBillIncident[]> {
  const { data } = await api.get<WrcBillIncident[]>('/weekly-revenue-closure/bills/action-taken', {
    params: batchId != null ? { batch_id: batchId } : undefined,
  })
  return data
}

export async function notifyIncident(incidentId: number): Promise<WrcIncidentNotifyResult> {
  const { data } = await api.post<WrcIncidentNotifyResult>(`/weekly-revenue-closure/bills/${incidentId}/notify`, {})
  return data
}

// ---------- response portal (Vigilance side) ----------

export async function generateResponseLink(batchId: number, centreCode: string): Promise<WrcResponseLinkDetail> {
  const { data } = await api.post<WrcResponseLinkDetail>(
    `/weekly-revenue-closure/batches/${batchId}/centers/${centreCode}/response-link`,
  )
  return data
}

export async function publishLinksForBatch(batchId: number): Promise<WrcBatchPublishResult> {
  const { data } = await api.post<WrcBatchPublishResult>(`/weekly-revenue-closure/batches/${batchId}/publish-links`)
  return data
}

// Read-only counterpart to publishLinksForBatch above -- fetches whichever
// links already exist for this batch WITHOUT minting/invalidating
// anything, so looking one up to copy never re-publishes (and never
// breaks a link already shared with a center). Mirrors DCB's
// getPublishedLinks in resources/delayedCash.ts.
export async function getPublishedLinksForBatch(batchId: number): Promise<WrcBatchPublishResult> {
  const { data } = await api.get<WrcBatchPublishResult>(`/weekly-revenue-closure/batches/${batchId}/links`)
  return data
}

export async function getCentersActivity(batchId?: number): Promise<WrcCenterActivity[]> {
  const { data } = await api.get<WrcCenterActivity[]>('/weekly-revenue-closure/centers-activity', {
    params: batchId != null ? { batch_id: batchId } : undefined,
  })
  return data
}

export async function getCaseResponses(caseId: number): Promise<WrcCaseResponse[]> {
  const { data } = await api.get<WrcCaseResponse[]>(`/weekly-revenue-closure/cases/${caseId}/responses`)
  return data
}

export async function downloadCaseResponseEvidence(responseId: number, filename: string): Promise<void> {
  const token = localStorage.getItem(TOKEN_STORAGE_KEY)
  const base = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000') as string
  const response = await fetch(`${base}/weekly-revenue-closure/case-responses/${responseId}/evidence`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!response.ok) throw new Error(`Download failed (${response.status})`)
  const blob = await response.blob()
  const objectUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = objectUrl
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(objectUrl)
}

// ---------- export ----------

export async function downloadBatchExport(batchId: number, weekLabel: string): Promise<void> {
  const response = await api.get(`/weekly-revenue-closure/batches/${batchId}/export.xlsx`, {
    responseType: 'blob',
  })
  const blob = new Blob([response.data], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  })
  const objectUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = objectUrl
  a.download = `${weekLabel.replace(/\s+/g, '_').replace(/\//g, '-')}-Penalty.xlsx`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(objectUrl)
}
