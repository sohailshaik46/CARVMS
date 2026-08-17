import { api } from '../api'
import type { Token, UserOut } from '../types'

export interface RegisterPayload {
  username: string
  email: string
  password: string
  phone_number?: string
}

export interface LoginPayload {
  username: string
  password: string
}

export interface PasswordChangePayload {
  current_password: string
  new_password: string
}

export async function registerUser(payload: RegisterPayload): Promise<{ message: string }> {
  const { data } = await api.post('/auth/register', payload)
  return data
}

export async function login(payload: LoginPayload): Promise<Token> {
  const { data } = await api.post<Token>('/auth/login', payload)
  return data
}

export async function fetchMe(): Promise<UserOut> {
  const { data } = await api.get<UserOut>('/auth/me')
  return data
}

export async function changeMyPassword(payload: PasswordChangePayload): Promise<UserOut> {
  const { data } = await api.patch<UserOut>('/auth/me/password', payload)
  return data
}

export async function updateMyPhoneNumber(phone_number: string): Promise<UserOut> {
  const { data } = await api.patch<UserOut>('/auth/me/phone', { phone_number })
  return data
}

export async function requestPasswordResetOtp(phone_number: string): Promise<{ message: string }> {
  const { data } = await api.post('/auth/forgot-password', { phone_number })
  return data
}

export async function resetPasswordWithOtp(payload: {
  phone_number: string
  code: string
  new_password: string
}): Promise<{ message: string }> {
  const { data } = await api.post('/auth/reset-password', payload)
  return data
}
