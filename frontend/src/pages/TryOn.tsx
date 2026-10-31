import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { CheckCircle2, LoaderCircle, Sparkles } from 'lucide-react'
import { Button, ButtonLink, Container, Empty, Field, Modal, Notice, PageHeading, Panel, Select, Loading } from '../components/ui'
import { MemberPhotoPicker, type MemberPhoto } from '../components/MemberPhotoPicker'
import { useAuth } from '../lib/auth'
import { actionKey, apiBase, apiConfigured, ApiError, request, unwrap } from '../lib/api'
import { useBackend, usePrivateResource, useResource } from '../lib/hooks'
import { reconcileSelection, selectedPlan, selectionFromQuery, selectionQuery, useBelts, useKimonos, usePlans } from '../lib/catalogApi'
import { displayJob, isJobDone, isJobFailed, updateParticipant, type Belt, type Job, type Participant, type Plan } from '../lib/domain'
import { BookingReturn } from '../components/BookingReturn'
import { useBookingJourney } from '../lib/useBookingJourney'
import { sameSelection, saveJourney } from '../lib/bookingJourney'
import { BeltSelection, GarmentSelection, GroupSize } from './Plans'

type PhotoState = { consent:boolean; sessionId?:string; modelSessionId?:string; photoId?:string; modelId?:string; source:'PHOTO'|'MODEL'; error:string; job?:Job; sceneId?:string; sceneJobs?:Record<string,Job> }
const initialPhoto = ():PhotoState => ({consent:false,source:'PHOTO',error:''})
type Usage = { website?:{remaining:number}; websiteRemaining?:number }

