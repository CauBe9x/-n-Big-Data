import { useState } from 'react'
import { CartesianGrid, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from 'recharts'
import { fmt, fmt3, fmtInt, useApi } from '../api.js'
import { ChartBlock, DataTable, ErrorBox, HBar, Loading, PageHead, Section, TooltipBox } from '../components/ui.jsx'

const n3 = (v) => (v === undefined ? '–' : fmt3(v))

function modelRows(results, split = 'test') {
  return Object.entries(results).map(([name, r]) => ({ name, ...r[split], seconds: r.train_seconds }))
}

/** Ma trận nhầm lẫn dạng heatmap một màu (đậm = nhiều), chuẩn hoá theo hàng (recall). */
function Confusion({ labels, matrix }) {
  const short = (s) => (s.length > 40 ? s.slice(0, 39) + '…' : s)
  return (
    <div className="table-wrap">
      <table className="data" style={{ fontSize: 11.5 }}>
        <thead>
          <tr><th>Thực tế \ Dự đoán</th>{labels.map((l, j) => <th key={j} title={l} className="num">{j + 1}</th>)}</tr>
        </thead>
        <tbody>
          {matrix.map((row, i) => {
            const total = row.reduce((a, b) => a + b, 0) || 1
            return (
              <tr key={i}>
                <td title={labels[i]} style={{ whiteSpace: 'nowrap' }}>{i + 1}. {short(labels[i])}</td>
                {row.map((v, j) => {
                  const r = v / total
                  return (
                    <td key={j} className="num" title={`${labels[i]} → ${labels[j]}: ${v} tin (${Math.round(r * 100)}%)`}
                      style={{ background: v ? `rgba(14,122,106,${0.08 + r * 0.92})` : 'transparent', color: r > 0.5 ? '#fff' : '#15262e', padding: '6px 6px' }}>
                      {v || ''}
                    </td>
                  )
                })}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export default function Models() {
  const { data, error, loading } = useApi('/api/models/reports')
  const [tab, setTab] = useState('salary')
  const s = data?.salary, c = data?.category, k = data?.skills

  return (
    <>
      <PageHead title="Đánh giá mô hình">
        Mỗi bài toán so sánh một mô hình cơ sở (baseline) với các mô hình máy học. Dữ liệu chia 80/10/10 (train/validation/test)
        như bài báo gốc; mô hình tốt nhất được chọn trên tập validation và báo cáo trên tập test.
      </PageHead>
      <ErrorBox error={error} />
      {loading && <Loading />}
      <div className="tabs" role="tablist">
        {[['salary', 'Dự đoán lương'], ['skills', 'Dự đoán kỹ năng'], ['category', 'Phân loại ngành']].map(([key, l]) => (
          <button key={key} role="tab" className="tab" aria-selected={tab === key} onClick={() => setTab(key)}>{l}</button>
        ))}
      </div>

      {tab === 'salary' && s && (
        <>
          <Section title="Hồi quy mức lương" lede={`Mục tiêu: ${s.target}. Train ${fmtInt(s.n_train)}, validation ${fmtInt(s.n_val)}, test ${fmtInt(s.n_test)} tin. Mô hình học trên log(1+lương) rồi đổi ngược.`}>
            <div className="panel">
              <DataTable rows={modelRows(s.results)} rowClass={(r) => (r.name === s.best_model ? 'best' : '')} columns={[
                { key: 'name', label: 'Mô hình', render: (v) => <>{v}{v === s.best_model && <> <span className="pill">tốt nhất</span></>}</> },
                { key: 'RMSE', label: 'RMSE (triệu)', num: true, render: n3 }, { key: 'MAE', label: 'MAE (triệu)', num: true, render: n3 },
                { key: 'R2', label: 'R²', num: true, render: n3 }, { key: 'MAPE_%', label: 'MAPE %', num: true, render: fmt },
                { key: 'within_20%', label: 'Sai ≤ 20%', num: true, render: (v) => `${fmt(v)}%` }, { key: 'seconds', label: 'Thời gian (s)', num: true, render: fmt },
              ]} />
              <p className="hint" style={{ marginTop: 12 }}>
                Tham chiếu bài báo VietJobs (LREC 2026): {s.paper_reference.model} (fine-tune trên cả hai bộ dữ liệu) đạt RMSE {s.paper_reference.RMSE}, R² {s.paper_reference.R2}
                {' '}(chỉ dùng chức danh, hợp đồng, địa điểm, quốc gia, kinh nghiệm; cách chia tập khác nên chỉ so sánh tương đối).
                {s.results[s.best_model]['interval_80_coverage_%'] !== undefined &&
                  ` Khoảng dự đoán 80% bao phủ ${fmt(s.results[s.best_model]['interval_80_coverage_%'])}% giá trị thật trên tập test.`}
              </p>
            </div>
          </Section>
          <div className="grid-2">
            <ChartBlock title="Giá trị thật và dự đoán (tập test)" note="Điểm càng gần đường chéo càng chính xác; 400 tin đầu của tập test">
              <ResponsiveContainer width="100%" height={300}>
                <ScatterChart margin={{ top: 8, right: 12, bottom: 16, left: -4 }}>
                  <CartesianGrid stroke="#e4eae8" />
                  <XAxis type="number" dataKey="actual" name="Thật" domain={[0, 80]} allowDataOverflow tickLine={false}
                    label={{ value: 'Lương thật (triệu)', position: 'insideBottom', offset: -8, fontSize: 12, fill: '#5d6e75' }} />
                  <YAxis type="number" dataKey="predicted" name="Dự đoán" domain={[0, 80]} allowDataOverflow tickLine={false} />
                  <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 80, y: 80 }]} stroke="#5d6e75" strokeDasharray="4 4" />
                  <Tooltip content={<TooltipBox render={(d) => <>Thật {fmt(d.actual)} – dự đoán {fmt(d.predicted)} triệu</>} />} />
                  <Scatter isAnimationActive={false} data={s.scatter_sample} fill="#00836c" fillOpacity={0.55} />
                </ScatterChart>
              </ResponsiveContainer>
            </ChartBlock>
            <ChartBlock title="Sai số tuyệt đối trung bình theo ngành" note="MAE trên tập test, triệu đồng" table={s.error_by_category}
              columns={[{ key: 'cat', label: 'Ngành' }, { key: 'n', label: 'Số tin', num: true, render: fmtInt }, { key: 'MAE', label: 'MAE', num: true, render: fmt }]}>
              <HBar data={[...s.error_by_category].sort((a, b) => b.MAE - a.MAE)} labelKey="cat" valueKey="MAE" format={fmt} labelWidth={240} maxChars={36}
                tooltip={(d) => <><div className="t">{d.cat}</div>MAE {fmt(d.MAE)} triệu trên {fmtInt(d.n)} tin</>} />
            </ChartBlock>
          </div>
        </>
      )}

      {tab === 'skills' && k && (
        <>
          <Section title="Phân loại đa nhãn kỹ năng" lede={`${k.n_labels} nhãn kỹ năng phổ biến. Precision@5: trong 5 kỹ năng gợi ý đầu tiên có bao nhiêu kỹ năng đúng; Recall@10: tìm lại được bao nhiêu phần kỹ năng thật trong 10 gợi ý.`}>
            <div className="panel">
              <DataTable rows={modelRows(k.results)} rowClass={(r) => (r.name === k.best_model ? 'best' : '')} columns={[
                { key: 'name', label: 'Mô hình', render: (v) => <>{v}{v === k.best_model && <> <span className="pill">dùng trên giao diện</span></>}</> },
                { key: 'Precision@5', label: 'P@5', num: true, render: n3 }, { key: 'Recall@5', label: 'R@5', num: true, render: n3 },
                { key: 'Precision@10', label: 'P@10', num: true, render: n3 }, { key: 'Recall@10', label: 'R@10', num: true, render: n3 },
                { key: 'Micro_F1', label: 'Micro-F1', num: true, render: n3 }, { key: 'Macro_F1', label: 'Macro-F1', num: true, render: n3 },
              ]} />
              <p className="hint" style={{ marginTop: 12 }}>
                Baseline giả định đã biết ngành và gợi ý kỹ năng phổ biến nhất của ngành đó. Biến thể có mô tả đạt điểm cao vì kỹ năng
                thường được viết sẵn trong phần yêu cầu (gần với trích xuất thông tin); giao diện dùng mô hình chỉ cần chức danh.
              </p>
            </div>
          </Section>
          <ChartBlock title="F1 theo từng kỹ năng (40 kỹ năng phổ biến nhất)" table={k.per_label}
            columns={[{ key: 'skill', label: 'Kỹ năng' }, { key: 'kind', label: 'Loại' }, { key: 'support', label: 'Số tin test', num: true }, { key: 'f1', label: 'F1', num: true, render: n3 }]}>
            <HBar data={[...k.per_label].sort((a, b) => b.f1 - a.f1)} labelKey="skill" valueKey="f1" format={(v) => v.toFixed(2)}
              tooltip={(d) => <><div className="t">{d.skill}</div>F1 {n3(d.f1)} ({d.support} tin test, {d.kind === 'soft' ? 'kỹ năng mềm' : 'chuyên môn'})</>} />
          </ChartBlock>
        </>
      )}

      {tab === 'category' && c && (
        <>
          <Section title="Phân loại 16 ngành" lede={`Đầu vào: tiêu đề + mô tả + yêu cầu, TF-IDF từ và ký tự. Train ${fmtInt(c.n_train)}, test ${fmtInt(c.n_test)} tin. ${c.multi_label_pct ? `${fmt(c.multi_label_pct)}% tin được đăng dưới nhiều ngành, nên dự đoán được tính đúng nếu trùng một trong các ngành của tin; cột “chặt” chỉ so với ngành chính.` : ''}`}>
            <div className="panel">
              <DataTable rows={modelRows(c.results)} rowClass={(r) => (r.name === c.best_model ? 'best' : '')} columns={[
                { key: 'name', label: 'Mô hình', render: (v) => <>{v}{v === c.best_model && <> <span className="pill">tốt nhất</span></>}</> },
                { key: 'Accuracy', label: 'Accuracy', num: true, render: n3 }, { key: 'Macro_F1', label: 'Macro-F1', num: true, render: n3 },
                { key: 'Accuracy_strict', label: 'Accuracy (chặt)', num: true, render: n3 },
                { key: 'Weighted_F1', label: 'Weighted-F1', num: true, render: n3 }, { key: 'seconds', label: 'Thời gian (s)', num: true, render: fmt },
              ]} />
              <p className="hint" style={{ marginTop: 12 }}>
                Cùng mô hình nhưng chỉ dùng mô tả (giống thiết lập bài báo): Accuracy {n3(c.results[c.best_model].test_description_only?.Accuracy)},
                {' '}Macro-F1 {n3(c.results[c.best_model].test_description_only?.Macro_F1)}. Bài báo: {c.paper_reference.model} đạt
                {' '}Accuracy {c.paper_reference.Accuracy}, Macro-F1 {c.paper_reference.Macro_F1}.
              </p>
            </div>
          </Section>
          <div style={{ display: 'grid', gap: 24 }}>
            <ChartBlock title="F1 theo ngành" table={c.per_class}
              columns={[{ key: 'category', label: 'Ngành' }, { key: 'precision', label: 'Precision', num: true, render: n3 }, { key: 'recall', label: 'Recall', num: true, render: n3 }, { key: 'f1', label: 'F1', num: true, render: n3 }, { key: 'support', label: 'Số tin', num: true }]}>
              <HBar data={[...c.per_class].sort((a, b) => b.f1 - a.f1)} labelKey="category" valueKey="f1" format={(v) => v.toFixed(2)} labelWidth={240} maxChars={36}
                tooltip={(d) => <><div className="t">{d.category}</div>F1 {n3(d.f1)}, precision {n3(d.precision)}, recall {n3(d.recall)}</>} />
            </ChartBlock>
            <ChartBlock title="Ma trận nhầm lẫn (tập test)" note="Màu đậm theo tỷ lệ trong hàng; di chuột vào ô để xem chi tiết">
              <Confusion labels={c.labels} matrix={c.confusion_matrix} />
            </ChartBlock>
          </div>
        </>
      )}
    </>
  )
}
