const BASE_URL = import.meta.env.VITE_API_URL

export async function apiFetch(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    credentials: 'include',
    ...options,
  })
  const data = await res.json()
  if (data.error) throw new Error(data.error)
  return data
}
