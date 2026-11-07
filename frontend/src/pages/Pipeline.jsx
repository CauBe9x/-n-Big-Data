import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, LabelList, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, fmt, fmt3, fmtInt, post, useApi } from '../api.js'
import { ChartBlock, DataTable, ErrorBox, PageHead, Section, Skeleton, TooltipBox } from '../components/ui.jsx'
import { StatusDot } from '../components/viz.jsx'

const JOB_LABEL = {
  etl: 'ETL pandas', quality: 'Kiểm định chất lượng', salary: 'Mô hình lương', skills: 'Mô hình kỹ năng', category: 'Mô hình ngành',
  mining: 'Khai phá dữ liệu', spark: 'Spark Lakehouse', benchmark: 'Benchmark Spark',
}
const when = (s) => (s ? new Date(s).toLocaleString('vi-VN', { dateStyle: 'short', timeStyle: 'short' }) : '–')
const secs = (s) => (s == null ? '–' : s >= 90 ? `${fmt(s / 60)} phút` : `${fmt(s)} giây`)

function Flow({ overview, spark }) {
  const by = Object.fromEntries(overview.steps.map((s) => [s.job, s]))
  const etl = by.etl?.last_run
  const sp = spark.metrics
  const stage = (name) => sp?.stages?.find((s) => s.stage === name)
  const c = overview.counts
  const Node = ({ title, sub, value, kind }) => (
    <li className={`flow-node ${kind || ''}`}>
      <span className="flow-title">{title}</span>
      {value != null && <strong>{value}</strong>}
      <span className="flow-sub">{sub}</span>
    </li>
  )
  return (
    <div className="flow" aria-label="Sơ đồ luồng dữ liệu">
      <div className="flow-track">
        <h3>Luồng phục vụ ứng dụng</h3>
        <ol>
          <Node title="Nguồn" value={etl ? `${fmtInt(etl.rows_in)} dòng` : null} sub="VietJobs.csv, 18 cột" kind="src" />
          <Node title="ETL pandas" value={`${fmtInt(c.jobs)} tin`} sub="gộp trùng, chuẩn hoá" />
          <Node title="PostgreSQL" value={overview.database_size} sub={`${fmtInt(c.skill_links)} liên kết kỹ năng`} kind="store" />
          <Node title="Máy học, khai phá" value={`${c.models} mô hình`} sub={`${c.rules} luật · ${c.clusters} cụm`} />
          <Node title="FastAPI + React" sub="dashboard, dự đoán, tra cứu" kind="out" />
        </ol>
      </div>
      <div className="flow-track alt">
        <h3>Luồng Spark độc lập, dùng để đối soát</h3>
        <ol>
          <Node title="Nguồn" value={sp ? `${fmtInt(sp.reconcile.n_rows)} dòng` : null} sub="cùng file CSV" kind="src" />
          <Node title="Bronze" value={stage('Bronze') ? secs(stage('Bronze').seconds) : '–'} sub="Parquet, giữ nguyên nội dung" />
          <Node title="Silver" value={stage('Silver') ? `${fmtInt(stage('Silver').rows_out)} tin` : '–'} sub="cùng luật làm sạch với ETL" />
          <Node title="Gold" value={stage('Gold') ? `${Object.keys(stage('Gold').tables).length} bảng` : '–'} sub="tổng hợp có shuffle" />
          <Node title="Đối soát" sub="so với PostgreSQL" kind="out" />
        </ol>
      </div>
    </div>
  )
}

function JobPanel({ overview, onDone }) {
  const [job, setJob] = useState(overview.active)
  const [err, setErr] = useState(null)
  const logRef = useRef(null)

  useEffect(() => {
    if (!job?.running) return undefined
    const t = setInterval(async () => {
      try {
        const j = await api('/api/pipeline/jobs/current')
        setJob(j)
        if (j && !j.running) onDone()
      } catch (x) { setErr(x) }
    }, 1000)
    return () => clearInterval(t)
  }, [job?.running, onDone])

  useEffect(() => { if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight }, [job?.log?.length])

  const start = async (name) => {
    setErr(null)
    try { setJob(await post('/api/pipeline/jobs', { job: name })) } catch (x) { setErr(x) }
  }

  return (
    <div className="panel">
      <div className="job-buttons">
        {overview.jobs_available.map((j) => (
          <div key={j.job}>
            <button type="button" className="btn" disabled={!j.enabled || job?.running} onClick={() => start(j.job)}>
              {job?.running && job.job === j.job ? 'Đang chạy…' : `Chạy: ${j.label}`}
            </button>
            <p className="hint">{j.enabled ? `Mất ${j.estimate}.` : j.reason}</p>
          </div>
        ))}
      </div>
      <ErrorBox error={err} />
      {job && (
        <div className="terminal" aria-live="polite">
          <div className="terminal-head">
            <span>{job.label}</span>
            <span>{job.running ? `đang chạy, ${fmt(job.seconds)} giây` : job.exit_code === 0 ? `xong trong ${fmt(job.seconds)} giây` : `lỗi, mã ${job.exit_code}`}</span>
          </div>
          <pre ref={logRef}>{job.log.length ? job.log.join('\n') : 'Đang khởi động tiến trình…'}</pre>
        </div>
      )}
    </div>
  )
}

