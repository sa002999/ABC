import { renderToStaticMarkup } from 'react-dom/server'
import { expect, it, vi } from 'vitest'
import { MemberProfile } from '../src/components/MemberProfile'

vi.mock('../src/lib/auth',()=>({useAuth:()=>({user:{uid:'member'}})}))
vi.mock('../src/lib/hooks',()=>({usePrivateResource:()=>({
 data:{id:'member',displayName:'會員姓名',email:'member@example.test',emailVerified:false,phoneNumber:'+886912345678',phoneVerified:true},
 loading:false,error:'',setData:vi.fn(),reload:vi.fn(),
})}))

it('會員表單提供姓名、唯讀 Email、驗證入口與已驗證手機，沒有手機登入入口',()=>{
 const html=renderToStaticMarkup(<MemberProfile/>)
 expect(html).toContain('會員姓名')
 expect(html).toMatch(/type="email"[^>]*readOnly=""/)
 expect(html).toContain('重寄驗證信')
 expect(html).toContain('我已驗證，刷新狀態')
 expect(html).toContain('+886912345678')
 expect(html).toContain('新手機號碼')
 expect(html).toContain('目前登入密碼')
 expect(html).toContain('發送驗證碼')
 expect(html).not.toContain('手機登入')
})
