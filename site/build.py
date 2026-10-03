"""make site: build the public static site into site/dist.

Pages are HTML fragments in site/src; this script wraps each in the shared layout and renders
the results page from site/results.json only (written by `make export` from a real passing
end-to-end run). Without results.json the results page says so, labelled as having no data.
The site has no database access and makes no requests at runtime.

    python -m site.build      (module name clashes with the stdlib `site`; run as a file:)
    python site/build.py
"""
from __future__ import annotations

import html
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC, DIST = ROOT / "src", ROOT / "dist"
RESULTS = ROOT / "results.json"

PAGES = [("index.html", "What it does"), ("architecture.html", "Architecture"), ("results.html", "Results"),
         ("privacy.html", "Privacy"), ("terms.html", "Terms")]

LAYOUT = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{description}">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="/styles.css">
</head>
<body>
<header class="site">
<a class="brand" href="/">Blind Tuner</a>
<nav>{nav}</nav>
</header>
<main>
{body}
</main>
<footer class="site">
<p>Blind Tuner is a CodeUtsava X.0 entry for Problem Statement 4. Source: <a href="https://github.com/Derpinator96/Tiresias">github.com/Derpinator96/Tiresias</a>.</p>
<p><a href="/privacy.html">Privacy policy</a> &middot; <a href="/terms.html">Terms</a></p>
</footer>
</body>
</html>
"""


def _nav(current: str) -> str:
    current_attr = ' aria-current="page"'
    return " ".join(f'<a href="/{f}"{current_attr if f == current else ""}>{label}</a>' for f, label in PAGES)


def _fmt(v) -> str:
    """Values exactly as exported: no re-rounding, so every figure on the page is in
    results.json. Whole numbers get thousands separators."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return f"{int(v):,}" if float(v).is_integer() else repr(float(v))
    return html.escape(str(v))


def results_body() -> str:
    if not RESULTS.exists():
        return ("<h1>No end-to-end run has been exported yet</h1>\n"
                "<p class=\"placeholder\">PLACEHOLDER: this page shows numbers only from a passing end-to-end run, "
                "exported to results.json. None has passed yet, so there are no numbers here.</p>")
    r = json.loads(RESULTS.read_text(encoding="utf-8"))
    rows = "\n".join(
        f"<tr><th scope=\"row\">{html.escape(x['name'])}</th><td class=\"num\">{_fmt(x['value'])} {html.escape(x['unit'])}</td>"
        f"<td>{html.escape(x['source'])}</td><td>{html.escape(x['assumption'])}</td></tr>" for x in r["results"])
    missing = "".join(f"<li>{html.escape(m)}</li>" for m in r["not_built"])
    ds = r["dataset"]
    return f"""<h1>Results of end-to-end run {html.escape(r['run_id'])}</h1>
<dl class="meta">
<dt>Finished</dt><dd>{html.escape(r['finished_at'])}</dd>
<dt>Code version</dt><dd><code>{html.escape(r['git_commit'][:12])}</code></dd>
<dt>Dataset</dt><dd>hero table {_fmt(ds['hero_table_rows'])} rows, {_fmt(ds['hero_table_size_mb'])} MB ({html.escape(ds['assumption'])})</dd>
</dl>
<p>Every number below was produced by that run. Its source and the assumption it rests on are in the same row.</p>
<div class="table-wrap"><table>
<thead><tr><th scope="col">Measure</th><th scope="col">Value</th><th scope="col">Source</th><th scope="col">Assumption</th></tr></thead>
<tbody>
{rows}
</tbody></table></div>
<h2>Not built in this run</h2>
<ul>{missing}</ul>"""


def build() -> list[str]:
    # Empty the folder rather than delete it: on Windows a folder that is some process's
    # working directory (a local preview server) cannot be removed.
    DIST.mkdir(exist_ok=True)
    # Keep .vercel: `vercel link` stores the project link there.
    for old in DIST.iterdir():
        if old.name == ".vercel":
            continue
        shutil.rmtree(old) if old.is_dir() else old.unlink()
    for f in ("favicon.svg", "styles.css"):
        shutil.copy(ROOT / f, DIST / f)
    written = []
    for name, _label in PAGES:
        if name == "results.html":
            body = results_body()
        else:
            body = (SRC / name).read_text(encoding="utf-8")
        title = re.search(r"<h1>(.*?)</h1>", body, re.S).group(1)
        title = re.sub(r"<[^>]+>", "", title).strip()
        first_p = re.search(r"<p[^>]*>(.*?)</p>", body, re.S)
        description = re.sub(r"<[^>]+>", "", first_p.group(1)).strip() if first_p else title
        page = LAYOUT.format(title=html.escape(f"{title} | Blind Tuner") if name != "index.html" else "Blind Tuner",
                             description=html.escape(description[:300], quote=True), nav=_nav(name), body=body)
        (DIST / name).write_text(page, encoding="utf-8")
        written.append(name)
    (DIST / "vercel.json").write_text(json.dumps({"cleanUrls": False, "trailingSlash": False}) + "\n", encoding="utf-8")
    return written


if __name__ == "__main__":
    print("built:", ", ".join(build()), "->", DIST)
