import { api } from '../api'
import type { EmailConnectAuthorization, EmailConnectionStatus, EmailProviderInfo } from '../types'

export async function listEmailProviders(): Promise<EmailProviderInfo[]> {
  const { data } = await api.get<EmailProviderInfo[]>('/email/providers')
  return data
}

export async function getEmailConnectAuthorizationUrl(): Promise<EmailConnectAuthorization> {
  const { data } = await api.get<EmailConnectAuthorization>('/email/connect')
  return data
}

export async function getEmailConnectionStatus(): Promise<EmailConnectionStatus> {
  const { data } = await api.get<EmailConnectionStatus>('/email/status')
  return data
}

export async function disconnectEmail(): Promise<void> {
  await api.post('/email/disconnect')
}
