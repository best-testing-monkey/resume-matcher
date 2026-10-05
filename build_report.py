# build_report.py
"""Turn a job_matcher --mode embed JSONL output into a markdown + HTML report.

Reads similarity records plus the scraped job markdown files they point at
(for title/source/client/location), and writes a ranked report.

CLI usage:
    python build_report.py results.jsonl --out-dir reports --title "cv_1000 vs scraper"
"""

import argparse
import html
import json
import re
import statistics
from pathlib import Path

JOB_FIELD_RE = re.compile(r"^- (\w[\w ]*):\s*(.+)$")


def parse_job(path: Path) -> dict:
    """Pull title + metadata fields out of a scraped job markdown file."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    title = path.stem
    for line in lines:
        if line.startswith("# "):
            title = line[2:].strip()
            break
    fields = {}
    for line in lines:
        m = JOB_FIELD_RE.match(line)
        if m:
            fields[m.group(1).strip().lower()] = m.group(2).strip()
    location = fields.get("location", "")
    return {
        "title": title,
        "source": fields.get("source", ""),
        "client": fields.get("client", ""),
        "location": location,
        "posted": fields.get("posted", ""),
        "workplace": fields.get("workplace", ""),
    }


def site_name(job_file: str) -> str:
    """Derive a readable site name from the job file's slug prefix."""
    slug = Path(job_file).stem.split("-")[0]
    return slug.replace("_", " ").title()


def load_records(jsonl_path: Path) -> list[dict]:
    records = []
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        job_path = Path(row["job_file"])
        meta = parse_job(job_path)
        records.append(
            {
                "score": row["probs"]["similarity"],
                "job_file": row["job_file"],
                "site": site_name(row["job_file"]),
                **meta,
            }
        )
    records.sort(key=lambda r: -r["score"])
    for i, r in enumerate(records, start=1):
        r["rank"] = i
    return records


