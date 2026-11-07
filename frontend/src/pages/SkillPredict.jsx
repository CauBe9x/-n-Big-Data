import { useState } from 'react'
import { Link } from 'react-router-dom'
import { post } from '../api.js'
import { ErrorBox, History, PageHead, ProbList, Section } from '../components/ui.jsx'

const EXAMPLES = ['Data Analyst', 'Kế toán tổng hợp', 'Kỹ sư xây dựng', 'Nhân viên marketing online', 'Lễ tân khách sạn', 'Kỹ sư điện tự động hóa']

export default function SkillPredict() {
  const [title, setTitle] = useState('Data Analyst')
  const [res, setRes] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(0)

  const run = async (t = title) => {
    setBusy(true); setErr(null)
    try { setRes(await post('/api/predict/skills', { title: t, top_k: 15 })); setDone((n) => n + 1) }
    catch (x) { setErr(x) } finally { setBusy(false) }
  }

  return (
    <>
      <PageHead title="Gợi ý kỹ năng cần có">
        Nhập tên vị trí, mô hình phân loại đa nhãn sẽ trả về những kỹ năng mà nhà tuyển dụng thường đòi hỏi cho vị trí đó,
        kèm xác suất. Kỹ năng vượt ngưỡng của mô hình được đánh dấu là “nên có”.
      </PageHead>
      <form onSubmit={(e) => { e.preventDefault(); run() }} style={{ maxWidth: 760 }}>
        <div className="field">
          <label htmlFor="sk-title">Chức danh</label>
          <input id="sk-title" className="input" value={title} onChange={(e) => setTitle(e.target.value)} required
            style={{ fontSize: 20, padding: '12px 14px' }} />
        </div>
        <div style={{ height: 12 }} />
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <button className="btn" disabled={busy}>{busy ? 'Đang phân tích…' : 'Gợi ý kỹ năng'}</button>
          {EXAMPLES.map((ex) => (
            <button type="button" key={ex} className="btn ghost" onClick={() => { setTitle(ex); run(ex) }}>{ex}</button>
          ))}
        </div>
      </form>
      <ErrorBox error={err} />

      {res && (
        <Section>
          <div className="grid-2" style={{ marginTop: 32 }}>
            <div className="panel">
              <div className="chart-head"><div><h3>Kỹ năng chuyên môn</h3>
                <p className="note">Thanh đậm: nên có (xác suất ≥ {Math.round(res.threshold * 100)}%)</p></div></div>
              <ProbList items={res.technical} labelKey="skill" dimIf={(it) => !it.recommended} />
            </div>
            <div className="panel">
              <div className="chart-head"><div><h3>Kỹ năng mềm</h3>
                <p className="note">Kỹ năng mềm thường chung cho nhiều ngành nên xác suất thấp và đồng đều hơn</p></div></div>
              <ProbList items={res.soft} labelKey="skill" dimIf={(it) => !it.recommended} />
            </div>
          </div>
          <p className="hint" style={{ marginTop: 16 }}>
            Mô hình: {res.model}. Muốn biết kỹ năng nào gắn với lương cao, xem trang <Link to="/mining/skill-value">Kỹ năng & mức lương</Link>.
          </p>
        </Section>
      )}
      <History task="skills" version={done} describe={(o) => o.technical.slice(0, 4).join(', ')} />
    </>
  )
}
