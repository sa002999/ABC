import { createContext, useEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { Heart, UserRound, X, Sparkles, CalendarDays, Compass } from 'lucide-react'
import { useBackend } from '../lib/hooks'
import { HomeFooter } from './HomeFooter'
import '../home-menu.css'
import '../site-header.css'

const navigation = [['01', '探索和服方案', '探索適合你的和服體驗', '/plans'], ['02', 'AI 和服試穿', '預覽和服、腰帶與造型搭配', '/try-on'], ['03', '我的造型收藏', '查看儲存的和服造型', '/looks'], ['04', '會員中心', '登入與查看會員帳號', '/account'], ['05', '東京・京都門市', '查看東京與京都門市', '/stores'], ['06', '服務流程', '從線上預約到門市歸還', '/guide']]
export const HomeLanguageContext = createContext<'zh' | 'en'>('zh')

export function Layout() {
  const backend = useBackend()
  const [language, setLanguage] = useState<'zh' | 'en'>('zh')
  const [scrolled, setScrolled] = useState(false)
  const [menu, setMenu] = useState(false)
  const menuRef = useRef<HTMLDialogElement>(null)
  const opener = useRef<HTMLButtonElement>(null)
  const location = useLocation()
  const home = location.pathname === '/'
  useEffect(() => { setMenu(false); if (location.hash) requestAnimationFrame(() => document.getElementById(location.hash.slice(1))?.scrollIntoView()); else window.scrollTo(0, 0) }, [location.pathname, location.hash])
  useEffect(() => {
    if (!menu) return
    menuRef.current?.showModal()
    const old = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { menuRef.current?.close(); document.body.style.overflow = old; opener.current?.focus() }
  }, [menu])
  useEffect(() => {
    const sync = () => setScrolled(window.scrollY > 24)
    sync()
    window.addEventListener('scroll', sync, { passive: true })
    return () => window.removeEventListener('scroll', sync)
  }, [])
  useEffect(() => {
    document.documentElement.lang = home && language === 'en' ? 'en' : 'zh-Hant'
  }, [home, language])
  return <>
    <a href="#main-content" className="fixed top-2 left-2 z-[100] -translate-y-24 bg-paper p-3 focus:translate-y-0">跳至主要內容</a>
    {!home && <div className="site-header-space" aria-hidden="true" />}
    {(import.meta.env.DEV || !backend.capabilities.booking) && !home && <div className="bg-[#C4BCAC] px-4 py-1.5 text-center text-[10px] tracking-wider text-paper/85">LOCAL PREVIEW · React / Tailwind 移植檢查 · 正式服務尚未啟用</div>}
    <header id="home-header" className={scrolled ? 'is-scrolled' : ''}>
      <Link className="brand" to="/" aria-label="KINU TABI 首頁" onClick={event => { if (!home || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return; event.preventDefault(); window.scrollTo({ top: 0, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' }) }}><span>KINU</span><span>TABI</span></Link>
      <nav className="header-actions" aria-label="快捷導覽">
        <Link className="booking-link" to="/booking">{language === 'en' ? 'Book' : '預約'}</Link>
        <button className="language-toggle" type="button" aria-label="切換語言" onClick={() => setLanguage(value => value === 'zh' ? 'en' : 'zh')}><span className={language === 'zh' ? 'is-active' : ''}>中</span><span aria-hidden="true">／</span><span className={language === 'en' ? 'is-active' : ''}>EN</span></button>
        <button ref={opener} className="menu-trigger" type="button" aria-label="開啟選單" aria-controls="site-menu" aria-expanded={menu} onClick={() => setMenu(true)}><span className="menu-label">MENU</span><span className="menu-icon" aria-hidden="true"><i /><i /></span></button>
      </nav>
    </header>
    <dialog id="site-menu" ref={menuRef} onCancel={() => setMenu(false)} aria-label="主要導覽" className="home-menu-texture fixed inset-0 m-0 h-dvh max-h-none w-full max-w-none overflow-y-auto bg-[#202522] p-6 text-paper backdrop:bg-[#202522] md:p-12"><div className="flex items-center justify-between"><Link to="/" onClick={() => setMenu(false)} className="home-menu-brand">KINU TABI</Link><button onClick={() => setMenu(false)} aria-label="關閉選單" className="flex min-h-11 items-center gap-4 text-xs tracking-widest">CLOSE <X size={28} strokeWidth={1} /></button></div><div className="mx-auto mt-10 grid max-w-6xl gap-16 md:mt-20 md:grid-cols-[1.3fr_1fr]"><nav>{navigation.map(([n, title, subtitle, to]) => <Link key={to} to={to} onClick={() => setMenu(false)} className="group flex items-center gap-5 border-b border-paper/25 py-5 md:py-6"><span className="home-menu-number">{n}</span><div><strong className="home-menu-title font-serif text-2xl font-normal md:text-3xl">{title}</strong><span className="mt-2 block text-[13px] tracking-[.15em] text-paper/60">{subtitle}</span></div></Link>)}</nav><figure className="hidden md:block"><img src="/assets/kimono-umbrellas.jpg" className="h-[570px] w-full object-cover" alt="京都和服與和傘風格參考" /><figcaption className="mt-4 text-[10px] tracking-[.2em] text-paper/70">KYOTO · A MOMENT IN SILK</figcaption></figure></div></dialog>
    <main id="main-content" className="min-h-[60dvh]"><HomeLanguageContext.Provider value={language}><Outlet /></HomeLanguageContext.Provider></main>
    {home ? <HomeFooter /> : <footer className="border-t border-line bg-wash/45 px-5 pt-12 pb-26 md:px-10 md:pb-10"><div className="mx-auto max-w-6xl"><div className="flex flex-col justify-between gap-8 md:flex-row"><div><Link to="/" className="font-display text-2xl tracking-widest">KINU TABI</Link><p className="mt-3 font-serif text-xs text-muted">絹と旅、その一日を記憶に</p></div><nav aria-label="頁尾導覽" className="flex max-w-xl flex-wrap gap-x-6 gap-y-4 text-xs text-muted">{[['使用流程','guide'],['常見問題','faq'],['關於我們','about'],['聯絡我們','contact'],['隱私權政策','privacy'],['取消與退款','cancellation'],['服務條款','terms']].map(([label,path]) => <Link key={path} to={'/'+path} className="hover:text-ink">{label}</Link>)}</nav></div><div className="mt-10 flex flex-wrap justify-between gap-3 border-t border-line pt-5 text-[10px] tracking-wide text-muted"><p>© KINU TABI · TOKYO / KYOTO · Concept project</p><div className="flex gap-5"><Link to="/migration">移植狀態</Link><Link to="/admin">門市後台</Link><span>Photos via Unsplash · 風格參考</span></div></div></div></footer>}
    <nav aria-label="手機快捷導覽" className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 border-t border-line bg-paper/97 pb-[env(safe-area-inset-bottom)] backdrop-blur-sm md:hidden">{[[Compass,'方案','/plans'],[Sparkles,'試穿','/try-on'],[UserRound,'會員','/account'],[Heart,'收藏','/looks'],[CalendarDays,'預約','/booking']].map(([Icon,label,path]) => { const Component = Icon as typeof Compass; return <NavLink key={String(path)} to={String(path)} className={({isActive}) => `flex min-h-16 flex-col items-center justify-center gap-1.5 text-[10px] ${isActive ? 'text-vermilion' : 'text-muted'}`}><Component size={17} strokeWidth={1.4}/>{String(label)}</NavLink> })}</nav>
  </>
}
