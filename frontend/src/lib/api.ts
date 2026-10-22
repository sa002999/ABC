export const apiBase = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ?? ''
export const apiConfigured = true

export type Capabilities = { orderRead: boolean; voucher: boolean; cancellation: boolean; catalogRead: boolean; bookingDraft: boolean; booking: boolean; quote: boolean; inventoryHold: boolean; payment: boolean; aiGeneration: boolean; account: boolean; looks: boolean; mcp: boolean }
const unavailable: Capabilities = { orderRead: false, voucher: false, cancellation: false, catalogRead: false, bookingDraft: false, booking: false, quote: false, inventoryHold: false, payment: false, aiGeneration: false, account: false, looks: false, mcp: false }
let backend = { connected: false, capabilities: unavailable }
const listeners = new Set<() => void>()
export const backendSnapshot = () => backend
export const subscribeBackend = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener) } }
export function featureForPath(path: string): keyof Capabilities | null {
  if (/^\/api\/(try-on|models|scenes)(\/|\?|$)/.test(path) || path.startsWith('/api/account/generation-usage')) return 'aiGeneration'
  if (path.startsWith('/api/account/mcp')) return 'mcp'
  if (/^\/api\/looks(\/|\?|$)/.test(path) || path.startsWith('/api/plans/compare')) return 'looks'
  if (path.startsWith('/api/account')) return 'account'
  if (/^\/api\/booking-drafts(\/|\?|$)/.test(path)) return 'bookingDraft'
  if (path.startsWith('/api/pricing')) return 'quote'
  if (path.startsWith('/api/availability/holds')) return 'inventoryHold'
  if (path.startsWith('/api/orders')) return 'orderRead'
  if (/^\/api\/bookings\/[^/]+\/voucher/.test(path)) return 'voucher'
  if (/^\/api\/bookings\/[^/]+\/(cancel|cancellation-quote)/.test(path)) return 'cancellation'
  if (/^\/api\/(bookings|admin)(\/|\?|$)/.test(path)) return 'booking'
  return null
}

function acceptCapabilities(payload: unknown) {
  const incoming = (payload as { meta?: { capabilities?: Partial<Capabilities> } })?.meta?.capabilities
  if (!incoming) return
  const capabilities = Object.fromEntries(Object.keys(unavailable).map(key => [key, incoming[key as keyof Capabilities] === true])) as Capabilities
  if (backend.connected && JSON.stringify(capabilities) === JSON.stringify(backend.capabilities)) return
  backend = { connected: true, capabilities }; listeners.forEach(listener => listener())
}

export class ApiError extends Error {
  constructor(message: string, public status: number, public code = '', public details?: unknown) { super(message) }
}

export async function request<T>(path: string, options: { method?: string; body?: unknown; token?: string; key?: string; signal?: AbortSignal } = {}): Promise<T> {
  if (!apiConfigured) throw new ApiError('尚未設定後端 API。此操作未送出，也不會建立交易或生成圖片。', 0, 'NOT_CONFIGURED')
  const feature = path === '/api/bookings' && options.method === 'POST' ? 'payment' : featureForPath(path)
  if (feature && !(path === '/api/account' && options.method === 'PUT') && !backend.capabilities[feature]) throw new ApiError('此功能尚未啟用，操作未送出。請依目前服務狀態使用已開放的功能。', 0, 'FEATURE_UNAVAILABLE')
  let response: Response
  try { response = await fetch(`${apiBase}${path}`, {
    method: options.method ?? 'GET',
    headers: { Accept: 'application/json', ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...(options.token ? { Authorization: `Bearer ${options.token}` } : {}), ...(options.key ? { 'Idempotency-Key': options.key } : {}) },
    body: options.body ? JSON.stringify(options.body) : undefined,
    signal: options.signal,
  }) } catch (error) {
    if (options.signal?.aborted) throw error
    if (backend.connected) { backend = { connected: false, capabilities: unavailable }; listeners.forEach(listener => listener()) }
    throw new ApiError('無法連接後端服務，請確認本機 API 已啟動後重試。', 0, 'NETWORK_ERROR')
  }
  const payload = await response.json().catch(() => null)
  if (!response.ok) throw new ApiError(payload?.error?.message ?? `請求失敗（${response.status}），請稍後重試。`, response.status, payload?.error?.code, payload)
  if(payload===null)throw new ApiError('API 回應格式不正確，請確認後端網址與服務狀態。',response.status,'INVALID_RESPONSE')
  acceptCapabilities(payload)
  if (payload?.data && Array.isArray(payload.data)) {
    if (/^\/api\/(stores|models)(\?|$)/.test(path)) payload.data=payload.data.map((v: Record<string, unknown>) => ({...v,name:localized(v.name),address:localized(v.address),hours:v.openingHours?JSON.stringify(v.openingHours):undefined}))
    if (path.includes('/availability?')) payload.data=payload.data.map((v: Record<string, unknown>) => ({...v,id:v.slotId,label:new Date(v.startsAt as string).toLocaleTimeString('zh-TW',{timeZone:'Asia/Tokyo',hour:'2-digit',minute:'2-digit'})}))
  }
  if (/^\/api\/stores\/[^/]+$/.test(path) && payload) {payload.name=localized(payload.name);payload.address=localized(payload.address)}
  const resolveAssets=(value:unknown):unknown=>{
    if(Array.isArray(value))return value.map(resolveAssets)
    if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).map(([key,item])=>[key,typeof item==='string'&&/url$/i.test(key)?assetUrl(item):resolveAssets(item)]))
    return value
  }
  return resolveAssets(payload) as T
}

export function unwrap<T>(payload: T | { data: T }): T { return payload && typeof payload === 'object' && 'data' in payload && !('draftId' in payload) ? payload.data : payload as T }
export const localized = (value: unknown): string => typeof value === 'string' ? value : value && typeof value === 'object' ? String((value as Record<string, unknown>)['zh-Hant'] ?? Object.values(value)[0] ?? '') : ''
export const assetUrl = (value: string) => value?.startsWith('/api/') ? apiBase + value : value
export const actionKey = () => crypto.randomUUID()
