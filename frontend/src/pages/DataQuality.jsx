import { fmt, fmtInt, useApi } from '../api.js'
import { ChartBlock, DataTable, ErrorBox, HBar, PageHead, Section, Skeleton } from '../components/ui.jsx'

export default function DataQuality() {
  const { data: q, error, loading, reload } = useApi('/api/pipeline/quality')
  const raw = q?.raw
  const missing = raw ? raw.columns_profile.filter((c) => c.missing > 0).sort((a, b) => b.missing_pct - a.missing_pct) : []
  const complete = raw ? raw.columns_profile.length - missing.length : 0

  return (
    <>
      <PageHead title="Chất lượng dữ liệu">
        Hồ sơ đo trực tiếp trên VietJobs.csv gốc, trước và sau khi làm sạch. File gốc không bị sửa; mọi xử lý nằm trong pipeline và chạy lại được.
      </PageHead>
      <ErrorBox error={error} onRetry={reload} />
      {!q && loading && <Skeleton lines={[110, 300, 300]} />}
      {q && (
        <>
          <dl className="stat-list wide">
            <div><dt>Dòng gốc</dt><dd>{fmtInt(raw.rows)}</dd><p>{raw.columns} cột</p></div>
            <div><dt>Dòng trùng tin</dt><dd>{fmtInt(raw.duplicates.same_posting)}</dd><p>{fmtInt(raw.duplicates.full_row)} dòng trùng hoàn toàn</p></div>
            <div><dt>Tin duy nhất</dt><dd>{fmtInt(raw.duplicates.unique_postings)}</dd><p>{fmtInt(q.clean.multi_category_jobs)} tin thuộc nhiều ngành</p></div>
            <div><dt>Dòng ghi thoả thuận</dt><dd>{fmt(raw.salary.negotiable_pct)}%</dd><p>{fmtInt(raw.salary.negotiable_rows)} dòng không công bố lương</p></div>
          </dl>

          <Section title="Làm sạch thay đổi dữ liệu như thế nào" lede="Mỗi hàng là một trường có nhiều cách ghi trong dữ liệu gốc, và số giá trị còn lại sau khi chuẩn hoá.">
            <div className="panel">
              <DataTable rows={q.clean.steps} columns={[
                { key: 'field', label: 'Trường' }, { key: 'before', label: 'Trước', num: true, render: fmtInt },
                { key: 'after', label: 'Sau', num: true, render: fmtInt }, { key: 'how', label: 'Cách xử lý' },
              ]} />
            </div>
          </Section>

          <div className="grid-2 section">
            <ChartBlock title={`Giá trị thiếu ở ${missing.length} cột`}
              note={`${complete} cột còn lại đầy đủ. Thiếu ở languages_required nghĩa là tin không yêu cầu ngoại ngữ, không phải lỗi.`}
              table={missing} columns={[{ key: 'name', label: 'Cột' }, { key: 'missing', label: 'Số dòng thiếu', num: true, render: fmtInt }, { key: 'missing_pct', label: '%', num: true, render: fmt }]}>
              <HBar data={missing} labelKey="name" valueKey="missing_pct" format={(v) => `${fmt(v)}%`} labelWidth={150} />
            </ChartBlock>
            <div className="panel">
              <h3>Lương bất thường</h3>
              <p className="note">Các dòng ngoài khoảng {raw.salary.range_used[0]}–{raw.salary.range_used[1]} triệu vẫn ở trong CSDL nhưng không đi vào thống kê và huấn luyện.</p>
              <DataTable rows={[
                { k: 'Lương cao nhất trong dữ liệu (triệu/tháng)', v: fmt(raw.salary.max_value) },
                { k: 'Dòng có lương trung bình trên ngưỡng', v: fmtInt(raw.salary.above_range) },
                { k: 'Dòng có lương trung bình dưới ngưỡng', v: fmtInt(raw.salary.below_range) },
                { k: 'Dòng có salary_min > salary_max', v: fmtInt(raw.salary.min_gt_max) },
              ]} columns={[{ key: 'k', label: 'Kiểm tra' }, { key: 'v', label: 'Kết quả', num: true }]} />
              <h3 style={{ marginTop: 20 }}>Cột thời gian</h3>
              <p className="note">
                {raw.date_columns.length
                  ? `Phát hiện cột: ${raw.date_columns.join(', ')}.`
                  : 'Không có cột ngày đăng tin, nên ứng dụng không dựng biểu đồ xu hướng theo thời gian.'}
              </p>
            </div>
          </div>

          <Section title="Lược đồ dữ liệu gốc">
            <div className="panel">
              <DataTable rows={raw.columns_profile} columns={[
                { key: 'name', label: 'Cột', render: (v) => <code>{v}</code> },
                { key: 'dtype', label: 'Kiểu' },
                { key: 'unique', label: 'Giá trị khác nhau', num: true, render: fmtInt },
                { key: 'missing_pct', label: 'Thiếu', num: true, render: (v) => `${fmt(v)}%` },
                { key: 'note', label: 'Ý nghĩa' },
              ]} />
            </div>
          </Section>
        </>
      )}
    </>
  )
}