export function TryOn() {
  const auth=useAuth();const[params,setParams]=useSearchParams();const plans=usePlans();const belts=useBelts();const kimonos=useKimonos();const backend=useBackend();const aiEnabled=backend.capabilities.aiGeneration
  const navigate=useNavigate();const {journey,owner,returnTo,onward}=useBookingJourney()
  const plan=selectedPlan(plans.data,params.get('plan'))
  const [people,setPeople]=useState<Participant[]>(plan?selectionFromQuery(plan,params):[])
  const peopleRef=useRef(people);peopleRef.current=people
  const memberRef=useRef(auth.user?.uid);memberRef.current=auth.user?.uid
  const [photos,setPhotos]=useState<Record<string,PhotoState>>({})
  const photoRef=useRef(photos);photoRef.current=photos
  const [message,setMessage]=useState('');const [confirm,setConfirm]=useState<{personId:string;kind:'TRY_ON'|'SCENE'}|null>(null)
  const generationKeys=useRef(new Map<string,{body:string;key:string}>())
  const [busy,setBusy]=useState(false)
  const [photoBusy,setPhotoBusy]=useState(false);const [photoValidating,setPhotoValidating]=useState(false);const [removePhotoId,setRemovePhotoId]=useState<string|null>(null)
  const usage=usePrivateResource<Usage>('/api/account/generation-usage',{})
  const models=useResource<{id:string;name:string;role:'FEMALE'|'MALE';previewUrl:string;warning?:string|null}[]>('/api/models',[],undefined,aiEnabled)
  const consent=useResource<{version:string;text:string}>('/api/try-on/consent',{version:'',text:''},undefined,aiEnabled)
  const memberPhotos=usePrivateResource<MemberPhoto[]>('/api/try-on/photos',[])
  const scenes=useResource<{id:string;name:string}[]>('/api/scenes',[],undefined,aiEnabled)
  useEffect(()=>{
    if(!plan)return
    const next=selectionFromQuery(plan,params)
    setPeople(journey?.draft.planId===plan.id?journey.draft.participants:next)
    setPhotos({});setBusy(false);setPhotoBusy(false);setPhotoValidating(false);setConfirm(null);setMessage('');setRemovePhotoId(null)
  },[plan?.id,auth.user?.uid])
  useEffect(()=>{if(plan&&!kimonos.loading&&!belts.loading&&!kimonos.error&&!belts.error)setPeople(p=>reconcileSelection(p,plan,kimonos.data,belts.data))},[plan,kimonos.data,belts.data,kimonos.loading,belts.loading,people])
  useEffect(()=>{
    for(const person of people){
      const photo=photos[person.id]??initialPhoto()
      if(photo.source==='MODEL'&&!models.loading&&!models.error){
        const choices=models.data.filter(m=>m.role===person.role)
        if(!choices.some(m=>m.id===photo.modelId)&&photo.modelId!==choices[0]?.id)
          setPhoto(person.id,{modelId:choices[0]?.id,modelSessionId:undefined})
      }else if(photo.source==='PHOTO'&&!memberPhotos.loading&&!memberPhotos.error&&auth.user){
        if(!memberPhotos.data.some(p=>p.photoId===photo.photoId)&&photo.photoId!==memberPhotos.data[0]?.photoId)
          setPhoto(person.id,{photoId:memberPhotos.data[0]?.photoId,sessionId:undefined})
      }
    }
  },[people,photos,models.data,models.loading,models.error,memberPhotos.data,memberPhotos.loading,memberPhotos.error,auth.user?.uid])
  useEffect(()=>{if(!auth.user)return;const timer=setInterval(memberPhotos.reload,60000);return()=>clearInterval(timer)},[auth.user?.uid])
  function setPhoto(id:string,patch:Partial<PhotoState>) {
    const current=photoRef.current[id]??initialPhoto()
    const changed=(['source','photoId','modelId'] as const).some(key=>key in patch&&patch[key]!==current[key])
    if(changed||'sceneId' in patch)setPeople(all=>updateParticipant(all,id,{generationId:undefined}))
    setPhotos(all=>{
      const current=all[id]??initialPhoto()
      return {...all,[id]:{...current,...(changed?{job:undefined,sceneJobs:{}}:{}),...patch,...('job' in patch&&patch.job?.jobId!==current.job?.jobId?{sceneJobs:{}}:{})}}
    })
  }
  function changeOutfit(id:string,patch:Partial<Participant>) {
    setPeople(all=>updateParticipant(all,id,{...patch,generationId:undefined}))
    setPhoto(id,{job:undefined,sessionId:undefined,modelSessionId:undefined})
  }
  async function upload(person:Participant,file:File,replaceId?:string) {
    const photo=photos[person.id]??initialPhoto()
    if(!plan||!aiEnabled||!auth.user||!photo.consent||photoBusy)return
    if(file.size>10*1024*1024){setPhoto(person.id,{error:'照片上限為 10 MB。'});return}
    if(!['image/jpeg','image/png','image/heic','image/heif'].includes(file.type)&&! /\.hei[cf]$/i.test(file.name)){setPhoto(person.id,{error:'請選 JPEG、PNG 或 HEIC 照片。'});return}
    const member=memberRef.current
    setPhotoBusy(true);setPhotoValidating(false);setPhoto(person.id,{error:''});setMessage('')
    try {
      const token=await auth.token()
      const contentType=file.type||(/\.heif$/i.test(file.name)?'image/heif':'image/heic')
      const session=unwrap(await request<{sessionId:string}>('/api/try-on/sessions',{method:'POST',token,body:{planId:plan.id,kimonoId:person.kimonoId||plan.kimonoId,source:'SELF',consentAccepted:true,consentVersion:consent.data.version}}))
      const url=unwrap(await request<{uploadUrl:string;photoId:string;transport?:string;fields?:Record<string,string>}>(`/api/try-on/sessions/${session.sessionId}/upload-url`,{method:'POST',token,body:{fileName:file.name,contentType,size:file.size,replacePhotoId:replaceId}}))
      const uploadBody=new FormData();for(const [key,value] of Object.entries(url.fields??{}))uploadBody.append(key,value);uploadBody.append('file',file)
      const isApi=url.transport==='API'
      if(isApi&&!url.uploadUrl.startsWith(apiBase+'/api/try-on/sessions/'))throw new Error('照片上傳位址不正確。')
      const response=await fetch(url.uploadUrl,isApi?{method:'PUT',headers:{Authorization:'Bearer '+token,'Content-Type':contentType},body:file}:{method:'POST',body:uploadBody})
      if(!response.ok)throw new Error('照片上傳失敗，原照片仍保留。')
      if(memberRef.current!==member)return
      setPhotoValidating(true)
      const validation=unwrap(await request<MemberPhoto>(`/api/try-on/sessions/${session.sessionId}/validate`,{method:'POST',token,body:{photoId:url.photoId}}))
      if(validation.status!=='READY')throw new Error(validation.issues?.map(i=>i.message).join('；')||'照片未通過驗證，原照片仍保留。')
      if(memberRef.current!==member)return
      memberPhotos.setData(all=>[validation,...all.filter(p=>p.photoId!==replaceId)])
      const affected=peopleRef.current.filter(p=>{
        const current=photoRef.current[p.id]
        return current?.source==='PHOTO'&&(current.photoId===replaceId||!replaceId&&p.id===person.id)
      })
      for(const target of affected)setPhoto(target.id,{photoId:validation.photoId,sessionId:undefined,error:''})
      memberPhotos.reload()
      setMessage(replaceId?'新照片已通過人物與身體範圍檢查並替換原照片。':'人物照片已通過人物與身體範圍檢查，可供各位旅客選用。')
    }catch(error){if(memberRef.current===member){setPhoto(person.id,{error:(error as Error).message});memberPhotos.reload()}}
    finally{if(memberRef.current===member){setPhotoBusy(false);setPhotoValidating(false)}}
  }
  async function deletePhoto() {
    if(!removePhotoId||photoBusy)return
    const member=memberRef.current;const photoId=removePhotoId
    setPhotoBusy(true)
    try{
      await request('/api/try-on/photos/'+photoId,{method:'DELETE',token:await auth.token()})
      if(memberRef.current!==member)return
      memberPhotos.setData(all=>all.filter(p=>p.photoId!==photoId))
      for(const person of peopleRef.current)if(photoRef.current[person.id]?.photoId===photoId)setPhoto(person.id,{photoId:undefined,sessionId:undefined})
      setRemovePhotoId(null);memberPhotos.reload();setMessage('人物照片已刪除，既有生成圖與收藏仍保留。')
    }catch(error){if(memberRef.current===member)setMessage((error as Error).message)}
    finally{if(memberRef.current===member)setPhotoBusy(false)}
  }
  function selectedResult(person:Participant) {
    const photo=photos[person.id]
    return displayJob(photo?.job,photo?.sceneJobs?.[photo.sceneId??''])
  }
  async function generateScene(person:Participant,photo:PhotoState) {
    if(!photo.job||!isJobDone(photo.job.status)||!photo.sceneId)throw new Error('請先完成試穿並選擇場景。')
    const member=memberRef.current;const sceneId=photo.sceneId;const parentId=photo.job.jobId
    const operationId=person.id+':SCENE';const body={sceneId,confirmed:true};const signature=JSON.stringify([parentId,body])
    const previous=generationKeys.current.get(operationId);const key=previous?.body===signature?previous.key:actionKey()
    generationKeys.current.set(operationId,{body:signature,key})
    const job=unwrap(await request<Job>('/api/try-on/jobs/'+parentId+'/scene-generations',{method:'POST',token:await auth.token(),key,body}))
    generationKeys.current.delete(operationId)
    if(memberRef.current!==member||photoRef.current[person.id]?.job?.jobId!==parentId)return
    setPhotos(all=>({...all,[person.id]:{...all[person.id],sceneJobs:{...all[person.id]?.sceneJobs,[sceneId]:job}}}))
    setConfirm(null);usage.reload()
    if(job.reused)setMessage('已重用相同試穿圖與場景的有效結果，未扣額度，也未延長保存期限。')
  }
  async function generate() {
    if(!aiEnabled||!confirm||!plan)return
    const person=people.find(p=>p.id===confirm.personId)!;const photo=photos[person.id]??initialPhoto()
    const member=memberRef.current
    setBusy(true);setMessage('')
    try {
      if(confirm.kind==='SCENE'){await generateScene(person,photo);return}
      if(!person.kimonoId)throw new Error('請先選擇這位旅客的和服。')
      if(!kimonos.data.find(k=>k.id===person.kimonoId)?.imageUrl)throw new Error('所選商品圖片尚未補齊，暫時無法生成試穿圖。')
      const token=await auth.token();let sessionId=photo.source==='MODEL'?photo.modelSessionId:photo.sessionId
      if(photo.source==='MODEL') {
        if(!photo.modelId)throw new Error('請選擇商店模特兒。')
        if(!sessionId){const session=unwrap(await request<{sessionId:string}>('/api/try-on/sessions',{method:'POST',token,body:{planId:plan.id,kimonoId:person.kimonoId,source:'MODEL',modelId:photo.modelId}}));sessionId=session.sessionId;setPhoto(person.id,{modelSessionId:sessionId})}
      } else {
        if(!photo.photoId)throw new Error('請先從照片庫選擇一張人物照片，或新增照片。')
        if(!sessionId){const session=unwrap(await request<{sessionId:string}>('/api/try-on/sessions',{method:'POST',token,body:{planId:plan.id,kimonoId:person.kimonoId,source:'SELF',photoId:photo.photoId}}));sessionId=session.sessionId;setPhoto(person.id,{sessionId})}
      }
      await request(`/api/try-on/sessions/${sessionId}`,{method:'PATCH',token,body:{planId:plan.id,kimonoId:person.kimonoId}})
      const path=`/api/try-on/sessions/${sessionId}/generations`
      const body={planId:plan.id,kimonoId:person.kimonoId,beltId:person.role==='FEMALE'?person.beltId:null,...(photo.source==='MODEL'?{modelId:photo.modelId}:{photoId:photo.photoId}),confirmed:true}
      const operationId=person.id+':'+confirm.kind;const signature=JSON.stringify(body);const previous=generationKeys.current.get(operationId);const key=previous?.body===signature?previous.key:actionKey();generationKeys.current.set(operationId,{body:signature,key})
      const job=unwrap(await request<Job>(path,{method:'POST',token,key,body}));generationKeys.current.delete(operationId)
      if(memberRef.current!==member)return
      const currentPerson=peopleRef.current.find(p=>p.id===person.id);const currentPhoto=photoRef.current[person.id]
      if(currentPerson?.kimonoId!==person.kimonoId||currentPerson?.beltId!==person.beltId||currentPhoto?.source!==photo.source
        ||currentPhoto?.photoId!==photo.photoId||currentPhoto?.modelId!==photo.modelId)return
      setPhoto(person.id,{job});setConfirm(null);usage.reload()
      if(job.reused)setMessage('已使用相同人物與搭配的既有試穿圖，本次未扣生成額度；保存期限維持不變。')
    }catch(error){
      if(error instanceof ApiError&&error.code==='IDEMPOTENCY_CONFLICT')generationKeys.current.delete(person.id+':'+confirm.kind)
      if(memberRef.current===member)setMessage((error as Error).message)
    }finally{if(memberRef.current===member)setBusy(false)}
  }
  const tracked=people.flatMap(person=>{
    const photo=photos[person.id]
    return [[person.id,'',photo?.job] as const,...Object.entries(photo?.sceneJobs??{}).map(([scene,job])=>[person.id,scene,job] as const)]
  }).filter((entry):entry is readonly [string,string,Job]=>!!entry[2])
  const activeJobs=tracked.filter(([, ,job])=>!isJobDone(job.status)&&!isJobFailed(job.status)).map(([, ,job])=>job.jobId).join(',')
  const trackedSignature=JSON.stringify(tracked.filter(([, ,job])=>!isJobFailed(job.status)).map(([id,scene,job])=>[id,scene,job.jobId,job.status]))
  useEffect(()=>{
    const jobs=JSON.parse(trackedSignature) as [string,string,string,string][]
    if(!jobs.length||!auth.user)return
    let stopped=false;let timer:ReturnType<typeof setTimeout>
    const poll=async()=>{
      try{const token=await auth.token();for(const [id,scene,jobId] of jobs){
        if(stopped)return
        const job=unwrap(await request<Job>('/api/try-on/jobs/'+jobId,{token}))
        if(stopped)return
        setPhotos(all=>{
          const current=all[id];if(!current)return all
          if(scene){if(current.sceneJobs?.[scene]?.jobId!==jobId)return all;return {...all,[id]:{...current,sceneJobs:{...current.sceneJobs,[scene]:job}}}}
          return current.job?.jobId===jobId?{...all,[id]:{...current,job}}:all
        })
      }}catch(error){if(!stopped)setMessage((error as Error).message)}
      if(!stopped)timer=setTimeout(poll,activeJobs?3000:60000)
    };timer=setTimeout(poll,activeJobs?1500:60000)
    return()=>{stopped=true;clearTimeout(timer)}
  },[trackedSignature,auth.user?.uid])
  function carrySelection(){if(!plan||!auth.user)return;try{sessionStorage.setItem('kinu:transfer:'+auth.user.uid,JSON.stringify({planId:plan.id,participants:people.map(person=>({...person,photoId:photos[person.id]?.photoId,generationId:selectedResult(person)?.generationId}))}))}catch{}}
  async function saveLook(){if(!plan||!backend.capabilities.looks)return;try{await request('/api/looks',{method:'POST',token:await auth.token(),key:actionKey(),body:{planId:plan.id,participants:people.map(person=>({id:person.id,role:person.role,kimonoId:person.kimonoId,beltId:person.beltId,generationId:selectedResult(person)?.generationId}))}});setMessage('造型已保存。');navigate(onward('/looks'))}catch(error){setMessage((error as Error).message)}}
  const selectionChanged=!!journey&&(!sameSelection(journey.draft,{planId:plan?.id??'',participants:people})||people.some(person=>selectedResult(person)?.generationId&&selectedResult(person)?.generationId!==journey.draft.participants.find(p=>p.id===person.id)?.generationId))
  function applyAndReturn(){
    if(!journey||!plan||!returnTo)return
    try{
      saveJourney(owner,{...journey,selection:{planId:plan.id,participants:people.map(person=>({...person,photoId:photos[person.id]?.photoId??person.photoId,generationId:selectedResult(person)?.generationId??person.generationId}))}})
      const target=new URL(returnTo,window.location.origin);target.searchParams.set('plan',plan.id);target.searchParams.set('applyLook','1');navigate(target.pathname+target.search)
    }catch{setMessage('無法保存搭配，請稍後再試。')}
  }
  if(plans.loading)return <Container><Loading/></Container>
  if(plans.error)return <Container><Notice tone="error">{plans.error}</Notice><Button onClick={plans.reload}>重試</Button></Container>
  if(!plan)return <Container><Empty>沒有可供試穿的方案，請先完成商品建檔。</Empty></Container>
  return <Container>
    <PageHeading eyebrow="AI STYLING · OPTIONAL" title="預覽，屬於你的造型" description="會員最多保存三張人物照片，各位旅客可分別選擇人物照片或商店模特兒。女生可加選腰帶；選擇來源不會自動生成。"/>
    {!auth.user&&<Notice>新增照片或生成前請先 <Link className="underline" to={'/login?returnTo='+encodeURIComponent('/try-on?'+params.toString())}>登入會員</Link>。可先預覽商店模特兒及商品。</Notice>}
    {!aiEnabled&&<Notice>AI 試穿服務尚未啟用，可先挑選和服與腰帶並查看商品圖片。</Notice>}
    {(kimonos.error||belts.error)&&<Notice tone="error">{kimonos.error||belts.error}</Notice>}
    <div className={people.length>1?'min-w-0':'mx-auto w-full min-w-0 max-w-[720px]'}>
      <div className="mb-8 w-full max-w-[360px]"><Field label="試穿方案"><Select value={plan.id} onChange={e=>setParams(p=>{const next=new URLSearchParams(p);next.set('plan',e.target.value);return next})}>
        {plans.data.map(p=><option key={p.id} value={p.id}>{p.name}{p.kind==='COUPLE'?'（雙人）':''}</option>)}
      </Select></Field></div>
      <div className="mb-6 max-w-[360px]"><GroupSize plan={plan} people={people} onChange={next=>{setPeople(next);setPhotos(all=>Object.fromEntries(Object.entries(all).filter(([id])=>next.some(p=>p.id===id))))}}/></div>
      <div className={`grid min-w-0 gap-6 ${people.length>1?'lg:grid-cols-2':''}`}>
        {people.map((person,index)=>{
          const photo=photos[person.id]??initialPhoto();const label=person.role==='FEMALE'?'女生':'男生'
          const sceneJob=photo.sceneJobs?.[photo.sceneId??''];const result=selectedResult(person)
          const image=result?.imageUrl??result?.resultUrl
          const suitableModels=plan.kind==='COUPLE'?models.data.filter(m=>m.role===person.role):models.data
          const selectedModel=suitableModels.find(m=>m.id===photo.modelId)
          return <Panel key={person.id} className="min-w-0">
            <div className="mb-6 flex items-center justify-between"><h2 className="font-serif text-2xl">旅客 {index+1} · {label}造型</h2><span className="text-[10px] tracking-wider text-muted">UNIFORM SIZE</span></div>
            <p className="mb-3 text-sm">人物來源</p>
            <div className="mb-5 flex flex-wrap gap-3">
              <Button disabled={photoBusy} onClick={()=>setPhoto(person.id,{source:'PHOTO',sessionId:undefined,error:''})} variant={photo.source==='PHOTO'?'primary':'secondary'}>人物照片</Button>
              <Button disabled={photoBusy} onClick={()=>setPhoto(person.id,{source:'MODEL',modelId:selectedModel?.id??suitableModels.find(m=>m.role===person.role)?.id,modelSessionId:undefined,error:''})} variant={photo.source==='MODEL'?'primary':'secondary'}>商店模特兒</Button>
            </div>
            {photo.source==='PHOTO'?<>
              {consent.data.text&&<p className="mb-4 text-xs leading-6 text-muted">{consent.data.text}</p>}
              {memberPhotos.error&&<Notice tone="error">{memberPhotos.error}<Button onClick={memberPhotos.reload}>重新載入照片</Button></Notice>}
              <MemberPhotoPicker photos={memberPhotos.data} selectedId={photo.photoId} label={label} loading={memberPhotos.loading}
                validating={photoValidating}
                busy={photoBusy} canUpload={!!auth.user&&aiEnabled&&!!consent.data.version} consent={photo.consent}
                onConsent={value=>setPhoto(person.id,{consent:value})}
                onSelect={selected=>setPhoto(person.id,{photoId:selected.photoId,sessionId:undefined,error:''})}
                onUpload={(file,replaceId)=>void upload(person,file,replaceId)} onDelete={setRemovePhotoId}/>
            </>:<div className="mb-6 w-full max-w-[400px]">
              <Field label={plan.kind==='COUPLE'?label+'模特兒':'商店模特兒（女生／男生）'}><Select value={selectedModel?.id??''} disabled={models.loading||!suitableModels.length}
                onChange={e=>{const model=models.data.find(m=>m.id===e.target.value);if(model&&model.role!==person.role)changeOutfit(person.id,{role:model.role,kimonoId:'',beltId:null});setPhoto(person.id,{modelId:e.target.value,modelSessionId:undefined,sessionId:undefined,error:''})}}>
                {!suitableModels.length&&<option value="">{models.loading?'讀取模特兒…':'尚無適用模特兒'}</option>}
                {suitableModels.map(m=><option key={m.id} value={m.id}>{m.name}</option>)}
              </Select></Field>
              {selectedModel&&<figure className="mt-4"><img src={selectedModel.previewUrl} alt={label+'模特兒預覽：'+selectedModel.name} className="block h-auto max-h-[360px] w-auto max-w-full object-contain"/>
                {selectedModel.warning&&<figcaption className="mt-2 text-xs leading-6 text-muted">{selectedModel.warning}</figcaption>}
              </figure>}
              {models.error&&<Notice tone="error">{models.error}</Notice>}
            </div>}
            <div className="mt-6 w-full max-w-[400px] space-y-5">
              <GarmentSelection participant={person} kimonos={kimonos.data} roleLocked={plan.kind==='COUPLE'&&people.indexOf(person)<2} onChange={patch=>changeOutfit(person.id,patch)}/>
              <BeltSelection participant={person} plan={plan} belts={belts.data} onChange={beltId=>changeOutfit(person.id,{beltId})}/>
              <Field label="場景"><Select value={photo.sceneId??''} disabled={busy} onChange={e=>setPhoto(person.id,{sceneId:e.target.value})}>
                <option value="">不變更</option>{scenes.data.map(scene=><option key={scene.id} value={scene.id}>{scene.name}</option>)}
              </Select></Field>
              {scenes.error&&<Notice tone="error">{scenes.error}</Notice>}
              {photo.sceneId&&<><p className="text-xs leading-6 text-muted">先完成試穿，再確認場景生成；每次新生成另用 1 次額度。盡量保留人物與服裝，AI 仍可能改變細節。</p>
                <Button disabled={!aiEnabled||!auth.user||busy||photoBusy||!!activeJobs||!photo.job||!isJobDone(photo.job.status)||!photo.job.imageUrl||!!sceneJob&&isJobDone(sceneJob.status)}
                  onClick={()=>setConfirm({personId:person.id,kind:'SCENE'})}>{sceneJob&&isJobDone(sceneJob.status)?'場景圖已完成':'確認場景生成'}</Button>
                {sceneJob&&!isJobDone(sceneJob.status)&&<Notice>{isJobFailed(sceneJob.status)?(sceneJob.failure?.message??'場景生成未成功，原始試穿圖仍保留，可重新確認場景生成。'):'場景生成中，原始試穿圖仍可查看。'}</Notice>}
              </>}

            </div>
            {photo.error&&<Notice tone="error"><span className="text-red-700">{photo.error}</span></Notice>}
            <Button variant="primary" className="mt-6 max-w-full" disabled={!aiEnabled||!auth.user||busy||photoBusy||!!activeJobs||!!photo.job&&isJobDone(photo.job.status)||!kimonos.data.find(k=>k.id===person.kimonoId)?.imageUrl||(photo.source==='MODEL'?!selectedModel:!photo.photoId)}
              onClick={()=>setConfirm({personId:person.id,kind:'TRY_ON'})}><Sparkles size={16}/>{photo.job&&isJobDone(photo.job.status)?label+'試穿圖已完成':'確認'+label+'試穿'}</Button>
            {photo.job&&<div className="mt-6 border-t border-line pt-6" role="status">
              {isJobDone(result?.status??'')&&image?<><img src={image} alt={label+(result?.kind==='SCENE'?' AI 場景結果':' AI 試穿結果')} className="max-h-96 w-full object-contain"/><p className="mt-3 flex items-center gap-2 text-xs text-forest"><CheckCircle2 size={14}/>{result?.kind==='SCENE'?'場景生成完成':'試穿生成完成'} · 圖片保存期限以後端為準</p></>
                :isJobFailed(photo.job.status)?<Notice tone="error">{photo.job.failure?.message??'生成未成功，請確認原因後重新提交。'}</Notice>
                :<p className="flex items-center gap-3 text-sm"><LoaderCircle className="animate-spin" size={16}/>生成處理中，請勿重複提交。</p>}
            </div>}
          </Panel>
        })}
      </div>
      {message&&<Notice>{message}</Notice>}
      <div className="mt-8 flex max-w-full flex-wrap gap-3 [&>a]:max-w-full [&>button]:max-w-full">
        {journey?<><BookingReturn to={returnTo}/>{selectionChanged&&<Button style={{borderRadius:0}} variant="primary" disabled={people.some(p=>!p.kimonoId)} onClick={applyAndReturn}>套用搭配並返回預約</Button>}</>
          :<ButtonLink primary onClick={carrySelection} to={'/booking?'+new URLSearchParams([...selectionQuery(plan,people),['from','tryon']])}>跳過或帶入搭配，直接預約</ButtonLink>}
        <Button disabled={!auth.user||!backend.capabilities.looks} onClick={saveLook}>加入造型收藏</Button><ButtonLink to={onward('/account/generations')}>我的生成圖</ButtonLink>
      </div>
      <p className="mt-5 text-xs leading-7 text-muted">每位會員每天可在網站生成 5 次 AI 圖片（試穿與場景共用），於日本午夜重設。生成圖保存 7 天，到期不影響收藏搭配。加選腰帶時使用該和服與腰帶的預製合成素材。相同人物與搭配若已有有效生成圖，直接顯示既有結果，不扣額度、不延長保存期限；生成結果不會作為人物來源。人物照片、生成圖與收藏可分別刪除。</p>
      <Modal title={confirm?.kind==='SCENE'?'確認場景生成':'確認本次試穿'} open={!!confirm} onClose={()=>!busy&&setConfirm(null)}>
        <p className="text-sm leading-8">{confirm?.kind==='SCENE'?'將以這位旅客的原始試穿圖變換所選背景，並傳送至 Google 處理。相同試穿圖與場景已有有效結果時直接重用；否則另用 1 次網站生成額度。場景失敗不影響原始試穿圖。':'將先查詢這位旅客相同人物來源、和服與腰帶搭配的有效試穿圖；有符合圖片時直接使用，不扣額度。沒有符合圖片時才建立新任務，使用 1 次網站生成額度。'}</p>
        <p className="mt-3 text-sm text-muted">剩餘額度：{usage.data.website?.remaining??usage.data.websiteRemaining??'由後端查核'}</p>
        <Button variant="primary" className="mt-6" disabled={busy} onClick={generate}>{busy?'提交中…':confirm?.kind==='SCENE'?'確認場景生成':'確認試穿'}</Button>
      </Modal>
      <Modal title="刪除這張人物照片？" open={!!removePhotoId} onClose={()=>!photoBusy&&setRemovePhotoId(null)}>
        <p className="text-sm leading-8">刪除後，各位旅客都無法再以這張照片生成或重用試穿結果；既有生成圖與收藏仍保留。</p>
        <Button className="mt-5" disabled={photoBusy} onClick={()=>void deletePhoto()}>{photoBusy?'刪除中…':'確認刪除人物照片'}</Button>
      </Modal>
    </div>
  </Container>
}
