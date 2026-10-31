import { useEffect, useRef, useState } from 'react'
import { Copy } from 'lucide-react'
import { Button, Container, Modal, Notice, PageHeading, Panel } from '../components/ui'
import { request, unwrap } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useBackend, usePrivateResource, useResource } from '../lib/hooks'
import { AccountNav, MemberNotice } from './Account'

export function MCP() {
  const auth = useAuth()
  const backend = useBackend()
  const metadata = usePrivateResource<{ valid?: boolean; expiresAt?: string }>('/api/account/mcp-token', {})
  const config = useResource<{ endpoint?: string; instructions?: string }>('/api/account/mcp-config', {}, undefined, backend.capabilities.mcp)
  const [secret, setSecret] = useState('')
  const [message, setMessage] = useState('')
  const [action, setAction] = useState<'create' | 'rotate' | 'revoke' | null>(null)
  const [busy, setBusy] = useState(false)
  const currentUid = useRef(auth.user?.uid)
  currentUid.current = auth.user?.uid
  const available = !!auth.user?.emailVerified && backend.capabilities.mcp && !metadata.loading && !metadata.error
  useEffect(() => { setSecret(''); setAction(null); setMessage('') }, [auth.user?.uid])
  async function copy(value: string, label: string) {
    try { await navigator.clipboard.writeText(value); setMessage(`已複製${label}。`) }
    catch { setMessage(`無法自動複製，請手動選取${label}。`) }
  }
  async function submit() {
    if (!action || busy) return
    setBusy(true)
    setSecret('')
    const uid = auth.user?.uid
    try {
      const value = unwrap(await request<{ token?: string }>('/api/account/mcp-token' + (action === 'rotate' ? '/rotate' : ''), {
        method: action === 'revoke' ? 'DELETE' : 'POST', token: await auth.token(), body: { confirmed: true },
      }))
      if (currentUid.current !== uid) return
      setSecret(value.token ?? '')
      metadata.reload()
      setAction(null)
      setMessage(action === 'revoke' ? '已撤銷 token，原連線已無法使用會員功能。' : '新 token 只顯示這一次，請複製到 AI 客戶端的連線設定。')
    } catch (error) { if (currentUid.current === uid) { setMessage((error as Error).message); metadata.reload() } }
    finally { setBusy(false) }
  }
  return <Container>
    <PageHeading eyebrow="CONNECT YOUR AI ASSISTANT" title="連接自己的 AI 小幫手" description="設定 MCP 端點及本人 token。公開探索免登入；會員授權、照片同意與每次生成確認分開。" />
    <AccountNav /><MemberNotice />
    <div className="grid gap-6 md:grid-cols-2">
      <Panel>
        <h2 className="font-serif text-xl">01　下載與設定連線</h2>
        <p className="mt-5 text-sm leading-8 text-muted">在 AI 客戶端新增 Streamable HTTP MCP 連線，填入下列端點。會員 token 請放在連線的 Bearer token／Authorization 設定，勿貼進對話。</p>
        {config.loading ? <p className="mt-4 text-sm">正在讀取端點…</p> : config.data.endpoint && <>
          <p className="mt-4 break-all font-mono text-sm">{config.data.endpoint}</p>
          <Button className="mt-4" onClick={() => void copy(config.data.endpoint!, '端點')}><Copy size={14} />複製端點</Button>
          <p className="mt-4 text-xs leading-7 text-muted">{config.data.instructions}</p>
        </>}
        {config.error && <Notice>{config.error}</Notice>}
      </Panel>
      <Panel>
        <h2 className="font-serif text-xl">02　管理本人 token</h2>
        <p className="mt-5 text-sm leading-8 text-muted">一人一個有效 token，90 天到期。建立或重建後僅完整顯示一次；後端只保存雜湊，無法讀回原值。</p>
        <p className="mt-4 text-sm">狀態：{!auth.user ? '登入後查看' : metadata.loading ? '讀取中…' : metadata.error ? '無法取得' : metadata.data.valid ? '有效' : '尚無有效 token'}</p>
        {metadata.data.expiresAt && <p className="mt-2 text-xs">到期時間：{new Date(metadata.data.expiresAt).toLocaleString('zh-TW', { timeZone: 'Asia/Tokyo' })}（日本時間）</p>}
        {metadata.error && <Notice>{metadata.error}<Button onClick={metadata.reload}>重試</Button></Notice>}
        <div className="mt-5 flex flex-wrap gap-3">
          <Button disabled={!available || busy || !!metadata.data.valid} onClick={() => setAction('create')}>建立</Button>
          <Button disabled={!available || busy || !metadata.data.valid} onClick={() => setAction('rotate')}>重建</Button>
          <Button disabled={!available || busy || !metadata.data.valid} onClick={() => setAction('revoke')}>撤銷</Button>
        </div>
        {secret && <div className="mt-5 border border-vermilion/30 p-4">
          <p className="text-xs">本人 token（僅顯示一次）：</p><p className="mt-3 break-all font-mono text-xs">{secret}</p>
          <div className="mt-3 flex gap-3"><Button onClick={() => void copy(secret, 'token')}><Copy size={14} />複製 token</Button><Button onClick={() => setSecret('')}>隱藏</Button></div>
        </div>}
      </Panel>
    </div>
    {message && <Notice>{message}</Notice>}
    <p className="mt-6 text-xs leading-7 text-muted">已提供逐人選款與 AI 試穿。MCP 每日 3 次，與網站額度分開；每次生成須另行確認，圖片於完成當日日本午夜到期，不加入網站生成圖收藏。預約草稿將於後續階段開放。</p>
    <Modal title={action === 'revoke' ? '撤銷 token？' : action === 'rotate' ? '重建 token？' : '建立 token？'} open={!!action} onClose={() => !busy && setAction(null)}>
      <p className="text-sm leading-8">{action === 'create' ? '新 token 僅回傳一次，用於本人 AI 客戶端連線。' : '現有 token 將立即失效。重建後須更新 AI 客戶端的連線設定。'}</p>
      <Button disabled={busy} className="mt-6" onClick={() => void submit()}>{busy ? '處理中…' : `確認${action === 'revoke' ? '撤銷' : action === 'rotate' ? '重建' : '建立'}`}</Button>
    </Modal>
  </Container>
}
