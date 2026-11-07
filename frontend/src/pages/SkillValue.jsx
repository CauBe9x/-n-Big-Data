import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, LabelList, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { fmt, fmtInt, qs, signedPct, useApi } from '../api.js'
import { ChartBlock, ErrorBox, Loading, PageHead, Section, SignedLabel, TooltipBox, signedDomain } from '../components/ui.jsx'

function PremiumChart({ rows }) {
  return (
    <ResponsiveContainer width="100%" height={Math.max(200, rows.length * 28 + 30)}>
      <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 64, left: 0, bottom: 4 }}>
        <CartesianGrid horizontal={false} stroke="#e4eae8" />
        <XAxis type="number" domain={signedDomain} tickFormatter={(v) => `${Math.round(v)}%`} axisLine={false} tickLine={false} />
        <YAxis type="category" dataKey="skill" width={170} tickLine={false} axisLine={false} interval={0} tick={{ fontSize: 12.5, fill: '#3c4f57' }} />
        <ReferenceLine x={0} stroke="#5d6e75" />
        <Tooltip cursor={{ fill: '#eef6f4' }} content={<TooltipBox render={(d) => <><div className="t">{d.skill}</div>
          Lương trung vị {fmt(d.median_salary)} triệu ({signedPct(d['premium_%'])})<br />{fmtInt(d.n_jobs)} tin, ngành chính: {d.top_category}</>} />} />
        <Bar dataKey="premium_%" isAnimationActive={false} radius={4} maxBarSize={18}>
          {rows.map((r, i) => <Cell key={i} fill={r['premium_%'] >= 0 ? '#00836c' : '#b8473a'} />)}
          <LabelList dataKey="premium_%" content={(p) => <SignedLabel {...p} format={signedPct} />} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

export default function SkillValue() {
  const [kind, setKind] = useState('technical')
  const [minJobs, setMinJobs] = useState(50)
  const { data, error, loading } = useApi(`/api/mining/skill-value${qs({ kind, sort: 'premium', min_jobs: minJobs, limit: 500 })}`)
  const top = data ? data.slice(0, 15) : []
  const bottom = data ? [...data].slice(-12).reverse() : []
  const cols = [
    { key: 'skill', label: 'Kỹ năng' }, { key: 'n_jobs', label: 'Số tin', num: true, render: fmtInt },
    { key: 'median_salary', label: 'Lương trung vị', num: true, render: fmt },
    { key: 'premium_%', label: 'Chênh lệch', num: true, render: signedPct }, { key: 'top_category', label: 'Ngành chính' },
  ]

  return (
    <>
      <PageHead title="Kỹ năng và mức lương">
        Với mỗi kỹ năng, lấy lương trung vị của các tin có yêu cầu kỹ năng đó rồi so với lương trung vị toàn thị trường.
        Đây là tương quan, chưa phải nhân quả: kỹ năng “đắt” thường đi kèm ngành hoặc vị trí cấp cao.
      </PageHead>
      <div className="tabs" role="tablist">
        {[['technical', 'Kỹ năng chuyên môn'], ['soft', 'Kỹ năng mềm']].map(([k, l]) => (
          <button key={k} role="tab" className="tab" aria-selected={kind === k} onClick={() => setKind(k)}>{l}</button>
        ))}
      </div>
      <div className="filters">
        <div className="field" style={{ minWidth: 260 }}>
          <label htmlFor="minj">Chỉ xét kỹ năng có ít nhất {minJobs} tin có lương</label>
          <input id="minj" type="range" min="30" max="500" step="10" value={minJobs} onChange={(e) => setMinJobs(Number(e.target.value))} />
        </div>
      </div>
      <ErrorBox error={error} />
      {loading && <Loading />}
      {data && data.length === 0 && <p className="state">Không có kỹ năng nào đủ số tin. Kéo thanh trượt sang trái.</p>}
      {data && data.length > 0 && (
        <Section>
          <div className="grid-2">
            <ChartBlock title="Đi kèm lương cao hơn thị trường" note="15 kỹ năng có chênh lệch dương lớn nhất" table={top} columns={cols}>
              <PremiumChart rows={top} />
            </ChartBlock>
            <ChartBlock title="Đi kèm lương thấp hơn thị trường" note="12 kỹ năng có chênh lệch thấp nhất" table={bottom} columns={cols}>
              <PremiumChart rows={bottom} />
            </ChartBlock>
          </div>
        </Section>
      )}
    </>
  )
}
