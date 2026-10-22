import { Link } from 'react-router-dom'
import { ButtonLink, Container, PageHeading } from '../components/ui'

const sections = [
  {
    id: 'explore', title: '探索和服方案',
    groups: [
      { title: '不需註冊，即可使用', items: [
        '瀏覽和服方案、價格、商品照片與預製穿搭圖。',
        '篩選方案、挑選和服與女生腰帶，瀏覽外拍服務比較。',
        '查看門市資訊、公開可預約時段，以及使用流程、常見問題與相關政策。',
      ] },
      { title: '和服與人數', items: [
        '所有和服統一尺寸；女生可選配件僅腰帶，男生無可選配件。',
        '情侶方案包含兩人的和服，計入兩名旅客、兩件和服。每筆預約限 1～3 位旅客，共用同一門市、日期與時段。',
      ] },
    ],
  },
  {
    id: 'membership', title: '會員與 AI 造型預覽',
    groups: [
      { title: '會員功能使用條件', items: [
        '請先完成會員註冊、電子信箱驗證並登入，再使用以下功能。',
        '造型收藏與收藏方案比較。',
        '本人照片上傳、AI 試穿及場景生成；查看與管理個人生成圖。',
        '預約、取得正式報價與付款；查看預約紀錄、QR Code 票券及申請取消預約。',
        '建立與使用 AI 小幫手連線憑證。',
      ] },
      { title: 'AI 與收藏皆為選用', items: [
        '不使用 AI、不上傳照片，也不必先收藏，即可選方案預約。',
        '可選本人照片或商店模特兒。情侶方案提供女生、男生兩個獨立照片位置，替換或刪除其中一人不影響另一人。',
        '使用本人照片前須取得照片當事人的處理同意；照片同意與每次生成確認分開，不會因上傳或登入而自動生成。',
        '預製穿搭圖是展示圖片，不是即時生成結果。AI 圖像僅供款式與配色參考，不保證實際合身度，也不等於實拍照片。',
      ] },
    ],
  },
  {
    id: 'services', title: '方案內容與選用服務',
    groups: [
      { title: '方案內容', items: [
        '著裝協助、髮型等服務是否包含，於各方案詳情列明。',
        '查看所選方案的租借時長與歸還規定，依預約門市的日本當地時間安排。',
      ] },
      { title: '選用與加購', items: [
        '女生腰帶可不加選；未加選不收額外配件費，方案已含的腰帶不重複計價。男生無可選配件。',
        '攝影可選擇不攝影、棚拍或室外拍攝。棚拍是否提供及服務內容，以所選實體門市現場安排為準。',
        '方案已包含的服務、腰帶與攝影項目不重複收費；已選外拍方案的內容沿用至預約，不需重複選擇。',
      ] },
    ],
  },
  {
    id: 'booking-payment', title: '預約與付款',
    groups: [
      { title: '', items: [
        '選擇門市、日期、時段與旅客人數，逐人確認和服搭配、選用服務及聯絡資料。返回前一步可繼續修改。',
        '全站以台幣 TWD 計價。取得正式報價後，先確認整筆明細、總額與取消退款政策；取得報價本身不會扣款。',
        '確認報價並前往付款後，成功建立整筆商品與名額暫留，才開始 10 分鐘期限。重新整理不會延長期限。',
        '正式預約須在付款確認成功，且商品與名額完成正式保留後才成立；成立後取得預約編號、會員票券與確認信。',
        '付款結果待確認時，請先查詢原預約狀態，避免再次付款。',
      ] },
    ],
  },
  {
    id: 'check-in', title: '到店報到與歸還',
    groups: [
      { title: 'QR Code 與到店期限', items: [
        '正式預約成立後，可於會員中心開啟動態 QR Code 票券，由預約會員本人至指定門市出示，並由人員核對及核銷。',
        '每筆預約共用一張票券，限核銷一次。QR Code 每 5 分鐘更新，舊碼失效，請開啟當下有效的票券。',
        '請於預約開始後 30 分鐘內報到，包含第 30 分鐘，以日本門市當地時間為準。超過期限仍未報到，票券失效。',
        '期限內已完成報到者，不會因排隊等待掃碼而被判定逾期，請由店員記錄報到時間。',
        '取消預約或核銷完成後，票券失效，不可再次核銷。重新整理或更新 QR Code，不會延長報到期限。',
      ] },
      { title: '體驗與歸還', items: [
        '依所選方案時間體驗並歸還和服；遲到不順延原定結束時間。',
        '歸還後由門市檢查與整備，再重新開放出租。',
      ] },
    ],
  },
  {
    id: 'photo-delivery', title: '實拍照片交付',
    groups: [
      { title: '', items: [
        '實拍照片由合作攝影師透過雲端連結寄送至您預約時填寫的電子信箱，交付時間與方式依攝影師安排。',
        '請確認預約信箱填寫正確。實拍照片交付與網站 AI 生成圖為不同服務。',
      ] },
    ],
  },
]

export function Guide() {
  return <Container className="max-w-4xl!">
    <PageHeading eyebrow="BEFORE YOU BOOK" title="服務與預約須知" description="從選擇和服、預約付款到門市報到，出發前需要了解的事，都整理在這裡。"/>
    <nav aria-label="服務與預約須知頁內導覽" className="mb-12 grid gap-x-6 gap-y-4 border-b border-line pb-8 sm:grid-cols-2 lg:grid-cols-3">
      {sections.map((section, index) => <a key={section.id} href={'#' + section.id} className="flex min-h-11 items-center gap-3 text-sm underline-offset-4 hover:underline">
        <span className="shrink-0 text-xs text-forest">{String(index + 1).padStart(2, '0')}</span>{section.title}
      </a>)}
    </nav>
    {sections.map((section, index) => <section key={section.id} id={section.id} aria-labelledby={section.id + '-title'} tabIndex={-1} className="mb-10 min-w-0 scroll-mt-28 border-b border-line pb-10">
      <h2 id={section.id + '-title'} className="grid grid-cols-[24px_minmax(0,1fr)] items-baseline font-serif text-2xl md:grid-cols-[32px_minmax(0,1fr)]"><span className="shrink-0 font-sans text-xs text-forest">{String(index + 1).padStart(2, '0')}</span><span className="min-w-0">{section.title}</span></h2>
      {section.groups.map((group, groupIndex) => <div key={groupIndex} className="mt-6 pl-6 md:pl-8">
        {group.title && <h3 className="mb-3 text-sm font-medium">{group.title}</h3>}
        <ul className="list-disc space-y-3 pl-5 text-sm leading-8 text-muted">{group.items.map(item => <li key={item}>{item}</li>)}</ul>
      </div>)}
    </section>)}
    <div className="mt-8 flex flex-wrap gap-3"><ButtonLink to="/plans">探索方案</ButtonLink><ButtonLink to="/booking">開始預約</ButtonLink></div>
    <div className="mt-6 flex flex-wrap gap-x-6 gap-y-3 text-xs text-muted"><Link to="/faq" className="underline underline-offset-4">常見問題</Link><Link to="/cancellation" className="underline underline-offset-4">取消與退款</Link></div>
  </Container>
}
