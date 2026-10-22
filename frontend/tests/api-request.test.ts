import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

beforeEach(() => { vi.resetModules(); vi.stubEnv('VITE_API_BASE_URL', 'http://127.0.0.1:8000') })
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs() })

describe('後端功能狀態與錯誤處理', () => {
  it('原生草稿的 data 欄位不會讓草稿 ID 與版本被解包丟失', async () => {
    const api=await import('../src/lib/api')
    const draft={draftId:'draft',version:2,data:{guests:[]}}
    expect(api.unwrap(draft)).toBe(draft)
    expect(api.unwrap({data:[1,2]})).toEqual([1,2])
  })
  it('成功讀取公開資料後，仍不允許呼叫尚未開放的付款、收藏或 AI 端點', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: [], meta: { capabilities: { catalogRead: true, booking: false, quote: false, inventoryHold: false, payment: false, aiGeneration: false } } })))
    vi.stubGlobal('fetch', fetcher)
    const api = await import('../src/lib/api')
    await expect(api.request('/api/plans')).resolves.toHaveProperty('data', [])
    expect(api.backendSnapshot().connected).toBe(true)
    fetcher.mockClear()
    for (const path of ['/api/looks', '/api/try-on/sessions', '/api/pricing/quote', '/api/availability/holds', '/api/bookings']) {
      await expect(api.request(path, { method: 'POST', body: {} })).rejects.toMatchObject({ code: 'FEATURE_UNAVAILABLE' })
    }
    expect(fetcher).not.toHaveBeenCalled()
  })
  it('公開報價與保留能力可啟用草稿，但不會連帶開放預約成立或付款', async () => {
    const meta = { capabilities: { catalogRead: true, bookingDraft: true, quote: true, inventoryHold: true, booking: false, payment: false } }
    const fetcher = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ data: { status: 'ok' }, meta }))))
    vi.stubGlobal('fetch', fetcher)
    const api = await import('../src/lib/api')
    await api.request('/api/health')
    for (const path of ['/api/booking-drafts', '/api/pricing/quote', '/api/availability/holds']) {
      await api.request(path, { method: 'POST', token: 'verified-id-token', key: 'same-request-key', body: { fixture: true } })
      const [, options] = fetcher.mock.calls.at(-1)!
      expect(options.headers.Authorization).toBe('Bearer verified-id-token')
      expect(options.headers['Idempotency-Key']).toBe('same-request-key')
    }
    expect(api.featureForPath('/api/booking-drafts/own-draft')).toBe('bookingDraft')
    await expect(api.request('/api/bookings', { method: 'POST' })).rejects.toMatchObject({ code: 'FEATURE_UNAVAILABLE' })
    await expect(api.request('/api/orders/order')).rejects.toMatchObject({ code: 'FEATURE_UNAVAILABLE' })
  })
  it('保留衝突與會員未驗證保留伺服器錯誤，沒有當作保留成功', async () => {
    const meta = { capabilities: { inventoryHold: true } }
    const fetcher = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ data: {}, meta })))
      .mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ error: { code: 'CONFLICT', message: '當日庫存不足' } }), { status: 409 })))
    vi.stubGlobal('fetch', fetcher)
    const api = await import('../src/lib/api')
    await api.request('/api/health')
    await expect(api.request('/api/availability/holds', { method: 'POST', body: {} })).rejects.toMatchObject({ status: 409, code: 'CONFLICT', message: '當日庫存不足' })
  })
  it('付款停用時仍可查原單，不能重新扣款', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ data: null, meta: { capabilities: { orderRead: true, booking: true, payment: false } } })))))
    const api = await import('../src/lib/api')
    await api.request('/api/health')
    await expect(api.request('/api/orders/by-hold/original-hold')).resolves.toHaveProperty('data', null)
    await expect(api.request('/api/bookings', { method: 'POST' })).rejects.toMatchObject({ code: 'FEATURE_UNAVAILABLE' })
  })
  it('連線中斷顯示中文錯誤並關閉功能，不回傳舊示例商品', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    const api = await import('../src/lib/api')
    await expect(api.request('/api/plans')).rejects.toMatchObject({ code: 'NETWORK_ERROR', message: expect.stringContaining('請確認本機 API') })
    expect(api.backendSnapshot().connected).toBe(false)
  })
  it('查無商品時保留後端錯誤狀態，不自動替換成另一個方案', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { code: 'NOT_FOUND', message: '查無資料或資料已停用。' } }), { status: 404 })))
    const api = await import('../src/lib/api')
    await expect(api.request('/api/plans/missing')).rejects.toMatchObject({ status: 404, code: 'NOT_FOUND' })
  })
})
