import { participantsFor, planCities, validateParticipants, type Draft, type Participant, type Plan } from './domain'
import type { Quote } from './bookingQuote'

export type BookingJourney = {
  id: string
  returnTo: string
  draft: Draft
  step: number
  quote: Quote | null
  selection?: { planId: string; participants: Participant[] }
}

const memory = new Map<string,string>()
export const clearJourneys=()=>memory.clear()
const journeyStorage = {getItem:(key:string)=>memory.get(key)??null,setItem:(key:string,value:string)=>{memory.set(key,value)},removeItem:(key:string)=>{memory.delete(key)}}
const key = (owner: string, id: string) => `kinu:journey:${owner}:${id}`

export function readJourney(owner: string, id: string | null, storage: Pick<Storage, 'getItem'> = journeyStorage): BookingJourney | null {
  if (!id) return null
  try {
    const value: BookingJourney = JSON.parse(storage.getItem(key(owner, id)) ?? 'null')
    if (!value || value.id !== id || !value.returnTo.startsWith('/booking?') || value.returnTo.includes('\\')) return null
    validateParticipants(value.draft.participants)
    if (value.step < 0 || value.step > 6 || !Number.isInteger(value.step)) return null
    return value
  } catch { return null }
}

export function saveJourney(owner: string, journey: BookingJourney, storage: Pick<Storage, 'setItem'> = journeyStorage) {
  storage.setItem(key(owner, journey.id), JSON.stringify(journey))
}

export function removeJourney(owner: string, id: string, storage: Pick<Storage, 'removeItem'> = journeyStorage) {
  storage.removeItem(key(owner, id))
}

export function journeyLink(path: string, id: string) {
  const [pathname, search = ''] = path.split('?')
  const params = new URLSearchParams(search)
  params.set('bookingReturn', id)
  return pathname + '?' + params.toString()
}

export function freshBooking(plan: Plan, email = ''): Draft {
  return { planId: plan.id, city: plan.city.toLowerCase(), storeId: '', date: '', slot: '', participants: participantsFor(plan), photography: false, name: '', email, phone: '', acceptedPolicy: false }
}

export function sameSelection(a: { planId: string; participants: Participant[] }, b: { planId: string; participants: Participant[] }) {
  return a.planId === b.planId && JSON.stringify(a.participants.map(p => [p.id, p.role, p.kimonoId, p.beltId])) === JSON.stringify(b.participants.map(p => [p.id, p.role, p.kimonoId, p.beltId]))
}

export function applyJourneySelection(journey: BookingJourney, plan: Plan): Draft {
  const selection = journey.selection
  if (!selection || selection.planId !== plan.id) return journey.draft
  validateParticipants(selection.participants)
  const city = planCities(plan).includes(journey.draft.city) ? journey.draft.city : plan.city.toLowerCase()
  return { ...journey.draft, planId: plan.id, city, participants: selection.participants, acceptedPolicy: false,
    ...(city !== journey.draft.city ? { storeId: '', date: '', slot: '' } : {}) }
}
