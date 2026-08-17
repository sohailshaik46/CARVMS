import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '../../auth/AuthContext'
import { Card, CardBody, CardHeader } from '../../components/ui/Card'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { TextField } from '../../components/ui/Field'
import { ErrorBanner, Spinner } from '../../components/ui/Feedback'
import { Modal } from '../../components/ui/Modal'
import { Select } from '../../components/ui/Select'
import { Tooltip } from '../../components/ui/Tooltip'
import { useToast } from '../../components/ui/ToastProvider'
import { apiErrorMessage } from '../../lib/api'
import { listDimensions, listNodes } from '../../lib/resources/org'
import {
  assignUserOrgNode,
  createUserAsAdmin,
  listUsers,
  updateUserActive,
  updateUserPhoneNumber,
  updateUserRole,
} from '../../lib/resources/users'
import { ROLES, type Role, type UserAdminOut } from '../../lib/types'

/** Admin-only. Public self-registration (the Register page) stays
 * available for anyone -- this is the ADDITIONAL path where an Admin hands
 * someone a ready-made account with a real role already set, per the
 * user's explicit choice to keep both rather than replace one with the
 * other. Only an Admin ever sees this tab at all (gated in SettingsPage). */
export function UsersTab() {
  const { user: currentUser } = useAuth()
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [error, setError] = useState<string | null>(null)
  const [isCreateOpen, setIsCreateOpen] = useState(false)

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
      <Card>
        <CardHeader
          title="All Users"
          actions={
            <Tooltip text="Creates a ready-made account with a role already set -- the person can log in immediately, no self-registration or promotion step needed. Only you (an Admin) can do this.">
              <Button onClick={() => setIsCreateOpen(true)}>Create User</Button>
            </Tooltip>
          }
        />
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
                    <th className="py-2 pr-4">
                      <Tooltip text="What this user is allowed to do -- checked server-side on every request, never just hidden in the UI. Changing it is audit-logged.">
                        <span className="cursor-help underline decoration-dotted">Role</span>
                      </Tooltip>
                    </th>
                    <th className="py-2 pr-4">
                      <Tooltip text="The center/cluster/zone this user is anchored to, if any -- scopes what a Center/Cluster/Zonal Manager role can see. Admin/Auditor/Finance aren't scoped to one.">
                        <span className="cursor-help underline decoration-dotted">Org Assignment</span>
                      </Tooltip>
                    </th>
                    <th className="py-2 pr-4">
                      <Tooltip text="Inactive users can't log in at all, but their history/audit trail is kept -- use this instead of deleting an account.">
                        <span className="cursor-help underline decoration-dotted">Status</span>
                      </Tooltip>
                    </th>
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
                          <Tooltip
                            text={
                              isSelf
                                ? "You can't deactivate your own account -- prevents an accidental self-lockout."
                                : u.is_active
                                  ? 'Deactivated users keep their history but can no longer log in.'
                                  : 'Reactivates this account -- they can log in again immediately.'
                            }
                          >
                            <button
                              className="text-xs font-medium text-np-calming-blue hover:underline disabled:cursor-not-allowed disabled:text-slate-400 dark:text-neon-blue-400 dark:disabled:text-slate-500"
                              disabled={isSelf || activeMutation.isPending}
                              onClick={() => activeMutation.mutate({ id: u.id, is_active: !u.is_active })}
                            >
                              {u.is_active ? 'Deactivate' : 'Activate'}
                            </button>
                          </Tooltip>
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

      {isCreateOpen && <CreateUserModal onClose={() => setIsCreateOpen(false)} />}
    </div>
  )
}

function CreateUserModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [phoneNumber, setPhoneNumber] = useState('')
  const [role, setRole] = useState<Role>('Auditor')
  const [error, setError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: () =>
      createUserAsAdmin({
        username,
        email,
        password,
        phone_number: phoneNumber || undefined,
        role,
      }),
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      showToast(`Account created for ${created.username}`)
      onClose()
    },
    onError: (err) => setError(apiErrorMessage(err, 'Could not create user')),
  })

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    mutation.mutate()
  }

  return (
    <Modal title="Create User" onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && <ErrorBanner message={error} />}
        <p className="text-xs text-slate-500 dark:text-slate-400">
          Creates a real, ready-to-use account -- no email verification or self-registration step. Give the login
          details to the person directly.
        </p>
        <TextField id="cu-username" label="Username" required minLength={3} value={username} onChange={(e) => setUsername(e.target.value)} />
        <TextField id="cu-email" label="Email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        <TextField
          id="cu-password"
          label="Password"
          type="password"
          required
          minLength={8}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <TextField
          id="cu-phone"
          label="Mobile number (optional)"
          type="tel"
          placeholder="+919876543210"
          value={phoneNumber}
          onChange={(e) => setPhoneNumber(e.target.value)}
        />
        <div>
          <label htmlFor="cu-role" className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
            Role
          </label>
          <Select id="cu-role" value={role} onChange={(e) => setRole(e.target.value as Role)}>
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </Select>
        </div>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" isLoading={mutation.isPending}>
            Create
          </Button>
        </div>
      </form>
    </Modal>
  )
}

/** Click-to-edit mobile number cell -- shown as plain text until clicked,
 * then becomes a text input; Enter or blur saves, Escape cancels. */
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
