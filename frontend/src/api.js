export async function api(path, options = {}) {
  const res = await fetch(path, options)
  if (!res.ok) {
    let detail = res.statusText
    try { detail = (await res.json()).detail || detail } catch (e) {}
    throw new Error(detail)
  }
  return res.json()
}
