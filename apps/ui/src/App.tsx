import React from 'react'
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import Login from './pages/Login.tsx'
import Signup from './pages/Signup.tsx'
import Dashboard from './pages/Dashboard.tsx'
import MyInfra from './pages/MyInfra.tsx'
import Battle from './pages/Battle.tsx'
import MyWork from './pages/MyWork.tsx'
import Leaderboard from './pages/Leaderboard.tsx'
import Admin from './pages/Admin.tsx'
import Monitor from './pages/Monitor.tsx'
import Initiative from './pages/Initiative.tsx'
import Training from './pages/Training.tsx'
import Profile from './pages/Profile.tsx'
import AskAI from './components/AskAI.tsx'
import { getUser, isAdmin, isAuthed, logout } from './auth.ts'

function NavBar() {
  const user = getUser()
  const nav = useNavigate()
  if (!user) return null
  return (
    <nav style={{
      display: 'flex', alignItems: 'center', gap: 16,
      padding: '10px 24px', background: 'var(--bg-2)',
      borderBottom: '1px solid var(--border)',
    }}>
      <Link to="/" style={{ fontWeight: 700, color: 'var(--primary)', fontSize: 18 }}>tubewar</Link>
      <Link to="/dashboard">대시보드</Link>
      <Link to="/myinfra">내 인프라</Link>
      <Link to="/battle"
        onClick={() => window.dispatchEvent(new Event('tubewar:battle:reset'))}>
        공방전
      </Link>
      <Link to="/training">트레이닝</Link>
      <Link to="/mywork">내 워크북</Link>
      <Link to="/leaderboard">리더보드</Link>
      <Link to="/initiative">이니셔티브</Link>
      {isAdmin() && <Link to="/monitor">관제 대시보드</Link>}
      {isAdmin() && <Link to="/admin">관리자</Link>}
      <div style={{ flex: 1 }} />
      <Link to="/profile" style={{ color: 'var(--fg-dim)', fontSize: 13 }}>
        {user.name} ({user.role})
      </Link>
      <button className="ghost" onClick={() => { logout(); nav('/login') }}>로그아웃</button>
    </nav>
  )
}

function RequireAuth({ children }: { children: React.ReactNode }) {
  const loc = useLocation()
  if (!isAuthed()) return <Navigate to="/login" state={{ from: loc }} replace />
  return <>{children}</>
}

function RequireAdmin({ children }: { children: React.ReactNode }) {
  if (!isAuthed()) return <Navigate to="/login" replace />
  if (!isAdmin()) return <Navigate to="/dashboard" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <>
      <NavBar />
      <main style={{ maxWidth: 1100, margin: '0 auto', padding: 24 }}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<RequireAuth><Dashboard /></RequireAuth>} />
          <Route path="/myinfra"   element={<RequireAuth><MyInfra /></RequireAuth>} />
          <Route path="/profile"   element={<RequireAuth><Profile /></RequireAuth>} />
          <Route path="/battle"      element={<RequireAuth><Battle /></RequireAuth>} />
          <Route path="/mywork"      element={<RequireAuth><MyWork /></RequireAuth>} />
          <Route path="/leaderboard" element={<RequireAuth><Leaderboard /></RequireAuth>} />
          <Route path="/initiative"  element={<RequireAuth><Initiative /></RequireAuth>} />
          <Route path="/training"    element={<RequireAuth><Training /></RequireAuth>} />
          <Route path="/monitor"     element={<RequireAdmin><Monitor /></RequireAdmin>} />
          <Route path="/admin"       element={<RequireAdmin><Admin /></RequireAdmin>} />
        </Routes>
      </main>
      <AskAI />
    </>
  )
}
