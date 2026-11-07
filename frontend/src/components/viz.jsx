/* Các dạng biểu đồ HTML dùng chung. Quy ước màu của toàn ứng dụng:
   - Một chuỗi số liệu: ngọc bích. Độ lớn trên lưới: một tông ngọc từ nhạt đến đậm.
   - Trên/dưới mốc so sánh: ngọc (trên) và gạch (dưới), mốc là xám.
   - Vàng nghệ chỉ dành cho điểm đang được nhấn mạnh. */
import { fmt, fmtInt } from '../api.js'

/** Dải P25–P75 kèm vạch trung vị trên một thang chung cho mọi hàng. */
export function RangeBar({ row, max }) {
  if (row.median == null) return <span className="hint">Quá ít tin có lương</span>
  const pos = (v) => `${Math.min(100, (v / max) * 100)}%`
  return (
    <div className="rng" role="img"
      aria-label={`Trung vị ${fmt(row.median)} triệu, nửa giữa từ ${fmt(row.p25)} đến ${fmt(row.p75)} triệu`}
      title={`P25 ${fmt(row.p25)} · trung vị ${fmt(row.median)} · P75 ${fmt(row.p75)} triệu`}>
      <div className="rng-band" style={{ left: pos(row.p25), width: `calc(${pos(row.p75)} - ${pos(row.p25)})` }} />
      <div className="rng-mid" style={{ left: pos(row.median) }} />
    </div>
  )
}

export const rangeMax = (rows) => Math.max(10, ...rows.map((r) => r.p75 || 0)) * 1.04

/** Danh sách nhóm: tên, số tin, dải lương. Bấm một hàng để lọc theo nhóm đó (nếu có onPick). */
export function RangeList({ rows, labelKey, keyOf, activeKey, onPick, max }) {
  const scale = max || rangeMax(rows)
  return (
    <ul className="rng-list">
      {rows.map((r) => {
        const k = keyOf ? keyOf(r) : r[labelKey]
        const active = activeKey === k
        const body = (
          <>
            <span className="rng-label">{r[labelKey]}</span>
            <span className="rng-n">{fmtInt(r.jobs)} tin</span>
            <RangeBar row={r} max={scale} />
            <span className="rng-val">{r.median == null ? '–' : `${fmt(r.median)} tr`}</span>
          </>
        )
        return (
          <li key={k}>
            {onPick
              ? <button type="button" className={`rng-row ${active ? 'on' : ''}`} aria-pressed={active} onClick={() => onPick(active ? null : k)}>{body}</button>
              : <div className="rng-row static">{body}</div>}
          </li>
        )
      })}
    </ul>
  )
}

/** Chú giải cho dải lương. */
export function RangeLegend() {
  return (
    <p className="rng-legend">
      <span className="swatch band" aria-hidden="true" /> nửa giữa của mức lương (P25–P75)
      <span className="swatch tick" aria-hidden="true" /> trung vị
    </p>
  )
}

const HEAT = ['#e4f1ee', '#c3e1da', '#94ccc0', '#5fb1a2', '#2c9181', '#0a6f60']

/** Lưới ngành × kinh nghiệm. Ô ít mẫu để trống, không suy đoán. */
export function Heatmap({ data, activeSlug, onPick }) {
  const values = data.rows.flatMap((r) => Object.values(r.cells).map((c) => c.median)).filter((v) => v != null).sort((a, b) => a - b)
  if (!values.length) return <p className="state">Không đủ tin có lương để so sánh theo ngành và kinh nghiệm.</p>
  const lo = values[0]
  const hi = values[Math.floor(values.length * 0.97)]
  const klass = (v) => Math.min(HEAT.length - 1, Math.floor(((v - lo) / Math.max(1, hi - lo)) * HEAT.length))
  return (
    <>
      <div className="table-wrap">
        <table className="heat">
          <thead>
            <tr><th scope="col">Ngành</th>{data.columns.map((c) => <th key={c} scope="col">{c}</th>)}</tr>
          </thead>
          <tbody>
            {data.rows.map((r) => (
              <tr key={r.slug} className={activeSlug === r.slug ? 'on' : ''}>
                <th scope="row">
                  <button type="button" onClick={() => onPick(activeSlug === r.slug ? null : r.slug)}>{r.category}</button>
                </th>
                {data.columns.map((c) => {
                  const cell = r.cells[c]
                  if (!cell || cell.median == null) {
                    return <td key={c} className="empty" title={`${r.category}, ${c}: ${cell ? cell.n : 0} tin có lương, chưa đủ ${data.min_n} tin`}>·</td>
                  }
                  const i = klass(cell.median)
                  return (
                    <td key={c} style={{ background: HEAT[i], color: i >= 4 ? '#fff' : 'var(--ink)' }}
                      title={`${r.category}, ${c}: trung vị ${fmt(cell.median)} triệu, ${fmtInt(cell.n)} tin có lương`}>
                      {fmt(cell.median)}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="heat-legend">
        <span>{fmt(lo)} triệu</span>
        <span className="heat-ramp" aria-hidden="true">{HEAT.map((c) => <i key={c} style={{ background: c }} />)}</span>
        <span>từ {fmt(hi)} triệu</span>
        <span className="hint">· ô trống: dưới {data.min_n} tin có lương</span>
      </div>
    </>
  )
}

/** Thanh hai chiều quanh mốc 0, thang chung cho cả danh sách. */
export function DivergeBar({ value, max }) {
  if (value == null) return <span className="hint">–</span>
  const w = `${Math.min(50, (Math.abs(value) / max) * 50)}%`
  return (
    <span className="div-bar" aria-hidden="true">
      <i className={value >= 0 ? 'up' : 'down'} style={value >= 0 ? { left: '50%', width: w } : { right: '50%', width: w }} />
    </span>
  )
}

/** Tỷ lệ so với 100%. */
export function Meter({ value }) {
  return <span className="meter" aria-hidden="true"><i style={{ width: `${Math.min(100, value)}%` }} /></span>
}

export function StatusDot({ status, children }) {
  const label = { pass: 'Đạt', fail: 'Lệch', skipped: 'Chưa kiểm', success: 'Thành công', failed: 'Lỗi', running: 'Đang chạy' }[status] || status
  const icon = { pass: '✓', success: '✓', fail: '✕', failed: '✕', skipped: '–', running: '…' }[status] || '•'
  return <span className={`status ${status}`}><span aria-hidden="true">{icon}</span> {children || label}</span>
}
