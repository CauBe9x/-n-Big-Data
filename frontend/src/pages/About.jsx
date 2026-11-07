import { useApi, fmtInt } from '../api.js'
import { DataTable, PageHead, Section } from '../components/ui.jsx'

const LAYERS = [
  { name: 'Nguồn dữ liệu', items: ['VietJobs.csv', 'TopCV, thu thập bởi nhóm tác giả VietJobs'] },
  { name: 'Xử lý', items: ['ETL pandas', 'Spark: Bronze, Silver, Gold', 'Huấn luyện mô hình', 'FP-Growth, K-Means'] },
  { name: 'Lưu trữ', items: ['PostgreSQL', 'Parquet', 'File mô hình .joblib'] },
  { name: 'Phục vụ', items: ['FastAPI', 'Điều phối job pipeline'] },
  { name: 'Trình bày', items: ['React: dashboard, dự đoán, tra cứu', 'Superset (triển khai riêng, tuỳ chọn)'] },
]

const STACK = [
  { tech: 'PostgreSQL', role: 'CSDL phục vụ, 3NF, khoá ngoại, view BI', why: 'Dashboard cần lọc và gom nhóm tức thời, cần ràng buộc toàn vẹn' },
  { tech: 'pandas, scikit-learn, LightGBM', role: 'ETL và huấn luyện', why: 'Dữ liệu vừa RAM, thư viện đơn máy nhanh và đủ mô hình' },
  { tech: 'Apache Spark (local[*])', role: 'Lakehouse Parquet và đối soát độc lập, MLlib đối chứng', why: 'Là công nghệ trọng tâm của môn học; làm phép kiểm tra chéo thật với ETL' },
  { tech: 'Parquet', role: 'Lưu Bronze, Silver, Gold', why: 'Định dạng cột, nén tốt, đọc được cả ở Spark lẫn pandas' },
  { tech: 'FastAPI', role: 'REST API, validate đầu vào, nạp mô hình', why: 'Cùng ngôn ngữ với pipeline, dùng lại trực tiếp mã đặc trưng khi suy luận' },
  { tech: 'React, Vite, Recharts', role: 'Giao diện', why: 'Giữ nền tảng có sẵn của nhóm' },
]

const NOT_USED = [
  { tech: 'Kafka, Spark Streaming', why: 'Dữ liệu là một file tĩnh, không có luồng sự kiện để xử lý.' },
  { tech: 'Hadoop HDFS, YARN', why: 'Chỉ chạy trên một máy, cụm HDFS một nút không đem lại lợi ích gì.' },
  { tech: 'Airflow', why: 'Pipeline tuần tự, chạy theo yêu cầu; run_all và nhật ký pipeline_runs là đủ.' },
]

const LIMITS = [
  'Spark chạy local[*] trên một máy: có song song theo lõi CPU, không có xử lý phân tán trên nhiều máy.',
  'Hệ thống xử lý batch. Không có xử lý thời gian thực.',
  'Dữ liệu chỉ từ TopCV, kích thước khoảng 100 MB, nằm gọn trong RAM. Pipeline dùng công nghệ Big Data để học và đối soát, không phải vì dữ liệu buộc phải dùng.',
  'Không có ngày đăng tin, nên không phân tích được xu hướng theo thời gian.',
  'Khoảng 29% tin không công bố lương; kết quả lương chỉ đại diện cho nhóm tin có công bố.',
  'Kỹ năng do LLM trích xuất nên còn nhiễu. Chênh lệch lương theo kỹ năng là tương quan, không phải nhân quả.',
]

export default function About() {
  const { data } = useApi('/api/health')
  return (
    <>
      <PageHead title="Kiến trúc hệ thống">
        Hệ thống đọc dữ liệu tin tuyển dụng Việt Nam, làm sạch, lưu trữ, phân tích, rồi dùng máy học để dự đoán lương và kỹ năng cần có.
      </PageHead>

      <Section title="Bài toán">
        <div className="prose">
          <p>Tin tuyển dụng mô tả mức lương, địa điểm và kỹ năng theo nhiều cách khác nhau, và gần 3 trong 10 tin không công khai lương. Người tìm việc khó biết một vị trí đáng giá bao nhiêu, cần học kỹ năng gì.</p>
          <p>Hệ thống trả lời ba câu hỏi: thị trường đang trả bao nhiêu, một vị trí cụ thể nên có mức lương nào, và vị trí đó cần những kỹ năng gì. Người dùng dự kiến là sinh viên và người tìm việc, bộ phận nhân sự, và người phân tích thị trường lao động.</p>
        </div>
      </Section>

      <Section title="Các tầng của hệ thống" lede={data ? `Đang chạy với ${data.database}, ${fmtInt(data.jobs)} tin tuyển dụng.` : undefined}>
        <ol className="layers">
          {LAYERS.map((l) => (
            <li key={l.name}>
              <h3>{l.name}</h3>
              <ul>{l.items.map((i) => <li key={i}>{i}</li>)}</ul>
            </li>
          ))}
        </ol>
      </Section>

      <Section title="Công nghệ và lý do chọn">
        <div className="panel">
          <DataTable rows={STACK} columns={[{ key: 'tech', label: 'Công nghệ' }, { key: 'role', label: 'Vai trò' }, { key: 'why', label: 'Vì sao' }]} />
        </div>
      </Section>

      <div className="grid-2 section">
        <div className="panel">
          <h3>Có cân nhắc nhưng không dùng</h3>
          <dl className="plain-list">
            {NOT_USED.map((n) => <div key={n.tech}><dt>{n.tech}</dt><dd>{n.why}</dd></div>)}
          </dl>
        </div>
        <div className="panel">
          <h3>Giới hạn cần biết</h3>
          <ul className="plain-ul">{LIMITS.map((l) => <li key={l}>{l}</li>)}</ul>
        </div>
      </div>
    </>
  )
}
