import { apiConfigured, assetUrl, localized } from './api'
import { useResource } from './hooks'
import { participantsFor, type Belt, type Participant, type Kimono, type PhotographyOption, type Plan } from './domain'

type RawKimono={id:string;name:unknown;gender:'FEMALE'|'MALE';images?:{url:string;kind:string}[]}
export type ApiPlan={id:string;name:unknown;description:unknown;kind:'SINGLE'|'COUPLE';basePrice:number;additionalGuestPrice:number;currency:string;kimono:RawKimono;stores:{id:string;city:string}[];includedItems:string[];isDemo:boolean}
export function adaptPlan(raw:ApiPlan):Plan {
 if(raw.currency!=='TWD'||!Number.isSafeInteger(raw.basePrice)||raw.basePrice<0||!raw.stores.length)throw new Error('方案資料格式不完整。')
 return {id:raw.id,name:localized(raw.name),description:localized(raw.description),kind:raw.kind,role:raw.kimono.gender,
 price:raw.basePrice,additionalGuestPrice:raw.kind==='COUPLE'?raw.additionalGuestPrice:raw.basePrice,image:assetUrl(raw.kimono.images?.find(a=>a.kind==='PRODUCT')?.url??''),
 city:raw.stores[0].city.toLowerCase(),cities:[...new Set(raw.stores.map(s=>s.city.toLowerCase()))],storeIds:raw.stores.map(s=>s.id),
 kimonoId:raw.kimono.id,includedServices:raw.includedItems,isDemo:raw.isDemo}
}
export const canonicalPlanId=(id:string|null|undefined)=>id??''
export function usePlans(_path='/api/plans'){return useResource<Plan[]>('/api/plans?pageSize=50',[],undefined,true,v=>(v as ApiPlan[]).map(adaptPlan))}
export function usePlan(id:string|undefined){return useResource<Plan|null>('/api/plans/'+encodeURIComponent(id??''),null,undefined,!!id,v=>adaptPlan(v as ApiPlan))}
export function useBelts(){return useResource<Belt[]>('/api/belts',[],undefined,true,v=>(v as {id:string;name:string;priceTwd:number}[]).map(b=>({...b,price:b.priceTwd,category:'BELT'})))}
export function useKimonos(storeId=''){return useResource<Kimono[]>('/api/kimonos?pageSize=50'+(storeId?'&storeId='+encodeURIComponent(storeId):''),[],undefined,true,v=>(v as RawKimono[]).map(k=>({id:k.id,name:localized(k.name),gender:k.gender,color:'',imageUrl:assetUrl(k.images?.find(a=>a.kind==='PRODUCT')?.url??'')})))}
export function usePhotography(_storeId=''){return useResource<PhotographyOption[]>('/api/photography-options',[])}
export function selectedPlan(plans:Plan[],id:string|null){return id?plans.find(p=>p.id===id):plans[0]}
export function selectionQuery(plan: Plan, people: Participant[]) {
  const query = new URLSearchParams({ plan: plan.id })
  for (const person of people) {
    if (person.role === 'FEMALE' && person.beltId) query.set('belt', person.beltId)
    if (plan.kind === 'COUPLE') query.set(person.role === 'FEMALE' ? 'femaleKimono' : 'maleKimono', person.kimonoId)
    else { query.set('role', person.role); query.set('kimono', person.kimonoId) }
  }
  return query
}
export function selectionFromQuery(plan: Plan, query: URLSearchParams): Participant[] {
  return participantsFor(plan).map(person => {
    const role = plan.kind === 'COUPLE' ? person.role : query.get('role') === 'MALE' || query.get('plan') === 'example-male' ? 'MALE' : plan.role
    return { ...person, role, kimonoId: query.get(plan.kind === 'COUPLE' ? role === 'FEMALE' ? 'femaleKimono' : 'maleKimono' : 'kimono') ?? '', beltId: role === 'FEMALE' ? query.get('belt') || null : null }
  })
}
export function allowedBelts(plan: Plan, belts: Belt[]) {
  const ids = plan.optionalBeltIds ? [...plan.optionalBeltIds, ...(plan.includedBeltIds ?? [])] : null
  return ids ? belts.filter(b => ids.includes(b.id)) : belts
}
export function reconcileSelection(people: Participant[], plan: Plan, kimonos: Kimono[], belts: Belt[]) {
  const validBelts = allowedBelts(plan, belts)
  const next = people.map(p => ({ ...p, kimonoId: kimonos.some(k => k.id === p.kimonoId && k.gender === p.role) ? p.kimonoId : '', beltId: p.role === 'FEMALE' && validBelts.some(b => b.id === p.beltId) ? p.beltId : null }))
  return JSON.stringify(next) === JSON.stringify(people) ? people : next
}
