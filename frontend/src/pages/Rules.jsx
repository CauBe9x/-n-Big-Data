import { useState } from 'react'
import { fmt, fmt3, fmtInt, pct, qs, useApi } from '../api.js'
import { DataTable, ErrorBox, Loading, PageHead } from '../components/ui.jsx'

const TABS = [
  { type: 'salary', label: 'Kỹ năng dẫn tới mức lương', help: 'Vế phải là nhóm lương (Cao = top 25%, Thấp = bottom 25% của tin có lương).' },
  { type: 'category', label: 'Kỹ năng đặc trưng của ngành', help: 'Vế phải là ngành nghề: nhìn thấy các kỹ năng này, tin gần như chắc chắn thuộc ngành đó.' },
  { type: 'skill', label: 'Kỹ năng hay đi cùng nhau', help: 'Vế phải là một kỹ năng khác: gợi ý học thêm gì khi đã có kỹ năng ở vế trái.' },
]

export default function Rules() {
  const [type, setType] = useState('salary')
  const [skill, setSkill] = useState('')
  const [minConf, setMinConf] = useState(0.3)
  const { data, error, loading } = useApi(`/api/mining/rules${qs({ type, skill, min_confidence: minConf, limit: 200 })}`)
  const tab = TABS.find((t) => t.type === type)

  return (
    <>
      <PageHead title="Luật kết hợp kỹ năng">
        Thuật toán FP-Growth tìm các tập kỹ năng hay xuất hiện cùng nhau trong một tin, rồi sinh luật dạng
        “nếu tin yêu cầu A thì thường cũng có B”. Mỗi tin là một giao dịch gồm kỹ năng, ngành và nhóm lương.
      </PageHead>
      <div className="tabs" role="tablist">
        {TABS.map((t) => (
          <button key={t.type} role="tab" className="tab" aria-selected={type === t.type} onClick={() => setType(t.type)}>{t.label}</button>
        ))}
      </div>
      <p className="hint" style={{ marginTop: -4 }}>{tab.help}</p>
      <div className="filters">
        <div className="field">
          <label htmlFor="r-skill">Lọc theo kỹ năng ở vế trái</label>
          <input id="r-skill" className="input" value={skill} onChange={(e) => setSkill(e.target.value)} placeholder="ví dụ: excel" />
        </div>
        <div className="field" style={{ minWidth: 240 }}>
          <label htmlFor="r-conf">Độ tin cậy tối thiểu: {pct(minConf, 0)}</label>
          <input id="r-conf" type="range" min="0.25" max="0.95" step="0.05" value={minConf} onChange={(e) => setMinConf(Number(e.target.value))} />
        </div>
      </div>
      <ErrorBox error={error} />
      {loading && !data && <Loading />}
      {data && (
        <>
          <p className="hint">
            {fmtInt(data.count)} luật phù hợp, từ {fmtInt(data.n_transactions)} giao dịch, độ hỗ trợ tối thiểu {pct(data.min_support)}.
            {data.salary_thresholds && <> Lương thấp ≤ {fmt(data.salary_thresholds['Thấp<='])} triệu, lương cao ≥ {fmt(data.salary_thresholds['Cao>='])} triệu.</>}
          </p>
          {data.rules.length === 0 ? (
            <p className="state">Không có luật nào thoả điều kiện. Hạ độ tin cậy tối thiểu hoặc xoá ô lọc kỹ năng.</p>
          ) : (
            <div className="panel">
              <DataTable rows={data.rules} columns={[
                { key: 'antecedents', label: 'Nếu tin yêu cầu', render: (v) => <div className="chips">{v.map((s) => <span className="chip" key={s}>{s}</span>)}</div> },
                { key: 'consequent', label: 'thì thường có', render: (v) => <strong>{v.replace('Ngành=', '').replace('Lương=', 'Lương ')}</strong> },
                { key: 'support', label: 'Độ hỗ trợ', num: true, render: (v) => pct(v, 2) },
                { key: 'confidence', label: 'Độ tin cậy', num: true, render: (v) => pct(v) },
                { key: 'lift', label: 'Lift', num: true, render: fmt3 },
              ]} />
            </div>
          )}
          <p className="hint" style={{ marginTop: 12 }}>
            Độ hỗ trợ: tỷ lệ tin chứa cả hai vế. Độ tin cậy: trong các tin có vế trái, bao nhiêu phần trăm có vế phải.
            Lift &gt; 1: hai vế xuất hiện cùng nhau nhiều hơn mức ngẫu nhiên.
          </p>
        </>
      )}
    </>
  )
}