function Reconcile({ onResult }) {
  const [res, setRes] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const run = async () => {
    setBusy(true); setErr(null)
    try { const r = await post('/api/pipeline/reconcile', {}); setRes(r); onResult?.(r) } catch (x) { setErr(x) } finally { setBusy(false) }
  }
  useEffect(() => { run() }, []) // eslint-disable-line react-hooks/exhaustive-deps
  const groups = res ? [...new Set(res.checks.map((c) => c.group))] : []
  const show = (v) => (v === true ? 'có' : v === false ? 'không' : typeof v === 'number' ? fmt(v) : v ?? '–')
  return (
    <div className="panel">
      <div className="panel-bar">
        {res
          ? <p><strong>{res.summary.pass}</strong> đạt · <strong>{res.summary.fail}</strong> lệch · <strong>{res.summary.skipped}</strong> chưa kiểm</p>
          : <p className="hint">Đang kiểm tra…</p>}
        <button type="button" className="btn ghost" disabled={busy} onClick={run}>{busy ? 'Đang kiểm tra…' : 'Kiểm tra lại'}</button>
      </div>
      <ErrorBox error={err} />
      {groups.map((g) => (
        <div key={g} className="check-group">
          <h3>{g}</h3>
          <DataTable rows={res.checks.filter((c) => c.group === g)} columns={[
            { key: 'status', label: 'Kết quả', render: (v) => <StatusDot status={v} /> },
            { key: 'name', label: 'Kiểm tra', render: (v, r) => <>{v}{r.note && <span className="hint block">{r.note}</span>}</> },
            { key: 'expected', label: 'Kỳ vọng', num: true, render: show },
            { key: 'actual', label: 'Thực tế', num: true, render: show },
          ]} />
        </div>
      ))}
    </div>
  )
}

function SparkResults({ spark, best }) {
  const m = spark.metrics
  if (!m) {
    return <p className="state">Chưa có kết quả Spark. {spark.available ? 'Bấm nút chạy Spark ở trên.' : spark.reason}</p>
  }
  const ml = m.mllib
  const reg = ml ? Object.entries(ml.regression).map(([name, r]) => ({ name, ...r })) : []
  return (
    <>
      <div className="grid-2">
        <div className="panel">
          <h3>Thời gian từng tầng</h3>
          <p className="note">
            Spark {m.spark_version}, master <code>{m.master}</code> (mọi lõi CPU của một máy, mỗi task được thử lại tối đa 8 lần), {m.parallelism} luồng, {m.shuffle_partitions} partition.
            Lần chạy lúc {when(m.finished_at)}, tổng {secs(m.seconds_total)}.
          </p>
          <DataTable rows={m.stages} columns={[
            { key: 'stage', label: 'Tầng' },
            { key: 'rows_in', label: 'Vào', num: true, render: fmtInt },
            { key: 'rows_out', label: 'Ra', num: true, render: fmtInt },
            { key: 'seconds', label: 'Giây', num: true, render: fmt },
          ]} />
          <p className="hint">
            CSV nhiều dòng không chia nhỏ khi đọc nên đầu vào chỉ có {m.stages[0].input_partitions} partition.
            Pipeline chia lại thành {m.stages[0].partitions} partition để các bước sau chạy song song.
          </p>
        </div>
        <div className="panel">
          <h3>Top kỹ năng đi cùng nhau (bảng Gold)</h3>
          <p className="note">Do Spark tính bằng self-join trên {fmtInt(m.reconcile.n_jobs)} tin, đây là bước shuffle nặng nhất.</p>
          <DataTable rows={spark.gold.skill_pairs?.slice(0, 7) || []} columns={[
            { key: 'a', label: 'Kỹ năng' }, { key: 'b', label: 'Đi cùng' }, { key: 'count', label: 'Số tin', num: true, render: fmtInt },
          ]} />
        </div>
      </div>
      {ml && (
        <div className="panel" style={{ marginTop: 24 }}>
          <h3>Spark MLlib đối chứng với mô hình chính</h3>
          <p className="note">{ml.split}. Vì cách chia tập khác nhau, cột so sánh chỉ mang tính tham khảo.</p>
          <DataTable rows={[...reg, ...(best ? [best] : [])]} columns={[
            { key: 'name', label: 'Mô hình' }, { key: 'RMSE', label: 'RMSE (triệu)', num: true, render: fmt3 },
            { key: 'MAE', label: 'MAE (triệu)', num: true, render: fmt3 }, { key: 'R2', label: 'R²', num: true, render: fmt3 },
          ]} />
          <p className="hint">
            FP-Growth phân tán: {fmtInt(ml.fp_growth.transactions)} giao dịch, {fmtInt(ml.fp_growth.rules)} luật
            (support ≥ {ml.fp_growth.min_support}, confidence ≥ {ml.fp_growth.min_confidence}), {secs(ml.fp_growth.seconds)}.
          </p>
        </div>
      )}
    </>
  )
}

