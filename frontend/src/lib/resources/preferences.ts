import { api } from '../api'
import type { UserPreferences, UserPreferencesUpdate } from '../types'

export async function getMyPreferences(): Promise<UserPreferences> {
  const { data } = await api.get<UserPreferences>('/me/preferences')
  return data
}

export async function updateMyPreferences(payload: UserPreferencesUpdate): Promise<UserPreferences> {
  const { data } = await api.put<UserPreferences>('/me/preferences', payload)
  return data
}
