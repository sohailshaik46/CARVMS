import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '../auth/AuthContext'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { Badge } from '../components/ui/Badge'
import { ErrorBanner, Spinner } from '../components/ui/Feedback'
import { HeroBanner } from '../components/ui/HeroBanner'
import { NetworkNodesIllustration } from '../components/ui/Illustrations'
import { Select } from '../components/ui/Select'
import { Tooltip } from '../components/ui/Tooltip'
import { useToast } from '../components/ui/ToastProvider'
import { apiErrorMessage } from '../lib/api'
import { listDimensions, listNodes } from '../lib/resources/org'
import { assignUserOrgNode, listUsers, updateUserActive, updateUserPhoneNumber, updateUserRole } from '../lib/resources/users'
import { ROLES, type Role, type UserAdminOut } from '../lib/types'

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

  const phoneMutation = useMutation({
    mutationFn: ({ id, phone_number }: { id: number; phone_number: string }) => updateUserPhoneNumber(id, phone_number),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      showToast('Phone number updated')
    },
    onError: (err) => setError(apiErrorMessage(err, 'Could not update phone number -- use international format, e.g. +919876543210')),
  })

  return (
    <div className="space-y-6">
      <HeroBanner
        illustration={<NetworkNodesIllustration className="h-full w-full" />}
        kicker="Access Control"
        title="Users"
        subtitle="Every account's role, org-node scope, and mobile number -- role changes are audit-logged and no admin can promote or deactivate themselves."
      />

      <Card>
        <CardHeader title="All Users" />
        <CardBody>
          {isLoading && <Spinner />}
          {error && <ErrorBanner message={error} />}
          {data && (
            <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase text-slate-500 dark:text-slate-400">
                <tr>
                  <th className="py-2 pr-4">Username</th>
                  <th className="py-2 pr-4">Email</th>
                  <th className="py-2 pr-4">
                    <Tooltip text="Where THIS user's own password-reset OTP and case-deadline escalation alerts are sent -- never a shared number.">
                      <span className="cursor-help underline decoration-dotted">Mobile Number</span>
                    </Tooltip>
                  </th>
                  <th className="py-2 pr-4">Role</th>
                  <th className="py-2 pr-4">Org Assignment</th>
                  <th className="py-2 pr-4">Status</th>
                  <th className="py-2 pr-4">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
                {data.map((u) => {
                  const isSelf = u.id === currentUser?.id
                  return (
                    <tr key={u.id}>
                      <td className="py-2 pr-4 font-medium text-slate-800 dark:text-slate-100">{u.username}</td>
                      <td className="py-2 pr-4 text-slate-500 dark:text-slate-400">{u.email}</td>
                      <td className="py-2 pr-4">
                        <PhoneNumberCell
                          value={u.phone_number}
                          disabled={phoneMutation.isPending}
                          onSave={(phone_number) => phoneMutation.mutate({ id: u.id, phone_number })}
                        />
                      </td>
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
                          className="text-xs font-medium text-np-calming-blue hover:underline disabled:cursor-not-allowed disabled:text-slate-400 dark:text-neon-blue-400 dark:disabled:text-slate-500"
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

/** Click-to-edit mobile number cell -- shown as plain text until clicked,
 * then becomes a text input; Enter or blur saves, Escape cancels. Kept
 * local to this file since no other page needs to edit someone else's
 * phone number (a user's own number is edited in Settings instead). */
function PhoneNumberCell({
  value,
  disabled,
  onSave,
}: {
  value: UserAdminOut['phone_number']
  disabled: boolean
  onSave: (phoneNumber: string) => void
}) {
  const [isEditing, setIsEditing] = useState(false)
  const [draft, setDraft] = useState(value ?? '')

  function startEditing() {
    setDraft(value ?? '')
    setIsEditing(true)
  }

  function commit() {
    setIsEditing(false)
    const trimmed = draft.trim()
    if (trimmed && trimmed !== value) onSave(trimmed)
  }

  if (!isEditing) {
    return (
      <button
        type="button"
        onClick={startEditing}
        className="text-left text-slate-500 hover:text-np-calming-blue dark:text-slate-400 dark:hover:text-neon-blue-400"
        title="Click to set/change this user's mobile number"
      >
        {value ?? <span className="italic text-amber-600 dark:text-amber-400">Not set</span>}
      </button>
    )
  }

  return (
    <input
      autoFocus
      type="tel"
      className="w-36 rounded border border-slate-300 bg-white px-1.5 py-0.5 text-xs text-slate-800 dark:border-slate-600 dark:bg-void-900 dark:text-slate-100"
      value={draft}
      disabled={disabled}
      placeholder="+919876543210"
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === 'Enter') commit()
        if (e.key === 'Escape') setIsEditing(false)
      }}
    />
  )
}
