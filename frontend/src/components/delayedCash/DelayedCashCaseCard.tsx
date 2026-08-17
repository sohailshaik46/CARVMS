import { useRef, useState, type FormEvent } from 'react'
import { Button } from '../ui/Button'
import { TextAreaField, TextField } from '../ui/Field'
import { ErrorBanner } from '../ui/Feedback'
import { apiErrorMessage } from '../../lib/api'
import type { CenterDirectoryEntry, PublicDelayedCashCase, TatStatus } from '../../lib/types'

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
}

function formatDeadline(value: string | null): string {
  if (!value) return 'Not set'
  return new Date(value).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })
}

function TatBadge({ status }: { status: TatStatus }) {
  if (status === 'overdue') {
    return (
      <span className="inline-flex items-center rounded-full bg-brand-100 px-2.5 py-0.5 text-xs font-medium text-brand-700">
        Response window has closed
      </span>
    )
  }
  if (status === 'within_window') {
    return (
      <span className="inline-flex items-center rounded-full bg-[color:var(--color-np-teal)]/15 px-2.5 py-0.5 text-xs font-medium text-[color:var(--color-np-teal)]">
        Within response window
      </span>
    )
  }
  return (
    <span className="inline-flex items-center rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-500">
      No deadline set
    </span>
  )
}

export interface DelayedCashResponseFields {
  responder_name: string
  responder_npid: string
  responder_email: string
  reason: string
  selected_center_code?: string
  selected_center_name?: string
}

/** The header summary + submission form for one Delayed Cash Billing case.
 * Shared by both access paths -- the per-case token page and the single
 * shared link's open-cases picker -- so a fix or field change to the form
 * itself never has to happen twice. */
