export type GarmentRole = 'FEMALE' | 'MALE'
export type Plan = { id: string; name: string; city: string; kind: 'SINGLE' | 'COUPLE' | 'GROUP'; role: GarmentRole; price: number; image: string; description: string; kimonoId?: string; cities?: string[]; storeIds?: string[]; participantCount?: number; maxParticipants?: number; additionalGuestPrice?: number; includedServices?: string[]; includedBeltIds?: string[]; optionalBeltIds?: string[]; includedPhotographyOptionIds?: string[]; optionalPhotographyOptionIds?: string[]; isDemo?: boolean }
export type Belt = { id: string; name: string; price: number; category: 'BELT'; imageUrl?: string | null }
export type Kimono = { id: string; name: string; gender: GarmentRole; color: string; imageUrl: string | null }
export type PhotographyOption = { id: string; name: string; description: string; priceTwd: number | null; durationMinutes: number | null; photoCount: number | null; bookingMode: 'ONLINE' | 'ON_SITE_ONLY'; storeIds: string[] }
export type Participant = { id: string; role: GarmentRole; kimonoId: string; beltId: string | null; photoId?: string; generationId?: string }
export type Draft = { planId: string; city: string; storeId: string; date: string; slot: string; participants: Participant[]; photography: boolean; name: string; email: string; phone: string; acceptedPolicy: boolean; version?: number; draftId?: string }
export type Look = { id: string; planId: string; participants: Participant[]; generationId?: string }
export type Job = { kind?: 'TRY_ON'|'SCENE'; sceneId?:string; parentJobId?:string; failure?:{code:string;message:string}; jobId: string; status: string; generationId?: string; kimonoId?: string; beltId?: string | null; reused?: boolean; imageUrl?: string; resultUrl?: string; expiresAt?: string; message?: string }
export type Order = { orderNo: string; paymentStatus: string; bookingNo?: string | null; status?: string }

export const money = (value: number) => 'NT$' + new Intl.NumberFormat('zh-TW', { maximumFractionDigits: 0 }).format(value)
export const planCities = (plan: Plan) => plan.cities ?? [plan.city]
export const isPaidBooking = (order: Order) => !!order.bookingNo && ['PAID', 'AUTHORIZED', 'SUCCEEDED', 'CONFIRMED'].includes(order.paymentStatus)
export const isPending = (status: string) => ['PAYMENT_PENDING', 'PENDING', 'PROCESSING', 'REVIEW_REQUIRED', 'REFUND_REQUIRED'].includes(status)
export const isJobDone = (status: string) => ['SUCCEEDED', 'succeeded', 'COMPLETED'].includes(status)
export const isJobFailed = (status: string) => ['FAILED', 'failed', 'CANCELLED', 'EXPIRED', 'DELETED'].includes(status)

export function participantsFor(plan: Plan): Participant[] {
  return plan.kind === 'COUPLE'
    ? [{ id: 'female_1', role: 'FEMALE', kimonoId: '', beltId: null }, { id: 'male_1', role: 'MALE', kimonoId: '', beltId: null }]
    : Array.from({length:plan.kind==='GROUP'?2:1},(_,i)=>({ id:'guest_'+(i+1), role:plan.role, kimonoId:'', beltId:null }))
}

export const participantCounts = (plan: Plan) => plan.kind==='GROUP'?[2,3]:plan.kind==='COUPLE'?[2]:[1]
export function resizeParticipants(people: Participant[], count: number): Participant[] {
  return Array.from({length:count},(_,i)=>people[i]??{id:crypto.randomUUID(),role:'FEMALE',kimonoId:'',beltId:null})
}

export function validateParticipants(people: Participant[]) {
  if (people.length < 1 || people.length > 3) throw new Error('每筆預約限 1～3 名旅客。情侶方案計兩名。')
  if (new Set(people.map(p => p.id)).size !== people.length) throw new Error('旅客識別不可重複。')
  for (const person of people) {
    if (person.role !== 'FEMALE' && person.role !== 'MALE') throw new Error('請選擇有效的和服角色。')
    if (person.role === 'MALE' && person.beltId) throw new Error('男生無可選配件，不能加入腰帶。')
  }
  return people
}

export function updateParticipant(people: Participant[], id: string, patch: Partial<Participant>): Participant[] {
  return people.map(person => {
    if (person.id !== id) return person
    const next = { ...person, ...patch }
    if ((['role','kimonoId','beltId','photoId'] as const).some(key=>key in patch&&patch[key]!==person[key])
      && !('generationId' in patch)) next.generationId = undefined
    if (next.role === 'MALE') next.beltId = null
    return next
  })
}

export function estimatePrice(plan: Plan, people: Participant[], belts: Belt[], photography: boolean, photographyPrice = 0) {
  validateParticipants(people)
  if(!participantCounts(plan).includes(people.length))throw new Error('旅客人數不符合所選方案。')
  if(plan.kind==='COUPLE'&&people.map(p=>p.role).sort().join(',')!=='FEMALE,MALE')throw new Error('情侶方案限定一男一女。')
  // A couple package's base price is charged once, never once per participant.
  const beltsTotal = people.reduce((sum, p) => sum + (p.role === 'FEMALE' && !plan.includedBeltIds?.includes(p.beltId ?? '') ? belts.find(b => b.id === p.beltId)?.price ?? 0 : 0), 0)
  return (plan.kind==='COUPLE'?plan.price:plan.price*people.length) + beltsTotal + (photography && !plan.includedPhotographyOptionIds?.includes('photo-outdoor') ? photographyPrice : 0)
}

export function secondsLeft(expiresAt: string, serverTime: string, receivedAt: number, now: number) {
  const offset = new Date(serverTime).getTime() - receivedAt
  return Math.max(0, Math.ceil((new Date(expiresAt).getTime() - (now + offset)) / 1000))
}

export const safeReturnTo = (value: string | null) => value && value.startsWith('/') && !value.startsWith('//') && !value.includes('\\') ? value : '/account'
export function localDate() {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Tokyo', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date())
}

export const paymentLabel = (status?: string) => status === 'REFUNDED' ? '已退款' : status === 'PARTIALLY_REFUNDED' ? '已部分退款' : status === 'VOIDED' ? '已撤銷授權' : status === 'AUTHORIZED' ? '已授權、待請款' : status === 'PAID' ? '已請款' : status === 'PAYMENT_PENDING' ? '付款確認中' : status === 'FAILED' ? '付款未成功' : status === 'REVIEW_REQUIRED' || status === 'REFUND_REQUIRED' ? '交易需人工查核' : status ?? ''

export function displayJob(base:Job|undefined,scene:Job|undefined) {
  return scene&&isJobDone(scene.status)&&(scene.imageUrl||scene.resultUrl)?scene:base
}
