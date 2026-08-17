import { api } from '../api'
import type { DashboardLayout, DashboardLayoutConfig } from '../types'

export async function listDashboardLayouts(): Promise<DashboardLayout[]> {
  const { data } = await api.get<DashboardLayout[]>('/dashboard-layouts')
  return data
}

export async function createDashboardLayout(payload: {
  name: string
  description?: string | null
  config: DashboardLayoutConfig
  is_shared?: boolean
}): Promise<DashboardLayout> {
  const { data } = await api.post<DashboardLayout>('/dashboard-layouts', payload)
  return data
}

export async function deleteDashboardLayout(id: number): Promise<void> {
  await api.delete(`/dashboard-layouts/${id}`)
}
