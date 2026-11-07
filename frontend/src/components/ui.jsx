import { useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { useApi } from '../api.js'

export function PageHead({ title, children }) {
  return (
    <header className="page-head">
      <h1>{title}</h1>
      {children && <p>{children}</p>}
    </header>
  )
}

export function Section({ title, lede, children }) {
  return (
    <section className="section">
      {title && <h2>{title}</h2>}
      {lede && <p className="lede">{lede}</p>}
      {children}
    </section>
  )
}

export function Loading({ text = 'Đang tải dữ liệu…' }) {
  return <div className="state" role="status">{text}</div>
}

/** Khung chờ theo đúng chiều cao các khối sắp hiện, tránh trang bị giật khi có dữ liệu. */
export function Skeleton({ lines = [120, 240] }) {
  return (
    <div className="skel" role="status" aria-label="Đang tải dữ liệu">
      {lines.map((h, i) => <i key={i} style={{ height: h }} />)}
    </div>
  )
}

export function ErrorBox({ error, onRetry }) {
  if (!error) return null
  const offline = /Failed to fetch|NetworkError/.test(error.message || '')
  return (
    <div className="state error" role="alert">
      <span>{offline ? 'Không kết nối được máy chủ API. Hãy chạy run.bat rồi thử lại.' : (error.message || String(error))}</span>
      {onRetry && <button type="button" className="btn ghost" onClick={onRetry}>Thử lại</button>}
    </div>
  )
}

/** Khung biểu đồ: tiêu đề, ghi chú, và nút chuyển sang dạng bảng (khả năng tiếp cận). */
export function ChartBlock({ title, note, table, columns, children }) {
  const [asTable, setAsTable] = useState(false)
  return (
    <div className="panel">
      <div className="chart-head">
        <div>
          <h3>{title}</h3>
          {note && <p className="note">{note}</p>}
        </div>
        {table && (
          <button className="toggle-table" onClick={() => setAsTable((v) => !v)} aria-pressed={asTable}>
            {asTable ? 'Xem biểu đồ' : 'Xem bảng'}
          </button>
        )}
      </div>
      {asTable && table ? <DataTable rows={table} columns={columns} /> : children}
    </div>
  )
}

export function DataTable({ rows, columns, rowClass }) {
  const cols = columns || Object.keys(rows[0] || {}).map((k) => ({ key: k, label: k }))
  return (
    <div className="table-wrap">
      <table className="data">
        <thead>
          <tr>{cols.map((c) => <th key={c.key} className={c.num ? 'num' : ''}>{c.label}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className={rowClass ? rowClass(r) : ''}>
              {cols.map((c) => (
                <td key={c.key} className={c.num ? 'num' : ''}>{c.render ? c.render(r[c.key], r) : r[c.key]}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function TooltipBox({ active, payload, label, render }) {
  if (!active || !payload || !payload.length) return null
  return <div className="chart-tooltip">{render(payload[0].payload, label)}</div>
}

const JADE = '#00836c'

/** Nhãn giá trị cho cột có dấu: số dương đặt sau đầu cột; số âm đặt ngay bên phải vạch 0
 *  (không đè lên tên trục ở bên trái). */
export function SignedLabel({ x, y, width, height, value, format = (v) => v }) {
  const right = Math.max(x, x + width)
  return (
    <text x={right + 6} y={y + height / 2} dy={4} textAnchor="start" fontSize={12}
      fill={value < 0 ? '#b8473a' : '#3c4f57'}>{format(value)}</text>
  )
}

/** Miền trục có chừa chỗ cho nhãn ở hai phía. */
export const signedDomain = [(min) => (min < 0 ? Math.floor((min * 1.1) / 10) * 10 : 0), (max) => Math.max(max > 0 ? Math.ceil((max * 1.3) / 10) * 10 : 0, 10)]

/** Biểu đồ cột ngang một chuỗi (so sánh độ lớn giữa các nhóm). */
export function HBar({ data, labelKey, valueKey, format = (v) => v, tooltip, height, highlight, highlightColor = '#e3a521', onBarClick, labelWidth = 190, maxChars = 30 }) {
  const h = height || Math.max(160, data.length * 30 + 30)
  return (
    <ResponsiveContainer width="100%" height={h}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 56, left: 0, bottom: 4 }} barCategoryGap={6}>
        <CartesianGrid horizontal={false} stroke="#e4eae8" />
        <XAxis type="number" tickFormatter={format} axisLine={false} tickLine={false} />
        <YAxis type="category" dataKey={labelKey} width={labelWidth} tickLine={false} axisLine={false}
          tick={{ fontSize: 12.5, fill: '#3c4f57' }} interval={0}
          tickFormatter={(v) => (String(v).length > maxChars ? String(v).slice(0, maxChars - 1) + '…' : v)} />
        <Tooltip cursor={{ fill: '#eef6f4' }} content={<TooltipBox render={tooltip || ((d) => <><div className="t">{d[labelKey]}</div>{format(d[valueKey])}</>)} />} />
        <Bar dataKey={valueKey} isAnimationActive={false} radius={[0, 4, 4, 0]} maxBarSize={22} onClick={onBarClick}
          cursor={onBarClick ? 'pointer' : undefined}>
          {data.map((d, i) => <Cell key={i} fill={highlight && highlight(d) ? highlightColor : JADE} />)}
          <LabelList dataKey={valueKey} position="right" formatter={format} style={{ fontSize: 12, fill: '#3c4f57' }} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

export function Select({ label, value, onChange, options, placeholder = 'Tất cả', id }) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <select id={id} className="select" value={value ?? ''} onChange={(e) => onChange(e.target.value || null)}>
        <option value="">{placeholder}</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </div>
  )
}

/** Ô nhập kỹ năng dạng chip, có gợi ý từ danh sách kỹ năng trong CSDL. */
export function SkillInput({ value, onChange, suggestions = [], id = 'skill-input', placeholder = 'Gõ kỹ năng rồi nhấn Enter' }) {
  const [text, setText] = useState('')
  const add = (s) => {
    const v = s.trim().toLowerCase()
    if (v && !value.includes(v)) onChange([...value, v])
    setText('')
  }
  return (
    <div>
      <input id={id} className="input" list={`${id}-list`} value={text} placeholder={placeholder}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); add(text) }
          if (e.key === 'Backspace' && !text && value.length) onChange(value.slice(0, -1))
        }}
        onBlur={() => text && add(text)} />
      <datalist id={`${id}-list`}>
        {suggestions.slice(0, 400).map((s) => <option key={s} value={s} />)}
      </datalist>
      {value.length > 0 && (
        <div className="chips" style={{ marginTop: 8 }}>
          {value.map((s) => (
            <span className="chip" key={s}>{s}
              <button aria-label={`Bỏ ${s}`} onClick={() => onChange(value.filter((x) => x !== s))}>×</button>
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

/** Các lượt dự đoán gần đây, đọc từ bảng predictions của PostgreSQL. */
export function History({ task, version, describe }) {
  const { data } = useApi(`/api/predict/history?task=${task}&limit=5&_=${version}`)
  if (!data?.length) return null
  return (
    <Section title="Lượt dự đoán gần đây" lede="Mỗi lượt được lưu vào bảng predictions kèm mô hình đã dùng.">
      <div className="panel">
        <ul className="history-list">
          {data.map((h) => (
            <li key={h.id}>
              <span>{h.input.title}</span>
              <span className="hint">{describe(h.output)}</span>
            </li>
          ))}
        </ul>
      </div>
    </Section>
  )
}

export function ProbList({ items, labelKey, valueKey = 'probability', dimIf }) {
  return (
    <ul className="prob-list">
      {items.map((it) => (
        <li key={it[labelKey]}>
          <span>{it[labelKey]}</span>
          <span className="prob-track" aria-hidden="true">
            <span className={`prob-fill ${dimIf && dimIf(it) ? 'dim' : ''}`} style={{ width: `${Math.max(2, it[valueKey] * 100)}%`, display: 'block' }} />
          </span>
          <span className="val">{(it[valueKey] * 100).toFixed(0)}%</span>
        </li>
      ))}
    </ul>
  )
}