export function DelayedCashCaseCard({
  caseData,
  centerDirectory,
  onSubmit,
}: {
  caseData: PublicDelayedCashCase
  centerDirectory: CenterDirectoryEntry[] | undefined
  onSubmit: (fields: DelayedCashResponseFields, evidence: File) => Promise<unknown>
}) {
  const [name, setName] = useState('')
  const [npid, setNpid] = useState('')
  const [email, setEmail] = useState('')
  const [reason, setReason] = useState('')
  const [centerCode, setCenterCode] = useState('')
  const [centerName, setCenterName] = useState('')
  const [evidenceFile, setEvidenceFile] = useState<File | null>(null)
  const [attachmentError, setAttachmentError] = useState<string | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [justSubmitted, setJustSubmitted] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Deliberately NOT pre-filled from the case's own center -- the responder
  // must actively pick their center. A mismatch is recorded, not blocked,
  // per the design, but it should only ever reflect a real choice.
  function handleCenterCodeChange(value: string) {
    setCenterCode(value)
    const match = centerDirectory?.find((c) => c.code === value)
    if (match) setCenterName(match.name)
  }

  function handleCenterNameChange(value: string) {
    setCenterName(value)
    const match = centerDirectory?.find((c) => c.name === value)
    if (match) setCenterCode(match.code)
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setSubmitError(null)
    if (!evidenceFile) {
      setAttachmentError('Supporting attachment is mandatory.')
      return
    }
    setAttachmentError(null)
    setIsSubmitting(true)
    try {
      await onSubmit(
        {
          responder_name: name,
          responder_npid: npid,
          responder_email: email,
          reason,
          selected_center_code: centerCode || undefined,
          selected_center_name: centerName || undefined,
        },
        evidenceFile,
      )
      setJustSubmitted(true)
      setName('')
      setNpid('')
      setEmail('')
      setReason('')
      setEvidenceFile(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
    } catch (err) {
      setSubmitError(apiErrorMessage(err, 'Could not submit your response'))
    } finally {
      setIsSubmitting(false)
    }
  }

  const codeOptionsId = `center-code-options-${caseData.centre_code}`
  const nameOptionsId = `center-name-options-${caseData.centre_code}`

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
      <div className="border-b border-slate-100 pb-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h1 className="text-lg font-semibold text-slate-900">{caseData.centre_name}</h1>
            <p className="text-xs text-slate-500">{caseData.centre_code}</p>
          </div>
          <TatBadge status={caseData.tat_status} />
        </div>
        <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
          <div>
            <dt className="text-xs text-slate-500">Period</dt>
            <dd className="font-medium text-slate-800">
              {formatDate(caseData.period_start)} – {formatDate(caseData.period_end)}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">Delayed bills</dt>
            <dd className="font-medium text-slate-800">{caseData.total_bills}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">Calculated penalty</dt>
            <dd className="font-medium text-slate-800">
              ₹{Number(caseData.calculated_penalty).toLocaleString('en-IN')}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">Respond by</dt>
            <dd className="font-medium text-slate-800">{formatDeadline(caseData.deadline)}</dd>
          </div>
        </dl>

        {caseData.bills.length > 0 && (
          <div className="mt-4">
            <p className="mb-1 text-xs font-medium text-slate-500">
              Bill(s) this response covers -- please address each one in your remarks below:
            </p>
            <div className="overflow-x-auto rounded-md border border-slate-200">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 uppercase text-slate-500">
                  <tr>
                    <th className="px-2 py-1.5">Sales Bill</th>
                    <th className="px-2 py-1.5">Bill Date</th>
                    <th className="px-2 py-1.5">Delay (days)</th>
                    <th className="px-2 py-1.5">Penalty</th>
                    <th className="px-2 py-1.5">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {caseData.bills.map((b) => (
                    <tr key={b.sales_bill}>
                      <td className="px-2 py-1.5 font-medium text-slate-800">{b.sales_bill}</td>
                      <td className="px-2 py-1.5 text-slate-600">{formatDate(b.bill_date)}</td>
                      <td className="px-2 py-1.5 text-slate-600">{b.calculated_day_difference}</td>
                      <td className="px-2 py-1.5 text-slate-600">₹{Number(b.calculated_penalty).toLocaleString('en-IN')}</td>
                      <td className="px-2 py-1.5 text-slate-600">{b.considered ? b.considered.replace(/_/g, ' ') : 'Awaiting your remark'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {(justSubmitted || caseData.already_responded) && (
        <p className="mt-4 rounded-md bg-[color:var(--color-np-teal)]/10 px-3 py-2 text-sm text-[color:var(--color-np-deep-blue)]">
          {justSubmitted
            ? 'Your response has been submitted. If Vigilance needs further proof, you will be notified by email and can submit again below.'
            : 'A response has already been recorded for this case. You can still submit again below — for example, if Vigilance has asked for further proof.'}
        </p>
      )}

      <form onSubmit={handleSubmit} className="mt-5 space-y-4">
        {submitError && <ErrorBanner message={submitError} />}

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label htmlFor={`center_code-${caseData.centre_code}`} className="mb-1 block text-sm font-medium text-slate-700">
              Center Code <span className="text-brand-600">*</span>
            </label>
            <input
              id={`center_code-${caseData.centre_code}`}
              list={codeOptionsId}
              required
              autoComplete="off"
              placeholder="Type to search…"
              className="block w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-brand-500 focus:outline focus:outline-2 focus:outline-brand-500/30"
              value={centerCode}
              onChange={(e) => handleCenterCodeChange(e.target.value)}
            />
            <datalist id={codeOptionsId}>
              {(centerDirectory ?? []).map((c) => (
                <option key={c.code} value={c.code}>
                  {c.name}
                </option>
              ))}
            </datalist>
          </div>
          <div>
            <label htmlFor={`center_name-${caseData.centre_code}`} className="mb-1 block text-sm font-medium text-slate-700">
              Center Name <span className="text-brand-600">*</span>
            </label>
            <input
              id={`center_name-${caseData.centre_code}`}
              list={nameOptionsId}
              required
              autoComplete="off"
              placeholder="Type to search…"
              className="block w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-brand-500 focus:outline focus:outline-2 focus:outline-brand-500/30"
              value={centerName}
              onChange={(e) => handleCenterNameChange(e.target.value)}
            />
            <datalist id={nameOptionsId}>
              {(centerDirectory ?? []).map((c) => (
                <option key={c.code} value={c.name} />
              ))}
            </datalist>
          </div>
        </div>
        {centerCode &&
          centerCode !== caseData.centre_code &&
          centerDirectory?.some((c) => c.code === centerCode) && (
            <p className="rounded-md bg-brand-50 px-3 py-2 text-xs text-brand-700">
              You selected a different center than this case is linked to ({caseData.centre_code}). That's fine
              if you're responding on their behalf — Vigilance will see both.
            </p>
          )}

        <TextField
          id={`responder_name-${caseData.centre_code}`}
          label={
            <>
              Center Manager Name <span className="text-brand-600">*</span>
            </>
          }
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <TextField
          id={`responder_npid-${caseData.centre_code}`}
          label={
            <>
              Center Manager NP ID <span className="text-brand-600">*</span>
            </>
          }
          required
          value={npid}
          onChange={(e) => setNpid(e.target.value)}
        />
        <TextField
          id={`responder_email-${caseData.centre_code}`}
          type="email"
          label={
            <>
              Center Manager Email ID <span className="text-brand-600">*</span>
            </>
          }
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <TextAreaField
          id={`reason-${caseData.centre_code}`}
          label={
            <>
              Reason / Remarks for the delayed bill(s) <span className="text-brand-600">*</span>
            </>
          }
          required
          rows={4}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
        <div>
          <label htmlFor={`evidence-${caseData.centre_code}`} className="mb-1 block text-sm font-medium text-slate-700">
            Supporting Evidence <span className="text-brand-600">*</span>
          </label>
          <input
            id={`evidence-${caseData.centre_code}`}
            ref={fileInputRef}
            type="file"
            required
            className="block w-full text-sm text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-brand-50 file:px-3 file:py-2 file:text-sm file:font-medium file:text-brand-700 hover:file:bg-brand-100"
            onChange={(e) => {
              setEvidenceFile(e.target.files?.[0] ?? null)
              setAttachmentError(null)
            }}
          />
          {attachmentError && <p className="mt-1 text-xs text-red-600">{attachmentError}</p>}
          {!attachmentError && (
            <p className="mt-1 text-xs text-slate-400">
              A supporting attachment is mandatory — the submit button will not proceed without one.
            </p>
          )}
        </div>

        <Button type="submit" isLoading={isSubmitting} className="w-full">
          Submit Response
        </Button>
      </form>
    </div>
  )
}
