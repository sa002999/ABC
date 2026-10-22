import { useContext, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { Button, ButtonLink, Container, Eyebrow } from '../components/ui'
import { faq } from '../data/catalog'
import { apiConfigured } from '../lib/api'
import { usePlans } from '../lib/catalogApi'
import { planCities } from '../lib/domain'
import { PlanCard } from './Plans'
import { JourneyClosing } from '../components/JourneyClosing'

import { HomeLanguageContext } from '../components/Layout'
import '../home-hero.css'
export function Home() {
  return <>
    <Hero />
    <JourneyFinder />
    <section id="guide" className="border-y border-line bg-wash/55"><Container><Eyebrow>HOW IT WORKS</Eyebrow><h2 className="mt-5 font-serif text-3xl leading-relaxed md:text-[42px]">第一次穿和服，也可以很從容</h2><div className="mt-10 grid gap-8 md:grid-cols-3">{[['01','選擇方案','依城市、同行者與風格，查看方案內容及價格。'],['02','預約付款','登入後選門市、日期、人數與逐人搭配，確認整筆總價後付款。'],['03','到店體驗','前往指定門市，完成報到與著裝，再展開散策。']].map(([n,title,text]) => <article key={n} className="border-t border-line pt-6"><span className="font-display text-4xl italic text-vermilion/70">{n}</span><h3 className="mt-4 font-serif text-xl">{title}</h3><p className="mt-3 text-sm leading-8 text-muted">{text}</p></article>)}</div><p className="mt-8 text-xs text-muted">AI 造型預覽、收藏比較皆為選用。不使用，也能直接預約。</p></Container></section>
    <section id="ai" className="grid min-h-[790px] overflow-hidden bg-[#365449] text-paper min-[961px]:grid-cols-[1.08fr_.92fr]">
      <div className="relative min-h-[560px] min-w-0 overflow-hidden bg-[#253e36] min-[721px]:min-h-[720px] min-[961px]:min-h-0">
        <span className="absolute top-[9%] right-[6%] z-10 rotate-3 bg-paper px-6 py-5 font-display text-[10px] leading-[1.8] tracking-[.17em] text-[#202522] max-[720px]:top-[5%] max-[720px]:right-[3%] max-[720px]:p-[13px]">YOUR PHOTO<br/>YOUR COLORS<br/>YOUR JOURNEY</span>
        <img src="/assets/kimono-red.jpg" alt="紅色和服造型參考，非本次生成結果" loading="lazy" className="absolute top-[10%] left-[10%] h-[70%] w-[57%] -rotate-3 object-cover shadow-[0_25px_55px_rgba(0,0,0,.25)] max-[720px]:top-[8%] max-[720px]:left-[4%] max-[720px]:w-[69%]"/>
        <img src="/assets/kimono-umbrellas.jpg" alt="和服與和傘風格參考" loading="lazy" className="absolute right-[5%] bottom-[8%] h-[50%] w-[42%] rotate-4 border-[10px] border-paper object-cover shadow-[0_25px_55px_rgba(0,0,0,.25)] max-[720px]:right-[1%] max-[720px]:h-[44%] max-[720px]:w-[47%]"/>
        <span aria-hidden="true" className="absolute bottom-[7%] left-[7%] z-10 border-2 border-[#cb746d] px-[7px] py-[9px] font-serif text-[23px] leading-[1.1] font-semibold text-[#cb746d]">試<br/>着</span>
        <small className="absolute bottom-[2%] left-[7%] z-10 text-[11px] leading-[1.7] text-paper/65">預製展示圖 · 非本次生成結果</small>
      </div>
      <div className="flex min-w-0 flex-col justify-center px-5 py-20 md:px-10 md:py-28">
        <div className="border-b border-paper/30 pb-5 [&>p]:text-paper"><Eyebrow>AI STYLING · OPTIONAL</Eyebrow></div>
        <p className="mt-[60px] text-[10px] tracking-[.24em] text-paper/75">SEE IT BEFORE YOU WEAR IT</p>
        <h2 className="mt-5 font-serif text-[42px] leading-[1.5]">先遇見，<br/>適合你的和服造型</h2>
        <p className="mt-7 max-w-md text-sm leading-8 text-paper/75">使用模特兒，或上傳照片，預覽自己的和服造型。女生可選腰帶，男生無配件；情侶方案提供兩個獨立照片位置。</p>
        <p className="mt-3 text-sm leading-8 text-paper/75">喜歡的造型可收藏，也可直接預約。登入並確認後，才開始生成。</p>
        <div className="mt-8 flex flex-wrap gap-3">
          <Link to="/try-on" className="inline-flex min-h-[46px] items-center justify-center gap-2 border border-[#9d5448] bg-[#9d5448] px-[22px] py-[11px] text-[13px] tracking-[.1em] text-white transition-colors hover:border-vermilion hover:bg-vermilion focus-visible:outline-paper">開始 AI 和服試穿 <ArrowRight size={15}/></Link>
          <Link to="/booking" className="inline-flex min-h-[46px] items-center justify-center border border-paper/75 px-[22px] py-[11px] text-[13px] tracking-[.1em] text-paper transition-colors hover:bg-paper/8 focus-visible:outline-paper">直接預約</Link>
        </div>
        <p className="mt-[50px] max-w-[470px] border-t border-paper/23 pt-[15px] text-[11px] leading-6 text-paper/52">AI 圖像僅供款式與配色參考，不保證實際合身度。</p>
      </div>
    </section>
    <section id="inspiration" className="bg-wash/65"><Container><div className="border-b border-[#202522]/22 pb-5"><Eyebrow>STYLE INSPIRATION</Eyebrow></div><div className="mt-5 flex flex-wrap justify-between gap-5"><h2 className="font-serif text-3xl md:text-[42px]">和服風格靈感</h2><p className="max-w-sm text-xs leading-7 text-muted">從喜歡的畫面，找到相近的和服方案。圖片為風格參考，非顧客評價或旅客實拍紀錄。</p></div><div className="mt-10 grid gap-6 md:grid-cols-[1fr_1.3fr_.9fr] max-[720px]:-mr-5 max-[720px]:flex max-[720px]:snap-x max-[720px]:snap-mandatory max-[720px]:gap-3 max-[720px]:overflow-x-auto max-[720px]:pr-5">{[['kimono-shrine.jpg','ASAKUSA COUPLE','東京・情侶體驗','couple'],['kimono-couple.jpg','GION WALK','京都・午後散策','solo'],['kimono-portrait.jpg','SOFT BOTANICAL','京都・清新造型','solo']].map(([image,title,desc,party],i) => <Link to={'/plans?party='+party} key={title} className={`max-[720px]:basis-[78vw] max-[720px]:shrink-0 max-[720px]:snap-center ${i===1?'md:pt-14':''}`}><div className="relative overflow-hidden"><img src={'/assets/'+image} alt={desc+'風格參考'} className="h-80 w-full object-cover transition-transform duration-500 hover:scale-105 md:h-[420px] max-[720px]:h-[470px]" loading="lazy"/><div className="absolute inset-x-0 bottom-0 bg-linear-to-t from-black/55 to-transparent p-5 pt-16 text-white"><span className="font-display text-sm tracking-[.1em]">{title}</span><small className="mt-2 block text-[10px] tracking-wider">{desc}</small></div></div><span className="mt-4 block text-xs">查看相近方案 →</span></Link>)}</div></Container></section>
    <Container className="grid gap-10 md:grid-cols-[.8fr_1.2fr]"><div><Eyebrow>BEFORE YOUR JOURNEY</Eyebrow><h2 className="mt-5 font-serif text-3xl leading-relaxed md:text-[42px]">出發前，<br/>你可能想知道</h2><p className="mt-5 text-sm text-muted">先回答常見疑問，再安心安排體驗。</p><Link to="/faq" className="mt-6 inline-block text-xs underline underline-offset-8">查看全部常見問題 →</Link></div><div>{faq.map(([q,a]) => <details key={q} className="group border-b border-line py-5"><summary className="flex min-h-7 list-none items-center justify-between gap-5 text-sm">{q}<span className="text-lg text-muted group-open:rotate-45" aria-hidden="true">+</span></summary><p className="mt-4 text-sm leading-8 text-muted">{a}</p></details>)}</div></Container>
    <JourneyClosing />
  </>
}

function Hero() {
  const language = useContext(HomeLanguageContext)
  const english = language === 'en'
  return <div className="v75-home">
    <section id="top" className="hero" data-testid="hero" aria-labelledby="hero-title">
      <div className="paper-grain" aria-hidden="true" />
      <div className="hero-note" aria-hidden="true"><span>WEAR</span><span>WANDER</span><span>REMEMBER</span></div>
      <img className="sakura-art" src="/assets/sakura-watercolor.png" alt="" aria-hidden="true" />
      <figure className="hero-photo hero-photo-top">
        <picture><source media="(max-width:720px)" srcSet="/assets/kimono-friends-brush-mobile.png" /><img src="/assets/kimono-friends-brush-desktop.png" alt="兩位穿著和服的旅客走在綠意與朱紅欄杆之間" /></picture>
        <figcaption>KYOTO · 35.0116° N</figcaption>
      </figure>
      <img className="temple-eave" src="/assets/temple-eave-painted.png" alt="" aria-hidden="true" />
      <div className="hero-city" aria-hidden="true"><b>浅草</b><span>ASAKUSA</span><i /></div>
      <div className="hero-center">
        <div className="sun-disc" aria-hidden="true" />
        <p className="eyebrow">KIMONO · TRAVEL · MEMORY</p>
        <h1 id="hero-title"><img src="/assets/kinu-tabi-brush-wordmark.png" alt="KINU TABI" /></h1>
        <p className="hero-tagline">{english ? 'Wear a journey that is uniquely yours' : '穿上一段屬於你的日本旅程'}</p>
        <p className="hero-description">{english ? 'Kimono rental, AI styling preview and store booking in Tokyo and Kyoto' : '東京・京都和服租借｜AI 造型預覽｜門市預約'}</p>
        <div className="hero-actions"><Link className="button button-primary" to="/plans">{english ? 'Explore experiences' : '探索和服方案'}</Link><Link className="button button-ghost" to="/try-on">{english ? 'Preview my AI look' : 'AI 預覽我的造型'}</Link></div>
      </div>
      <div className="hero-photo-pair" aria-label="和服風格參考照片">
        <figure className="hero-photo hero-photo-bottom-left"><picture><source media="(max-width:720px)" srcSet="/assets/kimono-couple-brush-mobile.png" /><img src="/assets/kimono-couple.jpg" alt="一對穿著和服的旅客走在京都石板坡道上" /></picture><figcaption>TOGETHER IN KYOTO</figcaption></figure>
        <figure className="hero-photo hero-photo-bottom-right"><picture><source media="(max-width:720px)" srcSet="/assets/kimono-portrait-brush-mobile.png" /><img src="/assets/kimono-portrait.jpg" alt="穿著綠色花卉和服的人像" /></picture><figcaption>FIND YOUR COLORS</figcaption></figure>
      </div>
      <a className="scroll-cue" href="#plans" aria-label="向下探索"><span>SCROLL TO EXPLORE</span><i aria-hidden="true" /></a>
    </section>
  </div>
}

function JourneyFinder() {
  const [choices,setChoices] = useState({ city:'', party:'', purpose:'' })
  const [shown,setShown] = useState(false)
  const plans=usePlans()
  const groups = [{ key:'city',title:'旅遊城市',hint:'這次想去哪裡？',options:[['tokyo','東京・淺草'],['kyoto','京都・祇園']] },{key:'party',title:'同行對象',hint:'和誰一起體驗？',options:[['solo','一個人'],['couple','情侶'],['family','朋友／家人']]},{key:'purpose',title:'使用此服務的目的',hint:'這次想留下什麼樣的回憶？',options:[['walk','觀光／城市散策'],['photo','旅拍／紀念攝影'],['ceremony','婚禮出席／正式儀式'],['tea','茶道／藝文體驗'],['meeting','兩家人會面']]}]
  const selectedLabels = groups.map(group => group.options.find(([value]) => value === choices[group.key as keyof typeof choices])?.[1]).filter((label): label is string => Boolean(label))
  const selectedCount = Object.values(choices).filter(Boolean).length
  const progressText = selectedCount === 0 ? '選好三個條件，找到適合這趟旅程的方案。' : selectedCount === 3 ? '三個條件已選好，可以查看推薦方案。' : `已選 ${selectedCount}／3 個條件，請繼續選擇。`
  const matched=plans.data.filter(p => (!choices.city || planCities(p).includes(choices.city)) && (choices.party==='couple' ? p.kind==='COUPLE' : !choices.party || p.kind==='SINGLE'))
  return <section id="plans" className="bg-[#eee8dc]"><Container><div className="flex flex-col justify-between gap-6 md:flex-row md:items-end"><div><Eyebrow>FIND YOUR JOURNEY</Eyebrow><h2 className="mt-5 font-serif text-[42px] leading-[1.4]">不知道怎麼選？<br/>從你的旅程開始</h2></div><p className="max-w-md text-sm leading-8 text-muted">告訴我們地點、同行者與使用目的，<br className="hidden md:block"/>從和服體驗中，整理出適合你的選擇。</p></div><form className="mt-10" onSubmit={e=>{e.preventDefault();setShown(true)}}><div className="grid gap-0 border-y border-line md:grid-cols-[.8fr_.8fr_1.5fr]">{groups.map((g,i)=><fieldset key={g.key} className="border-b border-line py-7 last:border-0 md:border-r md:border-b-0 md:px-6 md:first:pl-0 md:last:pr-0"><legend className="sr-only">{g.title}</legend><p className="text-xs tracking-wider"><span className="mr-3 text-vermilion">0{i+1}</span>{g.title}</p><p className="mt-3 font-serif text-lg">{g.hint}</p><div className="mt-5 flex flex-wrap gap-2">{g.options.map(([value,label])=><label key={value} className="relative cursor-pointer"><input className="peer sr-only" type="radio" name={g.key} value={value} required checked={choices[g.key as keyof typeof choices]===value} onChange={()=>{setChoices(c=>({...c,[g.key]:value}));setShown(false)}}/><span className="inline-flex min-h-11 items-center border border-[#d0cdc3] px-3 py-2 text-xs transition-colors hover:border-[#77766e] peer-checked:border-[#202522] peer-checked:bg-[#202522] peer-checked:text-white peer-focus-visible:outline-2 peer-focus-visible:outline-vermilion">{label}</span></label>)}</div></fieldset>)}</div><div className="mt-6 flex flex-wrap items-center justify-between gap-5"><p className="text-xs text-muted" role="status">{progressText}</p><Button type="submit" className="rounded-none! border-vermilion! bg-vermilion text-white">查看推薦方案 <ArrowRight size={15}/></Button></div></form>{shown&&<div className="mt-12" aria-live="polite"><div className="mb-6 flex items-center justify-between"><h3 className="font-serif text-2xl">為這趟旅程推薦</h3><button onClick={()=>{setChoices({city:'',party:'',purpose:''});setShown(false)}} className="min-h-11 text-xs underline">重新選擇</button></div><div aria-label="已選條件" className="mt-5 mb-4 flex flex-wrap gap-2">{selectedLabels.map(label => <span key={label} className="border border-[#c4c5b8] bg-[#e0ded1] px-3 py-1.5 text-xs text-[#202522]">{label}</span>)}</div><p className="mb-6 text-xs text-muted">{apiConfigured?'以下為教學示範方案；選擇不會保留庫存。':'以下為示例商品，尚未連接正式庫存'}</p>{plans.loading&&<p role="status">正在載入方案…</p>}{plans.error&&<p role="alert">{plans.error}</p>}<div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">{matched.map(p=><PlanCard key={p.id} plan={p} query={'&city='+choices.city+'&party='+choices.party+'&purpose='+choices.purpose}/>)}</div>{!matched.length&&<p className="py-6 text-sm text-muted">沒有符合條件的方案，請調整條件。</p>}</div>}</Container></section>
}
