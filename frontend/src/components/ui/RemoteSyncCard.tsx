import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Card, CardBody, CardHeader } from './Card'
import { Button } from './Button'
import { Tooltip } from './Tooltip'
import { useToast } from './ToastProvider'
import { apiErrorMessage } from '../../lib/api'
import { getRemoteSyncStatus } from '../../lib/resources/org'

/** A flattened, domain-agnostic shape every remote-sync report (Org
 * Master, DCB, WRC) reduces to for display -- each page's own resource
 * call returns its full typed report; the page sums that report's own
 * *_created/*_updated/*_unchanged fields into this before handing it to
 * the card below. */
export interface RemoteSyncSummary {
  created: number
  updated: number
  unchanged: number
  changedList: string[]
}

interface RemoteSyncCardProps {
  title: string
  whatIsThisTooltip: string
  pushLabel: string
  pushDescription: string
  pullLabel: string
  pullDescription: string
  onPreviewPush: () => Promise<RemoteSyncSummary>
  onApplyPush: () => Promise<RemoteSyncSummary>
  onPreviewPull: () => Promise<RemoteSyncSummary>
  onApplyPull: () => Promise<RemoteSyncSummary>
}

/** Manual, explicit sync against Render's live database -- NEVER
 * automatic. Every direction is the same two-step flow: "Preview" runs a
 * commit=false dry run (zero writes) and shows exactly what would
 * change; "Apply" is the only thing that actually writes, and only
 * appears once a preview has run. Never deletes anything either
 * direction -- see whichever *_remote_sync_service backs the page using
 * this component for the full safety contract. */
export function RemoteSyncCard({
  title,
  whatIsThisTooltip,
  pushLabel,
  pushDescription,
  pullLabel,
  pullDescription,
  onPreviewPush,
  onApplyPush,
  onPreviewPull,
  onApplyPull,
}: RemoteSyncCardProps) {
  // Hides itself entirely on an instance where REMOTE_DATABASE_URL was
  // never configured (e.g. Render itself) -- Push/Pull could never work
  // there, so there's no point showing buttons that only ever error.
  // Renders nothing while this is still loading too, rather than
  // flashing the card and then yanking it away a moment later.
  const { data: status } = useQuery({ queryKey: ['remote-sync-status'], queryFn: getRemoteSyncStatus })
  if (!status?.configured) return null

  return (
    <Card>
      <CardHeader
        title={title}
        actions={
          <Tooltip text={whatIsThisTooltip}>
            <span className="text-xs text-slate-400 dark:text-slate-500">What is this?</span>
          </Tooltip>
        }
      />
      <CardBody className="space-y-4">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <RemoteSyncDirection title={pushLabel} description={pushDescription} onPreview={onPreviewPush} onApply={onApplyPush} />
          <RemoteSyncDirection title={pullLabel} description={pullDescription} onPreview={onPreviewPull} onApply={onApplyPull} />
        </div>
      </CardBody>
    </Card>
  )
}

function RemoteSyncDirection({
  title,
  description,
  onPreview,
  onApply,
}: {
  title: string
  description: string
  onPreview: () => Promise<RemoteSyncSummary>
  onApply: () => Promise<RemoteSyncSummary>
}) {
  const { showToast } = useToast()
  const [preview, setPreview] = useState<RemoteSyncSummary | null>(null)
  const [error, setError] = useState<string | null>(null)

  const previewMutation = useMutation({
    mutationFn: onPreview,
    onSuccess: (summary) => {
      setError(null)
      setPreview(summary)
    },
    onError: (err) => setError(apiErrorMessage(err, 'Preview failed')),
  })

  const applyMutation = useMutation({
    mutationFn: onApply,
    onSuccess: (summary) => {
      setPreview(null)
      showToast(`Applied: ${summary.created} created, ${summary.updated} updated.`)
    },
    onError: (err) => setError(apiErrorMessage(err, 'Apply failed')),
  })

  const totalChanges = preview ? preview.created + preview.updated : 0

  return (
    <div className="rounded-md border border-slate-200 p-3 dark:border-slate-700">
      <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">{title}</p>
      <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{description}</p>

      {error && <p className="mt-2 text-xs text-red-600 dark:text-red-400">{error}</p>}

      {!preview && (
        <Button className="mt-3" variant="secondary" isLoading={previewMutation.isPending} onClick={() => previewMutation.mutate()}>
          Preview
        </Button>
      )}

      {preview && (
        <div className="mt-3 space-y-2">
          <div className="rounded-md border border-amber-300 bg-amber-50 p-2 text-xs text-amber-800 dark:border-amber-800 dark:bg-amber-500/10 dark:text-amber-300">
            <p className="font-semibold">Nothing has been written yet -- this is a preview.</p>
            <p className="mt-1">
              {preview.created} row(s) would be created, {preview.updated} would be updated, {preview.unchanged} are already
              identical.
            </p>
            {preview.changedList.length > 0 && (
              <ul className="mt-2 max-h-32 list-disc space-y-0.5 overflow-y-auto pl-4">
                {preview.changedList.map((name, i) => (
                  <li key={i}>{name}</li>
                ))}
              </ul>
            )}
          </div>
          <div className="flex gap-2">
            <Button variant="danger" isLoading={applyMutation.isPending} disabled={totalChanges === 0} onClick={() => applyMutation.mutate()}>
              Apply {totalChanges} change(s)
            </Button>
            <Button variant="secondary" onClick={() => setPreview(null)} disabled={applyMutation.isPending}>
              Cancel
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
