import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '../auth/AuthContext'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { Badge } from '../components/ui/Badge'
import { TextField } from '../components/ui/Field'
import { EmptyState, ErrorBanner, Spinner } from '../components/ui/Feedback'
import { HeroBanner } from '../components/ui/HeroBanner'
import { ReportBarsIllustration } from '../components/ui/Illustrations'
import { useToast } from '../components/ui/ToastProvider'
import { apiErrorMessage } from '../lib/api'
import {
  createReportTemplate,
  deleteReportTemplate,
  listReportHistory,
  listReportTemplates,
  regenerateReport,
  runTemplate,
} from '../lib/resources/reports'
import { REPORT_FORMATS, type ReportFormat } from '../lib/types'

const FORMAT_LABELS: Record<ReportFormat, string> = {
  csv: 'CSV',
  xlsx: 'Excel',
  pdf: 'PDF',
  docx: 'Word',
  pptx: 'PPT',
}

export function ReportsPage() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [error, setError] = useState<string | null>(null)
  const [runningId, setRunningId] = useState<number | null>(null)

  const { data: templates, isLoading: templatesLoading } = useQuery({
    queryKey: ['report-templates'],
    queryFn: listReportTemplates,
  })
  const { data: history, isLoading: historyLoading } = useQuery({
    queryKey: ['report-history'],
    queryFn: listReportHistory,
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteReportTemplate(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['report-templates'] })
      showToast('Template deleted')
    },
    onError: (err) => setError(apiErrorMessage(err, 'Could not delete template')),
  })

  async function handleRun(templateId: number, format: ReportFormat) {
    setError(null)
    setRunningId(templateId)
    try {
      await runTemplate(templateId, format)
      queryClient.invalidateQueries({ queryKey: ['report-history'] })
      showToast(`Report generated (${format.toUpperCase()})`)
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not run template'))
    } finally {
      setRunningId(null)
    }
  }

  async function handleRegenerate(historyId: number, format: ReportFormat) {
    setError(null)
    setRunningId(historyId)
    try {
      await regenerateReport(historyId, format)
      queryClient.invalidateQueries({ queryKey: ['report-history'] })
      showToast('Regenerated from live data')
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not regenerate'))
    } finally {
      setRunningId(null)
    }
  }

  return (
    <div className="space-y-6">
      <HeroBanner
        illustration={<ReportBarsIllustration className="h-full w-full" />}
        kicker="Export & History"
        title="Reports"
        subtitle="Reusable filter templates and a full history of every export -- CSV, Excel, PDF, Word, or PPT, regenerated on demand from the same Delayed Cash Billing + Weekly Revenue Closure numbers."
      />
      {error && <ErrorBanner message={error} />}

      <Card>
        <CardHeader title="Saved Templates" />
        <CardBody className="space-y-4">
          {templatesLoading && <Spinner />}
          {templates && templates.length === 0 && (
            <EmptyState title="No saved templates yet" hint="Save a named filter set below to reuse it every period." />
          )}
          {templates && templates.length > 0 && (
            <ul className="space-y-2">
              {templates.map((t) => (
                <li key={t.id} className="rounded border border-slate-800 p-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="font-medium text-slate-200">{t.name}</p>
                      {t.description && <p className="text-xs text-slate-500">{t.description}</p>}
                    </div>
                    <div className="flex items-center gap-2">
                      {REPORT_FORMATS.map((fmt) => (
                        <Button
                          key={fmt}
                          variant="secondary"
                          isLoading={runningId === t.id}
                          onClick={() => handleRun(t.id, fmt)}
                        >
                          Run {FORMAT_LABELS[fmt]}
                        </Button>
                      ))}
                      {(user?.role === 'Admin' || user?.id === t.created_by_id) && (
                        <Button variant="ghost" onClick={() => deleteMutation.mutate(t.id)}>
                          Delete
                        </Button>
                      )}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}

          <NewTemplateForm
            onCreated={() => {
              queryClient.invalidateQueries({ queryKey: ['report-templates'] })
              showToast('Template saved')
            }}
          />
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="History" />
        <CardBody>
          {historyLoading && <Spinner />}
          {history && history.length === 0 && <EmptyState title="No reports generated yet" />}
          {history && history.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs uppercase text-slate-500">
                  <tr>
                    <th className="py-2 pr-4">Name</th>
                    <th className="py-2 pr-4">Format</th>
                    <th className="py-2 pr-4">Status</th>
                    <th className="py-2 pr-4">Generated</th>
                    <th className="py-2 pr-4">Regenerate</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {history.map((h) => (
                    <tr key={h.id}>
                      <td className="py-2 pr-4">
                        {h.name}
                        {h.regenerated_from_id && (
                          <span className="ml-1 text-xs text-slate-500">(regenerated from #{h.regenerated_from_id})</span>
                        )}
                      </td>
                      <td className="py-2 pr-4 uppercase text-xs">{h.format}</td>
                      <td className="py-2 pr-4">
                        <Badge tone="status">{h.status}</Badge>
                      </td>
                      <td className="py-2 pr-4 text-slate-500">{new Date(h.generated_at).toLocaleString()}</td>
                      <td className="py-2 pr-4">
                        <Button
                          variant="ghost"
                          isLoading={runningId === h.id}
                          onClick={() => handleRegenerate(h.id, h.format)}
                        >
                          Regenerate
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardBody>
      </Card>
    </div>
  )
}

function NewTemplateForm({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [periodFrom, setPeriodFrom] = useState('')
  const [periodTo, setPeriodTo] = useState('')
  const [error, setError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: () =>
      createReportTemplate({
        name,
        description: description || null,
        filters: { period_from: periodFrom || undefined, period_to: periodTo || undefined },
      }),
    onSuccess: () => {
      setName('')
      setDescription('')
      setPeriodFrom('')
      setPeriodTo('')
      onCreated()
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
    <form onSubmit={handleSubmit} className="space-y-3 border-t border-slate-800 pt-4">
      <p className="text-xs font-semibold uppercase text-slate-500">Save a new template</p>
      {error && <ErrorBanner message={error} />}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
        <TextField id="tpl-name" label="Name" required value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Monthly Vigilance Report" />
        <TextField id="tpl-desc" label="Description (optional)" value={description} onChange={(e) => setDescription(e.target.value)} />
        <TextField id="tpl-period-from" label="Period from" type="date" value={periodFrom} onChange={(e) => setPeriodFrom(e.target.value)} />
        <TextField id="tpl-period-to" label="Period to" type="date" value={periodTo} onChange={(e) => setPeriodTo(e.target.value)} />
      </div>
      <Button type="submit" isLoading={mutation.isPending}>
        Save template
      </Button>
    </form>
  )
}
