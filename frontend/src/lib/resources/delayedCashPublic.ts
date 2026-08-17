import { api } from '../api'
import type {
  CenterDirectoryEntry,
  DelayedCashCaseResponseOut,
  PublicDelayedCashCase,
  PublicOpenDelayedCashCase,
} from '../types'

export async function getPublicDelayedCashCase(token: string): Promise<PublicDelayedCashCase> {
  const { data } = await api.get<PublicDelayedCashCase>(`/public/delayed-cash/cases/${token}`)
  return data
}

export async function getCenterDirectory(): Promise<CenterDirectoryEntry[]> {
  const { data } = await api.get<CenterDirectoryEntry[]>('/public/delayed-cash/centers-directory')
  return data
}

// Single shared link: every case still open for the given center, found by
// picking a center from the directory above instead of holding a token.
export async function getOpenCasesForCenter(centreCode: string): Promise<PublicOpenDelayedCashCase[]> {
  const { data } = await api.get<PublicOpenDelayedCashCase[]>('/public/delayed-cash/open-cases', {
    params: { centre_code: centreCode },
  })
  return data
}

interface ResponseFields {
  responder_name: string
  responder_npid: string
  responder_email: string
  reason: string
  selected_center_code?: string
  selected_center_name?: string
}

function buildResponseForm(fields: ResponseFields, evidence: File): FormData {
  const form = new FormData()
  form.append('responder_name', fields.responder_name)
  form.append('responder_npid', fields.responder_npid)
  form.append('responder_email', fields.responder_email)
  form.append('reason', fields.reason)
  if (fields.selected_center_code) form.append('selected_center_code', fields.selected_center_code)
  if (fields.selected_center_name) form.append('selected_center_name', fields.selected_center_name)
  form.append('evidence', evidence)
  return form
}

export async function submitDelayedCashCaseResponse(
  token: string,
  fields: ResponseFields,
  evidence: File,
): Promise<DelayedCashCaseResponseOut> {
  const { data } = await api.post<DelayedCashCaseResponseOut>(
    `/public/delayed-cash/cases/${token}/respond`,
    buildResponseForm(fields, evidence),
    { headers: { 'Content-Type': 'multipart/form-data' } },
  )
  return data
}

// Same submission, reached via the single shared link (no token) -- the
// responder picked their case's id from getOpenCasesForCenter above.
export async function submitDelayedCashCaseResponseById(
  centerPenaltyId: number,
  fields: ResponseFields,
  evidence: File,
): Promise<DelayedCashCaseResponseOut> {
  const { data } = await api.post<DelayedCashCaseResponseOut>(
    `/public/delayed-cash/cases/by-id/${centerPenaltyId}/respond`,
    buildResponseForm(fields, evidence),
    { headers: { 'Content-Type': 'multipart/form-data' } },
  )
  return data
}
