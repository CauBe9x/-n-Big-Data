import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useMeta } from '../App.jsx'
import { fmt, fmtInt, qs, signedPct, useApi } from '../api.js'
import { ChartBlock, ErrorBox, PageHead, Section, Select, Skeleton, TooltipBox } from '../components/ui.jsx'
import { DivergeBar, Heatmap, RangeBar, RangeLegend, RangeList, rangeMax } from '../components/viz.jsx'

const KEYS = ['region', 'province', 'category', 'experience', 'contract_type']
const REGIONS = ['Miền Bắc', 'Miền Trung', 'Miền Nam', 'Khác']
const SORTS = [
  { key: 'jobs', label: 'Số tin' },
  { key: 'median', label: 'Lương' },
  { key: 'negotiable_pct', label: 'Tỷ lệ thoả thuận' },
]

function Delta({ value, base, unit }) {
  if (value == null || base == null || value === base) return null
  const d = value - base
  return <span className={`delta ${d > 0 ? 'up' : 'down'}`}>{d > 0 ? '▲' : '▼'} {fmt(Math.abs(d))}{unit} so với toàn thị trường</span>
}

function Headline({ k, market, filtered }) {
  return (
    <div className="headline">
      <div className="hero-figure">
        <span className="eyebrow">Lương trung vị</span>
        <div className="big">{k.median == null ? '–' : fmt(k.median)}<small>triệu đồng/tháng</small></div>
        <p>Một nửa số tin nằm trong khoảng <strong>{fmt(k.p25)}–{fmt(k.p75)} triệu</strong>. Trung bình cộng {fmt(k.mean)} triệu.</p>
        {filtered && <Delta value={k.median} base={market.median} unit=" triệu" />}
      </div>
      <dl className="stat-list">
        <div><dt>Tin tuyển dụng</dt><dd>{fmtInt(k.jobs)}</dd>
          <p>{filtered ? `${fmt((k.jobs * 100) / market.jobs)}% toàn bộ dữ liệu` : 'sau khi gộp tin trùng'}</p></div>
        <div><dt>Công bố lương</dt><dd>{fmtInt(k.with_salary)}</dd>
          <p>{k.negotiable_pct == null ? '' : `${fmt(k.negotiable_pct)}% tin ghi “thoả thuận”`}</p></div>
        <div><dt>Yêu cầu ngoại ngữ</dt><dd>{k.language_pct == null ? '–' : `${fmt(k.language_pct)}%`}</dd>
          <p>{filtered ? `Toàn thị trường: ${fmt(market.language_pct)}%` : 'trên tổng số tin'}</p></div>
      </dl>
    </div>
  )
}

