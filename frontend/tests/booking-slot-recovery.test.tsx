import { isValidElement, type ReactNode } from 'react'
import { expect, it, vi } from 'vitest'
import { examplePlans } from '../src/data/catalog'
import { freshBooking } from '../src/lib/bookingJourney'
import { ApiError, request } from '../src/lib/api'
import { Booking } from '../src/pages/Booking'

const state = vi.hoisted(() => ({ values: [] as unknown[], index: 0, reload: vi.fn() }))
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
vi.mock('../src/lib/auth', () => ({ useAuth: () => ({ ready: true, user: { uid: 'member' }, token: async () => 'token' }) }))
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
 findForm(Booking())!.onSubmit({ preventDefault() {} })
 await vi.waitFor(() => expect(state.values[2]).toBe(false))
 expect(state.values[1]).toBe(1)
 expect(state.values[0]).toEqual({ ...draft, slot: '', acceptedPolicy: false })
 expect(state.values[3]).toContain('請重新選擇日期與時段')
 expect(state.reload).toHaveBeenCalled()

 state.values[0] = { ...draft, date: '2026-11-10', slot: 'new-slot' }
 state.index = 0
 vi.mocked(request).mockResolvedValueOnce({ draftId: 'draft', version: 4 })
 findForm(Booking())!.onSubmit({ preventDefault() {} })
 await vi.waitFor(() => expect(state.values[1]).toBe(2))
 expect(request).toHaveBeenLastCalledWith('/api/booking-drafts/draft', expect.objectContaining({
  method: 'PATCH', body: expect.objectContaining({ slotId: 'new-slot', version: 3 }),
 }))
})
