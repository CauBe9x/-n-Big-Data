import { useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from 'recharts'
import { fmt, fmt3, fmtInt, useApi } from '../api.js'
import { ChartBlock, DataTable, ErrorBox, Loading, PageHead, Section, TooltipBox } from '../components/ui.jsx'

export default function Clusters() {
  const { data, error, loading } = useApi('/api/mining/clusters')
  const [sel, setSel] = useState(null)
  const current = data && (data.clusters.find((c) => c.id === sel) || data.clusters[0])
  const pts = useMemo(() => {
    if (!data || !current) return { on: [], off: [] }
    return { on: data.points.filter((p) => p.c === current.id), off: data.points.filter((p) => p.c !== current.id) }
  }, [data, current])
  const labelOf = useMemo(() => Object.fromEntries((data?.clusters || []).map((c) => [c.id, c.label])), [data])
  const sil = data ? Object.entries(data.silhouette).map(([k, v]) => ({ k: Number(k), v })) : []

  return (
    <>
      <PageHead title="Phân cụm công việc">
        Mỗi tin được biểu diễn bằng TF-IDF của chức danh và của kỹ năng chuyên môn, giảm chiều bằng SVD rồi gom nhóm bằng K-Means.
        Số cụm k được chọn theo hệ số silhouette. Chọn một cụm để xem nó gồm những công việc gì.
      </PageHead>
      <ErrorBox error={error} />
      {loading && <Loading />}
      {data && current && (
        <>
          <Section>
            <div className="grid-2">
              <ChartBlock title="Bản đồ các tin tuyển dụng (PCA 2 chiều)"
                note={`${fmtInt(data.points.length)} tin lấy mẫu; điểm màu ngọc thuộc cụm đang chọn`}>
                <ResponsiveContainer width="100%" height={340}>
                  <ScatterChart margin={{ top: 8, right: 8, bottom: 0, left: -20 }}>
                    <CartesianGrid stroke="#eef2f1" />
                    <XAxis type="number" dataKey="x" tick={false} axisLine={false} />
                    <YAxis type="number" dataKey="y" tick={false} axisLine={false} />
                    <ZAxis range={[14, 14]} />
                    <Tooltip content={<TooltipBox render={(d) => <><div className="t">{d.t}</div>{labelOf[d.c]}</>} />} />
                    <Scatter data={pts.off} fill="#c6d1ce" isAnimationActive={false} />
                    <Scatter data={pts.on} fill="#00836c" stroke="#fff" strokeWidth={1} isAnimationActive={false} />
                  </ScatterChart>
                </ResponsiveContainer>
              </ChartBlock>
              <div className="panel">
                <div className="chart-head"><div>
                  <h3>{current.label}</h3>
                  <p className="note">{fmtInt(current.size)} tin, lương trung vị {current.median_salary ? `${fmt(current.median_salary)} triệu` : 'không đủ dữ liệu'}</p>
                </div></div>
                <p className="hint" style={{ margin: '8px 0 4px' }}>Chức danh tiêu biểu</p>
                <p style={{ margin: 0 }}>{current.example_titles.join('; ')}</p>
                <p className="hint" style={{ margin: '14px 0 6px' }}>Kỹ năng chuyên môn phổ biến</p>
                <div className="chips">{current.top_skills.map((s) => <span className="chip" key={s}>{s}</span>)}</div>
                <p className="hint" style={{ margin: '14px 0 6px' }}>Ngành chiếm ưu thế</p>
                {current.top_categories.map((c) => (
                  <div key={c.name} style={{ fontSize: 14 }}>{c.name}: <strong>{Math.round(c.share * 100)}%</strong></div>
                ))}
              </div>
            </div>
          </Section>

          <Section title={`${data.k} cụm được tìm thấy`} lede="Nhấn vào một dòng để làm nổi bật cụm trên bản đồ.">
            <div className="panel">
              <div className="table-wrap">
                <table className="data">
                  <thead><tr><th>Cụm (chức danh phổ biến nhất)</th><th>Kỹ năng đặc trưng</th><th className="num">Số tin</th><th className="num">Lương trung vị</th><th>Ngành chính</th></tr></thead>
                  <tbody>
                    {data.clusters.map((c) => (
                      <tr key={c.id} className={c.id === current.id ? 'best' : ''} style={{ cursor: 'pointer' }} tabIndex={0}
                        onClick={() => setSel(c.id)} onKeyDown={(e) => e.key === 'Enter' && setSel(c.id)} aria-selected={c.id === current.id}>
                        <td>{c.label}</td>
                        <td>{(c.distinct_skills?.length ? c.distinct_skills : c.top_skills).slice(0, 4).join(', ')}</td>
                        <td className="num">{fmtInt(c.size)}</td>
                        <td className="num">{c.median_salary ? fmt(c.median_salary) : '–'}</td>
                        <td>{c.top_categories[0]?.name}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </Section>

          <Section title="Chọn số cụm k" lede={`Silhouette cao hơn nghĩa là các cụm tách bạch hơn. Với dữ liệu văn bản, silhouette thường tăng dần theo k, nên k được giới hạn trong khoảng 8–40 để mỗi cụm vẫn đủ lớn để diễn giải. Đã chọn k = ${data.k}.`}>
            <div className="grid-2">
              <ChartBlock title="Hệ số silhouette theo k" table={sil} columns={[{ key: 'k', label: 'k' }, { key: 'v', label: 'Silhouette', num: true, render: fmt3 }]}>
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={sil} margin={{ top: 8, right: 8, left: -10, bottom: 0 }}>
                    <CartesianGrid vertical={false} stroke="#e4eae8" />
                    <XAxis dataKey="k" tickLine={false} />
                    <YAxis tickLine={false} axisLine={false} tickFormatter={(v) => v.toFixed(2)} />
                    <Tooltip cursor={{ fill: '#eef6f4' }} content={<TooltipBox render={(d) => <>k = {d.k}: {fmt3(d.v)}</>} />} />
                    <Bar dataKey="v" isAnimationActive={false} radius={[4, 4, 0, 0]} maxBarSize={40}>
                      {sil.map((d) => <Cell key={d.k} fill={d.k === data.k ? '#00836c' : '#9fc9c0'} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </ChartBlock>
              <div className="panel">
                <DataTable rows={[
                  { a: 'Biểu diễn', b: 'TF-IDF 1–2 gram của chức danh ghép với TF-IDF kỹ năng chuyên môn (trọng số 0,7)' },
                  { a: 'Giảm chiều', b: `TruncatedSVD 80 thành phần (giữ ${Math.round(data.explained_variance_svd * 100)}% phương sai)` },
                  { a: 'Thuật toán', b: 'K-Means trên vector đã chuẩn hoá L2 (tương đương khoảng cách cosine)' },
                  { a: 'Trực quan', b: 'PCA 2 chiều trên không gian SVD' },
                ]} columns={[{ key: 'a', label: 'Bước' }, { key: 'b', label: 'Cách làm' }]} />
              </div>
            </div>
          </Section>
        </>
      )}
    </>
  )
}
