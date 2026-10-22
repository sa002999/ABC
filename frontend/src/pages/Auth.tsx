import { useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { Button, Container, Eyebrow, Field, Notice, inputClass } from '../components/ui'
import { authConfigured, useAuth } from '../lib/auth'
import { safeReturnTo } from '../lib/domain'

const errors:Record<string,string> = { 'auth/invalid-credential':'電子郵件或密碼不正確。', 'auth/email-already-in-use':'此電子郵件已註冊，請改為登入。', 'auth/weak-password':'密碼強度不足，請依密碼要求重新設定。', 'auth/too-many-requests':'嘗試次數過多，請稍後再試。', 'auth/network-request-failed':'網路連線失敗，請檢查連線後重試。' }
export function AuthPage() {
  const auth=useAuth();const navigate=useNavigate();const location=useLocation();const[params]=useSearchParams()
  const mode=location.pathname==='/register'?'register':location.pathname==='/reset-password'?'reset':location.pathname==='/verify-email'?'verify':'login'
  const titles={login:'歡迎回來',register:'開始你的和服旅程',reset:'重設密碼',verify:'驗證電子郵件'}
  const [email,setEmail]=useState('');const [password,setPassword]=useState('');const [status,setStatus]=useState('');const [busy,setBusy]=useState(false)
  async function submit(e:FormEvent) {
    e.preventDefault();setBusy(true);setStatus('')
    try {
      if(mode==='login'){await auth.login(email,password);navigate(safeReturnTo(params.get('returnTo')))}
      else if(mode==='register'){await auth.register(email,password);navigate('/verify-email?returnTo='+encodeURIComponent(safeReturnTo(params.get('returnTo'))))}
      else if(mode==='reset'){await auth.reset(email);setStatus('若此信箱可接收重設通知，請至信箱依指示操作。')}
      else {await auth.verify();setStatus('驗證信已寄出，請檢查收件匣與垃圾郵件。')}
    } catch(error){const e=error as Error&{code?:string};setStatus(errors[e.code??'']??e.message)}finally{setBusy(false)}
  }
  return <Container className="max-w-5xl"><div className="grid overflow-hidden border border-line md:grid-cols-2"><div className="relative hidden md:block"><img src="/assets/kimono-portrait.jpg" alt="和服造型參考" className="absolute inset-0 h-full w-full object-cover"/><div className="absolute inset-x-0 bottom-0 bg-linear-to-t from-ink/75 p-8 pt-24 text-paper"><p className="font-display text-2xl tracking-wider">A MOMENT IN SILK</p><p className="mt-4 font-serif text-sm leading-7">把喜歡的造型，<br/>留給值得記住的一天。</p></div></div><div className="p-6 md:p-10"><Eyebrow>YOUR KINU TABI JOURNEY</Eyebrow><h1 className="mt-5 font-serif text-3xl">{titles[mode]}</h1><p className="mt-5 text-sm leading-7 text-muted">{mode==='verify'?'付款及建立 MCP token 前，需要完成電子郵件驗證。':mode==='reset'?'輸入註冊時使用的電子郵件。':'登入後可保存造型、使用 AI 預覽與預約體驗。'}</p>{!authConfigured&&<Notice>Firebase 尚未設定，登入與註冊目前未啟用。</Notice>}{mode==='verify'&&auth.user?.emailVerified?<Notice tone="success">電子郵件已驗證。<Link to={safeReturnTo(params.get('returnTo'))} className="ml-2 underline">繼續原操作</Link></Notice>:<form onSubmit={submit} className="mt-7 space-y-5">{mode!=='verify'&&<Field label="電子郵件"><input required type="email" autoComplete="email" value={email} onChange={e=>setEmail(e.target.value)} className={inputClass}/></Field>}{['login','register'].includes(mode)&&<Field label="密碼" hint={mode==='register'?'至少 6 個字元；實際要求以 Firebase 密碼政策為準。':undefined}><input required type="password" minLength={mode==='register'?6:undefined} autoComplete={mode==='register'?'new-password':'current-password'} value={password} onChange={e=>setPassword(e.target.value)} className={inputClass}/></Field>}<Button type="submit" variant="primary" className="w-full" disabled={busy||!authConfigured||(mode==='verify'&&!auth.user)}>{busy?'處理中…':mode==='register'?'建立會員帳號':mode==='reset'?'寄送重設密碼信':mode==='verify'?'寄送驗證信':'登入'}</Button>{mode==='verify'&&<Button type="button" className="w-full" onClick={async()=>{await auth.refresh();setStatus('已重新讀取驗證狀態。')}}>我已完成驗證，重新檢查</Button>}</form>}{status&&<Notice>{status}</Notice>}<div className="mt-7 flex flex-wrap gap-x-5 gap-y-3 text-xs text-muted"><Link to={'/login?returnTo='+encodeURIComponent(safeReturnTo(params.get('returnTo')))}>會員登入</Link><Link to={'/register?returnTo='+encodeURIComponent(safeReturnTo(params.get('returnTo')))}>建立帳號</Link><Link to="/reset-password">忘記密碼</Link></div><p className="mt-8 border-t border-line pt-5 text-[10px] leading-6 text-muted">照片處理同意於上傳時另外取得；註冊不會自動生成圖片或同意行銷用途。</p></div></div></Container>
}
