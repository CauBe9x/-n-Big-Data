import { Link } from 'react-router-dom'
import { fmt, fmtInt, useApi } from '../api.js'
import { ErrorBox, Skeleton } from '../components/ui.jsx'

const FEATURES = [
  { to: '/dashboard', title: 'Dashboard thị trường',
    text: 'Lương, ngành, địa lý, kỹ năng và ngoại ngữ, lọc theo miền, tỉnh, ngành, kinh nghiệm và hợp đồng.' },
  { to: '/predict/salary', title: 'Dự đoán mức lương',
    text: 'Nhập chức danh, nơi làm việc, kinh nghiệm và kỹ năng; mô hình trả về mức lương, khoảng 80% và các yếu tố ảnh hưởng.' },
  { to: '/predict/skills', title: 'Gợi ý kỹ năng cần có',
    text: 'Từ một chức danh, mô hình đa nhãn gợi ý kỹ năng chuyên môn và kỹ năng mềm nhà tuyển dụng hay yêu cầu.' },
  { to: '/predict/category', title: 'Phân loại ngành nghề',
    text: 'Dán tiêu đề và mô tả của một tin tuyển dụng, mô hình xếp tin vào một trong 16 nhóm ngành.' },
  { to: '/mining/rules', title: 'Luật kết hợp kỹ năng',
    text: 'Luật FP-Growth dạng “nếu tin yêu cầu A thì thường có B”, với vế phải là kỹ năng, ngành hoặc nhóm lương.' },
  { to: '/mining/clusters', title: 'Phân cụm công việc',
    text: 'K-Means gom các tin thành nhóm công việc, kèm kỹ năng đặc trưng và lương trung vị của từng nhóm.' },
  { to: '/pipeline', title: 'Pipeline Big Data',
    text: 'Hai đường xử lý độc lập, Spark Lakehouse và ETL, chạy trực tiếp và đối soát kết quả với nhau.' },
  { to: '/models', title: 'Đánh giá mô hình',
    text: 'So sánh mô hình trên tập test, đối chiếu với bài báo gốc, xem sai số theo ngành.' },
]

export default function Home({ health }) {
  const h = health.data
  const m = h?.models || {}
  const dash = useApi('/api/dashboard')
  const k = dash.data?.kpi
  const nReady = ['salary', 'skills', 'category'].filter((x) => m[x]).length

  return (
    <>
      <header className="home-hero">
        <span className="eyebrow">Đồ án Công nghệ Dữ liệu lớn</span>
        <h1>Một vị trí đáng giá bao nhiêu, và cần những kỹ năng gì?</h1>
        <p>
          Hệ thống phân tích tin tuyển dụng VietJobs từ TopCV: làm sạch và lưu trữ dữ liệu, xử lý bằng pipeline batch,
          rồi dùng máy học để dự đoán lương và gợi ý kỹ năng.
        </p>
        <div className="cta">
          <Link className="btn" to="/dashboard">Xem dashboard</Link>
          <Link className="btn ghost" to="/predict/salary">Thử dự đoán lương</Link>
        </div>
      </header>

      <ErrorBox error={health.error} onRetry={health.reload} />
      {!k && dash.loading && <Skeleton lines={[100]} />}
      {k && (
        <dl className="stat-list wide">
          <div><dt>Tin tuyển dụng</dt><dd>{fmtInt(k.jobs)}</dd><p>sau khi gộp tin trùng</p></div>
          <div><dt>Lương trung vị</dt><dd>{fmt(k.median)} triệu</dd><p>nửa giữa {fmt(k.p25)}–{fmt(k.p75)} triệu</p></div>
          <div><dt>Không công khai lương</dt><dd>{fmt(k.negotiable_pct)}%</dd><p>số tin ghi “thoả thuận”</p></div>
          <div><dt>Yêu cầu ngoại ngữ</dt><dd>{fmt(k.language_pct)}%</dd><p>trên tổng số tin</p></div>
        </dl>
      )}

      {h && (
        <ul className="facts home-facts" aria-label="Trạng thái hệ thống">
          <li><span className="ok-dot" aria-hidden="true" />CSDL: <strong>{h.database}</strong></li>
          <li><span className={`ok-dot ${nReady === 3 ? '' : 'off'}`} aria-hidden="true" />Mô hình: <strong>{nReady}/3</strong> sẵn sàng</li>
          <li><Link to="/pipeline">Xem pipeline và đối soát</Link></li>
        </ul>
      )}

      <section className="section">
        <h2 style={{ fontSize: 19, margin: '0 0 12px' }}>Chức năng</h2>
        <div className="feature-list">
          {FEATURES.map((f) => (
            <Link key={f.to} to={f.to} className="feature">
              <span className="feature-title">{f.title}</span>
              <span className="feature-text">{f.text}</span>
            </Link>
          ))}
        </div>
      </section>
    </>
  )
}
