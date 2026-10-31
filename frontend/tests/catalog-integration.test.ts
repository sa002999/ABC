import { describe, expect, it } from 'vitest'
import { adaptPlan, selectionFromQuery, selectionQuery, type ApiPlan } from '../src/lib/catalogApi'
import { estimatePrice, participantsFor, type Belt } from '../src/lib/domain'
import { fromServerDraft, toServerDraft, type ServerDraft } from '../src/lib/bookingApi'

const raw:ApiPlan={id:'30000000-0000-4000-8000-000000000001',name:{'zh-Hant':'情侶套餐'},description:{'zh-Hant':'兩名成人'},kind:'COUPLE',basePrice:2800,additionalGuestPrice:1500,currency:'TWD',kimono:{id:'female',name:{'zh-Hant':'和服'},gender:'FEMALE',images:[{url:'/api/catalog-assets/one',kind:'PRODUCT'}]},stores:[{id:'kyoto',city:'KYOTO'}],includedItems:[],isDemo:true}
const plan=adaptPlan(raw)
describe('React 與 FastAPI 商業規則',()=>{
 it('讀取多語系名稱、UUID、套餐價與門市關聯',()=>{
  expect(plan).toMatchObject({id:raw.id,name:'情侶套餐',price:2800,additionalGuestPrice:1500,city:'kyoto',storeIds:['kyoto']})
  expect(()=>adaptPlan({...raw,currency:'JPY'})).toThrow()
 })
 it('情侶固定兩人、團體按每人1400計價並保留三位旅客搭配',()=>{
  const people=participantsFor(plan)
  const belts:Belt[]=[{id:'belt',name:'腰帶',category:'BELT',price:200}]
  people[0].beltId='belt'
  expect(estimatePrice(plan,people,belts,false)).toBe(3000)
  expect(()=>estimatePrice(plan,[...people,{id:'third',role:'FEMALE',kimonoId:'female',beltId:null}],belts,false)).toThrow('人數')
  const group=adaptPlan({...raw,kind:'GROUP',basePrice:1400,coverImageUrl:'/assets/plan-group.webp'})
  const trio=[...participantsFor(group),{id:'third',role:'MALE' as const,kimonoId:'male',beltId:null}]
  expect(estimatePrice(group,trio.slice(0,2),[],false)).toBe(2800)
  expect(estimatePrice(group,trio,[],false)).toBe(4200)
  expect(selectionFromQuery(group,selectionQuery(group,trio))).toEqual(trio)
  expect(group.image).toBe('/assets/plan-group.webp')
  expect(()=>estimatePrice(group,trio.slice(0,1),[],false)).toThrow('人數')
  const single=adaptPlan({...raw,kind:'SINGLE'})
  expect(()=>estimatePrice(single,trio.slice(0,2),[],false)).toThrow('人數')
 })
 it('雙人照片對應的旅客與搭配可帶入預約',()=>{
  const people=participantsFor(plan).map(p=>({...p,kimonoId:p.role==='MALE'?'male':'female',beltId:p.role==='FEMALE'?'belt':null}))
  expect(selectionFromQuery(plan,selectionQuery(plan,people))).toEqual(people)
 })
 it('後端草稿還原聯絡資料、逐人腰帶與版本，回傳不丟失草稿識別',()=>{
  const saved:ServerDraft={draftId:'draft',version:3,activeHold:null,slot:{startsAt:'2026-11-01T00:00:00Z'},data:{storeId:'kyoto',slotId:'slot',guests:[{guestType:'ADULT_FEMALE',planId:plan.id,kimonoId:'female',accessoryIds:['belt']},{guestType:'ADULT_MALE',planId:plan.id,kimonoId:'male',accessoryIds:[]}],contactName:'測試',contactEmail:'test@example.com',contactPhone:'0912345678'}}
  const draft=fromServerDraft(saved,[plan]);const body=toServerDraft(draft)
  expect(draft).toMatchObject({draftId:'draft',version:3,date:'2026-11-01',name:'測試'})
  expect(body.guests.map(g=>g.accessoryIds)).toEqual([['belt'],[]])
  expect(body).not.toHaveProperty('size')
 })
})
