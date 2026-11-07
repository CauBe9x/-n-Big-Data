import { useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, Cell, LabelList, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { useMeta } from '../App.jsx'
import { fmt, fmtInt, post, qs, signedPct, useApi } from '../api.js'
import { ChartBlock, ErrorBox, History, PageHead, Section, SignedLabel, SkillInput, TooltipBox, signedDomain } from '../components/ui.jsx'

const chWidth = (s, min = 4) => `${Math.max(min, String(s || '').length + 1.5)}ch`

const EXAMPLES = [
  { title: 'Kế toán tổng hợp', province: 'Hà Nội', experience_years: 3, skills: ['excel', 'misa'] },
  { title: 'Backend Developer (Java)', province: 'Hồ Chí Minh', experience_years: 2, skills: ['java', 'sql', 'git'], languages: ['tiếng anh'] },
  { title: 'Nhân viên kinh doanh', province: 'Đà Nẵng', experience_years: 0, skills: [] },
]

export default function SalaryPredict() {
  const meta = useMeta()
  const [form, setForm] = useState({
    title: 'Chuyên viên phân tích dữ liệu', province: 'Hồ Chí Minh', experience_years: 2,
    contract_type: 'Toàn thời gian', category: '', skills: ['sql', 'python'], languages: [],
  })
  const [res, setRes] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(0)
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e?.target ? e.target.value : e }))
  const catSlug = form.category || res?.auto_category?.slug
  const dist = useApi(res ? `/api/stats/salary-distribution${qs({ category: catSlug, bin_size: 5, max_value: 80 })}` : null)

  const submit = async (e) => {
    e?.preventDefault()
    setBusy(true); setErr(null)
    try {
      setRes(await post('/api/predict/salary', {
        ...form, category: form.category || null,
        experience_years: form.experience_years === '' ? null : Number(form.experience_years),
      }))
      setDone((n) => n + 1)
    } catch (x) { setErr(x) } finally { setBusy(false) }
  }

  const cats = meta.data?.categories || []
  const catLabel = cats.find((c) => c.slug === form.category)?.name || 'để hệ thống tự nhận diện'
  const provs = meta.data?.provinces || []
  const contracts = meta.data?.contract_types || []
  const langs = meta.data?.languages || []
  const skillNames = (meta.data?.skills || []).map((s) => s.name)
  const scaleMax = res ? Math.max(60, Math.ceil(res.high / 10) * 10 + 10) : 60

  return (
    <>
      <PageHead title="Dự đoán mức lương">
        Điền vào câu bên dưới như khi mô tả một vị trí tuyển dụng. Mô hình hồi quy đã học từ các tin có công bố lương
        sẽ ước tính mức lương trung bình và khoảng dao động 80%.
      </PageHead>

      <form onSubmit={submit} aria-label="Thông tin vị trí cần dự đoán">
        <p className="sentence-form">
          Vị trí{' '}
          <input className="slot" aria-label="Chức danh" value={form.title} onChange={set('title')} style={{ width: chWidth(form.title, 8) }} required />
          {' '}làm việc tại{' '}
          <select className="slot" aria-label="Tỉnh/thành" value={form.province} onChange={set('province')} style={{ width: chWidth(form.province) }}>
            {provs.map((p) => <option key={p.name} value={p.name}>{p.name}</option>)}
          </select>
          , yêu cầu{' '}
          <input className="slot" aria-label="Số năm kinh nghiệm" type="number" min="0" max="30" step="0.5" value={form.experience_years}
            onChange={set('experience_years')} style={{ width: '3.2ch', textAlign: 'center' }} />
          {' '}năm kinh nghiệm, hợp đồng{' '}
          <select className="slot" aria-label="Loại hợp đồng" value={form.contract_type} onChange={set('contract_type')} style={{ width: chWidth(form.contract_type) }}>
            {contracts.map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}
          </select>
          , thuộc ngành{' '}
          <select className="slot" aria-label="Ngành nghề" value={form.category} onChange={set('category')} style={{ width: chWidth(catLabel, 10), maxWidth: '100%' }}>
            <option value="">để hệ thống tự nhận diện</option>
            {cats.map((c) => <option key={c.slug} value={c.slug}>{c.name}</option>)}
          </select>.
        </p>
        <div className="grid-2" style={{ maxWidth: 900, marginTop: 8 }}>
          <div className="field">
            <label htmlFor="sal-skills">Kỹ năng yêu cầu</label>
            <SkillInput id="sal-skills" value={form.skills} onChange={set('skills')} suggestions={skillNames} />
          </div>
          <div className="field">
            <label htmlFor="sal-langs">Ngoại ngữ</label>
            <SkillInput id="sal-langs" value={form.languages} onChange={set('languages')} suggestions={langs} placeholder="tiếng anh, tiếng nhật…" />
          </div>
        </div>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center', marginTop: 20 }}>
          <button className="btn" type="submit" disabled={busy}>{busy ? 'Đang dự đoán…' : 'Dự đoán lương'}</button>
          <span className="hint">Thử nhanh:</span>
          {EXAMPLES.map((ex) => (
            <button type="button" key={ex.title} className="btn ghost"
              onClick={() => setForm((f) => ({ ...f, languages: [], category: '', contract_type: 'Toàn thời gian', ...ex }))}>{ex.title}</button>
          ))}
        </div>
      </form>

      <ErrorBox error={err} />

      {res && (
        <>
          <div className="answer" aria-live="polite">
            <div className="big">{fmt(res.predicted)}<small>triệu đồng/tháng</small></div>
            <div className="range">
              80% khả năng nằm trong khoảng <strong>{fmt(res.low)}–{fmt(res.high)} triệu</strong>
              {res.auto_category && <><br />Ngành được nhận diện tự động: <strong>{res.auto_category.category}</strong></>}
            </div>
          </div>
          <div style={{ maxWidth: 760 }}>
            <div className="range-bar" role="img" aria-label={`Dự đoán ${fmt(res.predicted)} triệu, khoảng ${fmt(res.low)} đến ${fmt(res.high)} triệu, thang 0 đến ${scaleMax} triệu`}>
              <div className="band" style={{ left: `${(res.low / scaleMax) * 100}%`, width: `${((res.high - res.low) / scaleMax) * 100}%` }} />
              <div className="dot" style={{ left: `${(res.predicted / scaleMax) * 100}%` }} />
            </div>
            <div className="hint" style={{ display: 'flex', justifyContent: 'space-between' }}><span>0</span><span>{scaleMax} triệu</span></div>
          </div>

          <Section>
            <div className="grid-2" style={{ marginTop: 32 }}>
              <ChartBlock title="Các yếu tố đẩy lương lên hay kéo xuống"
                note={`So với mức nền ${fmt(res.baseline_salary)} triệu của một tin “trung bình”. Mô hình: ${res.model}`}
                table={res.factors.map((f) => ({ ...f, effect: signedPct(f.effect_pct) }))}
                columns={[{ key: 'factor', label: 'Nhóm yếu tố' }, { key: 'effect', label: 'Tác động', num: true }]}>
                <ResponsiveContainer width="100%" height={Math.max(180, res.factors.length * 34 + 20)}>
                  <BarChart data={res.factors} layout="vertical" margin={{ top: 4, right: 64, left: 0, bottom: 4 }}>
                    <CartesianGrid horizontal={false} stroke="#e4eae8" />
                    <XAxis type="number" domain={signedDomain} tickFormatter={(v) => `${Math.round(v)}%`} axisLine={false} tickLine={false} />
                    <YAxis type="category" dataKey="factor" width={120} tickLine={false} axisLine={false} tick={{ fontSize: 12.5, fill: '#3c4f57' }} />
                    <ReferenceLine x={0} stroke="#5d6e75" />
                    <Tooltip cursor={{ fill: '#eef6f4' }} content={<TooltipBox render={(d) => <><div className="t">{d.factor}</div>{signedPct(d.effect_pct)} so với mức nền</>} />} />
                    <Bar dataKey="effect_pct" isAnimationActive={false} radius={4} maxBarSize={20}>
                      {res.factors.map((f, i) => <Cell key={i} fill={f.effect_pct >= 0 ? '#00836c' : '#b8473a'} />)}
                      <LabelList dataKey="effect_pct" content={(p) => <SignedLabel {...p} format={signedPct} />} />
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </ChartBlock>
              <ChartBlock title="Vị trí của bạn trên thị trường"
                note={`Phân bố lương các tin cùng ngành; vạch vàng là mức dự đoán`} table={dist.data}
                columns={[{ key: 'range', label: 'Khoảng (triệu)' }, { key: 'count', label: 'Số tin', num: true, render: fmtInt }]}>
                {dist.data && (
                  <ResponsiveContainer width="100%" height={260}>
                    <BarChart data={dist.data} margin={{ top: 16, right: 8, left: -8, bottom: 0 }} barCategoryGap={2}>
                      <CartesianGrid vertical={false} stroke="#e4eae8" />
                      <XAxis dataKey="range" tickLine={false} interval="preserveStartEnd" minTickGap={14} tick={{ fontSize: 11 }} />
                      <YAxis tickLine={false} axisLine={false} tickFormatter={fmtInt} />
                      <Tooltip cursor={{ fill: '#eef6f4' }} content={<TooltipBox render={(d) => <><div className="t">{d.range} triệu</div>{fmtInt(d.count)} tin</>} />} />
                      <Bar dataKey="count" isAnimationActive={false} radius={[4, 4, 0, 0]}>
                        {dist.data.map((d, i) => <Cell key={i} fill={res.predicted >= d.from && res.predicted < d.to ? '#e3a521' : '#9fc9c0'} />)}
                      </Bar>
                      <ReferenceLine x={(dist.data.find((d) => res.predicted >= d.from && res.predicted < d.to) || dist.data[dist.data.length - 1]).range} stroke="#e3a521" strokeWidth={2}
                        label={{ value: `${fmt(res.predicted)} tr`, position: 'top', fill: '#7a5508', fontSize: 12 }} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </ChartBlock>
            </div>
          </Section>

          {res.top_features?.length > 0 && (
            <Section title="Đặc trưng cụ thể có ảnh hưởng lớn nhất" lede="Chỉ liệt kê các đặc trưng thực sự xuất hiện trong thông tin bạn nhập.">
              <div className="panel">
                <ul className="prob-list">
                  {res.top_features.map((f) => (
                    <li key={f.feature} style={{ gridTemplateColumns: '1fr 90px' }}>
                      <span>{f.feature}</span>
                      <span className="val" style={{ color: f.effect_pct >= 0 ? '#0a5f52' : '#b8473a', fontWeight: 600 }}>{signedPct(f.effect_pct)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </Section>
          )}
        </>
      )}
      <History task="salary" version={done} describe={(o) => `${fmt(o.predicted)} triệu (${fmt(o.low)}–${fmt(o.high)})`} />
    </>
  )
}
