import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { Badge } from '../components/ui/Badge'
import { ErrorBanner, Spinner } from '../components/ui/Feedback'
import { useToast } from '../components/ui/ToastProvider'
import { apiErrorMessage } from '../lib/api'
import { archiveDataset, getDataset, listDatasetColumns, reprocessDataset } from '../lib/resources/datasets'
import { AnomalySection } from './dataset-detail/AnomalySection'
import { ReconciliationSection } from './dataset-detail/ReconciliationSection'

export function DatasetDetailPage() {
  const { datasetId } = useParams()
  const id = Number(datasetId)
  const { user } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<'columns' | 'anomalies' | 'reconciliation'>('columns')

  const { data: dataset, isLoading, error: loadError } = useQuery({
    queryKey: ['dataset', id],
    queryFn: () => getDataset(id),
    enabled: Number.isFinite(id),
  })
  const { data: columns } = useQuery({
    queryKey: ['dataset-columns', id],
    queryFn: () => listDatasetColumns(id),
    enabled: Number.isFinite(id),
  })

  const reprocessMutation = useMutation({
    mutationFn: () => reprocessDataset(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dataset', id] })
      queryClient.invalidateQueries({ queryKey: ['dataset-columns', id] })
      showToast('Dataset reprocessed')
    },
    onError: (err) => setError(apiErrorMessage(err, 'Could not reprocess')),
  })

  const archiveMutation = useMutation({
    mutationFn: () => archiveDataset(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dataset', id] })
      showToast('Dataset archived')
    },
    onError: (err) => setError(apiErrorMessage(err, 'Could not archive')),
  })

  if (isLoading) return <Spinner />
  if (loadError) return <ErrorBanner message={apiErrorMessage(loadError, 'Could not load this dataset')} />
  if (!dataset) return null

  const canManage = user?.role === 'Admin' || user?.id === dataset.uploaded_by_id

  return (
    <div className="space-y-6">
      <button onClick={() => navigate('/datasets')} className="text-sm text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-100">
        ← Back to Datasets
      </button>

      <Card>
        <CardHeader
          title={dataset.name}
          actions={
            <div className="flex items-center gap-2">
              <Badge tone="status">{dataset.status}</Badge>
              {canManage && dataset.status !== 'archived' && (
                <>
                  <Button variant="secondary" isLoading={reprocessMutation.isPending} onClick={() => reprocessMutation.mutate()}>
                    Reprocess
                  </Button>
                  <Button variant="ghost" isLoading={archiveMutation.isPending} onClick={() => archiveMutation.mutate()}>
                    Archive
                  </Button>
                </>
              )}
            </div>
          }
        />
        <CardBody className="space-y-2">
          {error && <ErrorBanner message={error} />}
          <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-5">
            <Stat label="Type" value={dataset.source_type} />
            <Stat label="Rows" value={dataset.row_count ?? '—'} />
            <Stat label="Columns" value={dataset.column_count ?? '—'} />
            <Stat label="Duplicate rows" value={dataset.duplicate_row_count ?? '—'} />
            <Stat label="Quality score" value={dataset.quality_score != null ? `${dataset.quality_score}%` : '—'} />
          </dl>
          {dataset.profiling_error && <ErrorBanner message={`Profiling error: ${dataset.profiling_error}`} />}
        </CardBody>
      </Card>

      <div className="flex gap-2 border-b border-slate-200 dark:border-slate-700">
        {(['columns', 'anomalies', 'reconciliation'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-3 py-2 text-sm font-medium capitalize ${
              tab === t
                ? 'border-b-2 border-brand-600 text-brand-700 dark:border-neon-500 dark:text-neon-400'
                : 'text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200'
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === 'columns' && (
        <Card>
          <CardBody>
            {(!columns || columns.length === 0) && (
              <p className="text-sm text-slate-500 dark:text-slate-400">
                {dataset.status === 'uploaded'
                  ? 'This file type is not tabular, so no column profile was generated.'
                  : 'No column data available.'}
              </p>
            )}
            {columns && columns.length > 0 && (
              <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs uppercase text-slate-500 dark:text-slate-400">
                  <tr>
                    <th className="py-2 pr-4">Column</th>
                    <th className="py-2 pr-4">Type</th>
                    <th className="py-2 pr-4">Null rate</th>
                    <th className="py-2 pr-4">Mapped dimension</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
                  {columns.map((c) => (
                    <tr key={c.id} className="text-slate-800 dark:text-slate-100">
                      <td className="py-2 pr-4 font-medium">{c.name}</td>
                      <td className="py-2 pr-4">{c.inferred_type}</td>
                      <td className="py-2 pr-4">{(c.null_rate * 100).toFixed(1)}%</td>
                      <td className="py-2 pr-4">{c.mapped_dimension ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            )}
          </CardBody>
        </Card>
      )}

      {tab === 'anomalies' && (
        <Card>
          <CardBody>
            <AnomalySection datasetId={id} columns={columns ?? []} />
          </CardBody>
        </Card>
      )}

      {tab === 'reconciliation' && (
        <Card>
          <CardBody>
            <ReconciliationSection datasetId={id} />
          </CardBody>
        </Card>
      )}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <dt className="text-xs uppercase text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className="font-medium text-slate-800 dark:text-slate-100">{value}</dd>
    </div>
  )
}
