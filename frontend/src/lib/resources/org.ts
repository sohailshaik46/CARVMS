import { api } from '../api'
import type { CenterDetail, CenterDirectoryEntry, OrgDimension, OrgNode, OrgNodeWithPath } from '../types'

export async function listDimensions(): Promise<OrgDimension[]> {
  const { data } = await api.get<OrgDimension[]>('/org/dimensions')
  return data
}

export async function createDimension(payload: { key: string; label: string; sort_order: number }): Promise<OrgDimension> {
  const { data } = await api.post<OrgDimension>('/org/dimensions', payload)
  return data
}

export async function listNodes(params?: { dimension_key?: string; parent_id?: number | null }): Promise<OrgNode[]> {
  const { data } = await api.get<OrgNode[]>('/org/nodes', { params: { ...params, limit: 500 } })
  return data
}

export async function getNode(nodeId: number): Promise<OrgNodeWithPath> {
  const { data } = await api.get<OrgNodeWithPath>(`/org/nodes/${nodeId}`)
  return data
}

export async function getCenterDetail(centerCode: string): Promise<CenterDetail> {
  const { data } = await api.get<CenterDetail>(`/org/centers/${encodeURIComponent(centerCode)}/detail`)
  return data
}

/** Every active center as a flat {code, name} list, uncapped -- what the
 * global center-search combobox is populated from (see CenterCombobox).
 * Deliberately separate from listNodes(), which is paginated/capped. */
export async function getCentersDirectory(): Promise<CenterDirectoryEntry[]> {
  const { data } = await api.get<CenterDirectoryEntry[]>('/org/centers-directory')
  return data
}

export async function createNode(payload: {
  dimension_id: number
  parent_id: number | null
  name: string
  external_code?: string | null
}): Promise<OrgNode> {
  const { data } = await api.post<OrgNode>('/org/nodes', payload)
  return data
}

export async function updateNode(
  nodeId: number,
  payload: { name?: string; external_code?: string | null; is_active?: boolean },
): Promise<OrgNode> {
  const { data } = await api.patch<OrgNode>(`/org/nodes/${nodeId}`, payload)
  return data
}
