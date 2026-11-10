import { lazy, Suspense, Component, type ReactNode } from 'react'
import { Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Container, PageHeading, Notice, ButtonLink, Loading } from './components/ui'
import { Home } from './pages/Home'
import { Plans, PlanDetail } from './pages/Plans'
import { AuthPage } from './pages/Auth'
const TryOn = lazy(() => import('./pages/TryOn').then(m => ({ default: m.TryOn })))
const Booking = lazy(() => import('./pages/Booking').then(m => ({ default: m.Booking })))
const PaymentStatus = lazy(() => import('./components/BookingPayment').then(m => ({ default: m.PaymentStatus })))
const BookingComplete = lazy(() => import('./pages/Booking').then(m => ({ default: m.BookingComplete })))
const Looks = lazy(() => import('./pages/Account').then(m => ({ default: m.Looks })))
const Compare = lazy(() => import('./pages/Account').then(m => ({ default: m.Compare })))
const Account = lazy(() => import('./pages/Account').then(m => ({ default: m.Account })))
const Bookings = lazy(() => import('./pages/Account').then(m => ({ default: m.Bookings })))
const BookingDetail = lazy(() => import('./pages/Account').then(m => ({ default: m.BookingDetail })))
const Generations = lazy(() => import('./pages/Account').then(m => ({ default: m.Generations })))
const MCP = lazy(() => import('./pages/MCPAccount').then(m => ({ default: m.MCP })))
const Admin = lazy(() => import('./pages/Admin').then(m => ({ default: m.Admin })))
const Information = lazy(() => import('./pages/Information').then(m => ({ default: m.Information })))
const Stores = lazy(() => import('./pages/Information').then(m => ({ default: m.Stores })))
const Photography = lazy(() => import('./pages/Information').then(m => ({ default: m.Photography })))
const MigrationStatus = lazy(() => import('./pages/Information').then(m => ({ default: m.MigrationStatus })))

class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  render() { return this.state.failed ? <Container><PageHeading eyebrow="SOMETHING WENT WRONG" title="畫面暫時無法載入"/><Notice>請重新整理；若問題持續，請檢查服務狀態。</Notice><a href="/" className="underline">返回首頁</a></Container> : this.props.children }
}

export function App() {
  return <ErrorBoundary><Suspense fallback={<Container><Loading/></Container>}><Routes><Route element={<Layout/>}><Route index element={<Home/>}/><Route path="plans" element={<Plans/>}/><Route path="plans/compare" element={<Compare/>}/><Route path="plans/:planId" element={<PlanDetail/>}/>{['login','register','reset-password','verify-email'].map(path=><Route key={path} path={path} element={<AuthPage key={path}/>}/>)}<Route path="try-on" element={<TryOn/>}/><Route path="booking" element={<Booking/>}/><Route path="booking/payment/:orderNo" element={<PaymentStatus/>}/><Route path="booking/complete/:bookingNo" element={<BookingComplete/>}/><Route path="looks" element={<Looks/>}/><Route path="looks/compare" element={<Compare/>}/><Route path="account" element={<Account/>}/><Route path="account/mcp" element={<MCP/>}/><Route path="account/generations" element={<Generations/>}/><Route path="bookings" element={<Bookings/>}/><Route path="bookings/:bookingNo" element={<BookingDetail/>}/><Route path="admin" element={<Admin/>}/><Route path="admin/:section" element={<Admin/>}/><Route path="admin/:section/:recordId" element={<Admin/>}/><Route path="stores" element={<Stores/>}/><Route path="stores/:storeId" element={<Stores/>}/><Route path="photography" element={<Photography/>}/>{['guide','faq','about','contact','privacy','cancellation','terms'].map(path=><Route key={path} path={path} element={<Information key={path}/>}/>)}<Route path="migration" element={<MigrationStatus/>}/><Route path="*" element={<Container><PageHeading eyebrow="PAGE NOT FOUND" title="找不到這個頁面"/><ButtonLink to="/">回首頁</ButtonLink></Container>}/></Route></Routes></Suspense></ErrorBoundary>
}
