import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '../auth/AuthContext'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { Badge } from '../components/ui/Badge'
import { ErrorBanner, Spinner } from '../components/ui/Feedback'
import { HeroBanner } from '../components/ui/HeroBanner'
import { NetworkNodesIllustration } from '../components/ui/Illustrations'
import { Select } from '../components/ui/Select'
import { useToast } from '../components/ui/ToastProvider'
import { apiErrorMessage } from '../lib/api'
import { listDimensions, listNodes } from '../lib/resources/org'
import { assignUserOrgNode, listUsers, updateUserActive, updateUserRole } from '../lib/resources/users'
import { ROLES, type Role } from '../lib/types'

export function UsersAdminPage() {
  const { user: currentUser } = useAuth()
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [error, setError] = useState<string | null>(null)

  const { data, isLoading } = useQuery({ queryKey: ['users'], queryFn: listUsers })
  const { data: dimensions } = useQuery({ queryKey: ['org-dimensions'], queryFn: listDimensions })
  const { data: nodes } = useQuery({ queryKey: ['org-nodes'], queryFn: () => listNodes() })
  const dimensionById = new Map((dimensions ?? []).map((d) => [d.id, d]))

  const roleMutation = useMutation({
    mutationFn: ({ id, role }: { id: number; role: Role }) => updateUserRole(id, role),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      showToast('Role updated')
    },
    onError: (err) => setError(apiErrorMessage(err, 'Could not update role')),
  })

  const activeMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) => updateUserActive(id, is_active),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      showToast('Status updated')
    },
    onError: (err) => setError(apiErrorMessage(err, 'Could not update status')),
  })

  const orgNodeMutation = useMutation({
    mutationFn: ({ id, org_node_id }: { id: number; org_node_id: number | null }) =>
      assignUserOrgNode(id, org_node_id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      showToast('Org assignment updated')
    },
    onError: (err) => setError(apiErrorMessage(err, 'Could not update org assignment')),
  })

  return (
    <div className="space-y-6">
      <HeroBanner
        illustration={<NetworkNodesIllustration className="h-full w-full" />}
        kicker="Access Control"
        title="Users"
        subtitle="Every account's role and org-node scope -- role changes are audit-logged and no admin can promote or deactivate themselves."
      />

      <Card>
        <CardHeader title="All Users" />
        <CardBody>
          {isLoading && <Spinner />}
          {error && <ErrorBanner message={error} />}
          {data && (
            <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase text-slate-500">
                <tr>
                  <th className="py-2 pr-4">Username</th>
                  <th className="py-2 pr-4">Email</th>
                  <th className="py-2 pr-4">Role</th>
                  <th className="py-2 pr-4">Org Assignment</th>
                  <th className="py-2 pr-4">Status</th>
                  <th className="py-2 pr-4">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {data.map((u) => {
                  const isSelf = u.id === currentUser?.id
                  return (
                    <tr key={u.id}>
                      <td className="py-2 pr-4 font-medium">{u.username}</td>
                      <td className="py-2 pr-4 text-slate-500">{u.email}</td>
                      <td className="py-2 pr-4">
                        <Select
                          className="text-xs"
                          value={u.role}
                          disabled={isSelf || roleMutation.isPending}
                          onChange={(e) => roleMutation.mutate({ id: u.id, role: e.target.value as Role })}
                        >
                          {ROLES.map((r) => (
                            <option key={r} value={r}>
                              {r}
                            </option>
                          ))}
                        </Select>
                      </td>
                      <td className="py-2 pr-4">
                        <Select
                          className="text-xs"
                          value={u.org_node_id ?? ''}
                          disabled={orgNodeMutation.isPending}
                          onChange={(e) =>
                            orgNodeMutation.mutate({
                              id: u.id,
                              org_node_id: e.target.value ? Number(e.target.value) : null,
                            })
                          }
                        >
                          <option value="">Unassigned</option>
                          {(nodes ?? []).map((n) => (
                            <option key={n.id} value={n.id}>
                              [{dimensionById.get(n.dimension_id)?.key}] {n.name}
                              {!n.is_active ? ' (inactive)' : ''}
                            </option>
                          ))}
                        </Select>
                      </td>
                      <td className="py-2 pr-4">
                        <Badge tone="status">{u.is_active ? 'Active' : 'Inactive'}</Badge>
                      </td>
                      <td className="py-2 pr-4">
                        <button
                          className="text-xs font-medium text-brand-600 hover:underline disabled:cursor-not-allowed disabled:text-slate-400"
                          disabled={isSelf || activeMutation.isPending}
                          onClick={() => activeMutation.mutate({ id: u.id, is_active: !u.is_active })}
                          title={isSelf ? "You can't change your own status" : undefined}
                        >
                          {u.is_active ? 'Deactivate' : 'Activate'}
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            </div>
          )}
        </CardBody>
      </Card>
    </div>
  )
}
