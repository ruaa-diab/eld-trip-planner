const API_URL = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')

export class ApiError extends Error {
  /**
   * @param {number} status  HTTP status (0 when the server could not be reached)
   * @param {string} code    API error code, e.g. "address_not_found"
   * @param {string} message Readable message
   * @param {object|array|undefined} fields  Field names (address_not_found) or per-field messages (invalid_input)
   * @param {object|undefined} reasons  address_not_found only: field → "not_found" | "invalid_place"
   */
  constructor(status, code, message, fields, reasons) {
    super(message)
    this.status = status
    this.code = code
    this.fields = fields
    this.reasons = reasons
  }
}

/**
 * GET /api/autocomplete. Resolves with up to 5 labels; any failure resolves with [] (suggestions
 * are optional). Rejects only with AbortError when a newer request cancelled this one.
 */
export async function fetchSuggestions(text, signal) {
  try {
    const resp = await fetch(`${API_URL}/api/autocomplete?text=${encodeURIComponent(text)}`, { signal })
    if (!resp.ok) return []
    const body = await resp.json()
    return Array.isArray(body?.suggestions) ? body.suggestions.map((s) => s.label).filter(Boolean) : []
  } catch (err) {
    if (err.name === 'AbortError') throw err
    return []
  }
}

/** POST /api/plan-trip. Resolves with the plan; rejects with ApiError (or AbortError when cancelled). */
export async function planTrip(payload, signal) {
  let resp
  try {
    resp = await fetch(`${API_URL}/api/plan-trip`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal,
    })
  } catch (err) {
    if (err.name === 'AbortError') throw err
    throw new ApiError(0, 'network_error', "Can't reach the server. Check your connection and try again.")
  }

  let body = null
  try {
    body = await resp.json()
  } catch {
    // Non-JSON body (e.g. a proxy error page); handled below.
  }

  if (resp.ok && body) return body

  const error = body?.error
  if (error) throw new ApiError(resp.status, error.code, error.message, error.fields, error.reasons)
  throw new ApiError(resp.status, 'unknown_error', `Something went wrong (HTTP ${resp.status}). Try again.`)
}
