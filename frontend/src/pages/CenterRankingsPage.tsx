import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '../auth/AuthContext'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { HorizontalBarChart } from '../components/ui/Charts'
import { EmptyState, ErrorBanner, Spinner } from '../components/ui/Feedback'
import { HeroBanner } from '../components/ui/HeroBanner'
import { PodiumTrophyIllustration } from '../components/ui/Illustrations'
import { useToast } from '../components/ui/ToastProvider'
import { apiErrorMessage } from '../lib/api'
import { fetchCenterRankings, listCenterScoringWeights, updateCenterScoringWeight } from '../lib/resources/centerScoring'
import { CENTER_SCORE_COMPONENTS, COMPONENT_LABELS, type CenterScoreComponent } from '../lib/types'

function formatComponentValue(component: CenterScoreComponent, raw: number | null): string {
  if (raw === null) return 'n/a'
  if (component === 'non_compliance_rate') return `${raw.toFixed(0)}%`
  if (component === 'outstanding_penalty') return `₹${raw.toLocaleString('en-IN')}`
  return String(raw)
}

export function CenterRankingsPage() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [error, setError] = useState<string | null>(null)

  const { data: rankings, isLoading: rankingsLoading } = useQuery({
    queryKey: ['center-rankings'],
    queryFn: () => fetchCenterRankings({}),
  })
  const { data: weights } = useQuery({ queryKey: ['center-scoring-weights'], queryFn: listCenterScoringWeights })

  const weightMutation = useMutation({
    mutationFn: ({ component, weight }: { component: CenterScoreComponent; weight: number }) =>
      updateCenterScoringWeight(component, weight),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['center-scoring-weights'] })
      queryClient.invalidateQueries({ queryKey: ['center-rankings'] })
      showToast('Weight updated')
    },
    onError: (err) => setError(apiErrorMessage(err, 'Could not update weight')),
  })

  return (
    <div className="space-y-6">
      <HeroBanner
        illustration={<PodiumTrophyIllustration className="h-full w-full" />}
        kicker="Leaderboard"
        title="Center Performance Rankings"
        subtitle="SOP non-compliance analysis across Delayed Cash Billing + Weekly Revenue Closure -- a composite score built from configurable weights, relative to the centers currently being compared, never against an absolute target."
      />
      {error && <ErrorBanner message={error} />}

      {rankings && rankings.length > 0 && (
        <Card>
          <CardHeader title="Top Centers by Composite Score" />
          <CardBody>
            <HorizontalBarChart
              data={rankings
                .filter((r) => r.composite_score !== null)
                .slice(0, 8)
                .map((r) => ({ label: r.centre_name, value: r.composite_score as number }))}
              domain={[0, 100]}
            />
          </CardBody>
        </Card>
      )}

      {user?.role === 'Admin' && (
        <Card>
          <CardHeader title="Scoring Weights" />
          <CardBody>
            <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">
              Equal weights by default — adjust to reflect real business priorities. Scores are relative to the
              centers currently being compared, not against an absolute target.
            </p>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              {CENTER_SCORE_COMPONENTS.map((component) => {
                const current = weights?.find((w) => w.component_key === component)
                return (
                  <div key={component}>
                    <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">{COMPONENT_LABELS[component]}</label>
                    <input
                      type="number"
                      step="0.05"
                      min="0"
                      className="w-full rounded border border-slate-300 bg-white px-2 py-1 text-sm text-slate-800 dark:border-slate-700 dark:bg-void-900 dark:text-slate-100"
                      defaultValue={current?.weight ?? 0}
                      onBlur={(e) => {
                        const value = Number(e.target.value)
                        if (!Number.isNaN(value) && value !== current?.weight) {
                          weightMutation.mutate({ component, weight: value })
                        }
                      }}
                    />
                  </div>
                )
              })}
            </div>
          </CardBody>
        </Card>
      )}

      <Card>
        <CardHeader title="Rankings" />
        <CardBody>
          {rankingsLoading && <Spinner />}
          {rankings && rankings.length === 0 && (
            <EmptyState
              title="No centers to rank"
              hint="No Delayed Cash Billing or Weekly Revenue Closure data has a case attached to a center yet."
            />
          )}
          {rankings && rankings.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs uppercase text-slate-500 dark:text-slate-400">
                  <tr>
                    <th className="py-2 pr-4">Rank</th>
                    <th className="py-2 pr-4">Center</th>
                    <th className="py-2 pr-4">Cases</th>
                    <th className="py-2 pr-4">Score</th>
                    {CENTER_SCORE_COMPONENTS.map((c) => (
                      <th key={c} className="py-2 pr-4">
                        {COMPONENT_LABELS[c]}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
                  {rankings.map((r) => (
                    <tr key={r.centre_code}>
                      <td className="py-2 pr-4 font-medium text-slate-800 dark:text-slate-100">#{r.rank}</td>
                      <td className="py-2 pr-4 text-slate-800 dark:text-slate-100">
                        {r.centre_name}
                        <div className="text-xs text-slate-500 dark:text-slate-400">{r.centre_code}</div>
                      </td>
                      <td className="py-2 pr-4 text-slate-500 dark:text-slate-400">{r.case_count}</td>
                      <td className="py-2 pr-4">
                        <span
                          className={`font-semibold ${
                            r.composite_score === null
                              ? 'text-slate-500 dark:text-slate-400'
                              : r.composite_score >= 66
                                ? 'text-green-600'
                                : r.composite_score >= 33
                                  ? 'text-yellow-600'
                                  : 'text-red-600'
                          }`}
                        >
                          {r.composite_score ?? '—'}
                        </span>
                      </td>
                      {CENTER_SCORE_COMPONENTS.map((c) => (
                        <td key={c} className="py-2 pr-4 text-slate-500 dark:text-slate-400">
                          {formatComponentValue(c, r.components[c]?.raw ?? null)}
                        </td>
                      ))}
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
