import { apiFetch } from './client'

export const getFiles = (folderLink) =>
  apiFetch(`/drive/files?folder_link=${encodeURIComponent(folderLink)}`)
