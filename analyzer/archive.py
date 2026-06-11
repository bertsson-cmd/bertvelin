"""Daily archive — keeps every briefing as reports/archive/YYYY-MM-DD.html
with a calendar index, so the whole tournament's picks stay browsable and
the scoreboard stays auditable (nobody can accuse the bot of rewriting
history: the Action commits the archive to git).
"""

from __future__ import annotations
import os
import re
import shutil

INDEX_CSS = """
*{box-sizing:border-box;margin:0}
body{background:#008080;font-family:Tahoma,"MS Sans Serif",sans-serif;font-size:12px;padding:40px 16px}
.win{max-width:520px;margin:0 auto;background:#c0c0c0;padding:3px;border:2px solid;
 border-color:#fff #404040 #404040 #fff;box-shadow:1px 1px 0 #000,4px 4px 0 rgba(0,0,0,.25)}
.tbar{display:flex;justify-content:space-between;background:linear-gradient(90deg,#000080,#1084d0);
 color:#fff;font-weight:bold;padding:3px 8px}
.body{background:#fff;border:2px solid;margin:3px;padding:8px 4px;
 border-color:#808080 #fff #fff #808080;max-height:70vh;overflow:auto}
a.row{display:block;padding:5px 10px;color:#000;text-decoration:none;font-family:"Courier New",monospace}
a.row:hover{background:#000080;color:#fff}
.back{display:block;text-align:center;padding:6px;font-weight:bold}
"""


def archive_report(report_path: str, day: str, reports_dir: str = "reports") -> str:
    """Copy today's briefing into the archive and rebuild the index.
    Returns the relative href of the archive index (for the taskbar link)."""
    arch_dir = os.path.join(reports_dir, "archive")
    os.makedirs(arch_dir, exist_ok=True)

    dated = os.path.join(arch_dir, f"{day}.html")
    with open(report_path, encoding="utf-8") as f:
        html = f.read()
    # inside archive/ the index link is a sibling, not a child
    with open(dated, "w", encoding="utf-8") as f:
        f.write(html.replace('href="archive/index.html"', 'href="index.html"'))

    days = sorted((f[:-5] for f in os.listdir(arch_dir)
                   if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.html", f)), reverse=True)
    rows = "\n".join(f'<a class="row" href="{d}.html">&#128196; {d}</a>' for d in days)
    index = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bertpicker — gamlir seðlar</title><style>{INDEX_CSS}</style></head><body>
<div class="win">
  <div class="tbar"><span>archive.exe — Gamlir seðlar</span><span>&#10005;</span></div>
  <div class="body">{rows or '<a class="row">empty</a>'}</div>
  <a class="back" href="../index.html">&larr; Back to today</a>
</div></body></html>"""
    with open(os.path.join(arch_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(index)
    return "archive/index.html"
