import { useEffect, useState, useSyncExternalStore, type ReactNode } from 'react'
import { apiConfigured, backendSnapshot, featureForPath, request, subscribeBackend, unwrap } from './api'
import { useAuth } from './auth'

export function useBackend() { return useSyncExternalStore(subscribeBackend, backendSnapshot, backendSnapshot) }
export function BackendConnection({ children }: { children: ReactNode }) {
  const backend=useBackend()
  useEffect(()=>{
    if(backend.connected)return
    const controller=new AbortController();let timer:ReturnType<typeof setTimeout>
    const probe=async()=>{try{await request('/api/health',{signal:controller.signal})}catch{if(!controller.signal.aborted)timer=setTimeout(probe,5000)}}
    void probe();return()=>{controller.abort();clearTimeout(timer)}
  },[backend.connected])
  return children
}

export function useResource<T>(path: string, fallback: T, token?: string, enabled = true, parse?: (value: unknown) => T) {
  const [data, setData] = useState<T>(fallback)
  const [loading, setLoading] = useState(apiConfigured && enabled)
  const [error, setError] = useState('')
  const [version, setVersion] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setError('')
    if (!apiConfigured || !enabled) { setData(fallback); setLoading(false); return }
    setLoading(true)
    request<T | { data: T }>(path, { signal: controller.signal, token }).then(value => { if (!controller.signal.aborted) setData(parse ? parse(unwrap(value)) : unwrap(value)) }).catch(err => { if (!controller.signal.aborted) { setData(fallback); setError(err.message) } }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
    // Callers keep fallback stable; path/token changes define resource identity.
  }, [path, token, version, enabled])
  return { data, loading, error, reload: () => setVersion(v => v + 1), example: !apiConfigured }
}

export function usePrivateResource<T>(path: string, fallback: T) {
  const auth = useAuth()
  const backend = useBackend()
  const feature = featureForPath(path)
  const[tokenError,setTokenError]=useState('')
  const [credential, setCredential] = useState({ uid: '', token: '' })
  useEffect(() => {
    let active = true
    setCredential({ uid: '', token: '' });setTokenError('')
    if (auth.user) auth.token().then(token => { if (active) setCredential({ uid: auth.user!.uid, token }) }).catch(error => {if(active)setTokenError(error.message)})
    return () => { active = false }
  }, [auth.user?.uid])
  const valid = !!auth.user && credential.uid === auth.user.uid && (!feature || backend.capabilities[feature])
  const result = useResource(path, fallback, valid ? credential.token : undefined, valid)
  return valid ? result : { ...result, data: fallback, loading: false, error: tokenError }
}
