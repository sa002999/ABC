import type { MemberProfile } from '../lib/memberProfile'
import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Button, ButtonLink, Check, Container, Field, Loading, Notice, PageHeading, Panel, Select, inputClass } from '../components/ui'
import { useAuth } from '../lib/auth'
import { ApiError, actionKey, localized, request, unwrap } from '../lib/api'
import { useBackend, useResource } from '../lib/hooks'
import { selectionFromQuery, useBelts, useKimonos, usePlans } from '../lib/catalogApi'
import { money, participantsFor, participantCounts, secondsLeft, updateParticipant, type Draft } from '../lib/domain'
import { quoteExpired, validateQuote, type Quote } from '../lib/bookingQuote'
import { readJourney, saveJourney, journeyLink } from '../lib/bookingJourney'
import { fromServerDraft, toServerDraft, type Hold, type ServerDraft } from '../lib/bookingApi'
import { BeltSelection, GarmentSelection } from './Plans'

type Slot={id:string;label:string;available:boolean;reason?:string}
const steps=['門市','日期時段','旅客人數','逐人搭配','加購服務','聯絡資料','摘要確認']

export function Booking(){
 const auth=useAuth();const backend=useBackend();const[params]=useSearchParams();const plans=usePlans();const belts=useBelts()
 const stores=useResource<{id:string;name:string;city:string}[]>('/api/stores',[])
 const[draft,setDraft]=useState<Draft|null>(null);const[step,setStep]=useState(0);const[busy,setBusy]=useState(false);const[message,setMessage]=useState('');const[quote,setQuote]=useState<Quote|null>(null);const[hold,setHold]=useState<Hold|null>(null)
 const[receivedAt,setReceivedAt]=useState(0);const[now,setNow]=useState(Date.now());const[initialized,setInitialized]=useState(false)
 const operation=useRef(false);const revision=useRef(0);const holdKey=useRef(actionKey());const owner=useRef('');const form=useRef<HTMLFormElement>(null)
 const plan=plans.data.find(p=>p.id===draft?.planId)
 const kimonos=useKimonos(draft?.storeId)
 const slots=useResource<Slot[]>(`/api/stores/${draft?.storeId}/availability?from=${draft?.date}&to=${draft?.date}&partySize=${draft?.participants.length}`,[],undefined,!!draft?.storeId&&!!draft?.date)
 useEffect(()=>{
  if(!auth.ready||!plans.data.length||!backend.connected)return
  let active=true;owner.current=auth.user?.uid??'guest';setInitialized(false);setBusy(false);setDraft(null);setQuote(null);setHold(null);setMessage('');setStep(0)
  async function initialize(){
   let contact={name:'',email:auth.user?.email??'',phone:''}
   try{
    if(auth.user){
     const token=await auth.token();const id=params.get('draftId')
     let carried:{planId:string;participants:Draft['participants']}|null=null
     if(params.get('lookId')){
      const look=await request<{planId:string;participants:Draft['participants']}>('/api/looks/'+encodeURIComponent(params.get('lookId')!),{token});carried=look
     }else if(params.get('from')==='tryon'){
      const key='kinu:transfer:'+auth.user.uid
      try{carried=JSON.parse(sessionStorage.getItem(key)??'null')}catch{}
     }
     const journey=readJourney(auth.user.uid,params.get('bookingReturn'))
     if(journey?.selection)carried=journey.selection
     const rows=id?[await request<ServerDraft>('/api/booking-drafts/'+encodeURIComponent(id),{token})]:unwrap(await request<ServerDraft[]>('/api/booking-drafts',{token}))
     if(rows.length){if(active){
      let restored=fromServerDraft(rows[0],plans.data)
      if(carried&&!rows[0].activeHold&&plans.data.some(p=>p.id===carried!.planId)){
       restored={...restored,planId:carried.planId,participants:carried.participants,acceptedPolicy:false};setStep(3)
      }
      if(carried)sessionStorage.removeItem('kinu:transfer:'+auth.user!.uid)
      setDraft(restored);setHold(rows[0].activeHold);setReceivedAt(Date.now());setMessage(carried&&!rows[0].activeHold?'已帶入搭配，請保存並重新取得報價。':'已恢復後端保存的本人草稿。')
     }return}
     const profile=await request<MemberProfile>('/api/account',{token})
     contact={name:profile.displayName??'',email:profile.email,phone:profile.phoneVerified?profile.phoneNumber??'':''}
     if(carried&&plans.data.some(p=>p.id===carried!.planId)){
      const chosen=plans.data.find(p=>p.id===carried!.planId)!
      if(active){sessionStorage.removeItem('kinu:transfer:'+auth.user!.uid);setDraft({planId:chosen.id,city:chosen.city,storeId:'',date:'',slot:'',participants:carried.participants,photography:false,...contact,acceptedPolicy:false})}
      return
     }
    }
    const returning=readJourney(auth.user?.uid??'guest',params.get('bookingReturn'))
    if(returning){if(active){setDraft({...returning.draft,...(returning.selection?{planId:returning.selection.planId,participants:returning.selection.participants}:{}),acceptedPolicy:false});setStep(returning.step)}return}
    const chosen=plans.data.find(p=>p.id===params.get('plan'))??plans.data[0]
    if(active)setDraft({planId:chosen.id,city:chosen.city,storeId:params.get('storeId')??'',date:'',slot:'',participants:selectionFromQuery(chosen,params),photography:false,...contact,acceptedPolicy:false})
   }catch(e){if(active)setMessage((e as Error).message)}finally{if(active)setInitialized(true)}
  }
  void initialize();return()=>{active=false}
 },[auth.ready,auth.user?.uid,plans.data,backend.connected])
 useEffect(()=>{if(!hold&&!quote)return;const timer=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(timer)},[hold,quote])
 function change(patch:Partial<Draft>){revision.current++;setDraft(d=>d?{...d,...patch,acceptedPolicy:patch.acceptedPolicy??false}:d);setQuote(null);setMessage('')}
 async function save():Promise<ServerDraft>{
  if(!draft)throw new Error('尚未載入草稿。')
  const expectedOwner=owner.current
  const token=await auth.token();let id=draft.draftId;let version=draft.version
  if(!id){
   const created=await request<ServerDraft>('/api/booking-drafts',{method:'POST',token,body:toServerDraft(draft)})
   id=created.draftId;version=created.version
   if(created.activeHold)throw new Error('已有有效暫留，請重新整理恢復原草稿。')
  }
  if(owner.current!==expectedOwner)throw new Error('帳號已變更，已停止保存草稿。')
  const saved=await request<ServerDraft>('/api/booking-drafts/'+id,{method:'PATCH',token,body:{...toServerDraft(draft),version}})
  if(owner.current!==expectedOwner)throw new Error('帳號已變更，已停止套用草稿。')
  setDraft(d=>d?{...d,draftId:saved.draftId,version:saved.version}:d);return saved
 }
 async function perform(action:()=>Promise<void>){
  if(operation.current)return
  const uid=owner.current;operation.current=true;setBusy(true);setMessage('')
  try{await action()}catch(e){
   if(owner.current===uid){
    if(e instanceof ApiError&&e.code==='SLOT_UNAVAILABLE'){
     change({slot:''});setStep(1);slots.reload()
     setMessage('原時段已無法預約，已返回日期時段步驟。請重新選擇日期與時段；其他草稿資料已保留，選好後再保存並繼續。')
    }else setMessage((e as Error).message)
   }
  }finally{operation.current=false;if(owner.current===uid)setBusy(false)}
 }
 async function next(){if(!draft||!form.current?.reportValidity())return
  if(step===0&&!draft.storeId){setMessage('請選擇門市。');return}
  if(step===1&&(!draft.slot||!draft.date)){setMessage('請選擇有效日期與場次。');return}
  if(step===3&&draft.participants.some(p=>!p.kimonoId)){setMessage('請為每位旅客選擇和服。');return}
  await perform(async()=>{if(auth.user)await save();setStep(s=>Math.min(6,s+1))})
 }
 async function getQuote(){await perform(async()=>{
  if(!draft?.acceptedPolicy)throw new Error('請確認本次資料與暫留規則。')
  const expectedOwner=owner.current;const current=revision.current;const saved=await save();const value=unwrap(await request<Quote>('/api/pricing/quote',{method:'POST',token:await auth.token(),body:{draftId:saved.draftId,version:saved.version}}))
  validateQuote(value);if(current!==revision.current||owner.current!==expectedOwner)return;setQuote(value);setNow(Date.now());holdKey.current=actionKey()
 })}
 async function reserve(){const expectedOwner=owner.current;await perform(async()=>{
  if(!quote||quoteExpired(quote)||!draft?.draftId)throw new Error('請重新取得報價。')
  const storageKey='kinu:hold-request:'+auth.user?.uid+':'+quote.quoteToken
  const key=sessionStorage.getItem(storageKey)??holdKey.current;sessionStorage.setItem(storageKey,key)
  const value=unwrap(await request<Hold>('/api/availability/holds',{method:'POST',token:await auth.token(),key,body:{draftId:draft.draftId,quoteToken:quote.quoteToken}}))
  if(owner.current!==expectedOwner)return
  setHold(value);setReceivedAt(Date.now());setNow(Date.now());setQuote(null)
 })}
 async function release(){const expectedOwner=owner.current;await perform(async()=>{await request('/api/availability/holds/'+hold!.holdId,{method:'DELETE',token:await auth.token()});if(owner.current!==expectedOwner)return;setHold(null);setQuote(null);slots.reload()})}
 const journeyId=useRef(crypto.randomUUID())
 function keepJourney(){if(draft){const original='/booking?'+new URLSearchParams({plan:draft.planId,...(draft.draftId?{draftId:draft.draftId}:{})});saveJourney(auth.user?.uid??'guest',{id:journeyId.current,returnTo:original,draft,step,quote:null})}}
 const remaining=hold?secondsLeft(hold.expiresAt,hold.serverTime,receivedAt,now):0
 if(plans.error||stores.error)return <Container><Notice tone="error">{plans.error||stores.error}</Notice><Button onClick={()=>{plans.reload();stores.reload()}}>重試</Button></Container>
 if(!initialized)return <Container><Loading/></Container>
 if(!draft||!plan)return <Container><Notice>{message||'原方案已無法使用，請明確選擇新的方案。'}</Notice>{draft&&<Field label="替換方案"><Select value="" onChange={e=>{const next=plans.data.find(p=>p.id===e.target.value)!;change({planId:next.id,city:next.city,storeId:'',slot:'',date:'',participants:participantsFor(next)});setStep(0)}}><option value="">選擇方案</option>{plans.data.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</Select></Field>}<ButtonLink to="/plans">探索方案</ButtonLink></Container>
 return <Container><PageHeading eyebrow="BOOK YOUR JOURNEY" title="預約你的和服體驗" description="單人方案 1 人；情侶方案固定一男一女 2 人；團體方案 2～3 人。"/>
 <Notice>開發階段提供報價與 10 分鐘暫留；付款尚未開放，暫留不代表預約成立。</Notice>
 {!auth.user&&<Notice>登入後可將草稿保存至後端並恢復。<ButtonLink to={'/login?returnTo='+encodeURIComponent('/booking?'+params.toString())}>登入會員</ButtonLink></Notice>}
 {message&&<Notice>{message}</Notice>}
 {hold?<Panel><h2 className="font-serif text-2xl">{hold.status==='HELD'&&remaining>0?'資源已暫留':'暫留已到期或釋放'}</h2><p className="mt-4">{money(hold.total)} · 剩餘 {Math.floor(remaining/60)} 分 {remaining%60} 秒</p><p className="my-5">此處尚未付款，也未建立正式預約。</p><Button disabled={busy} onClick={release}>釋放暫留並返回草稿</Button></Panel>:<>
 <ol className="mb-8 grid grid-cols-4 gap-2 md:grid-cols-7">{steps.map((label,i)=><li key={label} className={'border-b-2 py-3 text-xs '+(i===step?'border-vermilion text-vermilion':'border-line')}>{i+1}. {label}</li>)}</ol>
 <div className="grid items-start gap-8 lg:grid-cols-[1.5fr_1fr]"><Panel><form ref={form} onSubmit={e=>{e.preventDefault();void next()}} className="space-y-6"><h2 className="font-serif text-2xl">{steps[step]}</h2><fieldset disabled={busy} className="space-y-6">
 {step===0&&<><Field label="方案"><Select value={plan.id} onChange={e=>{const p=plans.data.find(p=>p.id===e.target.value)!;change({planId:p.id,city:p.city,storeId:'',slot:'',participants:participantsFor(p)})}}>{plans.data.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</Select></Field><Field label="門市"><Select required value={draft.storeId} onChange={e=>{const store=stores.data.find(s=>s.id===e.target.value);change({storeId:e.target.value,city:store?.city.toLowerCase()??plan.city,slot:'',participants:draft.participants.map(p=>({...p,kimonoId:'',generationId:undefined}))})}}><option value="">選擇門市</option>{stores.data.filter(s=>plan.storeIds?.includes(s.id)).map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</Select></Field></>}
 {step===1&&<><Field label="日本當地日期"><input required type="date" value={draft.date} onChange={e=>change({date:e.target.value,slot:''})} className={inputClass}/></Field><Field label="場次"><Select required value={draft.slot} onChange={e=>change({slot:e.target.value})}><option value="">選擇時段</option>{slots.data.map(s=><option key={s.id} value={s.id} disabled={!s.available}>{s.label}{!s.available?'（不可預約）':''}</option>)}</Select></Field>{slots.loading&&<Loading/>}{slots.error&&<Notice tone="error">{slots.error}</Notice>}<p className="text-xs text-muted">開始前至少 24 小時至未來 90 天；選擇場次不占用名額。</p></>}
 {step===2&&<Field label="旅客人數"><Select value={draft.participants.length} onChange={e=>{const count=Number(e.target.value);const people=[...draft.participants];while(people.length<count)people.push({id:crypto.randomUUID(),role:'FEMALE',kimonoId:'',beltId:null});change({participants:people.slice(0,count)})}}>{participantCounts(plan).map(n=><option key={n} value={n}>{n} 位成人</option>)}</Select></Field>}
 {step===3&&<>{draft.participants.map((p,i)=><div key={p.id} className="space-y-4 border-b border-line pb-6"><h3>旅客 {i+1}</h3><GarmentSelection participant={p} kimonos={kimonos.data} roleLocked={plan.kind==='COUPLE'&&i<2} onChange={patch=>change({participants:updateParticipant(draft.participants,p.id,{...patch,generationId:undefined})})}/><BeltSelection participant={p} belts={belts.data} plan={plan} onChange={beltId=>change({participants:updateParticipant(draft.participants,p.id,{beltId})})}/></div>)}<div className="flex flex-wrap gap-3"><ButtonLink onClick={keepJourney} to={journeyLink('/try-on?plan='+plan.id,journeyId.current)}>AI 試穿此搭配</ButtonLink><ButtonLink onClick={keepJourney} to={journeyLink('/looks',journeyId.current)}>從收藏挑選</ButtonLink></div>{(kimonos.error||belts.error)&&<Notice tone="error">{kimonos.error||belts.error}</Notice>}</>}
 {step===4&&<Notice>女生腰帶於搭配步驟選擇並另行計費。攝影、其他配件與 AI 腰帶穿戴尚未開放。</Notice>}
 {step===5&&<><Field label="聯絡姓名"><input required value={draft.name} onChange={e=>change({name:e.target.value})} className={inputClass}/></Field><Field label="Email"><input required type="email" value={draft.email} onChange={e=>change({email:e.target.value})} className={inputClass}/></Field><Field label="電話"><input required type="tel" value={draft.phone} onChange={e=>change({phone:e.target.value})} className={inputClass}/></Field><p className="text-xs text-muted">聯絡資料保存於本人後端草稿，不寫入瀏覽器儲存空間。</p></>}
 {step===6&&<><p>{draft.name} · {draft.participants.length} 位成人 · {draft.date}</p><Check checked={draft.acceptedPolicy} onChange={e=>change({acceptedPolicy:e.target.checked})}>我已確認搭配與聯絡資料，了解報價不占庫存，暫留不代表預約成立。</Check><Button disabled={!auth.user||!draft.acceptedPolicy} onClick={getQuote}>取得後端報價</Button></>}
 </fieldset><div className="flex gap-4">{step>0&&<Button disabled={busy} onClick={()=>setStep(s=>s-1)}>上一步</Button>}{step<6&&<Button type="submit" disabled={busy}>保存並繼續</Button>}</div></form></Panel>
 <Panel><h2 className="font-serif text-xl">{plan.name}</h2><p className="mt-4">{draft.participants.length} 位 · 統一尺寸</p><p className="mt-4 text-sm text-muted">金額以後端報價為準；情侶套餐計價一次，腰帶分開計費。</p>{quote&&<div className="mt-6 space-y-4">{quote.lineItems?.map((l,i)=><p key={i}>{localized(l.label)} · {money(l.amount)}</p>)}<strong>{money(quote.total)}</strong><p>{quoteExpired(quote,now)?'報價已到期':'確認報價後才會建立暫留。'}</p><Button disabled={busy||quoteExpired(quote,now)||!auth.user?.emailVerified} onClick={reserve}>確認報價並暫留 10 分鐘</Button>{!auth.user?.emailVerified&&<ButtonLink to="/verify-email">先完成 Email 驗證</ButtonLink>}</div>}</Panel></div></>}
 </Container>
}

export function BookingComplete(){return <Container><Notice>付款與正式預約尚未開放。</Notice><ButtonLink to="/booking">返回預約草稿</ButtonLink></Container>}
