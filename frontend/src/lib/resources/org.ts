import { api } from '../api'
import type { CenterDetail, CenterDirectoryEntry, OrgDimension, OrgNode, OrgNodeWithPath, RemoteSyncReport } from '../types'

export async function listDimensions(): Promise<OrgDimension[]> {
  const { data } = await api.get<OrgDimension[]>('/org/dimensions')
  return data
}

export async function createDimension(payload: { key: string; label: string; sort_order: number }): Promise<OrgDimension> {
  const { data } = await api.post<OrgDimension>('/org/dimensions', payload)
  return data
}

/** limit is 5000, not the old 500 -- the real Org Master already has 846
 * nodes, so 500 silently hid ~346 of them from the Nodes table. Matches
 * the server-side cap in GET /org/nodes / org_service.list_nodes. */
export async function listNodes(params?: { dimension_key?: string; parent_id?: number | null }): Promise<OrgNode[]> {
  const { data } = await api.get<OrgNode[]>('/org/nodes', { params: { ...params, limit: 5000 } })
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

/** Whether THIS instance can even attempt a remote sync -- shared by all
 * three Data Sync cards (Org Master, DCB, WRC), since they all gate on
 * the exact same REMOTE_DATABASE_URL setting. Lets each card hide
 * itself on an instance (e.g. Render) where sync was never configured,
 * rather than showing Push/Pull buttons that only ever error. */
export async function getRemoteSyncStatus(): Promise<{ configured: boolean }> {
  const { data } = await api.get<{ configured: boolean }>('/org/sync/remote/status')
  return data
}

/** Manual Org Master sync against REMOTE_DATABASE_URL -- never automatic.
 * commit=false (the default) previews the diff and writes nothing; call
 * again with commit=true once the preview looks right. Never deletes
 * anything on the receiving side (see org_master_remote_sync_service). */
export async function pushOrgMasterToRemote(commit: boolean): Promise<RemoteSyncReport> {
  const { data } = await api.post<RemoteSyncReport>('/org/sync/remote/push', null, { params: { commit } })
  return data
}

export async function pullOrgMasterFromRemote(commit: boolean): Promise<RemoteSyncReport> {
  const { data } = await api.post<RemoteSyncReport>('/org/sync/remote/pull', null, { params: { commit } })
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
