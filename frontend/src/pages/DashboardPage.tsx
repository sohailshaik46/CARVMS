import { useEffect, useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '../auth/AuthContext'
import { Card, CardBody, CardHeader, KpiCard } from '../components/ui/Card'
import { HorizontalBarChart, PieChartWidget, recordToBarData } from '../components/ui/Charts'
import { Button } from '../components/ui/Button'
import { TextField } from '../components/ui/Field'
import { ErrorBanner, Spinner } from '../components/ui/Feedback'
import { HeroBanner } from '../components/ui/HeroBanner'
import { RadarScanIllustration } from '../components/ui/Illustrations'
import { Modal } from '../components/ui/Modal'
import { Select } from '../components/ui/Select'
import { useToast } from '../components/ui/ToastProvider'
import { apiErrorMessage } from '../lib/api'
import { downloadExport, fetchDashboardSummary, type ExportFormat } from '../lib/resources/dashboard'
import { createDashboardLayout, deleteDashboardLayout, listDashboardLayouts } from '../lib/resources/dashboardLayouts'
import { getMyPreferences } from '../lib/resources/preferences'
import { createReportTemplate } from '../lib/resources/reports'
import { resolveVisibleKpis } from '../lib/dashboardKpis'
import type { DashboardFilters } from '../lib/types'

export function DashboardPage() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [filters, setFilters] = useState<DashboardFilters>({})
  const [selectedLayoutId, setSelectedLayoutId] = useState<number | ''>('')
  const [exportingFormat, setExportingFormat] = useState<ExportFormat | null>(null)
  const [exportError, setExportError] = useState<string | null>(null)
  const [isSaveTemplateOpen, setIsSaveTemplateOpen] = useState(false)
  const [isSaveLayoutOpen, setIsSaveLayoutOpen] = useState(false)

  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard-summary', filters],
    queryFn: () => fetchDashboardSummary(filters),
  })
  const { data: layouts } = useQuery({ queryKey: ['dashboard-layouts'], queryFn: listDashboardLayouts })
  // Which KPI cards show, and in what order -- set on Settings' Dashboard
  // tab, saved server-side per user. Falls back to the full default set
  // (undefined -> resolveVisibleKpis' own default) until that loads.
  const { data: preferences } = useQuery({ queryKey: ['my-preferences'], queryFn: getMyPreferences })
  const visibleKpis = resolveVisibleKpis(preferences?.dashboard_config?.visible_kpis)

  const deleteLayoutMutation = useMutation({
    mutationFn: (id: number) => deleteDashboardLayout(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dashboard-layouts'] })
      setSelectedLayoutId('')
      showToast('Layout deleted')
    },
    onError: (err) => setExportError(apiErrorMessage(err, 'Could not delete layout')),
  })

  function applyLayout(layoutId: number | '') {
    setSelectedLayoutId(layoutId)
    if (!layoutId) return
    const layout = layouts?.find((l) => l.id === layoutId)
    if (!layout) return
    setFilters(layout.config.default_filters)
  }

  const selectedLayout = layouts?.find((l) => l.id === selectedLayoutId)
  const canManageSelectedLayout = selectedLayout && (user?.id === selectedLayout.owner_id || user?.role === 'Admin')

  async function handleExport(format: ExportFormat) {
    setExportError(null)
    setExportingFormat(format)
    try {
      await downloadExport(format, filters)
    } catch (err) {
      setExportError(apiErrorMessage(err, 'Export failed'))
    } finally {
      setExportingFormat(null)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <HeroBanner
          illustration={<RadarScanIllustration className="h-full w-full" />}
          kicker="Command Center"
          title="Dashboard"
          actions={
            <>
              <Button variant="secondary" isLoading={exportingFormat === 'csv'} onClick={() => handleExport('csv')}>
                CSV
              </Button>
              <Button variant="secondary" isLoading={exportingFormat === 'xlsx'} onClick={() => handleExport('xlsx')}>
                Excel
              </Button>
              <Button variant="secondary" isLoading={exportingFormat === 'pdf'} onClick={() => handleExport('pdf')}>
                PDF
              </Button>
              <Button variant="secondary" isLoading={exportingFormat === 'docx'} onClick={() => handleExport('docx')}>
                Word
              </Button>
              <Button variant="secondary" isLoading={exportingFormat === 'pptx'} onClick={() => handleExport('pptx')}>
                PPT
              </Button>
              <Button variant="secondary" onClick={() => setIsSaveTemplateOpen(true)}>
                Save as Report Template
              </Button>
              <Button variant="secondary" onClick={() => setIsSaveLayoutOpen(true)}>
                Save as Layout
              </Button>
            </>
          }
        />
        <LiveClock />
      </div>

      {exportError && <ErrorBanner message={exportError} />}

      <Card>
        <CardHeader
          title="Layout"
          actions={
            <div className="flex items-center gap-2">
              <Select
                className="text-sm"
                value={selectedLayoutId}
                onChange={(e) => applyLayout(e.target.value ? Number(e.target.value) : '')}
              >
                <option value="">Default view</option>
                {layouts?.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.name}
                    {l.is_shared ? ' (shared)' : ''}
                  </option>
                ))}
              </Select>
              {canManageSelectedLayout && (
                <Button variant="ghost" onClick={() => deleteLayoutMutation.mutate(selectedLayout!.id)}>
                  Delete layout
                </Button>
              )}
            </div>
          }
        />
        <CardBody className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <TextField
            id="period_from"
            label="Period from"
            type="date"
            value={filters.period_from ?? ''}
            onChange={(e) => setFilters((f) => ({ ...f, period_from: e.target.value || undefined }))}
          />
          <TextField
            id="period_to"
            label="Period to"
            type="date"
            value={filters.period_to ?? ''}
            onChange={(e) => setFilters((f) => ({ ...f, period_to: e.target.value || undefined }))}
          />
          <div className="flex items-end">
            <Button variant="ghost" onClick={() => setFilters({})}>
              Clear filters
            </Button>
          </div>
        </CardBody>
      </Card>

      {isLoading && <Spinner />}
      {error && <ErrorBanner message={apiErrorMessage(error, 'Could not load dashboard')} />}

      {data && (
        <>
          {/* Which cards, and in what order, comes from Settings ->
              Dashboard (see resolveVisibleKpis) -- this loop is the only
              place that renders a KPI card, so a hidden/reordered key here
              is exactly what the user configured, nothing hardcoded. */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {visibleKpis.map((kpi) => (
              <KpiCard key={kpi.key} label={kpi.label} value={kpi.value(data)} hint={kpi.hint?.(data)} to={kpi.to} />
            ))}
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader title="Non-Compliant Centers by Cluster" />
              <CardBody>
                {data.cluster_breakdown.length === 0 ? (
                  <p className="text-sm text-slate-400">No non-compliant centers in scope for these filters.</p>
                ) : (
                  <PieChartWidget
                    data={data.cluster_breakdown.map((c) => ({ label: c.cluster, value: c.non_compliant_center_count }))}
                  />
                )}
              </CardBody>
            </Card>
            <Card>
              <CardHeader title="Non-Compliant Centers by Zone" />
              <CardBody>
                {data.zone_breakdown.length === 0 ? (
                  <p className="text-sm text-slate-400">No non-compliant centers in scope for these filters.</p>
                ) : (
                  <HorizontalBarChart data={data.zone_breakdown.map((z) => ({ label: z.zone, value: z.non_compliant_center_count }))} />
                )}
              </CardBody>
            </Card>
          </div>

          <Card>
            <CardHeader title="Repeat SOP Violators" />
            <CardBody>
              {data.repeated_centers.length === 0 ? (
                <p className="text-sm text-slate-400">No center has 2+ not-considered verdicts in scope for these filters.</p>
              ) : (
                <HorizontalBarChart
                  data={recordToBarData(
                    Object.fromEntries(data.repeated_centers.map((r) => [`${r.centre_name} (${r.centre_code})`, r.violation_count])),
                  )}
                />
              )}
            </CardBody>
          </Card>
        </>
      )}

      <PendingTasksPanel />

      {isSaveTemplateOpen && (
        <SaveTemplateModal filters={filters} onClose={() => setIsSaveTemplateOpen(false)} />
      )}
      {isSaveLayoutOpen && (
        <SaveLayoutModal filters={filters} onClose={() => setIsSaveLayoutOpen(false)} />
      )}
    </div>
  )
}

