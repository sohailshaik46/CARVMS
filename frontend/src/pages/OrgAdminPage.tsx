import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { SelectField, TextField } from '../components/ui/Field'
import { ErrorBanner, Spinner } from '../components/ui/Feedback'
import { HeroBanner } from '../components/ui/HeroBanner'
import { NetworkNodesIllustration } from '../components/ui/Illustrations'
import { useToast } from '../components/ui/ToastProvider'
import { apiErrorMessage } from '../lib/api'
import { createDimension, createNode, listDimensions, listNodes, updateNode } from '../lib/resources/org'
import type { OrgNode } from '../lib/types'

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

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="Dimensions" />
          <CardBody className="space-y-4">
            {dimensionsLoading && <Spinner />}
            {dimensions && (
              <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs uppercase text-slate-500">
                  <tr>
                    <th className="py-1 pr-4">Key</th>
                    <th className="py-1 pr-4">Label</th>
                    <th className="py-1 pr-4">Order</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {dimensions.map((d) => (
                    <tr key={d.id}>
                      <td className="py-1 pr-4 font-mono text-xs">{d.key}</td>
                      <td className="py-1 pr-4">{d.label}</td>
                      <td className="py-1">{d.sort_order}</td>
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
            {nodes && nodes.length === 0 && <p className="text-sm text-slate-500">No nodes created yet.</p>}
            {nodes && nodes.length > 0 && (
              <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs uppercase text-slate-500">
                  <tr>
                    <th className="py-1 pr-4">Name</th>
                    <th className="py-1 pr-4">Dimension</th>
                    <th className="py-1 pr-4">Parent</th>
                    <th className="py-1 pr-4">Code</th>
                    <th className="py-1 pr-4">Status</th>
                    <th className="py-1 pr-4">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
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
      <td className="py-1 pr-4">{node.name}</td>
      <td className="py-1 pr-4 font-mono text-xs">{dimensionKey}</td>
      <td className="py-1 pr-4 text-slate-500">{parentName}</td>
      <td className="py-1 pr-4">
        <input
          className="w-28 rounded border border-slate-700 px-1.5 py-0.5 text-xs"
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
          className="text-xs font-medium text-brand-600 hover:underline disabled:cursor-not-allowed disabled:text-slate-400"
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
    <form onSubmit={handleSubmit} className="space-y-2 border-t border-slate-800 pt-3">
      <p className="text-xs font-semibold uppercase text-slate-500">Add dimension</p>
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
    <form onSubmit={handleSubmit} className="space-y-2 border-t border-slate-800 pt-3">
      <p className="text-xs font-semibold uppercase text-slate-500">Add node</p>
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
