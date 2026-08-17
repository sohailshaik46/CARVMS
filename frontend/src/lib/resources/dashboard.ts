import { api, TOKEN_STORAGE_KEY } from '../api'
import type { DashboardFilters, DashboardSummary } from '../types'

export async function fetchDashboardSummary(filters: DashboardFilters): Promise<DashboardSummary> {
  const { data } = await api.get<DashboardSummary>('/dashboard/summary', { params: filters })
  return data
}

export type ExportFormat = 'csv' | 'xlsx' | 'pdf' | 'docx' | 'pptx'

/** Builds a direct download URL for the given filters. The browser needs
 * the auth header too, so we can't just <a href>; see downloadExport(). */
function exportUrl(format: ExportFormat, filters: DashboardFilters): string {
  const base = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000') as string
  const params = new URLSearchParams()
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value))
  })
  return `${base}/reports/billing/export.${format}?${params.toString()}`
}

export async function downloadExport(format: ExportFormat, filters: DashboardFilters): Promise<void> {
  const token = localStorage.getItem(TOKEN_STORAGE_KEY)
  const response = await fetch(exportUrl(format, filters), {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!response.ok) {
    throw new Error(`Export failed (${response.status})`)
  }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `billing_compliance_export.${format}`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
