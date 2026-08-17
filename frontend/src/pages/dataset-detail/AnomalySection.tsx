import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '../../components/ui/Button'
import { Badge } from '../../components/ui/Badge'
import { SelectField, TextAreaField } from '../../components/ui/Field'
import { EmptyState, ErrorBanner } from '../../components/ui/Feedback'
import { Modal } from '../../components/ui/Modal'
import { useToast } from '../../components/ui/ToastProvider'
import { apiErrorMessage } from '../../lib/api'
import { dismissAnomaly, listAnomalies, scanDataset } from '../../lib/resources/anomalies'
import { ANOMALY_RULE_CODES, type AnomalyRuleCode, type DatasetAnomaly, type DatasetColumn } from '../../lib/types'

export function AnomalySection({ datasetId, columns }: { datasetId: number; columns: DatasetColumn[] }) {
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [error, setError] = useState<string | null>(null)
  const [selectedRules, setSelectedRules] = useState<AnomalyRuleCode[]>(['duplicate_row'])
  const [repeatedValueColumn, setRepeatedValueColumn] = useState('')
  const [outlierColumn, setOutlierColumn] = useState('')
  const [dismissingAnomaly, setDismissingAnomaly] = useState<DatasetAnomaly | null>(null)

  const { data: anomalies } = useQuery({
    queryKey: ['anomalies', datasetId],
    queryFn: () => listAnomalies(datasetId),
  })

  const scanMutation = useMutation({
    mutationFn: () =>
      scanDataset(datasetId, {
        rules: selectedRules,
        repeated_value_column: selectedRules.includes('repeated_value') ? repeatedValueColumn : undefined,
        outlier_column: selectedRules.includes('outlier_iqr') ? outlierColumn : undefined,
      }),
    onSuccess: (found) => {
      queryClient.invalidateQueries({ queryKey: ['anomalies', datasetId] })
      showToast(`Scan complete: ${found.length} anomal${found.length === 1 ? 'y' : 'ies'} found`)
    },
    onError: (err) => setError(apiErrorMessage(err, 'Scan failed')),
  })

  const dismissMutation = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) => dismissAnomaly(id, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['anomalies', datasetId] })
      showToast('Anomaly dismissed')
      setDismissingAnomaly(null)
    },
    onError: (err) => setError(apiErrorMessage(err, 'Could not dismiss')),
  })

  function toggleRule(rule: AnomalyRuleCode) {
    setSelectedRules((prev) => (prev.includes(rule) ? prev.filter((r) => r !== rule) : [...prev, rule]))
  }

  return (
    <div className="space-y-4">
      {error && <ErrorBanner message={error} />}

      <div className="rounded border border-dashed border-slate-700 p-3">
        <p className="mb-2 text-xs font-semibold uppercase text-slate-500">Run a forensic scan</p>
        <div className="flex flex-wrap gap-4">
          {ANOMALY_RULE_CODES.map((rule) => (
            <label key={rule} className="flex items-center gap-1.5 text-sm">
              <input type="checkbox" checked={selectedRules.includes(rule)} onChange={() => toggleRule(rule)} />
              {rule.replace('_', ' ')}
            </label>
          ))}
        </div>
        <div className="mt-3 flex flex-wrap items-end gap-2">
          {selectedRules.includes('repeated_value') && (
            <SelectField
              id="repeated-col"
              label="Repeated-value column"
              className="w-48"
              value={repeatedValueColumn}
              onChange={(e) => setRepeatedValueColumn(e.target.value)}
            >
              <option value="">Select column…</option>
              {columns.map((c) => (
                <option key={c.name} value={c.name}>
                  {c.name}
                </option>
              ))}
            </SelectField>
          )}
          {selectedRules.includes('outlier_iqr') && (
            <SelectField
              id="outlier-col"
              label="Outlier column"
              className="w-48"
              value={outlierColumn}
              onChange={(e) => setOutlierColumn(e.target.value)}
            >
              <option value="">Select column…</option>
              {columns.map((c) => (
                <option key={c.name} value={c.name}>
                  {c.name}
                </option>
              ))}
            </SelectField>
          )}
          <Button
            variant="secondary"
            isLoading={scanMutation.isPending}
            disabled={selectedRules.length === 0}
            onClick={() => {
              setError(null)
              scanMutation.mutate()
            }}
          >
            Run scan
          </Button>
        </div>
      </div>

      {anomalies && anomalies.length === 0 && <EmptyState title="No anomalies detected yet" hint="Run a scan above." />}
      {anomalies && anomalies.length > 0 && (
        <ul className="space-y-2">
          {anomalies.map((a) => (
            <li key={a.id} className="rounded border border-slate-800 bg-slate-900 p-3 text-sm">
              <div className="flex items-center justify-between">
                <span className="font-medium">{a.entity_description}</span>
                <div className="flex items-center gap-2">
                  <Badge tone="risk">{a.risk_level}</Badge>
                  <Badge tone="status">{a.status}</Badge>
                </div>
              </div>
              <p className="mt-1 text-xs text-slate-500">{a.recommended_verification}</p>
              {a.status === 'Open' && (
                <div className="mt-2 flex gap-2">
                  <Button variant="ghost" onClick={() => setDismissingAnomaly(a)}>
                    Dismiss
                  </Button>
                </div>
              )}
              {a.status === 'Dismissed' && a.dismissed_reason && (
                <p className="mt-1 text-xs italic text-slate-500">Dismissed: {a.dismissed_reason}</p>
              )}
            </li>
          ))}
        </ul>
      )}

      {dismissingAnomaly && (
        <DismissModal
          anomaly={dismissingAnomaly}
          isPending={dismissMutation.isPending}
          onConfirm={(reason) => dismissMutation.mutate({ id: dismissingAnomaly.id, reason })}
          onClose={() => setDismissingAnomaly(null)}
        />
      )}
    </div>
  )
}

function DismissModal({
  anomaly,
  isPending,
  onConfirm,
  onClose,
}: {
  anomaly: DatasetAnomaly
  isPending: boolean
  onConfirm: (reason: string) => void
  onClose: () => void
}) {
  const [reason, setReason] = useState('')

  return (
    <Modal title="Dismiss Anomaly" onClose={onClose}>
      <div className="space-y-4">
        <p className="text-sm text-slate-500">{anomaly.entity_description}</p>
        <TextAreaField
          id="dismiss-reason"
          label="Reason for dismissing"
          required
          rows={3}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="e.g. Confirmed legitimate resubmission by center"
        />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!reason.trim()} isLoading={isPending} onClick={() => onConfirm(reason)}>
            Dismiss
          </Button>
        </div>
      </div>
    </Modal>
  )
}