def histogram(scores: list[float], bucket: float = 0.05) -> list[tuple[float, float, int]]:
    lo = (min(scores) // bucket) * bucket
    hi = (max(scores) // bucket + 1) * bucket
    edges = []
    e = lo
    while e < hi - 1e-9:
        edges.append(round(e, 2))
        e += bucket
    counts = [0] * len(edges)
    for s in scores:
        idx = min(int((s - lo) / bucket), len(edges) - 1)
        counts[idx] += 1
    return [(edges[i], round(edges[i] + bucket, 2), counts[i]) for i in range(len(edges))]


def site_breakdown(records: list[dict]) -> list[dict]:
    by_site: dict[str, list[float]] = {}
    for r in records:
        by_site.setdefault(r["site"], []).append(r["score"])
    rows = [
        {
            "site": site,
            "count": len(scores),
            "avg": statistics.mean(scores),
            "top": max(scores),
        }
        for site, scores in by_site.items()
    ]
    rows.sort(key=lambda r: -r["avg"])
    return rows


def write_markdown(
    out_path: Path,
    title: str,
    resume_file: str,
    records: list[dict],
    stats: dict,
    sites: list[dict],
    top_n: int,
) -> None:
    lines = [f"# {title}", ""]
    lines.append(
        f"Resume `{resume_file}` scored against **{stats['count']}** postings "
        "via bi-encoder cosine similarity (`job_matcher.py --mode embed`)."
    )
    lines.append("")
    lines.append("## Score distribution")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    for label, key in [
        ("Count", "count"),
        ("Min", "min"),
        ("P25", "p25"),
        ("Median", "median"),
        ("P75", "p75"),
        ("Max", "max"),
        ("Mean", "mean"),
    ]:
        val = stats[key]
        lines.append(f"| {label} | {val if key == 'count' else f'{val:.3f}'} |")
    lines.append("")
    lines.append(
        "Cosine similarity is a ranking signal, not a calibrated match "
        "probability — treat this as a coarse shortlist, not a verdict."
    )
    lines.append("")

    lines.append("## By site")
    lines.append("")
    lines.append("| Site | Postings | Avg score | Top score |")
    lines.append("|---|---:|---:|---:|")
    for row in sites:
        lines.append(
            f"| {row['site']} | {row['count']} | {row['avg']:.3f} | {row['top']:.3f} |"
        )
    lines.append("")

    lines.append(f"## Top {top_n} matches")
    lines.append("")
    lines.append("| # | Score | Job | Site | Workplace | Location |")
    lines.append("|---:|---:|---|---|---|---|")
    for r in records[:top_n]:
        job_link = f"[{r['title']}]({r['source']})" if r["source"] else r["title"]
        lines.append(
            f"| {r['rank']} | {r['score']:.3f} | {job_link} | {r['site']} | "
            f"{r['workplace'] or '—'} | {r['location'] or '—'} |"
        )
    lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def write_html(
    out_path: Path,
    title: str,
    resume_file: str,
    records: list[dict],
    stats: dict,
    sites: list[dict],
    hist: list[tuple[float, float, int]],
    top_n: int,
) -> None:
    max_count = max(c for _, _, c in hist) or 1
    bars = []
    for lo, hi, count in hist:
        pct = round(count / max_count * 100, 1)
        bars.append(
            f'<div class="bar-col"><div class="bar" style="height:{pct}%" '
            f'tabindex="0" data-count="{count}" data-range="{lo:.2f}–{hi:.2f}">'
            f'</div><div class="bar-label">{lo:.2f}</div></div>'
        )
    bars_html = "".join(bars)

    site_rows = "".join(
        f"<tr><td>{html.escape(r['site'])}</td><td class='num'>{r['count']}</td>"
        f"<td class='num'>{r['avg']:.3f}</td><td class='num'>{r['top']:.3f}</td></tr>"
        for r in sites
    )

    match_rows = []
    for r in records[:top_n]:
        job_cell = (
            f'<a href="{html.escape(r["source"])}" target="_blank" rel="noopener">'
            f'{html.escape(r["title"])}</a>'
            if r["source"]
            else html.escape(r["title"])
        )
        match_rows.append(
            f"<tr><td class='num'>{r['rank']}</td><td class='num score'>{r['score']:.3f}</td>"
            f"<td>{job_cell}</td><td>{html.escape(r['site'])}</td>"
            f"<td>{html.escape(r['workplace'] or '—')}</td>"
            f"<td>{html.escape(r['location'] or '—')}</td></tr>"
        )
    match_rows_html = "".join(match_rows)

    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
  :root {{
    color-scheme: light;
    --surface-1: #fcfcfb;
    --page: #f9f9f7;
    --text-primary: #0b0b0b;
    --text-secondary: #52514e;
    --text-muted: #898781;
    --gridline: #e1e0d9;
    --baseline: #c3c2b7;
    --series-1: #2a78d6;
    --border: rgba(11,11,11,0.10);
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      color-scheme: dark;
      --surface-1: #1a1a19;
      --page: #0d0d0d;
      --text-primary: #ffffff;
      --text-secondary: #c3c2b7;
      --text-muted: #898781;
      --gridline: #2c2c2a;
      --baseline: #383835;
      --series-1: #3987e5;
      --border: rgba(255,255,255,0.10);
    }}
  }}
  :root[data-theme="dark"] {{
    color-scheme: dark;
    --surface-1: #1a1a19;
    --page: #0d0d0d;
    --text-primary: #ffffff;
    --text-secondary: #c3c2b7;
    --text-muted: #898781;
    --gridline: #2c2c2a;
    --baseline: #383835;
    --series-1: #3987e5;
    --border: rgba(255,255,255,0.10);
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    background: var(--page);
    color: var(--text-primary);
  }}
  .wrap {{ max-width: 980px; margin: 0 auto; padding: 32px 20px 64px; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }}
  .sub {{ color: var(--text-secondary); font-size: 14px; margin: 0 0 28px; }}
  .card {{
    background: var(--surface-1);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 20px;
    margin-bottom: 24px;
  }}
  .card h2 {{ font-size: 15px; margin: 0 0 16px; color: var(--text-secondary); font-weight: 600; }}
  .tiles {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 24px; }}
  .tile {{
    background: var(--surface-1);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 16px;
  }}
  .tile .label {{ font-size: 12px; color: var(--text-secondary); margin-bottom: 6px; }}
  .tile .value {{ font-size: 26px; font-weight: 600; }}
  .chart {{
    display: flex;
    align-items: flex-end;
    gap: 6px;
    height: 200px;
    border-bottom: 1px solid var(--baseline);
    padding-top: 8px;
  }}
  .bar-col {{ flex: 1; display: flex; flex-direction: column; align-items: center; height: 100%; justify-content: flex-end; }}
  .bar {{
    width: 100%;
    max-width: 24px;
    background: var(--series-1);
    border-radius: 4px 4px 0 0;
    position: relative;
    cursor: default;
    min-height: 2px;
  }}
  .bar:hover, .bar:focus {{ filter: brightness(1.12); outline: none; }}
  .bar-label {{ font-size: 10px; color: var(--text-muted); margin-top: 6px; white-space: nowrap; }}
  .bar::after {{
    content: attr(data-count) " jobs \\2022 " attr(data-range);
    position: absolute;
    bottom: calc(100% + 6px);
    left: 50%;
    transform: translateX(-50%);
    background: var(--text-primary);
    color: var(--surface-1);
    font-size: 11px;
    padding: 4px 8px;
    border-radius: 6px;
    white-space: nowrap;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.1s;
  }}
  .bar:hover::after, .bar:focus::after {{ opacity: 1; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th, td {{ text-align: left; padding: 7px 10px; border-bottom: 1px solid var(--gridline); }}
  th {{ color: var(--text-secondary); font-weight: 600; font-size: 12px; }}
  td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  td.score {{ font-weight: 600; }}
  a {{ color: var(--series-1); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .note {{ font-size: 12px; color: var(--text-muted); margin-top: 10px; }}
</style>
</head>
<body>
<div class="viz-root">
<div class="wrap">
  <h1>{html.escape(title)}</h1>
  <p class="sub">Resume <code>{html.escape(resume_file)}</code> vs {stats['count']} scraped postings &middot; bi-encoder cosine similarity (job_matcher.py --mode embed)</p>

  <div class="tiles">
    <div class="tile"><div class="label">Postings scored</div><div class="value">{stats['count']}</div></div>
    <div class="tile"><div class="label">Top score</div><div class="value">{stats['max']:.3f}</div></div>
    <div class="tile"><div class="label">Median score</div><div class="value">{stats['median']:.3f}</div></div>
    <div class="tile"><div class="label">Mean score</div><div class="value">{stats['mean']:.3f}</div></div>
  </div>

  <div class="card">
    <h2>Score distribution</h2>
    <div class="chart">
      {bars_html}
    </div>
    <p class="note">Cosine similarity is a ranking signal, not a calibrated match probability &mdash; treat this as a coarse shortlist, not a verdict.</p>
  </div>

  <div class="card">
    <h2>By site</h2>
    <table>
      <thead><tr><th>Site</th><th class="num">Postings</th><th class="num">Avg score</th><th class="num">Top score</th></tr></thead>
      <tbody>{site_rows}</tbody>
    </table>
  </div>

  <div class="card">
    <h2>Top {top_n} matches</h2>
    <p class="note">Workplace is extracted by the scraper per-site (a structured field, badge, or label on the posting) &mdash; blank means no such signal was found, not that the role is confirmed on-site.</p>
    <table>
      <thead><tr><th class="num">#</th><th class="num">Score</th><th>Job</th><th>Site</th><th>Workplace</th><th>Location</th></tr></thead>
      <tbody>{match_rows_html}</tbody>
    </table>
  </div>
</div>
</div>
</body>
</html>
"""
    out_path.write_text(doc, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jsonl", help="job_matcher --mode embed JSONL output")
    parser.add_argument("--out-dir", default="reports", help="Output directory (default: reports)")
    parser.add_argument("--title", default="Resume match report", help="Report title")
    parser.add_argument("--resume-file", default=None, help="Resume file label (default: inferred from JSONL)")
    parser.add_argument("--top-n", type=int, default=30, help="Number of top matches to list (default: 30)")
    parser.add_argument("--name", default="report", help="Base filename for outputs (default: report)")
    args = parser.parse_args()

    jsonl_path = Path(args.jsonl)
    records = load_records(jsonl_path)
    if not records:
        raise SystemExit("no records found in " + args.jsonl)

    resume_file = args.resume_file
    if not resume_file:
        first_row = json.loads(jsonl_path.read_text(encoding="utf-8").splitlines()[0])
        resume_file = first_row.get("resume_file", "")

    scores = [r["score"] for r in records]
    stats = {
        "count": len(scores),
        "min": min(scores),
        "max": max(scores),
        "mean": statistics.mean(scores),
        "median": statistics.median(scores),
        "p25": statistics.quantiles(scores, n=4)[0],
        "p75": statistics.quantiles(scores, n=4)[2],
    }
    sites = site_breakdown(records)
    hist = histogram(scores)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"{args.name}.md"
    html_path = out_dir / f"{args.name}.html"

    write_markdown(md_path, args.title, resume_file, records, stats, sites, args.top_n)
    write_html(html_path, args.title, resume_file, records, stats, sites, hist, args.top_n)
    print(f"wrote {md_path}")
    print(f"wrote {html_path}")


if __name__ == "__main__":
    main()
