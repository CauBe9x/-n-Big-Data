"""Sinh sơ đồ ERD (từ CSDL PostgreSQL thật) và sơ đồ kiến trúc hệ thống bằng Graphviz.

    pip install psycopg2-binary   # + cài Graphviz (lệnh `dot`)
    python docs/make_diagrams.py  # -> docs/erd.png, docs/erd.svg, docs/architecture.png, docs/architecture.svg
"""
from __future__ import annotations

import html
import os
import subprocess
from pathlib import Path

import psycopg2

DSN = os.getenv("VIETJOBS_PG_DSN", "postgresql://vietjobs:vietjobs@localhost:5432/vietjobs")
OUT = Path(__file__).resolve().parent
FONT = "DejaVu Sans"

GROUPS = {  # nhóm bảng -> màu tiêu đề
    "Dữ liệu tuyển dụng": ("#0e7a6a", ["jobs", "provinces", "categories", "skills", "languages",
                                        "job_categories", "job_skills", "job_languages"]),
    "Máy học": ("#2a5d9f", ["ml_training_runs", "ml_models", "model_metrics", "predictions"]),
    "Khai phá dữ liệu": ("#a35a12", ["mining_runs", "association_rules", "rule_antecedents", "clusters",
                                      "job_clusters", "cluster_k_scores", "skill_salary_stats"]),
}
SHORT_TYPES = {"character varying": "varchar", "integer": "int", "smallint": "smallint", "bigint": "bigint",
               "numeric": "numeric", "double precision": "float8", "real": "float4", "boolean": "bool",
               "text": "text", "jsonb": "jsonb", "timestamp without time zone": "timestamp"}


def fetch_schema(cur):
    cur.execute("""SELECT table_name, column_name, data_type, is_nullable, ordinal_position
                   FROM information_schema.columns WHERE table_schema = 'public'
                   AND table_name IN (SELECT table_name FROM information_schema.tables
                                      WHERE table_schema = 'public' AND table_type = 'BASE TABLE')
                   ORDER BY table_name, ordinal_position""")
    cols: dict[str, list] = {}
    for t, c, typ, nullable, _ in cur.fetchall():
        cols.setdefault(t, []).append((c, SHORT_TYPES.get(typ, typ), nullable == "YES"))
    cur.execute("""SELECT tc.table_name, kcu.column_name FROM information_schema.table_constraints tc
                   JOIN information_schema.key_column_usage kcu USING (constraint_schema, constraint_name)
                   WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = 'public'""")
    pks = {(t, c) for t, c in cur.fetchall()}
    cur.execute("""SELECT con.conrelid::regclass::text, a.attname, con.confrelid::regclass::text, af.attname
                   FROM pg_constraint con
                   JOIN pg_attribute a  ON a.attrelid = con.conrelid AND a.attnum = ANY (con.conkey)
                   JOIN pg_attribute af ON af.attrelid = con.confrelid AND af.attnum = ANY (con.confkey)
                   WHERE con.contype = 'f' AND con.connamespace = 'public'::regnamespace""")
    fks = cur.fetchall()
    return cols, pks, fks


def erd_dot(cols, pks, fks, only: str | None = None, title: str = "VietJobs – Lược đồ CSDL PostgreSQL") -> str:
    """only = tên một nhóm trong GROUPS để vẽ riêng nhóm đó."""
    groups = {k: v for k, v in GROUPS.items() if only is None or k == only}
    keep = {t for _, ts in groups.values() for t in ts}
    fks = [f for f in fks if f[0] in keep and f[2] in keep]
    fk_cols = {(t, c) for t, c, _, _ in fks}
    lines = [f'digraph ERD {{ graph [rankdir=LR, splines=spline, nodesep=0.35, ranksep=0.9, bgcolor="white", newrank=true, '
             f'fontname="{FONT}", pad=0.4, label=<<B>{title}</B><BR/>'
             f'<FONT POINT-SIZE="11">PK = khoá chính · FK = khoá ngoại · * = NOT NULL</FONT>>, labelloc=t, fontsize=20];',
             f'node [shape=plain, fontname="{FONT}", fontsize=10]; '
             f'edge [fontname="{FONT}", color="#7d8f93", arrowhead=crow, arrowtail=teetee, dir=both, penwidth=1.2, arrowsize=0.8];']
    for g_i, (gname, (color, tables)) in enumerate(groups.items()):
        lines.append(f'subgraph cluster_{g_i} {{ label=<<B>{gname}</B>>; fontsize=14; fontcolor="{color}"; '
                     f'style="rounded,dashed"; color="{color}"; margin=14;')
        for t in tables:
            if t not in cols:
                continue
            rows = [f'<TR><TD BGCOLOR="{color}" COLSPAN="3"><FONT COLOR="white"><B>{t}</B></FONT></TD></TR>']
            for c, typ, nullable in cols[t]:
                key = "PK" if (t, c) in pks else ""
                if (t, c) in fk_cols:
                    key = (key + " FK").strip()
                name = f"<B>{html.escape(c)}</B>" if "PK" in key else html.escape(c)
                star = "" if nullable else " *"
                key_cell = (f'<TD ALIGN="LEFT"><FONT COLOR="{color}"><B>{key}</B></FONT></TD>' if key
                            else '<TD> </TD>')
                rows.append(f'<TR><TD ALIGN="LEFT" PORT="{c}">{name}{star}</TD>'
                            f'<TD ALIGN="LEFT"><FONT COLOR="#5d6e75">{html.escape(typ)}</FONT></TD>'
                            f'{key_cell}</TR>')
            lines.append(f'"{t}" [label=<<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" CELLPADDING="4" '
                         f'COLOR="#c9d3d1">{"".join(rows)}</TABLE>>];')
        lines.append("}")
    # cạnh: bảng được tham chiếu (phía 1) -> bảng chứa khoá ngoại (phía nhiều); nhãn = cột FK
    for t, c, rt, rc in fks:
        lines.append(f'"{rt}" -> "{t}" [xlabel=<<FONT POINT-SIZE="8" COLOR="#5d6e75">{c}</FONT>>];')
    # các bảng danh mục cùng một cột cho gọn
    if "jobs" in keep:
        lines.append('{rank=same; provinces; categories; languages; skills;}')
        lines.append('{rank=same; job_categories; job_skills; job_languages;}')
    lines.append("}")
    return "\n".join(lines)


