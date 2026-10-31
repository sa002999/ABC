import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ArrowRight, Heart } from 'lucide-react'
import { Button, ButtonLink, Container, Empty, Eyebrow, Field, Loading, Notice, PageHeading, Panel, Select, ServiceNotice, inputClass } from '../components/ui'
import { cities } from '../data/catalog'
import { useBackend } from '../lib/hooks'
import { allowedBelts, reconcileSelection, selectionQuery, useBelts, useKimonos, usePlan, usePlans } from '../lib/catalogApi'
import { apiConfigured, actionKey, request } from '../lib/api'
import { useAuth } from '../lib/auth'
import { estimatePrice, money, participantsFor, resizeParticipants, planCities, updateParticipant, type Belt, type Kimono, type Participant, type Plan } from '../lib/domain'

export function PlanCard({ plan, query = '' }: { plan: Plan; query?: string }) {
  return <article className="group min-w-0 overflow-hidden border border-line bg-paper"><Link to={'/plans/'+plan.id+'?from=catalog'+query} className="block"><div className="relative overflow-hidden"><img src={plan.image} alt={plan.name+'和服風格參考'} loading="lazy" className="aspect-[4/4.5] w-full object-cover transition-transform duration-500 group-hover:scale-[1.03]"/><span className="absolute top-3 left-3 bg-paper/90 px-2.5 py-1.5 text-[9px] tracking-wider">{plan.kind==='GROUP'?'團體 2～3 人':plan.kind==='COUPLE'?'情侶兩人':'單人方案'} · 統一尺寸</span></div><div className="p-5"><Eyebrow>{planCities(plan).map(city=>cities[city]??city).join('／')}</Eyebrow><h3 className="mt-3 font-serif text-lg leading-relaxed">{plan.name}</h3><div className="mt-4 flex items-center justify-between border-t border-line pt-4"><span className="font-display text-lg">{money(plan.price)}{plan.kind==='GROUP'&&<span className="font-sans text-xs">／人</span>} <small className="font-sans text-[9px] text-muted">{!apiConfigured?'示例價':'含稅・示範價'}</small></span><ArrowRight size={17} strokeWidth={1}/></div></div></Link></article>
}

