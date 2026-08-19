import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Combobox } from '../components/ui/Combobox'
import { SelectField, TextField } from '../components/ui/Field'
import { ErrorBanner, Spinner } from '../components/ui/Feedback'
import { HeroBanner } from '../components/ui/HeroBanner'
import { NetworkNodesIllustration } from '../components/ui/Illustrations'
import { Tooltip } from '../components/ui/Tooltip'
import { useToast } from '../components/ui/ToastProvider'
import { apiErrorMessage } from '../lib/api'
import {
  createDimension,
  createNode,
  getCenterDetail,
  getCentersDirectory,
  listDimensions,
  listNodes,
  pullOrgMasterFromRemote,
  pushOrgMasterToRemote,
  updateNode,
} from '../lib/resources/org'
import type { CenterDetail, OrgNode, RemoteSyncReport } from '../lib/types'

export function OrgAdminPage() {
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [error, setError] = useState<string | null>(null)

  const { data: dimensions, isLoading: dimensionsLoading } = useQuery({
    queryKey: ['org-dimensions'],
    queryFn: listDimensions,
  })
  const { data: nodes, isLoading: nodesLoading } = useQuery({ queryKey: ['org-nodes'], queryFn: () => listNodes() })

  const dimensionMutation = useMutation({
    mutationFn: (payload: { key: string; label: string; sort_order: number }) => createDimension(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['org-dimensions'] })
      showToast('Dimension created')
    },
    onError: (err) => setError(apiErrorMessage(err, 'Could not create dimension')),
  })

  const nodeMutation = useMutation({
    mutationFn: (payload: { dimension_id: number; parent_id: number | null; name: string; external_code: string | null }) =>
      createNode(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['org-nodes'] })
      showToast('Node created')
    },
    onError: (err) => setError(apiErrorMessage(err, 'Could not create node')),
  })

  const updateNodeMutation = useMutation({
    mutationFn: ({ id, ...payload }: { id: number; is_active?: boolean; external_code?: string | null }) =>
      updateNode(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['org-nodes'] })
      showToast('Node updated')
    },
    onError: (err) => setError(apiErrorMessage(err, 'Could not update node')),
  })

  const dimensionById = new Map((dimensions ?? []).map((d) => [d.id, d]))
  const nodeById = new Map((nodes ?? []).map((n) => [n.id, n]))

  return (
    <div className="space-y-6">
      <HeroBanner
        illustration={<NetworkNodesIllustration className="h-full w-full" />}
        kicker="Org Master"
        title="Organization Hierarchy"
        subtitle="Zones, clusters, and centers -- the structure every audit, penalty, and ranking is scoped against."
      />
      {error && <ErrorBanner message={error} />}

      <CenterLookupCard />

      <RemoteSyncCard />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="Dimensions" />
          <CardBody className="space-y-4">
            {dimensionsLoading && <Spinner />}
            {dimensions && (
              <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs uppercase text-slate-500 dark:text-slate-400">
                  <tr>
                    <th className="py-1 pr-4">Key</th>
                    <th className="py-1 pr-4">Label</th>
                    <th className="py-1 pr-4">Order</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
                  {dimensions.map((d) => (
                    <tr key={d.id}>
                      <td className="py-1 pr-4 font-mono text-xs text-slate-800 dark:text-slate-100">{d.key}</td>
                      <td className="py-1 pr-4 text-slate-800 dark:text-slate-100">{d.label}</td>
                      <td className="py-1 text-slate-800 dark:text-slate-100">{d.sort_order}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            )}

            <NewDimensionForm
              onSubmit={(payload) => dimensionMutation.mutate(payload)}
              isPending={dimensionMutation.isPending}
            />
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Nodes" />
          <CardBody className="space-y-4">
            {nodesLoading && <Spinner />}
            {nodes && nodes.length === 0 && <p className="text-sm text-slate-500 dark:text-slate-400">No nodes created yet.</p>}
            {nodes && nodes.length > 0 && (
              <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs uppercase text-slate-500 dark:text-slate-400">
                  <tr>
                    <th className="py-1 pr-4">Name</th>
                    <th className="py-1 pr-4">Dimension</th>
                    <th className="py-1 pr-4">Parent</th>
                    <th className="py-1 pr-4">Code</th>
                    <th className="py-1 pr-4">Status</th>
                    <th className="py-1 pr-4">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
                  {nodes.map((n) => (
                    <NodeRow
                      key={n.id}
                      node={n}
                      dimensionKey={dimensionById.get(n.dimension_id)?.key}
                      parentName={n.parent_id ? nodeById.get(n.parent_id)?.name ?? String(n.parent_id) : '—'}
                      onUpdate={(payload) => updateNodeMutation.mutate({ id: n.id, ...payload })}
                      isPending={updateNodeMutation.isPending}
                    />
                  ))}
                </tbody>
              </table>
              </div>
            )}

            <NewNodeForm
              dimensions={dimensions ?? []}
              nodes={nodes ?? []}
              dimensionById={dimensionById}
              onSubmit={(payload) => nodeMutation.mutate(payload)}
              isPending={nodeMutation.isPending}
            />
          </CardBody>
        </Card>
      </div>
    </div>
  )
}

function CenterLookupCard() {
  const [input, setInput] = useState('')
  const [centerCode, setCenterCode] = useState<string | null>(null)

  const { data: directory } = useQuery({ queryKey: ['org-centers-directory'], queryFn: getCentersDirectory })

  const { data, isFetching, error, isError } = useQuery({
    queryKey: ['org-center-detail', centerCode],
    queryFn: () => getCenterDetail(centerCode as string),
    enabled: centerCode !== null,
    retry: false,
  })

  const options = (directory ?? [])
    .slice()
    .sort((a, b) => a.code.localeCompare(b.code))
    .map((c) => ({ value: c.code, label: `${c.code} -- ${c.name}`, searchText: c.name }))

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const trimmed = input.trim()
    if (trimmed) setCenterCode(trimmed)
  }

  return (
    <Card>
      <CardHeader
        title="Center Lookup"
        actions={
          <Tooltip text="Look up everything about one center -- who's the Center Manager (and their NPID/email), which cluster and zone it sits under, and who to escalate to at each level (Cluster Manager, Zonal Manager, Half Country Head).">
            <span className="text-xs text-slate-400 dark:text-slate-500">What is this?</span>
          </Tooltip>
        }
      />
      <CardBody className="space-y-4">
        <form onSubmit={handleSubmit} className="flex flex-wrap items-end gap-2">
          <div className="w-72">
            <label htmlFor="center-lookup-code" className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
              Center Code or Name
            </label>
            <Tooltip text="Type any part of a center's code or name (e.g. just '173') to search -- pick a match from the dropdown, or type a full code and press Enter/Look up.">
              <Combobox
                id="center-lookup-code"
                placeholder="e.g. 173 or Ongole…"
                value={input}
                onChange={setInput}
                onCommit={(code) => {
                  if (code) setCenterCode(code)
                }}
                options={options}
              />
            </Tooltip>
          </div>
          <Button type="submit" isLoading={isFetching}>
            Look up
          </Button>
        </form>

        {isError && <ErrorBanner message={apiErrorMessage(error, 'Center not found')} />}

        {data && <CenterDetailGrid detail={data} />}
      </CardBody>
    </Card>
  )
}

/** Manual, explicit Org Master sync against Render's live database --
 * NEVER automatic (see org_master_remote_sync_service's module docstring
 * for the full safety contract). Each direction is a two-step flow:
 * "Preview" (commit=false) shows exactly what would change with zero
 * writes, then "Apply" (commit=true) is the only thing that actually
 * writes -- and only after a preview has been run, so nothing happens
 * from a single accidental click. Never deletes anything either way. */
function RemoteSyncCard() {
  const { showToast } = useToast()
  const [pushPreview, setPushPreview] = useState<RemoteSyncReport | null>(null)
  const [pullPreview, setPullPreview] = useState<RemoteSyncReport | null>(null)
  const [notConfigured, setNotConfigured] = useState<string | null>(null)

  function handleError(err: unknown) {
    const message = apiErrorMessage(err, 'Sync failed')
    setNotConfigured(message)
    showToast(message, 'error')
  }

  const pushPreviewMutation = useMutation({
    mutationFn: () => pushOrgMasterToRemote(false),
    onSuccess: (report) => {
      setNotConfigured(null)
      setPushPreview(report)
    },
    onError: handleError,
  })
  const pushApplyMutation = useMutation({
    mutationFn: () => pushOrgMasterToRemote(true),
    onSuccess: (report) => {
      setPushPreview(null)
      showToast(
        `Pushed to Render: ${report.dimensions_created + report.nodes_created} created, ${report.dimensions_updated + report.nodes_updated} updated.`,
      )
    },
    onError: handleError,
  })

  const pullPreviewMutation = useMutation({
    mutationFn: () => pullOrgMasterFromRemote(false),
    onSuccess: (report) => {
      setNotConfigured(null)
      setPullPreview(report)
    },
    onError: handleError,
  })
  const pullApplyMutation = useMutation({
    mutationFn: () => pullOrgMasterFromRemote(true),
    onSuccess: (report) => {
      setPullPreview(null)
      showToast(
        `Pulled from Render: ${report.dimensions_created + report.nodes_created} created, ${report.dimensions_updated + report.nodes_updated} updated.`,
      )
    },
    onError: handleError,
  })

  return (
    <Card>
      <CardHeader
        title="Data Sync with Render"
        actions={
          <Tooltip text="Manual only -- nothing here ever runs automatically or in the background. Push copies THIS computer's Org Master (centers, zones, clusters, managers) up to the live Render database; Pull copies Render's Org Master down to this computer. Neither one ever deletes anything on either side -- a row missing on one side is only ever added, never removed from the side that has it. Each button previews the exact changes first (writes nothing); a second click actually applies them.">
            <span className="text-xs text-slate-400 dark:text-slate-500">What is this?</span>
          </Tooltip>
        }
      />
      <CardBody className="space-y-4">
        {notConfigured && <ErrorBanner message={notConfigured} />}

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <RemoteSyncDirection
            title="Push to Render"
            description="Send this computer's Org Master up to the live Render database."
            preview={pushPreview}
            isPreviewing={pushPreviewMutation.isPending}
            isApplying={pushApplyMutation.isPending}
            onPreview={() => pushPreviewMutation.mutate()}
            onApply={() => pushApplyMutation.mutate()}
            onCancel={() => setPushPreview(null)}
          />
          <RemoteSyncDirection
            title="Pull from Render"
            description="Bring Render's live Org Master down to this computer."
            preview={pullPreview}
            isPreviewing={pullPreviewMutation.isPending}
            isApplying={pullApplyMutation.isPending}
            onPreview={() => pullPreviewMutation.mutate()}
            onApply={() => pullApplyMutation.mutate()}
            onCancel={() => setPullPreview(null)}
          />
        </div>
      </CardBody>
    </Card>
  )
}

function RemoteSyncDirection({
  title,
  description,
  preview,
  isPreviewing,
  isApplying,
  onPreview,
  onApply,
  onCancel,
}: {
  title: string
  description: string
  preview: RemoteSyncReport | null
  isPreviewing: boolean
  isApplying: boolean
  onPreview: () => void
  onApply: () => void
  onCancel: () => void
}) {
  const totalChanges = preview
    ? preview.dimensions_created + preview.dimensions_updated + preview.nodes_created + preview.nodes_updated
    : 0

  return (
    <div className="rounded-md border border-slate-200 p-3 dark:border-slate-700">
      <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">{title}</p>
      <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{description}</p>

      {!preview && (
        <Button className="mt-3" variant="secondary" isLoading={isPreviewing} onClick={onPreview}>
          Preview
        </Button>
      )}

      {preview && (
        <div className="mt-3 space-y-2">
          <div className="rounded-md border border-amber-300 bg-amber-50 p-2 text-xs text-amber-800 dark:border-amber-800 dark:bg-amber-500/10 dark:text-amber-300">
            <p className="font-semibold">Nothing has been written yet -- this is a preview.</p>
            <p className="mt-1">
              {preview.dimensions_created + preview.nodes_created} row(s) would be created,{' '}
              {preview.dimensions_updated + preview.nodes_updated} would be updated,{' '}
              {preview.dimensions_unchanged + preview.nodes_unchanged} are already identical.
            </p>
            {preview.changed_node_names.length > 0 && (
              <ul className="mt-2 max-h-32 list-disc space-y-0.5 overflow-y-auto pl-4">
                {preview.changed_node_names.map((name, i) => (
                  <li key={i}>{name}</li>
                ))}
              </ul>
            )}
          </div>
          <div className="flex gap-2">
            <Button
              variant="danger"
              isLoading={isApplying}
              disabled={totalChanges === 0}
              onClick={onApply}
            >
              Apply {totalChanges} change(s)
            </Button>
            <Button variant="secondary" onClick={onCancel} disabled={isApplying}>
              Cancel
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

function CenterDetailGrid({ detail }: { detail: CenterDetail }) {
  return (
    <div className="grid grid-cols-1 gap-4 border-t border-slate-200 pt-4 sm:grid-cols-2 lg:grid-cols-4 dark:border-slate-700">
      <DetailField
        label="Center"
        value={`${detail.center_code} -- ${detail.center_name}`}
        tooltip="This center's own code and name, exactly as they appear in the Org Master."
      />
      <DetailField
        label="Status"
        value={detail.is_active ? 'Active' : 'Inactive'}
        tooltip="Whether this center is currently active in the Org Master -- an inactive center is excluded from remark-automation lookups by default."
      />
      <DetailField
        label="Center Manager"
        value={detail.center_manager_name}
        tooltip="The person in charge at this specific center (Center Incharge)."
      />
      <DetailField
        label="Center Manager NPID"
        value={detail.center_manager_npid}
        tooltip="The Center Manager's NephroPlus employee ID (NPID)."
      />
      <DetailField
        label="Center Email"
        value={detail.center_manager_email}
        tooltip="This center's own email address -- where 'Notify Center' emails in DCB/WRC are sent."
      />
      <DetailField
        label="Center Phone"
        value={detail.center_manager_phone}
        tooltip="The Center Manager's phone number, if on file."
      />
      <DetailField
        label="Cluster Manager"
        value={detail.cluster_manager_name}
        tooltip="This center's Cluster Manager -- a cluster has no separate name of its own; it's identified only by who manages it."
      />
      <DetailField
        label="Cluster Manager Email"
        value={detail.cluster_manager_email}
        tooltip="The Cluster Manager's email -- who this center's escalations go to first."
      />
      <DetailField
        label="Cluster Manager Phone"
        value={detail.cluster_manager_phone}
        tooltip="The Cluster Manager's phone number, if on file."
      />
      <DetailField
        label="Zone"
        value={detail.zone_name}
        tooltip="The zone this center's cluster sits under."
      />
      <DetailField
        label="Zonal Manager"
        value={detail.zonal_manager_name}
        tooltip="Who manages this center's entire zone -- the next level of escalation above the Cluster Manager."
      />
      <DetailField
        label="Zonal Manager Email"
        value={detail.zonal_manager_email}
        tooltip="The Zonal Manager's email."
      />
      <DetailField
        label="Zonal Manager Phone"
        value={detail.zonal_manager_phone}
        tooltip="The Zonal Manager's phone number, if on file."
      />
      <DetailField
        label="Half Country Head"
        value={detail.half_country_head}
        tooltip="The most senior person over this center's zone, if this zone reports to one -- some zones have no Half Country Head and report directly."
      />
    </div>
  )
}

function DetailField({ label, value, tooltip }: { label: string; value: string | null; tooltip: string }) {
  return (
    <Tooltip text={tooltip}>
      <div>
        <p className="text-xs font-semibold uppercase text-slate-500 dark:text-slate-400">{label}</p>
        <p className="text-sm text-slate-800 dark:text-slate-100">
          {value ?? <span className="text-slate-400 dark:text-slate-500">—</span>}
        </p>
      </div>
    </Tooltip>
  )
}

function NodeRow({
  node,
  dimensionKey,
  parentName,
  onUpdate,
  isPending,
}: {
  node: OrgNode
  dimensionKey: string | undefined
  parentName: string
  onUpdate: (payload: { is_active?: boolean; external_code?: string | null }) => void
  isPending: boolean
}) {
  const [code, setCode] = useState(node.external_code ?? '')

  return (
    <tr className={!node.is_active ? 'opacity-60' : undefined}>
      <td className="py-1 pr-4 text-slate-800 dark:text-slate-100">{node.name}</td>
      <td className="py-1 pr-4 font-mono text-xs text-slate-800 dark:text-slate-100">{dimensionKey}</td>
      <td className="py-1 pr-4 text-slate-500 dark:text-slate-400">{parentName}</td>
      <td className="py-1 pr-4">
        <input
          className="w-28 rounded border border-slate-300 bg-white px-1.5 py-0.5 text-xs text-slate-800 dark:border-slate-700 dark:bg-void-900 dark:text-slate-100"
          value={code}
          placeholder="—"
          onChange={(e) => setCode(e.target.value)}
          onBlur={() => {
            if (code !== (node.external_code ?? '')) onUpdate({ external_code: code || null })
          }}
        />
      </td>
      <td className="py-1 pr-4">
        <Badge tone="status">{node.is_active ? 'Active' : 'Inactive'}</Badge>
      </td>
      <td className="py-1 pr-4">
        <button
          className="text-xs font-medium text-np-calming-blue hover:underline disabled:cursor-not-allowed disabled:text-slate-400 dark:text-neon-blue-400 dark:disabled:text-slate-500"
          disabled={isPending}
          onClick={() => onUpdate({ is_active: !node.is_active })}
        >
          {node.is_active ? 'Deactivate' : 'Activate'}
        </button>
      </td>
    </tr>
  )
}

function NewDimensionForm({
  onSubmit,
  isPending,
}: {
  onSubmit: (payload: { key: string; label: string; sort_order: number }) => void
  isPending: boolean
}) {
  const [key, setKey] = useState('')
  const [label, setLabel] = useState('')
  const [sortOrder, setSortOrder] = useState(10)

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    onSubmit({ key, label, sort_order: sortOrder })
    setKey('')
    setLabel('')
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-2 border-t border-slate-200 pt-3 dark:border-slate-700">
      <p className="text-xs font-semibold uppercase text-slate-500 dark:text-slate-400">Add dimension</p>
      <div className="grid grid-cols-3 gap-2">
        <TextField id="dim-key" label="Key" placeholder="e.g. district" pattern="^[a-z0-9_]+$" required value={key} onChange={(e) => setKey(e.target.value)} />
        <TextField id="dim-label" label="Label" placeholder="District" required value={label} onChange={(e) => setLabel(e.target.value)} />
        <TextField id="dim-order" label="Sort order" type="number" value={sortOrder} onChange={(e) => setSortOrder(Number(e.target.value))} />
      </div>
      <Button type="submit" variant="secondary" isLoading={isPending}>
        Add dimension
      </Button>
    </form>
  )
}

function NewNodeForm({
  dimensions,
  nodes,
  dimensionById,
  onSubmit,
  isPending,
}: {
  dimensions: { id: number; key: string; label: string }[]
  nodes: { id: number; name: string; dimension_id: number }[]
  dimensionById: Map<number, { key: string; label: string }>
  onSubmit: (payload: { dimension_id: number; parent_id: number | null; name: string; external_code: string | null }) => void
  isPending: boolean
}) {
  const [dimensionId, setDimensionId] = useState<number | ''>('')
  const [parentId, setParentId] = useState<number | ''>('')
  const [name, setName] = useState('')
  const [externalCode, setExternalCode] = useState('')

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!dimensionId || !name) return
    onSubmit({
      dimension_id: dimensionId,
      parent_id: parentId || null,
      name,
      external_code: externalCode || null,
    })
    setName('')
    setExternalCode('')
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-2 border-t border-slate-200 pt-3 dark:border-slate-700">
      <p className="text-xs font-semibold uppercase text-slate-500 dark:text-slate-400">Add node</p>
      <div className="grid grid-cols-2 gap-2">
        <SelectField id="node-dim" label="Dimension" required value={dimensionId} onChange={(e) => setDimensionId(e.target.value ? Number(e.target.value) : '')}>
          <option value="">Select…</option>
          {dimensions.map((d) => (
            <option key={d.id} value={d.id}>
              {d.label}
            </option>
          ))}
        </SelectField>
        <SelectField id="node-parent" label="Parent (optional)" value={parentId} onChange={(e) => setParentId(e.target.value ? Number(e.target.value) : '')}>
          <option value="">None (top level)</option>
          {nodes.map((n) => (
            <option key={n.id} value={n.id}>
              [{dimensionById.get(n.dimension_id)?.key}] {n.name}
            </option>
          ))}
        </SelectField>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <TextField id="node-name" label="Name" required value={name} onChange={(e) => setName(e.target.value)} />
        <TextField id="node-code" label="External code (optional)" value={externalCode} onChange={(e) => setExternalCode(e.target.value)} />
      </div>
      <Button type="submit" variant="secondary" isLoading={isPending}>
        Add node
      </Button>
    </form>
  )
}
