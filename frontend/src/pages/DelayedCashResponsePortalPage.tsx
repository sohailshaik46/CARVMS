import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import nephroplusLogo from '../assets/nephroplus-logo.svg'
import { DelayedCashCaseCard, type DelayedCashResponseFields } from '../components/delayedCash/DelayedCashCaseCard'
import { Spinner } from '../components/ui/Feedback'
import {
  getCenterDirectory,
  getPublicDelayedCashCase,
  submitDelayedCashCaseResponse,
} from '../lib/resources/delayedCashPublic'

export function DelayedCashResponsePortalPage() {
  const { token = '' } = useParams<{ token: string }>()
  const queryClient = useQueryClient()

  const {
    data: caseData,
    isLoading,
    error: caseError,
  } = useQuery({
    queryKey: ['delayed-cash-public-case', token],
    queryFn: () => getPublicDelayedCashCase(token),
    retry: false,
  })

  const { data: centerDirectory } = useQuery({
    queryKey: ['delayed-cash-centers-directory'],
    queryFn: getCenterDirectory,
  })

  async function handleSubmit(fields: DelayedCashResponseFields, evidence: File) {
    const result = await submitDelayedCashCaseResponse(token, fields, evidence)
    queryClient.invalidateQueries({ queryKey: ['delayed-cash-public-case', token] })
    return result
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10">
      <div className="w-full max-w-lg">
        <div className="mb-6 flex flex-col items-center text-center">
          <img src={nephroplusLogo} alt="NephroPlus" className="h-9 w-auto" />
          <p className="mt-3 text-sm font-medium text-[color:var(--color-np-deep-blue)]">
            Delayed Cash Billing — Response Required
          </p>
        </div>

        {isLoading && (
          <div className="flex justify-center rounded-lg border border-slate-200 bg-white py-8 shadow-sm">
            <Spinner />
          </div>
        )}

        {caseError && !isLoading && (
          <div className="rounded-lg border border-slate-200 bg-white py-4 text-center shadow-sm">
            <p className="text-sm font-medium text-slate-800">This link is invalid or has expired.</p>
            <p className="mt-1 text-xs text-slate-500">
              Please check the link from your notification email, or contact the Vigilance team for a new one.
            </p>
          </div>
        )}

        {caseData && (
          <DelayedCashCaseCard caseData={caseData} centerDirectory={centerDirectory} onSubmit={handleSubmit} />
        )}

        <p className="mt-4 text-center text-xs text-slate-400">
          NephroPlus Vigilance Team · This link is unique to your center and case.
        </p>
      </div>
    </div>
  )
}