export function Plans() {
  const [params,setParams]=useSearchParams()
  const city=params.get('city')??'';const party=params.get('party')??'';const keyword=params.get('keyword')??''
  const resource=usePlans('/api/plans?'+params.toString())
  const [sort,setSort]=useState('default')
  const filtered=resource.data.filter(p=>(!city||planCities(p).includes(city))&&(!keyword||p.name.includes(keyword))&&(party==='couple'?p.kind==='COUPLE':party==='solo'?p.kind==='SINGLE':party==='group'?p.kind==='GROUP':true)).sort((a,b)=>sort==='low'?a.price-b.price:sort==='high'?b.price-a.price:0)
  function filter(key:string,value:string) { setParams(old=>{const next=new URLSearchParams(old);value?next.set(key,value):next.delete(key);return next}) }
  return <Container><PageHeading eyebrow="FIND YOUR EXPERIENCE" title="探索和服方案" description="一座城市，一套和服，一段屬於你的旅程。所有和服統一尺寸；女生可選腰帶，男生無配件。"/><ServiceNotice/><div className="grid gap-8 lg:grid-cols-[210px_1fr]"><aside className="space-y-6"><Field label="旅遊城市"><Select value={city} onChange={e=>filter('city',e.target.value)}><option value="">所有城市</option>{Object.entries(cities).map(([v,l])=><option key={v} value={v}>{l}</option>)}</Select></Field><Field label="同行對象"><Select value={party} onChange={e=>filter('party',e.target.value)}><option value="">所有方案</option><option value="solo">單人</option><option value="couple">情侶（兩人）</option><option value="group">團體（2～3 人）</option></Select></Field><Field label="搜尋方案"><input value={keyword} onChange={e=>filter('keyword',e.target.value)} className={inputClass.replace('rounded-sm', 'rounded-none')} placeholder="輸入方案名稱"/></Field><button onClick={()=>setParams({})} className="min-h-11 text-xs underline underline-offset-4">清除篩選條件</button><div className="border-t border-line pt-5 text-xs leading-7 text-muted">和服比較從收藏中選 2～3 個造型。外拍比較可公開瀏覽。</div><Link to="/photography" className="block text-xs underline">查看外拍比較 →</Link></aside><section><div className="mb-6 flex items-center justify-between gap-4"><p className="text-xs text-muted">{filtered.length} 個方案</p><Select aria-label="方案排序" className="max-w-40" value={sort} onChange={e=>setSort(e.target.value)}><option value="default">預設排序</option><option value="low">價格由低至高</option><option value="high">價格由高至低</option></Select></div>{resource.loading?<Loading/>:resource.error?<Notice tone="error">{resource.error}<button onClick={resource.reload} className="ml-3 underline">重試</button></Notice>:filtered.length?<div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">{filtered.map(p=><PlanCard key={p.id} plan={p} query={city?'&city='+encodeURIComponent(city):''}/>)}</div>:<Empty>沒有符合條件的方案，請調整篩選。</Empty>}</section></div></Container>
}

export function GarmentSelection({ participant, kimonos, onChange, roleLocked = false }: { participant: Participant; kimonos: Kimono[]; onChange: (patch: Partial<Participant>) => void; roleLocked?: boolean }) {
  const selected = kimonos.find(k=>k.id===participant.kimonoId)
  return <div className="space-y-5">{!roleLocked&&<Field label="和服角色"><Select value={participant.role} onChange={e=>onChange({role:e.target.value as 'FEMALE'|'MALE',kimonoId:'',beltId:null})}><option value="FEMALE">女生和服</option><option value="MALE">男生和服</option></Select></Field>}<Field label="和服（統一尺寸）"><Select value={participant.kimonoId} onChange={e=>onChange({kimonoId:e.target.value})}><option value="">選擇和服款式</option>{kimonos.filter(k=>k.gender===participant.role).map(k=><option key={k.id} value={k.id}>{k.name}</option>)}</Select></Field>{selected&&(selected.imageUrl?<img src={selected.imageUrl} alt={selected.name+'商品圖片'} loading="lazy" className="aspect-[4/5] w-full max-w-[280px] object-contain"/>:<p className="text-xs text-muted">{selected.name}的商品圖片待補。</p>)}</div>
}

export function BeltSelection({ participant, onChange, belts, plan }: { participant: Participant; onChange: (id: string | null) => void; belts: Belt[]; plan?: Plan }) {
  const options=plan?allowedBelts(plan,belts):belts
  const selected=options.find(b=>b.id===participant.beltId)
  return participant.role==='FEMALE'?<div className="space-y-5"><Field label="腰帶（女生選用）"><Select aria-label="腰帶（女生選用）" value={participant.beltId??''} onChange={e=>onChange(e.target.value||null)}><option value="">不加選腰帶</option>{options.filter(b=>b.category==='BELT').map(b=><option key={b.id} value={b.id}>{b.name} · {plan?.includedBeltIds?.includes(b.id)?'方案已含':'+'+money(b.price)}</option>)}</Select></Field>{selected&&(selected.imageUrl?<img src={selected.imageUrl} alt={selected.name+'商品圖片'} loading="lazy" className="aspect-[4/3] w-full max-w-[280px] object-contain"/>:<p className="text-xs text-muted">{selected.name}的商品圖片待補。</p>)}</div>:<p className="border border-line/60 px-4 py-3 text-sm text-muted">男生無可選配件，額外配件費為 0。</p>
}

export function PlanDetail() {
  const {planId}=useParams();const [params]=useSearchParams();const navigate=useNavigate();const auth=useAuth()
  const resource=usePlan(planId)
  const belts=useBelts();const kimonos=useKimonos();const backend=useBackend()
  const plan=resource.data
  const [people,setPeople]=useState<Participant[]>(plan?participantsFor(plan):[])
  const [status,setStatus]=useState('');const [busy,setBusy]=useState(false)
  useEffect(()=>{setPeople(plan?participantsFor(plan):[])},[plan?.id])
  useEffect(()=>{if(plan&&!kimonos.loading&&!belts.loading&&!kimonos.error&&!belts.error)setPeople(p=>reconcileSelection(p,plan,kimonos.data,belts.data))},[plan,kimonos.data,belts.data,kimonos.loading,belts.loading])
  async function save() {
    if(!backend.capabilities.looks)return
    if(!auth.user){navigate('/login?returnTo='+encodeURIComponent(location.pathname));return}
    setBusy(true);setStatus('')
    try{await request('/api/looks',{method:'POST',token:await auth.token(),key:actionKey(),body:{planId:plan!.id,participants:people}});setStatus('已保存到你的造型收藏。')}catch(e){setStatus((e as Error).message)}finally{setBusy(false)}
  }
  if(resource.loading)return <Container><Loading/></Container>
  if(resource.error)return <Container><Notice tone="error">{resource.error}</Notice></Container>
  if(!plan)return <Container><PageHeading eyebrow="PLAN NOT FOUND" title="找不到這個方案"/><ButtonLink to="/plans">返回探索</ButtonLink></Container>
  if(!people.length)return <Container><Loading/></Container>
  const selection=selectionQuery(plan,people);const city=params.get('city');if(city&&planCities(plan).includes(city))selection.set('city',city);const query=selection.toString()
  return <Container><div className="mb-8 flex gap-3 text-xs text-muted"><Link to="/plans">探索方案</Link><span>/</span><span>{plan.name}</span></div><ServiceNotice/>{(kimonos.error||belts.error)&&<Notice tone="error">{kimonos.error||belts.error}</Notice>}<div className="grid gap-10 lg:grid-cols-2"><div><img src={plan.image} alt={plan.name} className="aspect-[4/5] w-full object-cover"/><p className="mt-3 text-[10px] leading-6 text-muted">風格參考圖；非即時生成結果。圖中其他裝飾不提供加購。</p></div><div><Eyebrow>{planCities(plan).map(city=>cities[city]??city).join('／')} · {plan.kind==='GROUP'?'FOR YOUR GROUP':plan.kind==='COUPLE'?'FOR TWO':'FOR YOU'}</Eyebrow><h1 className="mt-5 font-serif text-3xl leading-relaxed md:text-4xl">{plan.name}</h1><p className="mt-6 text-sm leading-8 text-muted">{plan.description}</p><p className="mt-7 font-display text-3xl">{money(plan.price)} <span className="font-sans text-xs text-muted">{!apiConfigured?'示例價':plan.kind==='COUPLE'?'／兩人':'／人'}</span></p><div className="mt-7 border-y border-line py-5 text-sm leading-8"><p>和服：統一尺寸，不需選擇尺寸</p><p>人數：{plan.kind==='GROUP'?'兩至三名旅客，每人計價':plan.kind==='COUPLE'?'兩名旅客，一男一女':'一名旅客'}</p><p>{plan.includedServices?.join('、')??'包含服務以方案資料為準'}；歸還時間依所選門市</p></div><div className="mt-7 space-y-6"><GroupSize plan={plan} people={people} onChange={setPeople}/>{people.map((person,index)=><div key={person.id}><h2 className="mb-3 font-serif text-lg">旅客 {index+1} · {person.role==='FEMALE'?'女生搭配':'男生搭配'}</h2><GarmentSelection participant={person} kimonos={kimonos.data} roleLocked={plan.kind==='COUPLE'} onChange={patch=>setPeople(p=>updateParticipant(p,person.id,patch))}/><BeltSelection participant={person} plan={plan} belts={belts.data} onChange={beltId=>setPeople(p=>updateParticipant(p,person.id,{beltId}))}/></div>)}</div>{plan.kind==='COUPLE'&&<Notice>AI 試穿頁有「上傳女生照片」與「上傳男生照片」兩個獨立位置。可以不使用 AI，直接預約。</Notice>}<div className="mt-8 flex justify-between border-t border-line pt-6 text-sm"><span>{!apiConfigured?'示例搭配總價':'搭配小計'}</span><strong>{money(estimatePrice(plan,people,belts.data,false))}</strong></div><p className="mt-2 text-xs text-muted">付款前由後端重新確認價格、庫存與名額。選擇與收藏不保留商品。</p><div className="mt-6 flex flex-wrap gap-3"><ButtonLink primary to={'/booking?'+query}>立即預約</ButtonLink><ButtonLink to={'/try-on?'+query}>AI 試穿</ButtonLink><Button disabled={busy||!backend.capabilities.looks} onClick={save}><Heart size={16}/>收藏</Button></div>{status&&<Notice>{status}</Notice>}<div className="mt-8 border-t border-line pt-5"><Link to="/photography" className="text-sm underline underline-offset-4">比較外拍服務 →</Link></div></div></div></Container>
}

export function GroupSize({plan,people,onChange}:{plan:Plan;people:Participant[];onChange:(people:Participant[])=>void}) {
  return plan.kind==='GROUP'?<Field label="團體旅客人數"><Select value={people.length} onChange={e=>onChange(resizeParticipants(people,Number(e.target.value)))}><option value={2}>2 位成人</option><option value={3}>3 位成人</option></Select></Field>:null
}
