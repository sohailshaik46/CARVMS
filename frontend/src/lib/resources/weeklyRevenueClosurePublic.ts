import { api } from '../api'
import type { CenterDirectoryEntry, WrcCaseResponse, WrcPublicCase, WrcPublicOpenCase } from '../types'

export async function getPublicWrcCase(token: string): Promise<WrcPublicCase> {
  const { data } = await api.get<WrcPublicCase>(`/public/weekly-revenue/cases/${token}`)
  return data
}

export async function getWrcCenterDirectory(): Promise<CenterDirectoryEntry[]> {
  const { data } = await api.get<CenterDirectoryEntry[]>('/public/weekly-revenue/centers-directory')
  return data
}

export async function getWrcOpenCasesForCenter(centreCode: string): Promise<WrcPublicOpenCase[]> {
  const { data } = await api.get<WrcPublicOpenCase[]>('/public/weekly-revenue/open-cases', {
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

export async function submitWrcCaseResponse(token: string, fields: ResponseFields, evidence: File): Promise<WrcCaseResponse> {
  const { data } = await api.post<WrcCaseResponse>(
    `/public/weekly-revenue/cases/${token}/respond`,
    buildResponseForm(fields, evidence),
    { headers: { 'Content-Type': 'multipart/form-data' } },
  )
  return data
}

export async function submitWrcCaseResponseById(caseId: number, fields: ResponseFields, evidence: File): Promise<WrcCaseResponse> {
  const { data } = await api.post<WrcCaseResponse>(
    `/public/weekly-revenue/cases/by-id/${caseId}/respond`,
    buildResponseForm(fields, evidence),
    { headers: { 'Content-Type': 'multipart/form-data' } },
  )
  return data
}
