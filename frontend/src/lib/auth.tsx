import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { initializeApp } from 'firebase/app'
import { getAuth, onAuthStateChanged, signOut, signInWithEmailAndPassword, createUserWithEmailAndPassword, sendEmailVerification, sendPasswordResetEmail, type User } from 'firebase/auth'
import { clearJourneys } from './bookingJourney'
import { request } from './api'

const config = { apiKey: import.meta.env.VITE_FIREBASE_API_KEY, authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN, projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID, appId: import.meta.env.VITE_FIREBASE_APP_ID }
export const authConfigured = Object.values(config).every(Boolean)
const auth = authConfigured ? getAuth(initializeApp(config)) : null
type AuthContextType = { user: User | null; ready: boolean; token: () => Promise<string>; login: (email: string, password: string) => Promise<void>; register: (email: string, password: string) => Promise<void>; logout: () => Promise<void>; verify: () => Promise<void>; reset: (email: string) => Promise<void>; refresh: () => Promise<void> }
const Context = createContext<AuthContextType | null>(null)
const requireAuth = () => { if (!auth) throw new Error('尚未設定 Firebase，登入服務未啟用。'); return auth }
let synchronized: {uid: string; promise: Promise<unknown>} | null = null
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [ready, setReady] = useState(!auth)
  const [, setRevision] = useState(0)
  useEffect(() => { if (!auth) return; return onAuthStateChanged(auth, current => { clearJourneys(); setUser(current); setReady(true) }) }, [])
  const value: AuthContextType = {
    user, ready,
    token: async () => { const u = requireAuth().currentUser; if (!u || u.uid!==user?.uid) throw new Error('登入帳號已變更，請重新操作。'); const token=await u.getIdToken(); if(synchronized?.uid!==u.uid) synchronized={uid:u.uid,promise:request('/api/account',{method:'PUT',token,body:{}}).catch(error=>{synchronized=null;throw error})}; await synchronized.promise; return token },
    login: async (email, password) => { await signInWithEmailAndPassword(requireAuth(), email, password) },
    register: async (email, password) => { const result = await createUserWithEmailAndPassword(requireAuth(), email, password); await sendEmailVerification(result.user) },
    logout: async () => { await signOut(requireAuth()); synchronized=null; clearJourneys(); for (const key of Object.keys(sessionStorage)) if (key.startsWith('kinu:')) sessionStorage.removeItem(key) },
    verify: async () => { const u = requireAuth().currentUser; if (!u || u.uid!==user?.uid) throw new Error('登入帳號已變更，請重新操作。'); await sendEmailVerification(u) },
    reset: async email => { await sendPasswordResetEmail(requireAuth(), email) },
    refresh: async () => { const u = requireAuth().currentUser; if (u) { await u.reload(); await u.getIdToken(true); setUser(u); setRevision(v => v + 1) } },
  }
  useEffect(() => {
    if (!user) return
    let active = true
    user.getIdToken().then(token => active && request('/api/account', { method: 'PUT', token, body: {} })).catch(() => {})
    return () => { active = false }
  }, [user?.uid])
  return <Context.Provider value={value}>{children}</Context.Provider>
}
export const useAuth = () => { const context = useContext(Context); if (!context) throw new Error('AuthProvider required'); return context }
