import { isValidElement, type ReactNode } from 'react'
import { expect, it, vi } from 'vitest'
import { examplePlans } from '../src/data/catalog'
import { freshBooking } from '../src/lib/bookingJourney'
import { ApiError, request } from '../src/lib/api'
import { Booking } from '../src/pages/Booking'

const state = vi.hoisted(() => ({ values: [] as unknown[], index: 0, emailVerified: true, reload: vi.fn() }))
vi.mock('react', async original => ({
 ...await original<typeof import('react')>(),
 useEffect: () => {},
 useRef: (value: unknown) => ({ current: value === null ? { reportValidity: () => true } : value }),
 useState: (initial: unknown) => {
  const index = state.index++
  if (!(index in state.values)) state.values[index] = initial
  return [state.values[index], (value: unknown) => {
   state.values[index] = typeof value === 'function' ? value(state.values[index]) : value
  }]
 },
}))
vi.mock('react-router-dom', () => ({ useSearchParams: () => [new URLSearchParams()] }))
vi.mock('../src/lib/auth', () => ({ useAuth: () => ({ ready: true, user: { uid: 'member', emailVerified: state.emailVerified }, token: async () => 'token' }) }))
vi.mock('../src/lib/hooks', () => ({
 useBackend: () => ({ connected: true }),
 useResource: () => ({ data: [], reload: state.reload }),
}))
vi.mock('../src/lib/catalogApi', async () => {
 const { examplePlans } = await import('../src/data/catalog')
 return { usePlans: () => ({ data: examplePlans }), useBelts: () => ({ data: [] }), useKimonos: () => ({ data: [] }) }
})
vi.mock('../src/pages/Plans', () => ({ BeltSelection: () => null, GarmentSelection: () => null }))
vi.mock('../src/lib/api', async original => ({ ...await original<typeof import('../src/lib/api')>(), request: vi.fn() }))

function renderBookingFlow(node: ReactNode) {
 if (isValidElement(node) && typeof node.type === 'function' && node.type.name === 'BookingFlow') return (node.type as () => ReactNode)()
 return node
}

function findForm(node: ReactNode): { onSubmit: (event: { preventDefault: () => void }) => void } | undefined {
 if (Array.isArray(node)) return node.map(findForm).find(Boolean)
 if (!isValidElement<{ children?: ReactNode; onSubmit?: unknown }>(node)) return
 if (node.type === 'form') return node.props as ReturnType<typeof findForm>
 return findForm(node.props.children)
}

it('舊草稿時段失效時由門市步驟回到時段重選，保留其他資料並可再次保存', async () => {
 const draft = { ...freshBooking(examplePlans[0]), draftId: 'draft', version: 3, storeId: 'store', date: '2026-10-01', slot: 'old-slot', name: '旅客', email: 'guest@example.test', phone: '0900000000' }
 state.values = [draft, 0, false, '', null, null, 0, Date.now(), true]
 state.index = 0
 vi.mocked(request).mockRejectedValueOnce(new ApiError('時段已關閉', 409, 'SLOT_UNAVAILABLE'))
 findForm(renderBookingFlow(Booking()))!.onSubmit({ preventDefault() {} })
 await vi.waitFor(() => expect(state.values[2]).toBe(false))
 expect(state.values[1]).toBe(1)
 expect(state.values[0]).toEqual({ ...draft, slot: '', acceptedPolicy: false })
 expect(state.values[3]).toContain('請重新選擇日期與時段')
 expect(state.reload).toHaveBeenCalled()

 state.values[0] = { ...draft, date: '2026-11-10', slot: 'new-slot' }
 state.index = 0
 vi.mocked(request).mockResolvedValueOnce({ draftId: 'draft', version: 4, data: {contactEmail:draft.email,contactPhone:draft.phone}, contactVerification:{email:false,phone:false,memberName:true} })
 findForm(renderBookingFlow(Booking()))!.onSubmit({ preventDefault() {} })
 await vi.waitFor(() => expect(state.values[1]).toBe(2))
 expect(request).toHaveBeenLastCalledWith('/api/booking-drafts/draft', expect.objectContaining({
  method: 'PATCH', body: expect.objectContaining({ slotId: 'new-slot', version: 3 }),
 }))
})

it('登入 Email 未驗證時，預約入口提供會員中心連結且不載入草稿', () => {
 state.emailVerified = false
 try {
  const screen = Booking()
  expect(JSON.stringify(screen)).toContain('/account?returnTo=')
  expect(findForm(screen)).toBeUndefined()
 } finally {
  state.emailVerified = true
 }
})

it.each([
 [{displayName:' ',phoneVerified:true}, '填寫會員姓名'],
 [{displayName:'旅客',phoneVerified:false}, '完成會員手機驗證'],
])('會員資料未完成時，預約入口指引回會員中心', (profile, message) => {
 state.values = [null, 0, false, '', null, null, 0, Date.now(), true, {phoneNumber:'+886912345678',...profile}]
 state.index = 0
 const screen = renderBookingFlow(Booking())
 expect(JSON.stringify(screen)).toContain(message)
 expect(JSON.stringify(screen)).toContain('/account?returnTo=')
 expect(findForm(screen)).toBeUndefined()
})
