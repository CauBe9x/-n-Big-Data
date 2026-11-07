import { createContext, useContext, useEffect, useState } from 'react'
import { NavLink, Route, Routes, useLocation } from 'react-router-dom'
import { useApi } from './api.js'
import Home from './pages/Home.jsx'
import Jobs from './pages/Jobs.jsx'
import SalaryPredict from './pages/SalaryPredict.jsx'
import SkillPredict from './pages/SkillPredict.jsx'
import CategoryPredict from './pages/CategoryPredict.jsx'
import Rules from './pages/Rules.jsx'
import Clusters from './pages/Clusters.jsx'
import SkillValue from './pages/SkillValue.jsx'
import Models from './pages/Models.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Pipeline from './pages/Pipeline.jsx'
import DataQuality from './pages/DataQuality.jsx'
import About from './pages/About.jsx'

const MetaContext = createContext({ data: null })
export const useMeta = () => useContext(MetaContext)

const NAV = [
  { group: 'Thị trường', items: [
    { to: '/', label: 'Trang chủ' },
    { to: '/dashboard', label: 'Dashboard thị trường' },
    { to: '/jobs', label: 'Tra cứu tin tuyển dụng' },
  ] },
  { group: 'Máy học', items: [
    { to: '/predict/salary', label: 'Dự đoán mức lương' },
    { to: '/predict/skills', label: 'Gợi ý kỹ năng cần có' },
    { to: '/predict/category', label: 'Phân loại ngành nghề' },
    { to: '/models', label: 'Đánh giá mô hình' },
  ] },
  { group: 'Khai phá dữ liệu', items: [
    { to: '/mining/skill-value', label: 'Kỹ năng & mức lương' },
    { to: '/mining/rules', label: 'Luật kết hợp kỹ năng' },
    { to: '/mining/clusters', label: 'Phân cụm công việc' },
  ] },
  { group: 'Hệ thống dữ liệu', items: [
    { to: '/pipeline', label: 'Pipeline Big Data' },
    { to: '/data', label: 'Chất lượng dữ liệu' },
    { to: '/about', label: 'Kiến trúc hệ thống' },
  ] },
]

export default function App() {
  const meta = useApi('/api/meta')
  const health = useApi('/api/health')
  const dashboardUrl = health.data?.dashboard_url
  const [open, setOpen] = useState(false)
  const { pathname } = useLocation()
  useEffect(() => { setOpen(false); window.scrollTo(0, 0) }, [pathname])
  return (
    <MetaContext.Provider value={meta}>
      <div className="shell">
        <aside className={`sidebar ${open ? 'open' : ''}`}>
          <div className="sidebar-top">
          <NavLink to="/" className="brand" aria-label="VietJobs Lab – trang chủ">
            <span className="brand-mark" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 24 24"><path d="M4 20h4V11H4zm6 0h4V5h-4zm6 0h4v-6h-4z" fill="#fff" /></svg>
            </span>
            <span>
              <span className="brand-name">VietJobs Lab</span><br />
              <span className="brand-sub">Thị trường việc làm Việt Nam</span>
            </span>
          </NavLink>
          <button type="button" className="btn ghost menu-btn" aria-expanded={open} onClick={() => setOpen((v) => !v)}>{open ? 'Đóng' : 'Menu'}</button>
          </div>
          <nav className="nav" aria-label="Điều hướng chính">
            {NAV.map((g) => (
              <div className="nav-group" key={g.group}>
                <h2>{g.group}</h2>
                {g.items.map((it) => (
                  <NavLink key={it.to} to={it.to} end={it.to === '/'} className="nav-link">{it.label}</NavLink>
                ))}
              </div>
            ))}
            {health.data?.dashboard_online && (
              <div className="nav-group">
                <h2>Công cụ BI</h2>
                <a className="nav-link ext" href={dashboardUrl} target="_blank" rel="noreferrer">Dashboard Superset</a>
              </div>
            )}
          </nav>
          <div className="sidebar-foot">
            Dữ liệu: VietJobs (TopCV, 07–10/2025), Hugging Face dinhieufam/VietJobs. Đồ án môn Công nghệ dữ liệu lớn.
          </div>
        </aside>
        <main className="main">
          <div className="page-enter" key={pathname}>
          <Routes>
            <Route path="/" element={<Home health={health} />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/pipeline" element={<Pipeline />} />
            <Route path="/data" element={<DataQuality />} />
            <Route path="/about" element={<About />} />
            <Route path="/jobs" element={<Jobs />} />
            <Route path="/predict/salary" element={<SalaryPredict />} />
            <Route path="/predict/skills" element={<SkillPredict />} />
            <Route path="/predict/category" element={<CategoryPredict />} />
            <Route path="/models" element={<Models />} />
            <Route path="/mining/rules" element={<Rules />} />
            <Route path="/mining/clusters" element={<Clusters />} />
            <Route path="/mining/skill-value" element={<SkillValue />} />
            <Route path="*" element={<p className="state">Không có trang này. Chọn một mục ở thanh bên.</p>} />
          </Routes>
          </div>
        </main>
      </div>
    </MetaContext.Provider>
  )
}
