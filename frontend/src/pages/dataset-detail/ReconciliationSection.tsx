import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '../../components/ui/Button'
import { SelectField, TextField } from '../../components/ui/Field'
import { EmptyState, ErrorBanner } from '../../components/ui/Feedback'
import { useToast } from '../../components/ui/ToastProvider'
import { apiErrorMessage } from '../../lib/api'
import { listDatasets } from '../../lib/resources/datasets'
import { listReconciliations, runReconciliation } from '../../lib/resources/reconciliations'
import type { ReconciliationDetail } from '../../lib/types'

export function ReconciliationSection({ datasetId }: { datasetId: number }) {
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [datasetBId, setDatasetBId] = useState<number | ''>('')
  const [keyColumnA, setKeyColumnA] = useState('')
  const [keyColumnB, setKeyColumnB] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [lastResult, setLastResult] = useState<ReconciliationDetail | null>(null)

  const { data: allDatasets } = useQuery({ queryKey: ['datasets'], queryFn: () => listDatasets() })
  const { data: history } = useQuery({
    queryKey: ['reconciliations', datasetId],
    queryFn: () => listReconciliations(datasetId),
  })

  const mutation = useMutation({
    mutationFn: () =>
      runReconciliation({
        dataset_a_id: datasetId,
        dataset_b_id: datasetBId as number,
        key_column_a: keyColumnA,
        key_column_b: keyColumnB,
      }),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['reconciliations', datasetId] })
      setLastResult(result)
      showToast(result.status === 'completed' ? 'Reconciliation complete' : 'Reconciliation failed')
    },
    onError: (err) => setError(apiErrorMessage(err, 'Could not run reconciliation')),
  })

  const otherDatasets = allDatasets?.filter((d) => d.id !== datasetId) ?? []

  return (
    <div className="space-y-4">
      {error && <ErrorBanner message={error} />}

      <div className="rounded border border-dashed border-slate-700 p-3">
        <p className="mb-2 text-xs font-semibold uppercase text-slate-500">Reconcile against another dataset</p>
        <div className="flex flex-wrap items-end gap-2">
          <SelectField
            id="dataset-b"
            label="Compare with"
            className="w-56"
            value={datasetBId}
            onChange={(e) => setDatasetBId(e.target.value ? Number(e.target.value) : '')}
          >
            <option value="">Select dataset…</option>
            {otherDatasets.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name} (v{d.version})
              </option>
            ))}
          </SelectField>
          <TextField id="key-a" label="Key column (this dataset)" className="w-40" value={keyColumnA} onChange={(e) => setKeyColumnA(e.target.value)} />
          <TextField id="key-b" label="Key column (other dataset)" className="w-40" value={keyColumnB} onChange={(e) => setKeyColumnB(e.target.value)} />
          <Button
            variant="secondary"
            disabled={!datasetBId || !keyColumnA || !keyColumnB}
            isLoading={mutation.isPending}
            onClick={() => {
              setError(null)
              mutation.mutate()
            }}
          >
            Run reconciliation
          </Button>
        </div>
      </div>

      {lastResult && <ReconciliationResult result={lastResult} />}

      <div>
        <p className="mb-2 text-xs font-semibold uppercase text-slate-500">History</p>
        {history && history.length === 0 && <EmptyState title="No reconciliations run yet" />}
        {history && history.length > 0 && (
          <ul className="space-y-1 text-sm">
            {history.map((r) => (
              <li key={r.id} className="flex items-center justify-between rounded border border-slate-800 px-2 py-1">
                <span>
                  vs dataset #{r.dataset_a_id === datasetId ? r.dataset_b_id : r.dataset_a_id} — {r.status}
                </span>
                {r.status === 'completed' && (
                  <span className="text-xs text-slate-500">
                    {r.matched_count} matched / {r.mismatched_count} mismatched / {r.missing_in_b_count} missing /{' '}
                    {r.extra_in_b_count} extra
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

function ReconciliationResult({ result }: { result: ReconciliationDetail }) {
  if (result.status === 'failed') {
    return <ErrorBanner message={result.error ?? 'Reconciliation failed'} />
  }
  const details = result.details_json
  return (
    <div className="rounded border border-slate-800 bg-slate-900 p-3 text-sm">
      <div className="grid grid-cols-4 gap-2 text-center">
        <Stat label="Matched" value={result.matched_count} tone="text-green-600" />
        <Stat label="Mismatched" value={result.mismatched_count} tone="text-orange-600" />
        <Stat label="Missing" value={result.missing_in_b_count} tone="text-red-600" />
        <Stat label="Extra" value={result.extra_in_b_count} tone="text-blue-600" />
      </div>
      {details && details.mismatched_examples.length > 0 && (
        <div className="mt-3">
          <p className="text-xs font-semibold text-slate-500">Mismatch examples</p>
          <ul className="mt-1 space-y-1">
            {details.mismatched_examples.slice(0, 5).map((ex) => (
              <li key={ex.key} className="text-xs">
                <span className="font-mono">{ex.key}</span>:{' '}
                {Object.entries(ex.diffs)
                  .map(([col, diff]) => `${col} (${String(diff.a)} → ${String(diff.b)})`)
                  .join(', ')}
              </li>
            ))}
          </ul>
          {details.mismatched_examples_truncated && (
            <p className="mt-1 text-xs italic text-slate-500">More mismatches exist than shown here.</p>
          )}
        </div>
      )}
    </div>
  )
}

function Stat({ label, value, tone }: { label: string; value: number | null; tone: string }) {
  return (
    <div>
      <p className={`text-lg font-semibold ${tone}`}>{value ?? '—'}</p>
      <p className="text-xs text-slate-500">{label}</p>
    </div>
  )
}