function Benchmark({ b }) {
  if (!b) return <p className="state">Chưa đo. Chạy: <code>cd backend &amp;&amp; python -m pipeline.spark_job --benchmark</code></p>
  const real = b.sizes[0]
  const largest = b.sizes[b.sizes.length - 1]
  return (
    <>
      <div className="grid-2">
        <ChartBlock title="Thêm lõi CPU giúp Spark nhanh hơn bao nhiêu" note={`${fmtInt(b.cores[0].rows)} dòng (dữ liệu ×${b.core_factor}), thời gian là trung vị của ${b.repeats} lần đo. Máy có 4 lõi nên tăng tốc bị giới hạn.`}
          table={b.cores} columns={[{ key: 'cores', label: 'Số lõi', num: true }, { key: 'seconds', label: 'Giây', num: true, render: fmt3 }, { key: 'speedup', label: 'Tăng tốc', num: true, render: (v) => `×${fmt(v)}` }]}>
          <ResponsiveContainer width="100%" height={230}>
            <BarChart data={b.cores} margin={{ top: 20, right: 8, left: -14, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="#e4eae8" />
              <XAxis dataKey="cores" tickLine={false} tickFormatter={(v) => `${v} lõi`} />
              <YAxis tickLine={false} axisLine={false} unit="s" />
              <Tooltip cursor={{ fill: '#eef6f4' }} content={<TooltipBox render={(d) => <><div className="t">{d.cores} lõi</div>{fmt3(d.seconds)} giây, nhanh ×{fmt(d.speedup)}</>} />} />
              <Bar dataKey="seconds" fill="#00836c" radius={[4, 4, 0, 0]} maxBarSize={56} isAnimationActive={false}>
                <LabelList dataKey="seconds" position="top" formatter={(v) => `${fmt(v)} s`} style={{ fontSize: 12, fill: '#3c4f57' }} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartBlock>
        <ChartBlock title="Spark và pandas trên cùng một tải" note="4 lõi. Từ cột thứ hai trở đi là dữ liệu nhân bản, chỉ dùng để đo tốc độ, không đi vào phân tích."
          table={b.sizes} columns={[{ key: 'factor', label: 'Nhân', num: true, render: (v) => `×${v}` }, { key: 'rows', label: 'Số dòng', num: true, render: fmtInt }, { key: 'spark_seconds', label: 'Spark (s)', num: true, render: fmt3 }, { key: 'pandas_seconds', label: 'pandas (s)', num: true, render: fmt3 }]}>
          <ResponsiveContainer width="100%" height={230}>
            <BarChart data={b.sizes} margin={{ top: 20, right: 8, left: -14, bottom: 0 }} barGap={2}>
              <CartesianGrid vertical={false} stroke="#e4eae8" />
              <XAxis dataKey="rows" tickLine={false} tickFormatter={fmtInt} />
              <YAxis tickLine={false} axisLine={false} unit="s" />
              <Tooltip cursor={{ fill: '#eef6f4' }} content={<TooltipBox render={(d) => <><div className="t">{fmtInt(d.rows)} dòng</div>Spark {fmt3(d.spark_seconds)} s · pandas {fmt3(d.pandas_seconds)} s</>} />} />
              <Legend iconType="square" wrapperStyle={{ fontSize: 13 }} />
              <Bar dataKey="spark_seconds" name="Spark" fill="#00836c" radius={[4, 4, 0, 0]} maxBarSize={40} isAnimationActive={false}>
                <LabelList dataKey="spark_seconds" position="top" formatter={(v) => fmt(v)} style={{ fontSize: 12, fill: '#3c4f57' }} />
              </Bar>
              <Bar dataKey="pandas_seconds" name="pandas" fill="#e3a521" radius={[4, 4, 0, 0]} maxBarSize={40} isAnimationActive={false}>
                <LabelList dataKey="pandas_seconds" position="top" formatter={(v) => fmt(v)} style={{ fontSize: 12, fill: '#3c4f57' }} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartBlock>
      </div>
      <p className="method-note">
        <strong>Tải đo:</strong> {b.workload}. Với dữ liệu thật ({fmtInt(real.rows)} dòng), Spark mất {fmt(real.spark_seconds)} giây còn pandas mất {fmt(real.pandas_seconds)} giây.
        Ở mức lớn nhất ({fmtInt(largest.rows)} dòng), Spark mất {fmt(largest.spark_seconds)} giây còn pandas mất {fmt(largest.pandas_seconds)} giây.
        Vì vậy ETL phục vụ ứng dụng dùng pandas; Spark có giá trị khi dữ liệu lớn dần. Số đo trên một máy, dữ liệu nằm gọn trong RAM.
      </p>
    </>
  )
}

export default function Pipeline() {
  const [nonce, setNonce] = useState(0)
  const ov = useApi(`/api/pipeline/overview?_=${nonce}`)
  const spark = useApi(`/api/pipeline/spark?_=${nonce}`)
  const runs = useApi(`/api/pipeline/runs?limit=20&_=${nonce}`)
  const reports = useApi('/api/models/reports')
  const refresh = useRef(() => setNonce((n) => n + 1)).current
  const salary = reports.data?.salary
  const best = salary ? { name: `${salary.best_model} (mô hình chính)`, ...salary.results[salary.best_model]?.test } : null

  return (
    <>
      <PageHead title="Pipeline Big Data">
        Dữ liệu đi qua hai đường độc lập rồi được đối chiếu với nhau. Con số trên trang này lấy từ nhật ký chạy thật trong bảng pipeline_runs và kết quả của Spark.
      </PageHead>
      <ErrorBox error={ov.error} onRetry={refresh} />
      {!ov.data && ov.loading && <Skeleton lines={[220, 120, 300]} />}
      {ov.data && spark.data && (
        <>
          <Flow overview={ov.data} spark={spark.data} />

          <Section title="Chạy thử trực tiếp" lede="Các job chạy thành tiến trình riêng trên máy này, log hiện theo thời gian thực. ETL và huấn luyện chỉ chạy bằng dòng lệnh vì ETL tạo lại toàn bộ lược đồ.">
            <JobPanel overview={ov.data} onDone={refresh} />
          </Section>

          <Section title="Đối soát dữ liệu" lede="Bấm “Kiểm tra lại” để chạy lại ngay trên dữ liệu hiện tại. Có thể xem chi tiết quy tắc làm sạch ở trang Chất lượng dữ liệu.">
            <Reconcile />
            <p className="hint" style={{ marginTop: 8 }}><Link to="/data">Mở trang Chất lượng dữ liệu</Link></p>
          </Section>

          <Section title="Kết quả tầng Spark"><SparkResults spark={spark.data} best={best} /></Section>
          <Section title="Hiệu năng đo được"><Benchmark b={spark.data.benchmark} /></Section>

          <Section title="Nhật ký chạy pipeline" lede="20 lần chạy gần nhất.">
            <div className="panel">
              {runs.data?.length
                ? <DataTable rows={runs.data} columns={[
                  { key: 'job', label: 'Bước', render: (v) => JOB_LABEL[v] || v },
                  { key: 'status', label: 'Kết quả', render: (v) => <StatusDot status={v} /> },
                  { key: 'trigger', label: 'Từ', render: (v) => (v === 'ui' ? 'Giao diện' : 'Dòng lệnh') },
                  { key: 'started_at', label: 'Bắt đầu', render: when },
                  { key: 'seconds', label: 'Thời gian', num: true, render: secs },
                  { key: 'rows_in', label: 'Dòng vào', num: true, render: fmtInt },
                  { key: 'rows_out', label: 'Dòng ra', num: true, render: fmtInt },
                ]} />
                : <p className="state">Chưa có lần chạy nào được ghi nhận.</p>}
            </div>
          </Section>
        </>
      )}
    </>
  )
}
