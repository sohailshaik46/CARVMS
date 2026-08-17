const RISK_CLASSES: Record<string, string> = {
  Low: 'bg-green-100 text-green-800 dark:bg-green-500/15 dark:text-green-300',
  Medium: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-500/15 dark:text-yellow-300',
  High: 'bg-orange-100 text-orange-800 dark:bg-orange-500/15 dark:text-orange-300',
  Critical: 'bg-red-100 text-red-800 dark:bg-red-500/15 dark:text-red-300',
}

const STATUS_CLASSES: Record<string, string> = {
  Draft: 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-300',
  Assigned: 'bg-blue-100 text-blue-800 dark:bg-blue-500/15 dark:text-blue-300',
  'In Progress': 'bg-indigo-100 text-indigo-800 dark:bg-indigo-500/15 dark:text-indigo-300',
  'Under Review': 'bg-purple-100 text-purple-800 dark:bg-purple-500/15 dark:text-purple-300',
  'Action Required': 'bg-orange-100 text-orange-800 dark:bg-orange-500/15 dark:text-orange-300',
  Closed: 'bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-400',
  Cancelled: 'bg-slate-200 text-slate-500 line-through dark:bg-slate-700 dark:text-slate-400',
  Open: 'bg-blue-100 text-blue-800 dark:bg-blue-500/15 dark:text-blue-300',
  Resolved: 'bg-green-100 text-green-800 dark:bg-green-500/15 dark:text-green-300',
  Proposed: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-500/15 dark:text-yellow-300',
  Approved: 'bg-green-100 text-green-800 dark:bg-green-500/15 dark:text-green-300',
  Rejected: 'bg-red-100 text-red-800 dark:bg-red-500/15 dark:text-red-300',
  Recovered: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300',
  Escalated: 'bg-orange-100 text-orange-800 dark:bg-orange-500/15 dark:text-orange-300',
  Dismissed: 'bg-slate-200 text-slate-500 dark:bg-slate-700 dark:text-slate-400',
  uploaded: 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-300',
  profiling: 'bg-blue-100 text-blue-800 dark:bg-blue-500/15 dark:text-blue-300',
  clean: 'bg-green-100 text-green-800 dark:bg-green-500/15 dark:text-green-300',
  failed: 'bg-red-100 text-red-800 dark:bg-red-500/15 dark:text-red-300',
  archived: 'bg-slate-200 text-slate-500 dark:bg-slate-700 dark:text-slate-400',
  completed: 'bg-green-100 text-green-800 dark:bg-green-500/15 dark:text-green-300',
  published: 'bg-blue-100 text-blue-800 dark:bg-blue-500/15 dark:text-blue-300',
  closed: 'bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-400',
  validated: 'bg-purple-100 text-purple-800 dark:bg-purple-500/15 dark:text-purple-300',
  awaiting_cap_input: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-500/15 dark:text-yellow-300',
  capped: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300',
  considered: 'bg-green-100 text-green-800 dark:bg-green-500/15 dark:text-green-300',
  not_considered: 'bg-red-100 text-red-800 dark:bg-red-500/15 dark:text-red-300',
  manual_check: 'bg-sky-100 text-sky-800 dark:bg-sky-500/15 dark:text-sky-300',
  needs_more_detail: 'bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300',
  needs_proof: 'bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300',
  pending: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-500/15 dark:text-yellow-300',
}

export function Badge({ children, tone = 'default' }: { children: string; tone?: 'default' | 'risk' | 'status' }) {
  const classes =
    tone === 'risk'
      ? RISK_CLASSES[children] ?? 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-300'
      : STATUS_CLASSES[children] ?? 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-300'
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${classes}`}>
      {children}
    </span>
  )
}
