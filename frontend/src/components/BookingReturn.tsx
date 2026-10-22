import { Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { buttonClass } from './ui'

export function BookingReturn({ to }: { to: string | null }) {
  return to ? <Link to={to} className={buttonClass}><ArrowLeft size={14}/>返回預約</Link> : null
}
