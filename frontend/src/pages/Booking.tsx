import { BookingContactVerification } from '../components/BookingContactVerification'
import { normalizeMobile, type MemberProfile as Profile } from '../lib/memberProfile'
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
import { fromServerDraft, toServerDraft, type ContactVerification, type Hold, type ServerDraft } from '../lib/bookingApi'
import { BeltSelection, GarmentSelection } from './Plans'
import { BookingPayment } from '../components/BookingPayment'
import { usePrivateResource } from '../lib/hooks'
import { useParams } from 'react-router-dom'
import { paymentLabel } from '../lib/domain'

type Slot={id:string;label:string;available:boolean;reason?:string}
const steps=['門市','日期時段','旅客人數','逐人搭配','加購服務','聯絡資料','摘要確認']

const emptyContact={name:'',email:'',phone:''}
const memberContact=(profile:Profile)=>({name:profile.displayName??'',email:profile.email,phone:profile.phoneVerified?profile.phoneNumber??'':''})
const missingBookingProfile=(profile:Profile)=>[
 !profile.displayName?.trim()?'填寫會員姓名':'',
 !profile.phoneVerified||!profile.phoneNumber?.trim()?'完成會員手機驗證':'',
].filter(Boolean)

export function Booking(){
 const auth=useAuth();const [params]=useSearchParams()
 const returnTo='/booking?'+params.toString()
 if(!auth.ready)return <Container><Loading/></Container>
 if(!auth.user)return <Container><Notice>請先登入會員，再開始預約。 <ButtonLink to={'/login?returnTo='+encodeURIComponent(returnTo)}>登入會員</ButtonLink></Notice></Container>
 if(!auth.user.emailVerified)return <Container><Notice>請先到會員中心完成登入 Email 驗證，再開始預約。 <ButtonLink to={'/account?returnTo='+encodeURIComponent(returnTo)}>前往會員中心</ButtonLink></Notice></Container>
 return <BookingFlow key={auth.user.uid}/>
}

