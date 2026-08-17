import { api, TOKEN_STORAGE_KEY } from '../api'
import type { DashboardFilters, ReportFormat, ReportHistoryEntry, ReportTemplate } from '../types'

export async function listReportTemplates(): Promise<ReportTemplate[]> {
  const { data } = await api.get<ReportTemplate[]>('/report-templates')
  return data
}

export async function createReportTemplate(payload: {
  name: string
  description?: string | null
  filters: DashboardFilters
}): Promise<ReportTemplate> {
  const { data } = await api.post<ReportTemplate>('/report-templates', payload)
  return data
}

export async function deleteReportTemplate(id: number): Promise<void> {
  await api.delete(`/report-templates/${id}`)
}

export async function listReportHistory(): Promise<ReportHistoryEntry[]> {
  const { data } = await api.get<ReportHistoryEntry[]>('/report-history')
  return data
}

function base(): string {
  return (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000') as string
}

async function downloadBlob(url: string, filenameFallback: string): Promise<void> {
  const token = localStorage.getItem(TOKEN_STORAGE_KEY)
  const response = await fetch(url, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail ?? `Request failed (${response.status})`)
  }
  const blob = await response.blob()
  const objectUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = objectUrl
  a.download = filenameFallback
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(objectUrl)
}

export async function runTemplate(templateId: number, format: ReportFormat): Promise<void> {
  await downloadBlob(`${base()}/report-templates/${templateId}/run?format=${format}`, `report.${format}`)
}

export async function regenerateReport(historyId: number, format?: ReportFormat): Promise<void> {
  const params = format ? `?format=${format}` : ''
  await downloadBlob(`${base()}/report-history/${historyId}/regenerate${params}`, `report.${format ?? 'csv'}`)
}
