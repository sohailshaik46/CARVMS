import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import nephroplusLogo from '../assets/nephroplus-logo.svg'
import { WrcCaseCard, type WrcResponseFields } from '../components/weeklyRevenueClosure/WrcCaseCard'
import { EmptyState, Spinner } from '../components/ui/Feedback'
import {
  getWrcCenterDirectory,
  getWrcOpenCasesForCenter,
  submitWrcCaseResponseById,
} from '../lib/resources/weeklyRevenueClosurePublic'

/** The single shared response link for Weekly Revenue Closure -- mirrors
 * DelayedCashOpenLinkPage exactly. See weekly_revenue_response_service's
 * module docstring (backend) for the security trade-off this makes. */
export function WeeklyRevenueOpenLinkPage() {
  const [centerCode, setCenterCode] = useState('')
  const [centerName, setCenterName] = useState('')
  const queryClient = useQueryClient()

  const { data: centerDirectory } = useQuery({
    queryKey: ['weekly-revenue-centers-directory'],
    queryFn: getWrcCenterDirectory,
  })

  const resolvedCode = centerDirectory?.some((c) => c.code === centerCode) ? centerCode : ''

  const {
    data: openCases,
    isLoading,
    error,
  } = useQuery({
    queryKey: ['weekly-revenue-open-cases', resolvedCode],
    queryFn: () => getWrcOpenCasesForCenter(resolvedCode),
    enabled: !!resolvedCode,
  })

  function handleCenterCodeChange(value: string) {
    setCenterCode(value)
    const match = centerDirectory?.find((c) => c.code === value)
    setCenterName(match ? match.name : '')
  }

  function handleCenterNameChange(value: string) {
    setCenterName(value)
    const match = centerDirectory?.find((c) => c.name === value)
    setCenterCode(match ? match.code : '')
  }

  async function handleSubmit(caseId: number, fields: WrcResponseFields, evidence: File) {
    const result = await submitWrcCaseResponseById(caseId, fields, evidence)
    queryClient.invalidateQueries({ queryKey: ['weekly-revenue-open-cases', resolvedCode] })
    return result
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10">
      <div className="w-full max-w-lg space-y-4">
        <div className="mb-2 flex flex-col items-center text-center">
          <img src={nephroplusLogo} alt="NephroPlus" className="h-9 w-auto" />
          <p className="mt-3 text-sm font-medium text-[color:var(--color-np-deep-blue)]">
            Weekly Revenue Closure — Response Portal
          </p>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
          <p className="mb-4 text-sm text-slate-600">
            Select your center to see any Weekly Revenue Closure incident that needs a response.
          </p>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="wrc_picker_center_code" className="mb-1 block text-sm font-medium text-slate-700">
                Center Code
              </label>
              <input
                id="wrc_picker_center_code"
                list="wrc-picker-center-code-options"
                autoComplete="off"
                placeholder="Type to search…"
                className="block w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-brand-500 focus:outline focus:outline-2 focus:outline-brand-500/30"
                value={centerCode}
                onChange={(e) => handleCenterCodeChange(e.target.value)}
              />
              <datalist id="wrc-picker-center-code-options">
                {(centerDirectory ?? []).map((c) => (
                  <option key={c.code} value={c.code}>
                    {c.name}
                  </option>
                ))}
              </datalist>
            </div>
            <div>
              <label htmlFor="wrc_picker_center_name" className="mb-1 block text-sm font-medium text-slate-700">
                Center Name
              </label>
              <input
                id="wrc_picker_center_name"
                list="wrc-picker-center-name-options"
                autoComplete="off"
                placeholder="Type to search…"
                className="block w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-brand-500 focus:outline focus:outline-2 focus:outline-brand-500/30"
                value={centerName}
                onChange={(e) => handleCenterNameChange(e.target.value)}
              />
              <datalist id="wrc-picker-center-name-options">
                {(centerDirectory ?? []).map((c) => (
                  <option key={c.code} value={c.name} />
                ))}
              </datalist>
            </div>
          </div>
        </div>

        {resolvedCode && isLoading && (
          <div className="flex justify-center rounded-lg border border-slate-200 bg-white py-8 shadow-sm">
            <Spinner />
          </div>
        )}

        {resolvedCode && error && (
          <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
            Could not load cases for this center. Please try again.
          </p>
        )}

        {resolvedCode && openCases && openCases.length === 0 && (
          <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
            <EmptyState
              title="No open cases right now"
              hint="This center has no Weekly Revenue Closure incident currently awaiting a response."
            />
          </div>
        )}

        {openCases?.map((caseItem) => (
          <WrcCaseCard
            key={caseItem.id}
            caseData={caseItem}
            centerDirectory={centerDirectory}
            onSubmit={(fields, evidence) => handleSubmit(caseItem.id, fields, evidence)}
          />
        ))}

        <p className="text-center text-xs text-slate-400">NephroPlus Vigilance Team</p>
      </div>
    </div>
  )
}