function BookingFlow(){
 const auth=useAuth();const backend=useBackend();const[params]=useSearchParams();const plans=usePlans();const belts=useBelts()
 const stores=useResource<{id:string;name:string;city:string}[]>('/api/stores',[])
 const[draft,setDraft]=useState<Draft|null>(null);const[step,setStep]=useState(0);const[busy,setBusy]=useState(false);const[message,setMessage]=useState('');const[quote,setQuote]=useState<Quote|null>(null);const[hold,setHold]=useState<Hold|null>(null)
 const[receivedAt,setReceivedAt]=useState(0);const[now,setNow]=useState(Date.now());const[initialized,setInitialized]=useState(false)
 const [profile,setProfile]=useState<Profile|null>(null)
 const [verified,setVerified]=useState<{status:ContactVerification;email:string;phone:string}|null>(null)
 const [dirty,setDirty]=useState(false)
 const [savingContact,setSavingContact]=useState(false)
 const contactSave=useRef<Promise<void>|null>(null)
 const savedVersion=useRef<{draftId:string;version:number}|null>(null)
 const attemptedContactRevision=useRef(-1)
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
     const token=await auth.token();const id=params.get('draftId');const expectedHold=params.get('holdId')
     const member=await request<Profile>('/api/account',{token})
     if(active)setProfile(member)
     if(missingBookingProfile(member).length)return
     contact=memberContact(member)
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
     if(expectedHold&&(!id||rows[0]?.activeHold?.holdId!==expectedHold)){
      throw new Error('這筆暫留已到期或已釋放。請回到 MCP 重新查詢時段。')
     }
     if(rows.length){if(active){
      let restored=fromServerDraft(rows[0],plans.data)
      if(!rows[0].activeHold){
       if(restored.contactMode)setStep(5)
       if(restored.contactMode==='member')restored={...restored,...contact}
       if(!restored.contactMode){
        const hasCustom=(restored.name&&restored.name!==contact.name)||(restored.email&&restored.email!==contact.email)||(restored.phone&&restored.phone!==contact.phone)
        restored=hasCustom?{...restored,contactMode:'other'}:{...restored,...contact}
       }
      }
      setVerified({status:rows[0].contactVerification,email:rows[0].data.contactEmail,phone:rows[0].data.contactPhone})
      if(carried&&!rows[0].activeHold&&plans.data.some(p=>p.id===carried!.planId)){
       restored={...restored,planId:carried.planId,participants:carried.participants,acceptedPolicy:false};setStep(3)
      }
      if(carried)sessionStorage.removeItem('kinu:transfer:'+auth.user!.uid)
      setDraft(restored);setHold(rows[0].activeHold);setReceivedAt(Date.now());setMessage(carried&&!rows[0].activeHold?'已帶入搭配，請保存並重新取得報價。':'已恢復後端保存的本人草稿。')
     }return}
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
 async function save(value=draft):Promise<ServerDraft>{
  if(!value)throw new Error('尚未載入草稿。')
  const expectedOwner=owner.current
  const savingRevision=revision.current
  const token=await auth.token();let id=value.draftId;let version=value.version
  if(savedVersion.current&&savedVersion.current.draftId===id){
   version=Math.max(version??0,savedVersion.current.version)
  }
  if(!id){
   const created=await request<ServerDraft>('/api/booking-drafts',{method:'POST',token,body:toServerDraft(value)})
   id=created.draftId;version=created.version
   if(created.activeHold)throw new Error('已有有效暫留，請重新整理恢復原草稿。')
  }
  if(owner.current!==expectedOwner)throw new Error('帳號已變更，已停止保存草稿。')
  const saved=await request<ServerDraft>('/api/booking-drafts/'+id,{method:'PATCH',token,body:{...toServerDraft(value),version}})
  if(owner.current!==expectedOwner)throw new Error('帳號已變更，已停止套用草稿。')
  savedVersion.current={draftId:saved.draftId,version:saved.version}
  setDraft(d=>d?{...d,draftId:saved.draftId,version:saved.version}:d)
  setVerified({status:saved.contactVerification,email:saved.data.contactEmail,phone:saved.data.contactPhone})
  if(revision.current===savingRevision)setDirty(false)
  return saved
 }
 async function perform(action:()=>Promise<void>){
  if(operation.current)return false
  const uid=owner.current;operation.current=true;setBusy(true);setMessage('')
  try{if(contactSave.current)await contactSave.current;await action();return true}catch(e){
   if(owner.current===uid){
    if(e instanceof ApiError&&e.code==='SLOT_UNAVAILABLE'){
     change({slot:''});setStep(1);slots.reload()
     setMessage('原時段已無法預約，已返回日期時段步驟。請重新選擇日期與時段；其他草稿資料已保留，選好後再保存並繼續。')
    }else setMessage((e as Error).message)
   }
   return false
  }finally{operation.current=false;if(owner.current===uid)setBusy(false)}
 }
 useEffect(()=>{
  if(!dirty||busy||savingContact||step!==5||attemptedContactRevision.current===revision.current)return
  const savingRevision=revision.current
  const timer=setTimeout(()=>{
   if(operation.current||contactSave.current||revision.current!==savingRevision)return
   attemptedContactRevision.current=savingRevision
   setSavingContact(true)
   contactSave.current=save().then(()=>{},error=>{
    if(revision.current===savingRevision)setMessage((error as Error).message)
   }).finally(()=>{
    contactSave.current=null
    setSavingContact(false)
   })
  },650)
  return()=>clearTimeout(timer)
 },[dirty,busy,savingContact,step,draft?.name,draft?.email,draft?.phone])

 function editContact(patch:Partial<Draft>){change(patch);setDirty(true)}
 function normalizeContactPhone(){
  if(!draft||draft.contactMode!=='other')return
  try{
   const value=normalizeMobile(draft.phone.trim().startsWith('+81')?'+81':'+886',draft.phone)
   if(value!==draft.phone)editContact({phone:value})
  }catch{
   // Leave incomplete input available for editing.
  }
 }
 function switchContact(mode:'member'|'other'){
  if(!draft||!profile||mode===(draft.contactMode??'member'))return
  const other=draft.contactMode==='other'?{name:draft.name,email:draft.email,phone:draft.phone}:draft.otherContact
  const next={...draft,...(mode==='member'?memberContact(profile):other??emptyContact),contactMode:mode,otherContact:other,acceptedPolicy:false}
  change(next)
  void perform(async()=>{await save(next)})
 }
 async function verifyContact(path:string,body?:object){
  if(!draft)return false
  return perform(async()=>{
   const saved=await save()
   const token=await auth.token()
   const url='/api/booking-drafts/'+saved.draftId
   await request(url+'/contact/'+path,{method:'POST',token,body:{...body,version:saved.version}})
   const updated=await request<ServerDraft>(url,{token})
   if(owner.current===auth.user?.uid){
    setVerified({status:updated.contactVerification,email:updated.data.contactEmail,phone:updated.data.contactPhone})
    setMessage(path==='email'?'驗證碼已寄出，請查看聯絡信箱。':'已完成驗證。')
   }
  })
 }
 const emailVerified=!!draft&&(draft.email.trim().toLowerCase()===profile?.email.toLowerCase()&&profile.emailVerified||
   draft.contactMode==='other'&&draft.email===verified?.email&&verified.status?.email)
 const phoneVerified=!!draft&&(draft.phone===profile?.phoneNumber&&profile.phoneVerified||
   draft.contactMode==='other'&&draft.phone===verified?.phone&&verified.status?.phone)

 async function next(){if(!draft||!form.current?.reportValidity())return
  if(step===0&&!draft.storeId){setMessage('請選擇門市。');return}
  if(step===1&&(!draft.slot||!draft.date)){setMessage('請選擇有效日期與場次。');return}
  if(step===3&&draft.participants.some(p=>!p.kimonoId)){setMessage('請為每位旅客選擇和服。');return}
  if(step===5){
   if(!draft.name.trim()){setMessage('請填寫聯絡姓名。');return}
   if(draft.name.trim().length>40||draft.email.trim().length>40){setMessage('付款需要 40 字以內的聯絡姓名與 Email，請修改或選用其他聯絡資料。');return}
   if(!emailVerified||!phoneVerified){setMessage('請先完成聯絡 Email 與手機驗證。');return}
  }
  await perform(async()=>{
   const enteringContact=step===4&&!draft.contactMode
   const saved=await save(enteringContact?{...draft,contactMode:'member'}:draft)
   if(enteringContact)setDraft(current=>current?{...current,contactMode:'member'}:current)
   if(step===5&&(!saved.contactVerification.email||!saved.contactVerification.phone||!saved.contactVerification.memberName)){
    throw new Error('請確認聯絡資料並完成 Email 與手機驗證。')
   }
   setStep(s=>Math.min(6,s+1))
  })
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
 const missingProfile=profile?missingBookingProfile(profile):[]
 if(missingProfile.length)return <Container><Notice>請先到會員中心{missingProfile.join('、')}，再開始預約。 <ButtonLink to={'/account?returnTo='+encodeURIComponent('/booking?'+params.toString())}>前往會員中心</ButtonLink></Notice></Container>
 if(plans.error||stores.error)return <Container><Notice tone="error">{plans.error||stores.error}</Notice><Button onClick={()=>{plans.reload();stores.reload()}}>重試</Button></Container>
 if(!initialized)return <Container><Loading/></Container>
 if(!draft||!plan)return <Container><Notice>{message||'原方案已無法使用，請明確選擇新的方案。'}</Notice>{draft&&<Field label="替換方案"><Select value="" onChange={e=>{const next=plans.data.find(p=>p.id===e.target.value)!;change({planId:next.id,city:next.city,storeId:'',slot:'',date:'',participants:participantsFor(next)});setStep(0)}}><option value="">選擇方案</option>{plans.data.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</Select></Field>}<ButtonLink to="/plans">探索方案</ButtonLink></Container>
 const contactStep=step===5&&!hold
 const contactEditable=draft.contactMode==='other'
 const contactReady=!!emailVerified&&!!phoneVerified&&!!draft.name.trim()
 return <Container><PageHeading eyebrow={contactStep?'YOUR KIMONO JOURNEY':'BOOK YOUR JOURNEY'}
  title={contactStep?'讓我們與你保持聯繫':'預約你的和服體驗'}
  description={contactStep?'確認這次旅程的聯絡方式，讓預約通知與到店資訊準時送達。':'單人方案 1 人；情侶方案固定一男一女 2 人；團體方案 2～3 人。'}/>
 <Notice>目前為 Sandbox 測試付款，不會收取真實款項。確認付款且資源轉正式保留後，才成立測試預約。</Notice>
 {message&&<Notice>{message}</Notice>}
 {hold?<BookingPayment key={auth.user?.uid+hold.holdId} hold={hold} contact={{name:draft.name,email:draft.email,phone:draft.phone}} remaining={remaining} onRelease={()=>void release()}/>:<>
 <ol className="mb-8 grid grid-cols-4 gap-2 md:grid-cols-7">{steps.map((label,i)=><li key={label} className={'border-b-2 py-3 text-xs '+(i===step?'border-vermilion text-vermilion':'border-line')}>{i+1}. {label}</li>)}</ol>
 <div className="grid items-start gap-8 lg:grid-cols-[1.5fr_1fr]"><Panel className={contactStep?'bg-white/40 md:p-8':''}><form ref={form} onSubmit={e=>{e.preventDefault();void next()}} className="space-y-6"><h2 className="font-serif text-2xl">{contactStep?'預約聯絡資料':steps[step]}</h2><fieldset disabled={busy} className="space-y-6">
 {step===0&&<><Field label="方案"><Select value={plan.id} onChange={e=>{const p=plans.data.find(p=>p.id===e.target.value)!;change({planId:p.id,city:p.city,storeId:'',slot:'',participants:participantsFor(p)})}}>{plans.data.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</Select></Field><Field label="門市"><Select required value={draft.storeId} onChange={e=>{const store=stores.data.find(s=>s.id===e.target.value);change({storeId:e.target.value,city:store?.city.toLowerCase()??plan.city,slot:'',participants:draft.participants.map(p=>({...p,kimonoId:'',generationId:undefined}))})}}><option value="">選擇門市</option>{stores.data.filter(s=>plan.storeIds?.includes(s.id)).map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</Select></Field></>}
 {step===1&&<><Field label="日本當地日期"><input required type="date" value={draft.date} onChange={e=>change({date:e.target.value,slot:''})} className={inputClass}/></Field><Field label="場次"><Select required value={draft.slot} onChange={e=>change({slot:e.target.value})}><option value="">選擇時段</option>{slots.data.map(s=><option key={s.id} value={s.id} disabled={!s.available}>{s.label}{!s.available?'（不可預約）':''}</option>)}</Select></Field>{slots.loading&&<Loading/>}{slots.error&&<Notice tone="error">{slots.error}</Notice>}<p className="text-xs text-muted">開始前至少 24 小時至未來 90 天；選擇場次不占用名額。</p></>}
 {step===2&&<Field label="旅客人數"><Select value={draft.participants.length} onChange={e=>{const count=Number(e.target.value);const people=[...draft.participants];while(people.length<count)people.push({id:crypto.randomUUID(),role:'FEMALE',kimonoId:'',beltId:null});change({participants:people.slice(0,count)})}}>{participantCounts(plan).map(n=><option key={n} value={n}>{n} 位成人</option>)}</Select></Field>}
 {step===3&&<>{draft.participants.map((p,i)=><div key={p.id} className="space-y-4 border-b border-line pb-6"><h3>旅客 {i+1}</h3><GarmentSelection participant={p} kimonos={kimonos.data} roleLocked={plan.kind==='COUPLE'&&i<2} onChange={patch=>change({participants:updateParticipant(draft.participants,p.id,{...patch,generationId:undefined})})}/><BeltSelection participant={p} belts={belts.data} plan={plan} onChange={beltId=>change({participants:updateParticipant(draft.participants,p.id,{beltId})})}/></div>)}<div className="flex flex-wrap gap-3"><ButtonLink onClick={keepJourney} to={journeyLink('/try-on?plan='+plan.id,journeyId.current)}>AI 試穿此搭配</ButtonLink><ButtonLink onClick={keepJourney} to={journeyLink('/looks',journeyId.current)}>從收藏挑選</ButtonLink></div>{(kimonos.error||belts.error)&&<Notice tone="error">{kimonos.error||belts.error}</Notice>}</>}
 {step===4&&<Notice>女生腰帶於搭配步驟選擇並另行計費。攝影、其他配件與 AI 腰帶穿戴尚未開放。</Notice>}
 {step===5&&<>
  <fieldset className="grid gap-3 sm:grid-cols-2">
   <legend className="sr-only">聯絡資料來源</legend>
   {([
    ['member','使用會員聯絡資料','沿用已驗證的 Email 與手機'],
    ['other','使用其他聯絡資料','可填同行者資料，需另外驗證'],
   ] as const).map(([mode,title,description])=><label key={mode}
    className={`flex cursor-pointer items-start gap-3 border p-4 focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-forest ${(draft.contactMode??'member')===mode?'border-forest bg-forest/6':'border-line'}`}>
    <input type="radio" name="contactMode" value={mode} checked={(draft.contactMode??'member')===mode}
     onChange={()=>switchContact(mode)} className="mt-1 size-4 shrink-0 accent-forest"/>
    <span><span className="block text-sm font-medium">{title}</span><span className="mt-1 block text-xs leading-5 text-muted">{description}</span></span>
   </label>)}
  </fieldset>
  <Field label="聯絡姓名"><input required maxLength={40} autoComplete="name" value={draft.name} readOnly={!contactEditable} onChange={e=>editContact({name:e.target.value})} className={inputClass}/></Field>
  <BookingContactVerification email={draft.email} emailVerified={!!emailVerified} phoneVerified={!!phoneVerified} phone={draft.phone}
   editable={contactEditable} onEmailChange={email=>editContact({email})} onPhoneChange={phone=>editContact({phone})}
   onPhoneBlur={normalizeContactPhone} normalizePhone={phone=>editContact({phone})} submit={verifyContact}/>
  <p className="bg-wash/65 px-4 py-3 text-sm leading-7 text-muted">
   此聯絡方式僅供本次預約通知使用，不會更改會員資料。這筆預約仍由目前登入的會員管理。
  </p>
  {contactEditable&&<details className="border-t border-line pt-4 text-sm">
   <summary className="cursor-pointer">收不到驗證碼？</summary>
   <p className="mt-3 text-xs leading-6 text-muted">
    請確認 Email 與手機號碼，並檢查垃圾郵件。若仍未收到，可稍候再重新傳送驗證碼。
   </p>
  </details>}
 </>}
 {step===6&&<><p>{draft.participants.length} 位成人 · {draft.date}</p><p>聯絡資料 · {draft.name} · {draft.email} · {draft.phone}</p><Check checked={draft.acceptedPolicy} onChange={e=>change({acceptedPolicy:e.target.checked})}>我已確認搭配與聯絡資料，了解報價不占庫存，暫留不代表預約成立。</Check><Button disabled={!auth.user||!draft.acceptedPolicy} onClick={getQuote}>取得後端報價</Button></>}
 </fieldset>
 <div className={contactStep?'flex flex-wrap items-center justify-between gap-4':'flex gap-4'}>
  {step>0&&<Button className={contactStep?'border-transparent px-0 text-muted underline underline-offset-4 hover:bg-transparent hover:text-ink':''}
   disabled={busy} onClick={()=>{if(step===5&&dirty)void perform(async()=>{await save();setStep(4)});else setStep(s=>s-1)}}>
   {contactStep?'← 返回上一步':'上一步'}
  </Button>}
  {step<6&&<Button type="submit" variant={contactStep?'primary':'secondary'}
   className={contactStep?'border-vermilion bg-vermilion hover:border-ink':''}
   disabled={busy||(contactStep&&!contactReady)}>{contactStep?'繼續確認預約 →':'保存並繼續'}</Button>}
 </div>
 {contactStep&&!contactReady&&<p className="text-xs leading-6 text-muted">請填寫聯絡姓名並完成 Email 與手機驗證後繼續。</p>}
 </form>
 </Panel>
 <Panel><h2 className="font-serif text-xl">{plan.name}</h2><p className="mt-4">{draft.participants.length} 位 · 統一尺寸</p><p className="mt-4 text-sm text-muted">金額以後端報價為準；情侶套餐計價一次，腰帶分開計費。</p>{quote&&<div className="mt-6 space-y-4">{quote.lineItems?.map((l,i)=><p key={i}>{localized(l.label)} · {money(l.amount)}</p>)}<strong>{money(quote.total)}</strong><p>{quoteExpired(quote,now)?'報價已到期':'確認報價後才會建立暫留。'}</p><Button disabled={busy||quoteExpired(quote,now)||!auth.user?.emailVerified} onClick={reserve}>確認報價並暫留 10 分鐘</Button>{!auth.user?.emailVerified&&<ButtonLink to="/verify-email">先完成 Email 驗證</ButtonLink>}</div>}</Panel></div></>}
 </Container>
}

export function BookingComplete(){
 const{bookingNo}=useParams();const auth=useAuth();const booking=usePrivateResource<{bookingNo:string;paymentStatus:string;storeName:string;startTime:string;total:number}|null>('/api/bookings/'+encodeURIComponent(bookingNo??''),null)
 return <Container><PageHeading eyebrow="YOUR RESERVATION" title={booking.data?'測試預約已成立':'確認預約結果'}/>{!auth.user?<ButtonLink to={'/login?returnTo='+encodeURIComponent('/booking/complete/'+bookingNo)}>登入後查看本人預約</ButtonLink>:booking.loading?<Loading/>:booking.error?<Notice tone="error">{booking.error}</Notice>:booking.data?<Panel><Notice>Sandbox 測試預約，未收取真實款項。</Notice><p className="mt-5 break-all">預約編號：{booking.data.bookingNo}</p><p className="mt-4">{booking.data.storeName} · {new Date(booking.data.startTime).toLocaleString('zh-TW',{timeZone:'Asia/Tokyo'})}（日本時間）</p><p className="my-4">{money(booking.data.total)} · {paymentLabel(booking.data.paymentStatus)}</p><ButtonLink primary to={'/bookings/'+booking.data.bookingNo}>查看完整預約內容</ButtonLink><p className="mt-5 text-sm text-muted">確認 Email 與動態票券將於後續階段開放。</p></Panel>:null}<div className="mt-6"><ButtonLink to="/bookings">我的預約</ButtonLink></div></Container>
}
