import { useEffect, useState } from 'react'
import { useMeta } from '../App.jsx'
import { fmt, fmtInt, qs, useApi } from '../api.js'
import { ErrorBox, Loading, PageHead, Select } from '../components/ui.jsx'

function salaryText(j) {
  if (j.is_negotiable || !j.salary_avg) return 'Thoả thuận'
  if (j.salary_min && j.salary_max && j.salary_min !== j.salary_max) return `${fmt(j.salary_min)}–${fmt(j.salary_max)} triệu`
  return `${fmt(j.salary_avg)} triệu`
}

function JobDrawer({ id, onClose }) {
  const { data: j, error, loading } = useApi(`/api/jobs/${id}`)
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true" aria-label="Chi tiết tin tuyển dụng">
        <button className="btn ghost" onClick={onClose} style={{ float: 'right' }}>Đóng</button>
        {loading && <Loading />}
        <ErrorBox error={error} />
        {j && (
          <>
            <h2>{j.title}</h2>
            <p className="hint">{(j.all_categories?.length ? j.all_categories : [j.category]).join('; ')} – {j.location}</p>
            <dl className="dl">
              <dt>Mức lương</dt><dd><strong>{salaryText(j)}</strong></dd>
              {j.is_negotiable && j.estimated_salary && (
                <><dt>Ước tính của mô hình</dt>
                  <dd><span className="pill warm">{fmt(j.estimated_salary.predicted)} triệu</span>{' '}
                    <span className="hint">khoảng {fmt(j.estimated_salary.low)}–{fmt(j.estimated_salary.high)} triệu (tham khảo)</span></dd></>
              )}
              <dt>Kinh nghiệm</dt><dd>{j.experience || '–'}</dd>
              <dt>Hợp đồng</dt><dd>{j.contract_type}</dd>
              <dt>Giờ làm việc</dt><dd>{j.working_hours || '–'}</dd>
              <dt>Ngoại ngữ</dt><dd>{j.languages.length ? j.languages.join(', ') : 'Không yêu cầu'}</dd>
              <dt>Kỹ năng chuyên môn</dt>
              <dd><div className="chips">{j.technical_skills.length ? j.technical_skills.map((s) => <span className="chip" key={s}>{s}</span>) : '–'}</div></dd>
              <dt>Kỹ năng mềm</dt>
              <dd><div className="chips">{j.soft_skills.length ? j.soft_skills.map((s) => <span className="chip soft" key={s}>{s}</span>) : '–'}</div></dd>
              <dt>Bằng cấp</dt><dd>{j.qualifications.join('; ') || '–'}</dd>
              <dt>Phúc lợi</dt><dd>{j.benefits.join('; ') || '–'}</dd>
            </dl>
            <h3>Mô tả công việc</h3>
            <p className="prose-block">{j.description}</p>
            <h3>Yêu cầu</h3>
            <p className="prose-block">{j.requirements_text || '–'}</p>
          </>
        )}
      </aside>
    </>
  )
}

export default function Jobs() {
  const meta = useMeta()
  const [q, setQ] = useState('')
  const [query, setQuery] = useState('')
  const [f, setF] = useState({ category: null, province: null, experience: null, contract_type: null, has_salary: null, sort: 'relevance' })
  const [skill, setSkill] = useState('')
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState(null)
  const set = (k) => (v) => { setF((s) => ({ ...s, [k]: v })); setPage(1) }
  const { data, error, loading, reload } = useApi(`/api/jobs${qs({ q: query, skill, ...f, page, size: 20 })}`)
  const pages = data ? Math.max(1, Math.ceil(data.total / data.size)) : 1

  return (
    <>
      <PageHead title="Tra cứu tin tuyển dụng">
        Tìm theo chức danh (gõ có dấu hay không dấu đều được), lọc theo ngành, nơi làm việc, kinh nghiệm hoặc một kỹ năng cụ thể.
        Với tin chỉ ghi “thoả thuận”, mô hình sẽ ước tính mức lương tham khảo.
      </PageHead>
      <form className="filters" onSubmit={(e) => { e.preventDefault(); setQuery(q); setPage(1) }}>
        <div className="field" style={{ flex: '1 1 260px' }}>
          <label htmlFor="q">Chức danh</label>
          <input id="q" className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="ví dụ: ke toan, data analyst" />
        </div>
        <div className="field">
          <label htmlFor="sk">Kỹ năng</label>
          <input id="sk" className="input" list="sk-list" value={skill} onChange={(e) => { setSkill(e.target.value); setPage(1) }} placeholder="excel, autocad…" />
          <datalist id="sk-list">{(meta.data?.skills || []).slice(0, 300).map((s) => <option key={s.name + s.kind} value={s.name} />)}</datalist>
        </div>
        <button className="btn" type="submit">Tìm</button>
      </form>
      <div className="filters">
        <Select id="j-cat" label="Ngành" value={f.category} onChange={set('category')}
          options={(meta.data?.categories || []).map((c) => ({ value: c.slug, label: c.name }))} />
        <Select id="j-prov" label="Tỉnh / thành" value={f.province} onChange={set('province')}
          options={(meta.data?.provinces || []).map((p) => ({ value: p.name, label: p.name }))} />
        <Select id="j-exp" label="Kinh nghiệm" value={f.experience} onChange={set('experience')}
          options={(meta.data?.experience_buckets || []).map((b) => ({ value: b, label: b }))} />
        <Select id="j-con" label="Hợp đồng" value={f.contract_type} onChange={set('contract_type')}
          options={(meta.data?.contract_types || []).map((c) => ({ value: c.name, label: c.name }))} />
        <Select id="j-sal" label="Lương" value={f.has_salary} onChange={set('has_salary')}
          options={[{ value: 'true', label: 'Có công bố lương' }, { value: 'false', label: 'Thoả thuận' }]} />
        <Select id="j-sort" label="Sắp xếp" value={f.sort} onChange={(v) => set('sort')(v || 'relevance')} placeholder="Mặc định"
          options={[{ value: 'salary_desc', label: 'Lương cao → thấp' }, { value: 'salary_asc', label: 'Lương thấp → cao' }]} />
      </div>

      <ErrorBox error={error} onRetry={reload} />
      {data && <p className="hint">{fmtInt(data.total)} tin phù hợp</p>}
      {loading && !data && <Loading />}
      {data && data.items.length === 0 && <p className="state">Không có tin nào khớp. Thử bỏ bớt bộ lọc hoặc gõ chức danh ngắn hơn.</p>}
      <div>
        {data?.items.map((j) => (
          <article className="job-row" key={j.id} onClick={() => setOpen(j.id)} tabIndex={0}
            onKeyDown={(e) => e.key === 'Enter' && setOpen(j.id)}>
            <div>
              <h3>{j.title}</h3>
              <div className="job-meta">
                <span>{j.category}</span><span>{j.province}</span><span>{j.experience || 'Kinh nghiệm: không rõ'}</span><span>{j.contract_type}</span>
              </div>
            </div>
            <div className={`salary-tag ${j.is_negotiable ? 'neg' : ''}`}>{salaryText(j)}</div>
          </article>
        ))}
      </div>
      {data && data.total > data.size && (
        <div className="pager">
          <button className="btn ghost" disabled={page <= 1} onClick={() => setPage(page - 1)}>Trang trước</button>
          <span>Trang {page} / {fmtInt(pages)}</span>
          <button className="btn ghost" disabled={page >= pages} onClick={() => setPage(page + 1)}>Trang sau</button>
        </div>
      )}
      {open && <JobDrawer id={open} onClose={() => setOpen(null)} />}
    </>
  )
}
