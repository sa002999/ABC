import { useEffect, useRef, useId, isValidElement, cloneElement, type ReactElement, type ButtonHTMLAttributes, type ReactNode, type SelectHTMLAttributes } from 'react'
import { Link, type LinkProps } from 'react-router-dom'
import { ArrowRight, LoaderCircle, X } from 'lucide-react'
import { apiConfigured } from '../lib/api'
import { useBackend } from '../lib/hooks'

export const inputClass = 'w-full rounded-sm border border-line bg-paper px-4 py-3 text-sm outline-offset-2 focus:border-forest disabled:opacity-50'
export const buttonClass = 'inline-flex min-h-11 items-center justify-center gap-3 rounded-none border border-ink px-6 py-3 text-sm transition-colors hover:bg-ink hover:text-paper disabled:cursor-not-allowed disabled:opacity-45'
export const primaryClass = `${buttonClass} border-forest bg-forest text-white hover:bg-ink`
export function Button({ variant = 'secondary', className = '', ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' }) { return <button type="button" className={`${variant === 'primary' ? primaryClass : buttonClass} ${className}`} {...props} /> }
export function ButtonLink({ primary = false, className = '', children, ...props }: LinkProps & { primary?: boolean }) { return <Link className={`${primary ? primaryClass : buttonClass} ${className}`} {...props}>{children}<ArrowRight size={15} /></Link> }
export function Eyebrow({ children }: { children: ReactNode }) { return <p className="text-[10px] font-medium tracking-[.22em] text-forest uppercase">{children}</p> }
export function PageHeading({ eyebrow, title, description }: { eyebrow: string; title: string; description?: string }) { return <header className="mb-10 border-b border-line pb-8 md:mb-14"><Eyebrow>{eyebrow}</Eyebrow><h1 className="mt-4 font-serif text-3xl leading-relaxed md:text-5xl">{title}</h1>{description && <p className="mt-5 max-w-2xl text-sm leading-8 text-muted">{description}</p>}</header> }
export function Container({ children, className = '' }: { children: ReactNode; className?: string }) { return <div className={`mx-auto w-full max-w-6xl px-5 py-12 md:px-10 md:py-18 ${className}`}>{children}</div> }
export function Panel({ children, className = '' }: { children: ReactNode; className?: string }) { return <section className={`border border-line bg-white/20 p-5 md:p-7 ${className}`}>{children}</section> }
export function Notice({ children, tone = 'info' }: { children: ReactNode; tone?: 'info' | 'error' | 'success' }) { return <div role={tone === 'error' ? 'alert' : 'status'} className={`my-4 border-l-2 px-4 py-3 text-sm leading-7 ${tone === 'error' ? 'border-vermilion bg-vermilion/6 text-vermilion' : tone === 'success' ? 'border-forest bg-forest/8' : 'border-line bg-wash/65 text-muted'}`}>{children}</div> }
export function ServiceNotice() { const backend=useBackend();return !apiConfigured ? <Notice>目前為前端檢查模式。商品及價格為示例；後端尚未連接，未啟用正式 AI、庫存、付款或核銷。</Notice> : !backend.capabilities.booking ? <Notice>{backend.connected?'已連接教學示範資料；登入並驗證信箱後可取得正式報價與暫留資源。付款尚未開放；照片與 AI 試穿可由會員另行確認操作。':'正在確認後端服務；尚未開放正式預約、付款與 AI。'}</Notice> : null }
export function Loading() { return <div role="status" className="flex items-center gap-3 py-12 text-sm text-muted"><LoaderCircle className="animate-spin motion-reduce:animate-none" size={18} />載入中…</div> }
export function Empty({ children }: { children: ReactNode }) { return <div className="border border-dashed border-line px-5 py-14 text-center text-sm leading-8 text-muted">{children}</div> }
export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) { const id=useId(); return <div className="block"><label htmlFor={id} className="mb-2 block text-sm">{label}</label>{isValidElement(children)?cloneElement(children as ReactElement<{id?:string}>,{id}):children}{hint && <p className="mt-2 text-xs leading-6 text-muted">{hint}</p>}</div> }
export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) { return <select {...props} className={`${inputClass.replace('rounded-sm', 'rounded-none')} kinu-select ${props.className ?? ''}`} /> }
export function Check({ children, ...props }: { children: ReactNode } & ButtonHTMLAttributes<HTMLInputElement> & { checked?: boolean; onChange?: React.ChangeEventHandler<HTMLInputElement> }) { return <label className="flex min-h-11 items-start gap-3 text-sm leading-7"><input type="checkbox" className="mt-1.5 size-4 shrink-0 accent-forest" {...props} /><span>{children}</span></label> }

export function Modal({ title, open, onClose, children }: { title: string; open: boolean; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    if (!open) return
    const previous = document.activeElement as HTMLElement | null
    const dialog = ref.current
    dialog?.showModal()
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { dialog?.close(); document.body.style.overflow = previousOverflow; previous?.focus() }
  }, [open])
  return <dialog ref={ref} aria-label={title} onCancel={onClose} onClick={event => { if (event.target === ref.current) { const rect = ref.current!.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) onClose() } }} className="fixed inset-0 m-auto max-h-[90dvh] w-[calc(100%-2rem)] max-w-xl overflow-y-auto border border-line bg-paper p-6 text-ink backdrop:bg-ink/60 md:p-9"><div className="mb-6 flex items-start justify-between gap-4"><h2 className="font-serif text-2xl">{title}</h2><button onClick={onClose} aria-label="關閉對話框" className="-mt-2 -mr-2 flex size-11 shrink-0 items-center justify-center"><X size={20} /></button></div>{open && children}</dialog>
}
