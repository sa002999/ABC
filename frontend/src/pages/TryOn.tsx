import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Camera, CheckCircle2, ImagePlus, LoaderCircle, Sparkles, Trash2 } from 'lucide-react'
import { Button, ButtonLink, Check, Container, Empty, Field, Modal, Notice, PageHeading, Panel, Select, Loading } from '../components/ui'
import { useAuth } from '../lib/auth'
import { actionKey, apiBase, apiConfigured, request, unwrap } from '../lib/api'
import { useBackend, usePrivateResource, useResource } from '../lib/hooks'
import { reconcileSelection, selectedPlan, selectionFromQuery, selectionQuery, useBelts, useKimonos, usePlans } from '../lib/catalogApi'
import { isJobDone, isJobFailed, updateParticipant, type Belt, type Job, type Participant, type Plan } from '../lib/domain'
import { BookingReturn } from '../components/BookingReturn'
import { useBookingJourney } from '../lib/useBookingJourney'
import { sameSelection, saveJourney } from '../lib/bookingJourney'
import { BeltSelection, GarmentSelection } from './Plans'

type PhotoState = { file?: File; preview?: string; consent: boolean; sessionId?: string; modelSessionId?: string; photoId?: string; modelId?: string; source:'PHOTO'|'MODEL'; uploading:boolean; error:string; job?: Job }
const initialPhoto = ():PhotoState => ({consent:false,source:'PHOTO',uploading:false,error:''})
type Usage = { website?:{remaining:number}; websiteRemaining?:number }