ARCH = r'''digraph Arch {
graph [rankdir=LR, fontname="%(f)s", bgcolor="white", pad=0.5, nodesep=0.55, ranksep=0.75, newrank=true,
       label=<<B>VietJobs – Kiến trúc hệ thống (chạy local)</B>>, labelloc=t, fontsize=22];
node [shape=box, style="rounded,filled", fontname="%(f)s", fontsize=12, color="#9fb3ae", fillcolor="#f4f7f6",
      margin="0.2,0.12", width=2.6];
edge [fontname="%(f)s", fontsize=10, color="#5d6e75", fontcolor="#3c4f57", penwidth=1.3];

csv [label=<<B>VietJobs.csv</B><BR/>48.092 dòng · 18 cột<BR/><FONT POINT-SIZE="10">Hugging Face</FONT>>, shape=note,
     fillcolor="#fff7e6", color="#d8b26a", width=2];

subgraph cluster_pipe { label=<<B>① Pipeline dữ liệu &amp; máy học</B>>; style="rounded,dashed"; color="#0e7a6a";
  fontcolor="#0e7a6a"; margin=16;
  etl   [label=<<B>ETL</B><BR/>làm sạch · chuẩn hoá · gộp tin trùng>];
  train [label=<<B>Huấn luyện</B><BR/>LightGBM · OvR LogReg · Linear SVM>];
  mine  [label=<<B>Khai phá</B><BR/>FP-Growth · K-Means>];
  spark [label=<<B>Apache Spark</B> (tuỳ chọn)<BR/>Spark SQL · MLlib>, fillcolor="#fff1e8", color="#e0a37a"];
}

subgraph cluster_store { label=<<B>② Lưu trữ</B>>; style="rounded,dashed"; color="#2a5d9f"; fontcolor="#2a5d9f"; margin=16;
  pg  [label=<<B>PostgreSQL 16</B><BR/>CSDL <I>vietjobs</I><BR/>19 bảng · 4 view · 23 khoá ngoại>, shape=cylinder,
       fillcolor="#e3eefb", color="#2a5d9f", height=1.3];
  art [label=<<B>artifacts/*.joblib</B><BR/>3 mô hình đã huấn luyện>, shape=folder, fillcolor="#eef6f4"];
}

subgraph cluster_app { label=<<B>③ Ứng dụng máy học</B>>; style="rounded,dashed"; color="#0e7a6a"; fontcolor="#0e7a6a"; margin=16;
  api [label=<<B>Backend FastAPI</B> :8000<BR/>REST /api/… · SQLAlchemy>];
  fe  [label=<<B>Frontend React + Vite</B> :5173<BR/>dự đoán · gợi ý · phân loại · khai phá>];
}

subgraph cluster_bi { label=<<B>④ Dashboard thống kê (triển khai riêng)</B>>; style="rounded,dashed"; color="#a35a12";
  fontcolor="#a35a12"; margin=16;
  ss [label=<<B>Apache Superset</B> :8088<BR/>16 biểu đồ trên view v_job_*>, fillcolor="#fbf3ea", color="#d0a070"];
}

user [label=<<B>Người dùng</B><BR/>trình duyệt>, shape=ellipse, fillcolor="white", width=1.6];

{rank=same; etl; train; mine; spark;}
{rank=same; pg; art;}
{rank=same; api; ss;}

csv -> etl;
csv -> spark [style=dashed];
etl -> pg   [label="INSERT"];
train -> pg [label="đọc dữ liệu /\nghi kết quả", dir=both];
mine -> pg  [label="đọc dữ liệu /\nghi luật, cụm", dir=both];
train -> art [label="lưu mô hình"];
pg -> api   [label="SQL", dir=both];
art -> api  [label="nạp mô hình", style=dashed];
pg -> ss    [label="SQL trên view", dir=both];
api -> fe   [label="JSON", dir=both];
fe -> user  [dir=back];
ss -> user  [dir=back];
}
''' % {"f": FONT}


def render(dot_src: str, name: str) -> None:
    (OUT / f"{name}.dot").write_text(dot_src, encoding="utf-8")
    for fmt, extra in (("svg", []), ("png", ["-Gdpi=170"])):
        subprocess.run(["dot", f"-T{fmt}", *extra, "-o", str(OUT / f"{name}.{fmt}"), str(OUT / f"{name}.dot")],
                       check=True)
    print(f"  - {name}.png / {name}.svg")


if __name__ == "__main__":
    with psycopg2.connect(DSN) as conn, conn.cursor() as cur:
        cols, pks, fks = fetch_schema(cur)
    print(f"[Sơ đồ] {len(cols)} bảng, {len(fks)} khoá ngoại")
    render(erd_dot(cols, pks, fks), "erd")
    render(erd_dot(cols, pks, fks, only="Dữ liệu tuyển dụng",
                   title="VietJobs – Các bảng dữ liệu tuyển dụng (lõi)"), "erd_core")
    render(ARCH, "architecture")
