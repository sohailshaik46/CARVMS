import { api } from '../api'
import type { CenterRanking, CenterScoreComponent, CenterScoringWeight, DashboardFilters } from '../types'

export async function listCenterScoringWeights(): Promise<CenterScoringWeight[]> {
  const { data } = await api.get<CenterScoringWeight[]>('/center-scoring/weights')
  return data
}

export async function updateCenterScoringWeight(component: CenterScoreComponent, weight: number): Promise<CenterScoringWeight> {
  const { data } = await api.patch<CenterScoringWeight>(`/center-scoring/weights/${component}`, { weight })
  return data
}

export async function fetchCenterRankings(filters: DashboardFilters): Promise<CenterRanking[]> {
  const { data } = await api.get<CenterRanking[]>('/center-scoring/rankings', { params: filters })
  return data
}
