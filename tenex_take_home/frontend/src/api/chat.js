import { apiFetch } from './client'

export const sendMessage = (folderLink, message, history) =>
  apiFetch('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ folder_link: folderLink, message, history }),
  })
