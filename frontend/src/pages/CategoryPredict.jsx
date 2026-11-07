import { useState } from 'react'
import { post } from '../api.js'
import { ErrorBox, History, PageHead, ProbList, Section } from '../components/ui.jsx'

const SAMPLE = {
  title: 'Nhân viên vận hành hệ thống xử lý nước thải',
  description: 'Vận hành hằng ngày các công trình xử lý nước thải; châm hoá chất, test nhanh thông số vận hành, kiểm tra máy móc thiết bị; ghi chép số liệu và báo cáo.',
}

export default function CategoryPredict() {
  const [title, setTitle] = useState(SAMPLE.title)
  const [desc, setDesc] = useState(SAMPLE.description)
  const [res, setRes] = useState(null)
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(0)

  const run = async (e) => {
    e?.preventDefault()
    setBusy(true); setErr(null)
    try { setRes(await post('/api/predict/category', { title, description: desc || null, top_k: 5 })); setDone((n) => n + 1) }
    catch (x) { setErr(x) } finally { setBusy(false) }
  }

  return (
    <>
      <PageHead title="Phân loại ngành nghề">
        Dán tiêu đề và mô tả của một tin tuyển dụng bất kỳ, mô hình phân loại văn bản sẽ xếp tin vào một trong 16 nhóm ngành.
        Đây là bài toán thứ nhất trong bài báo gốc của bộ dữ liệu VietJobs.
      </PageHead>
      <form onSubmit={run} style={{ maxWidth: 820 }}>
        <div className="field" style={{ marginBottom: 12 }}>
          <label htmlFor="c-title">Tiêu đề tin</label>
          <input id="c-title" className="input" value={title} onChange={(e) => setTitle(e.target.value)} required />
        </div>
        <div className="field" style={{ marginBottom: 12 }}>
          <label htmlFor="c-desc">Mô tả công việc</label>
          <textarea id="c-desc" className="textarea" value={desc} onChange={(e) => setDesc(e.target.value)} />
        </div>
        <button className="btn" disabled={busy}>{busy ? 'Đang phân loại…' : 'Phân loại'}</button>
      </form>
      <ErrorBox error={err} />
      {res && (
        <Section>
          <div className="panel" style={{ marginTop: 32, maxWidth: 820 }} aria-live="polite">
            <p style={{ fontSize: 22, margin: '0 0 16px', fontWeight: 300 }}>
              Tin này thuộc nhóm <strong style={{ fontWeight: 700 }}>{res.predictions[0].category}</strong>
            </p>
            <ProbList items={res.predictions} labelKey="category" valueKey="score" dimIf={(it) => it !== res.predictions[0]} />
            <p className="hint" style={{ marginTop: 12 }}>
              Mô hình: {res.model}. {res.model.includes('SVM') ? 'Điểm là softmax của khoảng cách tới siêu phẳng (điểm tương đối, không phải xác suất hiệu chỉnh).' : 'Điểm là xác suất dự đoán.'}
            </p>
          </div>
        </Section>
      )}
      <History task="category" version={done} describe={(o) => o.top} />
    </>
  )
}
