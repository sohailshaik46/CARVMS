import { Link, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { EmptyState, ErrorBanner, Spinner } from '../components/ui/Feedback'
import { apiErrorMessage } from '../lib/api'
import { globalSearch } from '../lib/resources/search'
import type { SearchableType, SearchResultItem } from '../lib/types'

const TYPE_LABELS: Record<SearchableType, string> = {
  delayed_cash_bill: 'Delayed Cash Billing',
  wrc_incident: 'Weekly Revenue Closure',
  org_node: 'Org Hierarchy Nodes',
  report_template: 'Report Templates',
}

function linkFor(item: SearchResultItem): string | null {
  switch (item.entity_type) {
    case 'delayed_cash_bill':
      return '/delayed-cash'
    case 'wrc_incident':
      return '/weekly-revenue-closure'
    case 'report_template':
      return '/reports'
    default:
      return null
  }
}

export function SearchPage() {
  const [params] = useSearchParams()
  const query = params.get('q') ?? ''

  const { data, isLoading, error } = useQuery({
    queryKey: ['search', query],
    queryFn: () => globalSearch(query),
    enabled: query.length > 0,
  })

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-100">Search results for "{query}"</h1>

      {isLoading && <Spinner />}
      {error && <ErrorBanner message={apiErrorMessage(error)} />}
      {data && data.total === 0 && <EmptyState title="No matches found" hint="Try a different term." />}

      {data &&
        (Object.entries(data.results) as [SearchableType, SearchResultItem[]][]).map(([type, items]) => (
          <Card key={type}>
            <CardHeader title={`${TYPE_LABELS[type]} (${items.length})`} />
            <CardBody>
              <ul className="divide-y divide-slate-200 dark:divide-slate-700">
                {items.map((item) => {
                  const href = linkFor(item)
                  return (
                    <li key={`${type}-${item.id}`} className="py-2">
                      {href ? (
                        <Link to={href} className="font-medium text-np-calming-blue hover:underline dark:text-neon-blue-400">
                          {item.title}
                        </Link>
                      ) : (
                        <span className="font-medium text-slate-800 dark:text-slate-200">{item.title}</span>
                      )}
                      {item.subtitle && <p className="text-xs text-slate-500 dark:text-slate-400">{item.subtitle}</p>}
                    </li>
                  )
                })}
              </ul>
            </CardBody>
          </Card>
        ))}
    </div>
  )
}
