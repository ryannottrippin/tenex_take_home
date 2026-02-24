import { apiFetch } from './client'

export const LOGIN_URL = `${import.meta.env.VITE_API_URL}/auth/google`

export const getMe = () => apiFetch('/auth/me')