/** Small live clock, top-right of the Dashboard -- per the user's explicit
 * request, "so that I can complete tasks on time". Ticks client-side every
 * second; never round-trips to the server. */
function LiveClock() {
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="mt-1 shrink-0 rounded-md border border-slate-700 bg-void-950 px-3 py-1.5 text-right">
      <p className="text-sm font-semibold tabular-nums text-neon-400">
        {now.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
      </p>
      <p className="text-[11px] text-slate-400">{now.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}</p>
    </div>
  )
}

interface PendingTask {
  id: string
  text: string
  done: boolean
}

const PENDING_TASKS_KEY = 'carvms_pending_tasks_v1'

function loadPendingTasks(): PendingTask[] {
  try {
    const raw = localStorage.getItem(PENDING_TASKS_KEY)
    return raw ? (JSON.parse(raw) as PendingTask[]) : []
  } catch {
    return []
  }
}

/** A personal to-do panel -- per the user's explicit request ("i also need
 * the pending tasks are from my side so that i can complete those"). This
 * is deliberately local to the browser (no backend model exists for it,
 * and it's framed as personal scratch space, not a shared workflow item)
 * -- it will not follow the user to a different browser/device. */
function PendingTasksPanel() {
  const [tasks, setTasks] = useState<PendingTask[]>(loadPendingTasks)
  const [draft, setDraft] = useState('')

  useEffect(() => {
    localStorage.setItem(PENDING_TASKS_KEY, JSON.stringify(tasks))
  }, [tasks])

  function addTask(e: FormEvent) {
    e.preventDefault()
    if (!draft.trim()) return
    setTasks((prev) => [...prev, { id: crypto.randomUUID(), text: draft.trim(), done: false }])
    setDraft('')
  }

  function toggleTask(id: string) {
    setTasks((prev) => prev.map((t) => (t.id === id ? { ...t, done: !t.done } : t)))
  }

  function removeTask(id: string) {
    setTasks((prev) => prev.filter((t) => t.id !== id))
  }

  const pendingCount = tasks.filter((t) => !t.done).length

  return (
    <Card>
      <CardHeader title={`Pending Tasks${pendingCount ? ` (${pendingCount})` : ''}`} />
      <CardBody className="space-y-3">
        <form onSubmit={addTask} className="flex gap-2">
          <input
            className="flex-1 rounded-md border border-slate-700 bg-void-950 px-3 py-1.5 text-sm text-slate-200 placeholder:text-slate-600"
            placeholder="Add a personal to-do…"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
          <Button type="submit" variant="secondary">
            Add
          </Button>
        </form>
        {tasks.length === 0 ? (
          <p className="text-sm text-slate-400">Nothing pending -- add a task above to track it here.</p>
        ) : (
          <ul className="space-y-1">
            {tasks.map((t) => (
              <li key={t.id} className="flex items-center gap-2 rounded border border-slate-700 px-2 py-1.5 text-sm">
                <input type="checkbox" checked={t.done} onChange={() => toggleTask(t.id)} />
                <span className={`flex-1 ${t.done ? 'text-slate-600 line-through' : 'text-slate-200'}`}>{t.text}</span>
                <button type="button" className="text-xs text-slate-400 hover:text-neon-pink-400" onClick={() => removeTask(t.id)}>
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}
      </CardBody>
    </Card>
  )
}

function SaveTemplateModal({ filters, onClose }: { filters: DashboardFilters; onClose: () => void }) {
  const { showToast } = useToast()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [error, setError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: () => createReportTemplate({ name, description: description || null, filters }),
    onSuccess: () => {
      showToast(`Template "${name}" saved`)
      onClose()
    },
    onError: (err) => setError(apiErrorMessage(err, 'Could not save template')),
  })

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (!name) return
    mutation.mutate()
  }

  return (
    <Modal title="Save Current Filters as Report Template" onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && <ErrorBanner message={error} />}
        <p className="text-xs text-slate-400">
          Saves the filters currently applied above (from: {filters.period_from ?? '—'}, to: {filters.period_to ?? '—'})
          as a reusable report template.
        </p>
        <TextField id="save-tpl-name" label="Name" required value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Monthly Vigilance Report" />
        <TextField id="save-tpl-desc" label="Description (optional)" value={description} onChange={(e) => setDescription(e.target.value)} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" isLoading={mutation.isPending}>
            Save
          </Button>
        </div>
      </form>
    </Modal>
  )
}

function SaveLayoutModal({ filters, onClose }: { filters: DashboardFilters; onClose: () => void }) {
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [isShared, setIsShared] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: () =>
      createDashboardLayout({
        name,
        description: description || null,
        is_shared: isShared,
        config: { default_filters: filters },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dashboard-layouts'] })
      showToast(`Layout "${name}" saved`)
      onClose()
    },
    onError: (err) => setError(apiErrorMessage(err, 'Could not save layout')),
  })

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (!name) return
    mutation.mutate()
  }

  return (
    <Modal title="Save as Dashboard Layout" onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && <ErrorBanner message={error} />}
        <p className="text-xs text-slate-400">Saves the current period filter as a reusable named view.</p>
        <TextField id="save-layout-name" label="Name" required value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. July Review" />
        <TextField id="save-layout-desc" label="Description (optional)" value={description} onChange={(e) => setDescription(e.target.value)} />

        <label className="flex items-center gap-1.5 text-sm">
          <input type="checkbox" checked={isShared} onChange={(e) => setIsShared(e.target.checked)} />
          Share with all users (otherwise only you can see this layout)
        </label>

        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" isLoading={mutation.isPending}>
            Save
          </Button>
        </div>
      </form>
    </Modal>
  )
}
