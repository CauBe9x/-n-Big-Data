import { useCallback, useEffect, useState } from 'react'

const BASE = import.meta.env.VITE_API_URL || ''

export async function api(path, options = {}) {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
    body: options.body ? JSON.stringify(options.body) : undefined,
  })
  if (!res.ok) {
    let msg = `Lỗi ${res.status}`
    try {
      const j = await res.json()
      msg = typeof j.detail === 'string' ? j.detail : 'Dữ liệu nhập chưa hợp lệ, hãy kiểm tra lại các trường.'
    } catch { /* bỏ qua */ }
    throw new Error(msg)
  }
  return res.json()
}

export const post = (path, body) => api(path, { method: 'POST', body })

export function qs(params) {
  const p = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') p.set(k, v)
  })
  const s = p.toString()
  return s ? `?${s}` : ''
}

/** Gọi API GET và theo dõi trạng thái tải / lỗi. */
export function useApi(path) {
  const [state, setState] = useState({ data: null, error: null, loading: true })
  const [nonce, setNonce] = useState(0)
  const reload = useCallback(() => setNonce((n) => n + 1), [])
  useEffect(() => {
    if (!path) return
    let alive = true
    setState((s) => ({ ...s, loading: true, error: null }))
    api(path)
      .then((data) => alive && setState({ data, error: null, loading: false }))
      .catch((error) => alive && setState({ data: null, error, loading: false }))
    return () => { alive = false }
  }, [path, nonce])
  return { ...state, reload }
}

const nf1 = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 1 })
const nf0 = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 0 })
const nf3 = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 3, minimumFractionDigits: 3 })
export const fmt = (v) => (v === null || v === undefined || Number.isNaN(v) ? '–' : nf1.format(v))
export const fmtInt = (v) => (v === null || v === undefined ? '–' : nf0.format(v))
export const fmt3 = (v) => (v === null || v === undefined ? '–' : nf3.format(v))
export const pct = (v, d = 1) => (v === null || v === undefined ? '–' : `${(v * 100).toFixed(d).replace('.', ',')}%`)
export const signedPct = (v) => `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(1).replace('.', ',')}%`
export const trieu = (v) => (v === null || v === undefined ? 'Thoả thuận' : `${fmt(v)} triệu`)