export function TryOn() {
  const auth=useAuth();const[params,setParams]=useSearchParams();const plans=usePlans();const belts=useBelts();const kimonos=useKimonos();const backend=useBackend();const aiEnabled=backend.capabilities.aiGeneration
  const navigate=useNavigate();const {journey,owner,returnTo,onward}=useBookingJourney()
  const plan=selectedPlan(plans.data,params.get('plan'))
  const [people,setPeople]=useState<Participant[]>(plan?selectionFromQuery(plan,params):[])
  const memberRef=useRef(auth.user?.uid);memberRef.current=auth.user?.uid
  const [photos,setPhotos]=useState<Record<string,PhotoState>>({})
  const photoRef=useRef(photos);photoRef.current=photos
  const [message,setMessage]=useState('');const [confirm,setConfirm]=useState<{personId:string;kind:'TRY_ON'|'SCENE'}|null>(null)
  const generationKeys=useRef(new Map<string,{body:string;key:string}>())
  const [sceneId,setSceneId]=useState('');const [busy,setBusy]=useState(false)
  const usage=usePrivateResource<Usage>('/api/account/generation-usage',{})
  const models=useResource<{id:string;name:string;role?:string}[]>('/api/models',[],undefined,aiEnabled)
  const consent=useResource<{version:string;text:string}>('/api/try-on/consent',{version:'',text:''},undefined,aiEnabled)
  const sessions=usePrivateResource<{sessionId:string;source:string;status:string;modelId?:string;photo?:{photoId:string;previewUrl?:string};consentStatus:string}[]>('/api/try-on/sessions?pageSize=50',[])
  const scenes=useResource<{id:string;name:string}[]>('/api/scenes',[],undefined,false)
  const urls=useRef(new Set<string>())
  useEffect(()=>()=>{urls.current.forEach(url=>URL.revokeObjectURL(url))},[])
  useEffect(()=>{
    if(!plan)return
    const next=selectionFromQuery(plan,params)
    setPeople(journey?.draft.planId===plan.id?journey.draft.participants:next)
    urls.current.forEach(url=>URL.revokeObjectURL(url));urls.current.clear();setPhotos({});setBusy(false);setConfirm(null);setMessage('')
  },[plan?.id,auth.user?.uid])
  useEffect(()=>{if(plan&&!kimonos.loading&&!belts.loading&&!kimonos.error&&!belts.error)setPeople(p=>reconcileSelection(p,plan,kimonos.data,belts.data))},[plan,kimonos.data,belts.data,kimonos.loading,belts.loading,people])
  function setPhoto(id:string,patch:Partial<PhotoState>) {setPhotos(all=>({...all,[id]:{...(all[id]??initialPhoto()),...patch}}))}
  function chooseFile(id:string,file?:File) {
    if(!file)return
    if(file.size>10*1024*1024){setPhoto(id,{error:'照片上限為 10 MB。'});return}
    if(!['image/jpeg','image/png','image/heic','image/heif'].includes(file.type)&&! /\.hei[cf]$/i.test(file.name)){setPhoto(id,{error:'請選 JPEG、PNG 或 HEIC 照片。'});return}
    const old=photos[id]?.preview;if(old){URL.revokeObjectURL(old);urls.current.delete(old)}
    const preview=/\.hei[cf]$/i.test(file.name)?undefined:URL.createObjectURL(file);if(preview)urls.current.add(preview)
    setPhoto(id,{file,preview,photoId:undefined,error:''})
  }
  async function upload(person:Participant) {
    const photo=photos[person.id];if(!plan||!aiEnabled||!photo?.file||!photo.consent)return
    const member=memberRef.current
    setPhoto(person.id,{uploading:true,error:''})
    try {
      const token=await auth.token()
      const contentType=photo.file.type||(/\.heif$/i.test(photo.file.name)?'image/heif':'image/heic')
      const session=photo.sessionId?{sessionId:photo.sessionId}:unwrap(await request<{sessionId:string}>('/api/try-on/sessions',{method:'POST',token,key:actionKey(),body:{planId:plan.id,kimonoId:person.kimonoId,source:'SELF',consentAccepted:true,consentVersion:consent.data.version}}))
      const url=unwrap(await request<{uploadUrl:string;photoId:string;method?:string;transport?:string;fields?:Record<string,string>;headers?:Record<string,string>}>(`/api/try-on/sessions/${session.sessionId}/upload-url`,{method:'POST',token,body:{fileName:photo.file.name,contentType,size:photo.file.size}}))
      const uploadBody=new FormData();for(const [key,value] of Object.entries(url.fields??{}))uploadBody.append(key,value);uploadBody.append('file',photo.file)
      const isApi=url.transport==='API'
      if(isApi&&!url.uploadUrl.startsWith(apiBase+'/api/try-on/sessions/'))throw new Error('照片上傳位址不正確。')
      const response=await fetch(url.uploadUrl,isApi?{method:'PUT',headers:{Authorization:'Bearer '+token,'Content-Type':contentType},body:photo.file}:{method:'POST',body:uploadBody})
      if(!response.ok)throw new Error('照片上傳失敗，請重新嘗試。')
      const validation=unwrap(await request<{status:string;photoId:string;issues?:{message:string}[]}>(`/api/try-on/sessions/${session.sessionId}/validate`,{method:'POST',token,body:{photoId:url.photoId}}))
      if(!['VALID','VALIDATED','READY','FILE_READY','valid'].includes(validation.status))throw new Error(validation.issues?.map(i=>i.message).join('；')??'照片未通過驗證。')
      if(memberRef.current!==member)return
      setPhoto(person.id,{sessionId:session.sessionId,photoId:validation.photoId,uploading:false});sessions.reload()
    }catch(error){if(memberRef.current===member)setPhoto(person.id,{uploading:false,error:(error as Error).message})}
  }
  async function deletePhoto(personId:string,withdraw=false) {
    const member=memberRef.current;const p=photos[personId]
    try{if(p?.sessionId)await request(`/api/try-on/sessions/${p.sessionId}/photo${withdraw?'?withdrawConsent=true':''}`,{method:'DELETE',token:await auth.token()});if(memberRef.current!==member)return;if(p?.preview){URL.revokeObjectURL(p.preview);urls.current.delete(p.preview)};setPhotos(all=>({...all,[personId]:{...initialPhoto(),job:all[personId]?.job}}));sessions.reload()}catch(error){setMessage((error as Error).message)}
  }
  async function generate() {
    if(!aiEnabled||!confirm||!plan)return
    const person=people.find(p=>p.id===confirm.personId)!;const photo=photos[person.id]??initialPhoto()
    const member=memberRef.current
    setBusy(true);setMessage('')
    try {
      if(!person.kimonoId)throw new Error('請先選擇這位旅客的和服。')
      if(!kimonos.data.find(k=>k.id===person.kimonoId)?.imageUrl)throw new Error('所選商品圖片尚未補齊，暫時無法生成試穿圖。')
      const token=await auth.token();let sessionId=photo.source==='MODEL'?photo.modelSessionId:photo.sessionId
      if(photo.source==='MODEL') {
        if(!photo.modelId)throw new Error('請選擇商店模特兒。')
        if(!sessionId){const session=unwrap(await request<{sessionId:string}>('/api/try-on/sessions',{method:'POST',token,body:{planId:plan.id,kimonoId:person.kimonoId,source:'MODEL',modelId:photo.modelId}}));sessionId=session.sessionId;setPhoto(person.id,{modelSessionId:sessionId})}
      } else if(!photo.consent||!photo.photoId)throw new Error('請先同意、上傳並通過這位旅客的照片驗證。')
      await request(`/api/try-on/sessions/${sessionId}`,{method:'PATCH',token,body:{planId:plan.id,kimonoId:person.kimonoId}})
      const path=confirm.kind==='SCENE'?`/api/try-on/jobs/${photo.job?.jobId}/scene-generations`:`/api/try-on/sessions/${sessionId}/generations`
      const body=confirm.kind==='SCENE'?{sceneId,confirmed:true}:{planId:plan.id,kimonoId:person.kimonoId,...(photo.source==='MODEL'?{modelId:photo.modelId}:{photoId:photo.photoId}),confirmed:true}
      const operationId=person.id+':'+confirm.kind;const signature=JSON.stringify(body);const previous=generationKeys.current.get(operationId);const key=previous?.body===signature?previous.key:actionKey();generationKeys.current.set(operationId,{body:signature,key})
      const job=unwrap(await request<Job>(path,{method:'POST',token,key,body}));generationKeys.current.delete(operationId)
      if(memberRef.current!==member)return
      setPhoto(person.id,{job});setConfirm(null);usage.reload()
    }catch(error){if(memberRef.current===member)setMessage((error as Error).message)}finally{if(memberRef.current===member)setBusy(false)}
  }
  const activeJobs=Object.entries(photos).filter(([,p])=>p.job&&!isJobDone(p.job.status)&&!isJobFailed(p.job.status)).map(([id,p])=>id+':'+p.job!.jobId).join(',')
  useEffect(()=>{
    if(!activeJobs)return
    let stopped=false;let timer:ReturnType<typeof setTimeout>
    const poll=async()=>{
      try{const token=await auth.token();for(const item of activeJobs.split(',')){if(stopped)return;const[id,jobId]=item.split(':');const job=unwrap(await request<Job>('/api/try-on/jobs/'+jobId,{token}));if(!stopped)setPhoto(id,{job})}}catch(error){if(!stopped)setMessage((error as Error).message)}
      if(!stopped)timer=setTimeout(poll,3000)
    };timer=setTimeout(poll,1500);return()=>{stopped=true;clearTimeout(timer)}
  },[activeJobs,auth.user?.uid])
  function carrySelection(){if(!plan||!auth.user)return;try{sessionStorage.setItem('kinu:transfer:'+auth.user.uid,JSON.stringify({planId:plan.id,participants:people.map(person=>({...person,photoId:photos[person.id]?.photoId,generationId:photos[person.id]?.job?.generationId}))}))}catch{}}
  async function saveLook(){if(!plan||!backend.capabilities.looks)return;try{await request('/api/looks',{method:'POST',token:await auth.token(),key:actionKey(),body:{planId:plan.id,participants:people.map(person=>({id:person.id,role:person.role,kimonoId:person.kimonoId,beltId:person.beltId,generationId:photos[person.id]?.job?.generationId}))}});setMessage('造型已保存。');navigate(onward('/looks'))}catch(error){setMessage((error as Error).message)}}
  const completedJobs=Object.values(photos).filter(p=>p.job&&isJobDone(p.job.status)).map(p=>p.job!.jobId).join(',')
  useEffect(()=>{if(!completedJobs||!auth.user)return;let active=true;const timer=setInterval(async()=>{try{const token=await auth.token();for(const id of completedJobs.split(',')){const job=await request<Job>('/api/try-on/jobs/'+id,{token});if(active)setPhotos(all=>Object.fromEntries(Object.entries(all).map(([key,p])=>[key,p.job?.jobId===id?{...p,job}:p])))}}catch{}},60000);return()=>{active=false;clearInterval(timer)}},[completedJobs,auth.user?.uid])
  const selectionChanged=!!journey&&!sameSelection(journey.draft,{planId:plan?.id??'',participants:people})
  function applyAndReturn(){
    if(!journey||!plan||!returnTo)return
    try{
      saveJourney(owner,{...journey,selection:{planId:plan.id,participants:people.map(person=>({...person,photoId:photos[person.id]?.photoId??person.photoId,generationId:photos[person.id]?.job?.generationId??person.generationId}))}})
      const target=new URL(returnTo,window.location.origin);target.searchParams.set('plan',plan.id);target.searchParams.set('applyLook','1');navigate(target.pathname+target.search)
    }catch{setMessage('無法保存搭配，請稍後再試。')}
  }
  if(plans.loading)return <Container><Loading/></Container>
  if(plans.error)return <Container><Notice tone="error">{plans.error}</Notice><Button onClick={plans.reload}>重試</Button></Container>
  if(!plan)return <Container><Empty>沒有可供試穿的方案，請先完成商品建檔。</Empty></Container>
  return <Container><PageHeading eyebrow="AI STYLING · OPTIONAL" title="預覽，屬於你的造型" description="女生僅可選腰帶，男生無配件。情侶的兩張照片獨立管理；每次生成須另外確認。"/>{!auth.user&&<Notice>上傳或生成前請先 <Link className="underline" to={'/login?returnTo='+encodeURIComponent('/try-on?'+params.toString())}>登入會員</Link>。可先檢視表單，或略過 AI 直接預約。</Notice>}{!aiEnabled&&<Notice>方案、和服與腰帶已使用後端示範資料；AI 生成及上傳服務尚未啟用，商品圖片仍待補齊。可先挑選搭配。</Notice>}{(kimonos.error||belts.error)&&<Notice tone="error">{kimonos.error||belts.error}</Notice>}<div className={people.length>1?'min-w-0':'mx-auto w-full min-w-0 max-w-[720px]'}><div className="mb-8 w-full max-w-[360px]"><Field label="試穿方案"><Select value={plan.id} onChange={e=>setParams(p=>{const next=new URLSearchParams(p);next.set('plan',e.target.value);return next})}>{plans.data.map(p=><option key={p.id} value={p.id}>{p.name}{p.kind==='COUPLE'?'（雙人）':''}</option>)}</Select></Field></div><div className={`grid min-w-0 gap-6 ${people.length>1?'lg:grid-cols-2':''}`}>{people.map(person=>{const photo=photos[person.id]??initialPhoto();const label=person.role==='FEMALE'?'女生':'男生';const image=photo.job?.imageUrl??photo.job?.resultUrl;return <Panel key={person.id} className="min-w-0"><div className="mb-6 flex items-center justify-between"><h2 className="font-serif text-2xl">{label}造型</h2><span className="text-[10px] tracking-wider text-muted">UNIFORM SIZE</span></div><div className="mb-5 space-y-4">{consent.data.text&&<p className="text-xs leading-6 text-muted">{consent.data.text}</p>}<Field label="重用已保存的人物來源"><Select value="" onChange={e=>{const source=sessions.data.find(s=>s.sessionId===e.target.value);if(source)setPhoto(person.id,{source:source.source==='MODEL'?'MODEL':'PHOTO',sessionId:source.source==='SELF'?source.sessionId:undefined,modelSessionId:source.source==='MODEL'?source.sessionId:undefined,modelId:source.modelId,photoId:source.photo?.photoId,preview:source.photo?.previewUrl,consent:source.consentStatus==='GRANTED',file:undefined,job:undefined})}}><option value="">選擇本人已保存來源</option>{sessions.data.filter(s=>s.source==='MODEL'||s.photo&&s.consentStatus==='GRANTED').map((s,i)=><option key={s.sessionId} value={s.sessionId}>{s.source==='MODEL'?'模特兒':'本人照片'} {i+1} · {s.status}</option>)}</Select></Field></div><div className="mb-5 flex flex-wrap gap-3"><Button onClick={()=>setPhoto(person.id,{source:'PHOTO'})} variant={photo.source==='PHOTO'?'primary':'secondary'}>上傳照片</Button><Button onClick={()=>setPhoto(person.id,{source:'MODEL'})} variant={photo.source==='MODEL'?'primary':'secondary'}>商店模特兒</Button></div>{photo.source==='PHOTO'?<><div className={`tryon-photo-preview relative flex min-w-0 w-full items-center justify-center border border-dashed border-line bg-wash/40 ${photo.preview?'':'h-40 md:h-[200px]'}`}>{photo.preview?<img src={photo.preview} alt={label+'照片本機預覽'} className="block h-auto max-h-[280px] w-auto max-w-full object-contain md:max-h-[360px]"/>:<div className="min-w-0 max-w-full px-5 text-center text-muted [overflow-wrap:anywhere]"><Camera size={24} strokeWidth={1} className="mx-auto"/><p className="mt-3 font-serif">{photo.file?'HEIC 照片待後端轉換預覽':'上傳'+label+'照片'}</p><p className="mt-1 text-[11px] leading-6">單人正面全身照 · JPEG / PNG / HEIC · 10 MB 以內</p></div>}</div><div className="mt-5 min-w-0 max-w-full [overflow-wrap:anywhere]"><Check checked={photo.consent} onChange={e=>setPhoto(person.id,{consent:e.target.checked})}>我已取得這位照片當事人同意，並同意為 AI 試穿處理{label}照片。</Check><label className="mt-3 block text-sm">上傳{label}照片<input aria-label={'上傳'+label+'照片'} type="file" accept="image/jpeg,image/png,image/heic,image/heif,.heic" disabled={!photo.consent||!auth.user} className="mt-2 block min-w-0 w-full max-w-full text-xs file:mr-3 file:border file:border-line file:bg-paper file:px-4 file:py-3 file:text-ink disabled:opacity-40" onChange={e=>chooseFile(person.id,e.target.files?.[0])}/></label><div className="mt-4 flex flex-wrap gap-3"><Button disabled={!photo.file||!photo.consent||!auth.user||!aiEnabled||photo.uploading} onClick={()=>upload(person)}>{photo.uploading?'上傳驗證中…':photo.photoId?'照片已驗證':'上傳並驗證照片'}</Button><Button disabled={!photo.file&&!photo.photoId} onClick={()=>void deletePhoto(person.id)}><Trash2 size={14}/>刪除此人原圖</Button><Button disabled={!photo.sessionId} onClick={()=>void deletePhoto(person.id,true)}>撤回同意並刪除</Button></div>{photo.file&&<p className="mt-2 break-all text-[10px] text-muted">{photo.file.name} · 替換或刪除只影響這位旅客；選取檔案不會自動生成。</p>}</div></>:<div className="mb-6 w-full max-w-[400px]"><Field label={label+'模特兒'}><Select value={photo.modelId??''} onChange={e=>setPhoto(person.id,{modelId:e.target.value,modelSessionId:undefined})}><option value="">選擇商店模特兒</option>{models.data.filter(m=>!m.role||m.role===person.role).map(m=><option key={m.id} value={m.id}>{m.name}</option>)}</Select></Field>{!models.data.length&&<Notice>模特兒來源照需由後端建檔，不以商品展示圖代替。</Notice>}</div>}<div className="mt-6 w-full max-w-[400px] space-y-5"><GarmentSelection participant={person} kimonos={kimonos.data} roleLocked={plan.kind==='COUPLE'&&people.indexOf(person)<2} onChange={patch=>{setPeople(all=>updateParticipant(all,person.id,patch));setPhoto(person.id,{job:undefined})}}/><BeltSelection participant={person} plan={plan} belts={belts.data} onChange={beltId=>setPeople(all=>updateParticipant(all,person.id,{beltId}))}/></div>{photo.error&&<Notice tone="error">{photo.error}</Notice>}<Button variant="primary" className="mt-6 max-w-full" disabled={!aiEnabled||!auth.user||!!activeJobs||!kimonos.data.find(k=>k.id===person.kimonoId)?.imageUrl} onClick={()=>setConfirm({personId:person.id,kind:'TRY_ON'})}><Sparkles size={16}/>確認生成{label}試穿圖</Button>{photo.job&&<div className="mt-6 border-t border-line pt-6" role="status">{isJobDone(photo.job.status)&&image?<><img src={image} alt={label+'真實 AI 試穿結果'} className="max-h-96 w-full object-contain"/><p className="mt-3 flex items-center gap-2 text-xs text-forest"><CheckCircle2 size={14}/>生成完成 · 圖片保存期限以後端為準</p></>:isJobFailed(photo.job.status)?<Notice tone="error">生成未成功，請確認原因後重新提交；不以展示圖代替。</Notice>:<p className="flex items-center gap-3 text-sm"><LoaderCircle className="animate-spin" size={16}/>生成處理中，請勿重複提交。</p>}{false&&isJobDone(photo.job!.status)&&<div className="mt-5 w-full max-w-[400px] space-y-4"><Field label="選用外拍場景"><Select value={sceneId} onChange={e=>setSceneId(e.target.value)}><option value="">選擇場景</option>{scenes.data.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</Select></Field><Button disabled={!sceneId||!!activeJobs} onClick={()=>setConfirm({personId:person.id,kind:'SCENE'})}>確認場景生成（另計 1 次）</Button></div>}</div>}</Panel>})}</div>{message&&<Notice>{message}</Notice>}<div className="mt-8 flex max-w-full flex-wrap gap-3 [&>a]:max-w-full [&>button]:max-w-full">{journey?<><BookingReturn to={returnTo}/>{selectionChanged&&<Button style={{borderRadius:0}} variant="primary" disabled={people.some(p=>!p.kimonoId)} onClick={applyAndReturn}>套用搭配並返回預約</Button>}</>:<ButtonLink primary onClick={carrySelection} to={'/booking?'+new URLSearchParams([...selectionQuery(plan,people),['from','tryon']])}>跳過或帶入搭配，直接預約</ButtonLink>}<Button disabled={!auth.user||!backend.capabilities.looks} onClick={saveLook}>加入造型收藏</Button><ButtonLink to={onward("/account/generations")}>我的生成圖</ButtonLink></div><p className="mt-5 text-xs leading-7 text-muted">每位會員每天可在網站生成 5 次 AI 圖片，試穿與場景各算 1 次；MCP 另有每日 3 次額度，皆於日本午夜重設。網站生成圖保存 7 天，到期不影響收藏搭配。腰帶選擇會保存至收藏與預約，現階段 AI 只生成和服，不合成腰帶或場景。原始照片、生成圖與收藏可分別刪除，互不影響。</p><Modal title="確認本次生成" open={!!confirm} onClose={()=>!busy&&setConfirm(null)}><p className="text-sm leading-8">將為{people.find(p=>p.id===confirm?.personId)?.role==='FEMALE'?'女生':'男生'}建立一個{confirm?.kind==='SCENE'?'場景':'試穿'}任務，使用 1 次網站生成額度。選擇、上傳與生成確認是分開的操作。</p><p className="mt-3 text-sm text-muted">剩餘額度：{usage.data.website?.remaining??usage.data.websiteRemaining??'由後端查核'}</p><Button variant="primary" className="mt-6" disabled={busy} onClick={generate}>{busy?'提交中…':'同意並開始生成'}</Button></Modal></div></Container>
}
