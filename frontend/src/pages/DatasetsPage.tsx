import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { TextField } from '../components/ui/Field'
import { Badge } from '../components/ui/Badge'
import { EmptyState, ErrorBanner, Spinner } from '../components/ui/Feedback'
import { HeroBanner } from '../components/ui/HeroBanner'
import { DatasetScanIllustration } from '../components/ui/Illustrations'
import { Modal } from '../components/ui/Modal'
import { useToast } from '../components/ui/ToastProvider'
import { apiErrorMessage } from '../lib/api'
import { listDatasets, uploadDataset } from '../lib/resources/datasets'

export function DatasetsPage() {
  const navigate = useNavigate()
  const [isUploadOpen, setIsUploadOpen] = useState(false)

  const { data, isLoading, error } = useQuery({ queryKey: ['datasets'], queryFn: () => listDatasets() })

  return (
    <div className="space-y-6">
      <HeroBanner
        illustration={<DatasetScanIllustration className="h-full w-full" />}
        kicker="Data Intake"
        title="Datasets"
        subtitle="Upload raw data for profiling, reconciliation, and forensic anomaly scans -- every row traceable back to its source file."
        actions={<Button onClick={() => setIsUploadOpen(true)}>Upload Dataset</Button>}
      />

      <Card>
        <CardHeader title="All Datasets" />
        <CardBody>
          {isLoading && <Spinner />}
          {error && <ErrorBanner message={apiErrorMessage(error)} />}
          {data && data.length === 0 && (
            <EmptyState title="No datasets uploaded yet" hint="Upload a CSV or Excel file to get started." />
          )}
          {data && data.length > 0 && (
            <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase text-slate-500 dark:text-slate-400">
                <tr>
                  <th className="py-2 pr-4">Name</th>
                  <th className="py-2 pr-4">Type</th>
                  <th className="py-2 pr-4">Status</th>
                  <th className="py-2 pr-4">Rows</th>
                  <th className="py-2 pr-4">Columns</th>
                  <th className="py-2 pr-4">Quality</th>
                  <th className="py-2 pr-4">Version</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
                {data.map((ds) => (
                  <tr key={ds.id} className="cursor-pointer text-slate-800 hover:bg-slate-100 dark:text-slate-100 dark:hover:bg-slate-700" onClick={() => navigate(`/datasets/${ds.id}`)}>
                    <td className="py-2 pr-4">{ds.name}</td>
                    <td className="py-2 pr-4 uppercase text-xs text-slate-500 dark:text-slate-400">{ds.source_type}</td>
                    <td className="py-2 pr-4">
                      <Badge tone="status">{ds.status}</Badge>
                    </td>
                    <td className="py-2 pr-4">{ds.row_count ?? '—'}</td>
                    <td className="py-2 pr-4">{ds.column_count ?? '—'}</td>
                    <td className="py-2 pr-4">{ds.quality_score != null ? `${ds.quality_score}%` : '—'}</td>
                    <td className="py-2 pr-4">v{ds.version}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          )}
        </CardBody>
      </Card>

      {isUploadOpen && <UploadDatasetModal onClose={() => setIsUploadOpen(false)} />}
    </div>
  )
}

function UploadDatasetModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { showToast } = useToast()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: (file: File) => uploadDataset(file, name || file.name),
    onSuccess: (dataset) => {
      queryClient.invalidateQueries({ queryKey: ['datasets'] })
      showToast(`Dataset "${dataset.name}" uploaded`)
      onClose()
      navigate(`/datasets/${dataset.id}`)
    },
    onError: (err) => setError(apiErrorMessage(err, 'Upload failed')),
  })

  function handleSubmit() {
    setError(null)
    const file = fileInputRef.current?.files?.[0]
    if (!file) {
      setError('Choose a file first')
      return
    }
    mutation.mutate(file)
  }

  return (
    <Modal title="Upload Dataset" onClose={onClose}>
      <div className="space-y-4">
        {error && <ErrorBanner message={error} />}
        <TextField id="ds-name" label="Dataset name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. July Revenue Report" />
        <div>
          <label className="mb-1 block text-sm font-medium text-slate-600 dark:text-slate-400">File (CSV, Excel, PDF, Word, PPTX, image)</label>
          <input ref={fileInputRef} type="file" className="block w-full text-sm" />
        </div>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="button" isLoading={mutation.isPending} onClick={handleSubmit}>
            Upload
          </Button>
        </div>
      </div>
    </Modal>
  )
}