function Histogram({ data, median }) {
  const medianBin = data.findIndex((b) => median >= b.from && (b.to == null || median < b.to))
  return (
    <ResponsiveContainer width="100%" height={270}>
      <BarChart data={data} margin={{ top: 8, right: 4, left: -14, bottom: 0 }} barCategoryGap={1}>
        <CartesianGrid vertical={false} stroke="#e4eae8" />
        <XAxis dataKey="from" tickLine={false} interval={4} tickFormatter={(v) => (v === 60 ? '60+' : v)} />
        <YAxis tickLine={false} axisLine={false} tickFormatter={fmtInt} />
        <Tooltip cursor={{ fill: '#eef6f4' }} content={<TooltipBox render={(d) => <><div className="t">{d.range} triệu</div>{fmtInt(d.count)} tin</>} />} />
        <Bar dataKey="count" radius={[3, 3, 0, 0]} isAnimationActive={false}>
          {data.map((d, i) => <Cell key={d.from} fill={i === medianBin ? '#e3a521' : '#00836c'} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

function CategoryTable({ rows, active, onPick }) {
  const [sort, setSort] = useState('jobs')
  const sorted = useMemo(() => [...rows].sort((a, b) => (b[sort] ?? -1) - (a[sort] ?? -1)), [rows, sort])
  const scale = rangeMax(rows)
  const maxJobs = Math.max(...rows.map((r) => r.jobs), 1)
  return (
    <>
      <div className="seg" role="group" aria-label="Sắp xếp bảng ngành">
        <span className="hint">Sắp xếp theo</span>
        {SORTS.map((s) => <button key={s.key} type="button" aria-pressed={sort === s.key} onClick={() => setSort(s.key)}>{s.label}</button>)}
      </div>
      <div className="table-wrap">
        <table className="cat-table">
          <thead><tr><th scope="col">Ngành</th><th scope="col" className="num">Số tin</th><th scope="col">Lương P25–P75</th><th scope="col" className="num">Trung vị</th><th scope="col" className="num">Thoả thuận</th></tr></thead>
          <tbody>
            {sorted.map((r) => (
              <tr key={r.slug} className={active === r.slug ? 'on' : ''}>
                <th scope="row"><button type="button" aria-pressed={active === r.slug} onClick={() => onPick(active === r.slug ? null : r.slug)}>{r.name}</button></th>
                <td className="num"><span className="inline-bar"><i style={{ width: `${(r.jobs / maxJobs) * 100}%` }} /></span>{fmtInt(r.jobs)}</td>
                <td className="w-range"><RangeBar row={r} max={scale} /></td>
                <td className="num"><strong>{r.median == null ? '–' : fmt(r.median)}</strong></td>
                <td className="num">{fmt(r.negotiable_pct)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

function SkillTable({ rows }) {
  const scale = Math.max(10, ...rows.map((r) => Math.abs(r.premium_pct || 0)))
  const maxShare = Math.max(...rows.map((r) => r.share_pct), 1)
  return (
    <div className="table-wrap">
      <table className="cat-table">
        <thead><tr><th scope="col">Kỹ năng</th><th scope="col" className="num">Tỷ lệ tin yêu cầu</th><th scope="col">Lương so với nhóm đang xem</th><th scope="col" className="num">Chênh lệch</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.skill}>
              <th scope="row" className="plain">{r.skill}</th>
              <td className="num"><span className="inline-bar"><i style={{ width: `${(r.share_pct / maxShare) * 100}%` }} /></span>{fmt(r.share_pct)}%</td>
              <td className="w-range"><DivergeBar value={r.premium_pct} max={scale} /></td>
              <td className="num">{r.premium_pct == null ? '–' : signedPct(r.premium_pct)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function Dashboard() {
  const meta = useMeta()
  const [params, setParams] = useSearchParams()
  const [skillKind, setSkillKind] = useState('technical')
  const filters = Object.fromEntries(KEYS.map((k) => [k, params.get(k)]))
  const active = KEYS.filter((k) => filters[k])
  const { data: d, error, loading, reload } = useApi(`/api/dashboard${qs(filters)}`)

  const setFilter = (key, value) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value); else next.delete(key)
    if (key === 'region') next.delete('province')
    setParams(next, { replace: true })
  }
  const pick = (key) => (v) => setFilter(key, v)
  const filtered = active.length > 0
  const catName = (meta.data?.categories || []).find((c) => c.slug === filters.category)?.name

  return (
    <>
      <PageHead title="Dashboard thị trường tuyển dụng">
        Toàn bộ số liệu được tính từ PostgreSQL theo bộ lọc bạn chọn. Bấm vào một ngành, một tỉnh hoặc một hàng trong lưới để lọc nhanh.
      </PageHead>

      <div className="filter-bar" role="search" aria-label="Bộ lọc dashboard">
        <Select id="d-region" label="Miền" value={filters.region} onChange={pick('region')} options={REGIONS.map((r) => ({ value: r, label: r }))} />
        <Select id="d-prov" label="Tỉnh / thành" value={filters.province} onChange={pick('province')}
          options={(meta.data?.provinces || []).map((p) => ({ value: p.name, label: p.name }))} />
        <Select id="d-cat" label="Ngành" value={filters.category} onChange={pick('category')}
          options={(meta.data?.categories || []).map((c) => ({ value: c.slug, label: c.name }))} />
        <Select id="d-exp" label="Kinh nghiệm" value={filters.experience} onChange={pick('experience')}
          options={(meta.data?.experience_buckets || []).map((b) => ({ value: b, label: b }))} />
        <Select id="d-con" label="Hợp đồng" value={filters.contract_type} onChange={pick('contract_type')}
          options={(meta.data?.contract_types || []).map((c) => ({ value: c.name, label: c.name }))} />
        {filtered && <button type="button" className="btn ghost clear" onClick={() => setParams({}, { replace: true })}>Xoá {active.length} bộ lọc</button>}
        {loading && d && <span className="spin" role="status">Đang tính lại…</span>}
      </div>

      <ErrorBox error={error} onRetry={reload} />
      {!d && loading && <Skeleton lines={[150, 90, 300, 420]} />}

      {d && d.kpi.jobs === 0 && (
        <div className="empty-state">
          <h2>Không có tin nào khớp bộ lọc này</h2>
          <p>{catName ? `Ngành ${catName} không có tin` : 'Không có tin'} với tổ hợp điều kiện đang chọn. Hãy bỏ bớt một điều kiện.</p>
          <button type="button" className="btn" onClick={() => setParams({}, { replace: true })}>Xem toàn bộ thị trường</button>
        </div>
      )}

      {d && d.kpi.jobs > 0 && (
        <div className={loading ? 'dim-while-loading' : ''}>
          <Headline k={d.kpi} market={d.market} filtered={filtered} />

          {d.insights.length > 0 && (
            <Section title="Dữ liệu đang cho thấy điều gì">
              <ol className="insights">
                {d.insights.map((i) => <li key={i.title}><strong>{i.title}</strong><span>{i.text}</span></li>)}
              </ol>
            </Section>
          )}

          <Section title="Phân bố và lộ trình lương">
            <div className="grid-2">
              <ChartBlock title="Mức lương phân bố lệch phải"
                note="Số tin theo từng khoảng 2 triệu. Cột vàng chứa trung vị. Lương từ 60 triệu trở lên được gộp vào cột cuối."
                table={d.histogram} columns={[{ key: 'range', label: 'Khoảng (triệu)' }, { key: 'count', label: 'Số tin', num: true, render: fmtInt }]}>
                <Histogram data={d.histogram} median={d.kpi.median} />
              </ChartBlock>
              <ChartBlock title="Lương tăng theo kinh nghiệm"
                note="Bấm một nhóm để lọc. Nhóm trên 5 năm có rất ít tin công bố lương nên dao động rộng.">
                <RangeList rows={d.experience} labelKey="bucket" activeKey={filters.experience} onPick={pick('experience')} />
                <RangeLegend />
              </ChartBlock>
            </div>
          </Section>

          <Section title="So sánh các ngành"
            lede="Một tin thuộc nhiều ngành được tính ở mọi ngành của nó, vì vậy tổng cột Số tin lớn hơn tổng số tin. Bảng luôn hiện đủ ngành để so sánh, kể cả khi đang lọc một ngành.">
            <div className="panel">
              <CategoryTable rows={d.categories} active={filters.category} onPick={pick('category')} />
              <RangeLegend />
            </div>
          </Section>

          <Section title="Ngành nào trả cao ở từng mức kinh nghiệm" lede="Lương trung vị (triệu đồng/tháng). Tính trên bộ lọc miền, tỉnh và hợp đồng.">
            <div className="panel">
              <Heatmap data={d.heatmap} activeSlug={filters.category} onPick={pick('category')} />
            </div>
          </Section>

          <Section title="Địa lý">
            <div className="grid-2">
              <ChartBlock title="Theo miền" note="Miền “Khác” gồm tin ở nước ngoài và tin không xác định được địa điểm, nên không so sánh với ba miền còn lại.">
                <RangeList rows={d.regions} labelKey="region" activeKey={filters.region} onPick={pick('region')} />
                <RangeLegend />
              </ChartBlock>
              <ChartBlock title="12 tỉnh/thành nhiều tin nhất" note="Bấm một tỉnh để lọc.">
                <RangeList rows={d.provinces} labelKey="province" activeKey={filters.province} onPick={pick('province')} />
              </ChartBlock>
            </div>
          </Section>

          <Section title="Kỹ năng được yêu cầu và mức lương đi kèm"
            lede={`Chênh lệch là lương trung vị của các tin có yêu cầu kỹ năng so với lương trung vị của nhóm đang xem. Đây là tương quan, không phải nhân quả. Kỹ năng dưới ${d.rules.min_skill_n} tin có lương không tính chênh lệch.`}>
            <div className="panel">
              <div className="tabs" role="tablist">
                <button role="tab" className="tab" aria-selected={skillKind === 'technical'} onClick={() => setSkillKind('technical')}>Kỹ năng chuyên môn</button>
                <button role="tab" className="tab" aria-selected={skillKind === 'soft'} onClick={() => setSkillKind('soft')}>Kỹ năng mềm</button>
              </div>
              {d.skills[skillKind].length
                ? <SkillTable rows={d.skills[skillKind]} />
                : <p className="state">Nhóm đang xem không có tin nào nêu kỹ năng loại này.</p>}
            </div>
          </Section>

          <Section title="Ngoại ngữ và loại hợp đồng">
            <div className="grid-2">
              <ChartBlock title="Theo yêu cầu ngoại ngữ" note="Một tin yêu cầu hai ngoại ngữ được tính ở cả hai hàng.">
                <RangeList rows={d.languages} labelKey="language" />
                <RangeLegend />
              </ChartBlock>
              <ChartBlock title="Theo loại hợp đồng" note="Bán thời gian và thực tập kéo lương xuống rõ rệt, nên cần tách riêng khi so sánh.">
                <RangeList rows={d.contracts} labelKey="contract_type" activeKey={filters.contract_type} onPick={pick('contract_type')} />
                <RangeLegend />
              </ChartBlock>
            </div>
          </Section>

          <p className="method-note">
            <strong>Cách đọc số liệu.</strong> Lương chỉ tính trên tin công bố lương trong khoảng {d.rules.salary_range[0]}–{d.rules.salary_range[1]} triệu/tháng;
            nhóm dưới {d.rules.min_group_n} tin có lương không hiện trung vị.{' '}
            <strong>Vì sao không có biểu đồ theo thời gian?</strong> Bộ dữ liệu không có cột ngày đăng tin nên không thể tính xu hướng theo thời gian một cách trung thực;
            biểu đồ lương theo kinh nghiệm là “xu hướng” duy nhất có cơ sở từ dữ liệu.
          </p>
        </div>
      )}
    </>
  )
}
