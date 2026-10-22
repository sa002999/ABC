import { describe, expect, it } from 'vitest'
import { examplePlans } from '../src/data/catalog'
import { applyJourneySelection, freshBooking, journeyLink, readJourney, removeJourney, sameSelection, saveJourney, type BookingJourney } from '../src/lib/bookingJourney'

const plan = examplePlans[0]
const draft = { ...freshBooking(plan), storeId: 'chosen-store', date: '2026-11-01', slot: 'morning', name: '測試旅客', email: 'test@example.test', phone: '+81000000000', acceptedPolicy: true, draftId: 'draft-1', version: 3 }
const quote = { quoteToken: 'server-token', currency: 'TWD', total: 2400, expiresAt: '2026-10-20T01:00:00Z' }
const journey: BookingJourney = { id: 'journey-1', returnTo: '/booking?plan=' + plan.id + '&from=tryon&belt=', draft, step: 6, quote }
function memoryStorage() {
  const values = new Map<string, string>()
  return { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => { values.set(key, value) }, removeItem: (key: string) => { values.delete(key) } }
}

describe('預約的 AI 往返與重新開始', () => {
  it('保存原預約的步驟、聯絡資料與報價，只允許同一會員讀取', () => {
    const storage = memoryStorage()
    saveJourney('member-a', journey, storage)
    expect(readJourney('member-a', journey.id, storage)).toEqual(journey)
    expect(readJourney('member-b', journey.id, storage)).toBeNull()
    removeJourney('member-a', journey.id, storage)
    expect(readJourney('member-a', journey.id, storage)).toBeNull()
  })
  it('往返網址保留查詢參數且只包含流程識別碼，不包含聯絡資料或報價 token', () => {
    const link = journeyLink('/try-on?plan=' + plan.id, journey.id)
    expect(new URLSearchParams(link.split('?')[1]).get('plan')).toBe(plan.id)
    expect(link).toContain('bookingReturn=journey-1')
    expect(link).not.toContain(draft.email)
    expect(link).not.toContain(quote.quoteToken)
  })
  it('只瀏覽或生成圖不視為變更搭配，更換和服或腰帶才視為變更', () => {
    expect(sameSelection(draft, { ...draft, participants: draft.participants.map(p => ({ ...p, generationId: 'new-image' })) })).toBe(true)
    expect(sameSelection(draft, { ...draft, participants: draft.participants.map(p => ({ ...p, kimonoId: 'different-kimono' })) })).toBe(false)
  })
  it('套用搭配保留原日期門市及聯絡資料，要求重新確認政策', () => {
    const participants = draft.participants.map(p => ({ ...p, kimonoId: 'different-kimono' }))
    const applied = applyJourneySelection({ ...journey, selection: { planId: plan.id, participants } }, plan)
    expect(applied).toMatchObject({ storeId: draft.storeId, date: draft.date, slot: draft.slot, name: draft.name, email: draft.email, phone: draft.phone, acceptedPolicy: false, participants })
  })
  it('跨城市套用方案時清除不相容的門市時段，仍保留聯絡資料', () => {
    const otherPlan = { ...plan, id: 'other-city-plan', city: draft.city === 'kyoto' ? 'tokyo' : 'kyoto' }
    const applied = applyJourneySelection({ ...journey, selection: { planId: otherPlan.id, participants: draft.participants } }, otherPlan)
    expect(applied).toMatchObject({ planId: otherPlan.id, city: otherPlan.city, storeId: '', date: '', slot: '', name: draft.name })
  })
  it('重新開始只有目前方案的預設值，沒有舊聯絡資料、搭配圖片或後端草稿識別', () => {
    const fresh = freshBooking(plan)
    expect(fresh).toMatchObject({ planId: plan.id, storeId: '', date: '', slot: '', name: '', email: '', phone: '', acceptedPolicy: false, photography: false })
    expect(fresh.draftId).toBeUndefined()
    expect(fresh.version).toBeUndefined()
    expect(fresh.participants.every(p => !p.beltId && !p.photoId && !p.generationId)).toBe(true)
  })
})
