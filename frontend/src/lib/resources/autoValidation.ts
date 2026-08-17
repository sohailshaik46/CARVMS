import { api } from '../api'
import type { AutoValidationResponse, AutoValidationRule } from '../types'

// ---------- rules (shared across DCB + WRC) ----------

export async function listAutoValidationRules(activeOnly = false): Promise<AutoValidationRule[]> {
  const { data } = await api.get<AutoValidationRule[]>('/auto-validation-rules', {
    params: activeOnly ? { active_only: true } : undefined,
  })
  return data
}

export async function createAutoValidationRule(payload: {
  bucket: 'considered' | 'not_considered'
  category: string
  keyword_phrase: string
  decision_label: string
  reason?: string
  notes?: string
  applies_to?: 'both' | 'dcb' | 'wrc'
}): Promise<AutoValidationRule> {
  const { data } = await api.post<AutoValidationRule>('/auto-validation-rules', payload)
  return data
}

export async function setAutoValidationRuleActive(ruleId: number, isActive: boolean): Promise<AutoValidationRule> {
  const { data } = await api.patch<AutoValidationRule>(`/auto-validation-rules/${ruleId}/active`, {
    is_active: isActive,
  })
  return data
}

// ---------- DCB ----------

export async function listDcbAutoValidation(bucket?: string): Promise<AutoValidationResponse[]> {
  const { data } = await api.get<AutoValidationResponse[]>('/delayed-cash/auto-validation', {
    params: bucket ? { bucket } : undefined,
  })
  return data
}

export async function reevaluateDcbResponse(responseId: number): Promise<AutoValidationResponse> {
  const { data } = await api.post<AutoValidationResponse>(`/delayed-cash/auto-validation/${responseId}/reevaluate`)
  return data
}

export async function reevaluateAllDcb(): Promise<AutoValidationResponse[]> {
  const { data } = await api.post<AutoValidationResponse[]>('/delayed-cash/auto-validation/reevaluate-all')
  return data
}

export async function overrideDcbResponse(
  responseId: number,
  bucket: string,
  note?: string,
): Promise<AutoValidationResponse> {
  const { data } = await api.post<AutoValidationResponse>(`/delayed-cash/auto-validation/${responseId}/override`, {
    bucket,
    note,
  })
  return data
}

// ---------- WRC ----------

export async function listWrcAutoValidation(bucket?: string): Promise<AutoValidationResponse[]> {
  const { data } = await api.get<AutoValidationResponse[]>('/weekly-revenue-closure/auto-validation', {
    params: bucket ? { bucket } : undefined,
  })
  return data
}

export async function reevaluateWrcResponse(responseId: number): Promise<AutoValidationResponse> {
  const { data } = await api.post<AutoValidationResponse>(
    `/weekly-revenue-closure/auto-validation/${responseId}/reevaluate`,
  )
  return data
}

export async function reevaluateAllWrc(): Promise<AutoValidationResponse[]> {
  const { data } = await api.post<AutoValidationResponse[]>('/weekly-revenue-closure/auto-validation/reevaluate-all')
  return data
}

export async function overrideWrcResponse(
  responseId: number,
  bucket: string,
  note?: string,
): Promise<AutoValidationResponse> {
  const { data } = await api.post<AutoValidationResponse>(
    `/weekly-revenue-closure/auto-validation/${responseId}/override`,
    { bucket, note },
  )
  return data
}

// ---------- combined export ----------

export async function downloadAutoValidationExport(): Promise<void> {
  const response = await api.get('/auto-validation/export.xlsx', { responseType: 'blob' })
  const blob = new Blob([response.data], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  })
  const objectUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = objectUrl
  a.download = 'auto_validation_report.xlsx'
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(objectUrl)
}
