import { Link } from 'react-router-dom'
import '../home-footer-back-top.css'

const footerLinks = [['使用流程','guide'],['常見問題','faq'],['關於我們','about'],['聯絡我們','contact'],['隱私權政策','privacy'],['取消與退款','cancellation'],['服務條款','terms']]

export function HomeFooter() {
  return <footer id="home-footer" className="border-t border-paper/22 bg-[#202522] px-5 pt-12 pb-26 text-paper md:px-10 md:pb-10">
    <div className="mx-auto max-w-6xl">
      <div className="flex flex-col justify-between gap-8 md:flex-row">
        <div><Link to="/" className="font-display text-2xl tracking-widest">KINU TABI</Link><p className="mt-3 font-serif text-xs text-paper/58">絹と旅、その一日を記憶に</p></div>
        <div className="home-footer-links"><div className="home-footer-back-top-anchor"><button type="button" className="home-footer-back-top" aria-label="回到頂端" onClick={() => window.scrollTo({ top: 0, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' })} /></div><nav aria-label="頁尾導覽" className="flex max-w-xl flex-wrap gap-x-6 gap-y-4 text-xs text-paper/75">{footerLinks.map(([label,path]) => <Link key={path} to={'/'+path} className="hover:text-paper">{label}</Link>)}</nav></div>
      </div>
      <div className="mt-10 flex flex-wrap justify-between gap-3 border-t border-paper/22 pt-5 text-[10px] tracking-wide text-paper/58">
        <p>© KINU TABI · TOKYO / KYOTO · Concept project</p>
        <div className="flex flex-wrap items-start gap-x-5 gap-y-3">
          <Link to="/migration" className="hover:text-paper">管理狀態</Link>
          <Link to="/admin" className="hover:text-paper">門市後台</Link>
          <details className="max-w-[310px]">
            <summary className="cursor-pointer hover:text-paper">攝影素材來源</summary>
            <p className="mt-2 leading-[1.8]">Photos via <a href="https://unsplash.com" target="_blank" rel="noreferrer" className="text-paper underline">Unsplash</a>. Prototype use only.</p>
          </details>
        </div>
      </div>
    </div>
  </footer>
}
