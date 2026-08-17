import { api } from '../api'
import type { Role, UserAdminOut } from '../types'

export interface AdminUserCreatePayload {
  username: string
  email: string
  password: string
  phone_number?: string
  role?: Role
}

export async function listUsers(): Promise<UserAdminOut[]> {
  const { data } = await api.get<UserAdminOut[]>('/users', { params: { limit: 200 } })
  return data
}

export async function createUserAsAdmin(payload: AdminUserCreatePayload): Promise<UserAdminOut> {
  const { data } = await api.post<UserAdminOut>('/users', payload)
  return data
}

export async function updateUserRole(userId: number, role: Role): Promise<UserAdminOut> {
  const { data } = await api.patch<UserAdminOut>(`/users/${userId}/role`, { role })
  return data
}

export async function updateUserActive(userId: number, is_active: boolean): Promise<UserAdminOut> {
  const { data } = await api.patch<UserAdminOut>(`/users/${userId}/active`, { is_active })
  return data
}

export async function assignUserOrgNode(userId: number, org_node_id: number | null): Promise<UserAdminOut> {
  const { data } = await api.patch<UserAdminOut>(`/users/${userId}/org-node`, { org_node_id })
  return data
}

export async function updateUserPhoneNumber(userId: number, phone_number: string): Promise<UserAdminOut> {
  const { data } = await api.patch<UserAdminOut>(`/users/${userId}/phone`, { phone_number })
  return data
}
