import { api } from '../api'
import type { SearchResponse } from '../types'

export async function globalSearch(query: string): Promise<SearchResponse> {
  const { data } = await api.get<SearchResponse>('/search', { params: { q: query } })
  return data
}
