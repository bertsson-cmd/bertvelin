"""Render the daily briefing as a single self-contained HTML file.

Theme: BERTPICKER 1.0 — a Windows 95 desktop. Each slip is a program
window, the reasoning is a Notepad file, and there's a taskbar with a
Start button. The logo is blocky pixel-game lettering.
"""

from __future__ import annotations
from datetime import date

from .parlay import Parlay

CSS = """
:root{
  --desktop:#008080; --chrome:#c0c0c0; --titlebar1:#000080; --titlebar2:#1084d0;
  --ink:#000; --shadow:#404040; --hilite:#fff; --mid:#808080;
  --grass:#5d9c3a; --grassdark:#3e6b26; --dirt:#6b4a2f;
  --navy:#000080; --warnbar1:#7a0a0a; --warnbar2:#c43a10;
}
*{box-sizing:border-box;margin:0}
body{background:var(--desktop);color:var(--ink);
  font-family:Tahoma,"MS Sans Serif",Geneva,sans-serif;font-size:12px;
  min-height:100vh;padding:28px 16px 64px}
.wrap{max-width:960px;margin:0 auto}

/* ---- pixel-block logo ---- */
.logo{ text-align:center;margin:8px 0 6px;
  font-family:"Press Start 2P",monospace;color:var(--grass);
  font-size:clamp(20px,4.6vw,40px);letter-spacing:2px;line-height:1.2;
  text-shadow:0 3px 0 var(--grassdark),0 6px 0 var(--dirt),
              3px 0 0 var(--grassdark),-3px 0 0 var(--grassdark),
              6px 9px 0 rgba(0,0,0,.35);
  -webkit-text-stroke:1px #1d3312}
.logo small{font-size:.45em;color:#e9e2c8;
  text-shadow:0 2px 0 #6b6450,2px 3px 0 rgba(0,0,0,.35);-webkit-text-stroke:1px #444}
.splash{ text-align:center;font-family:"Press Start 2P",monospace;
  font-size:10px;color:#ff0;transform:rotate(-6deg);margin:2px 0 22px;
  text-shadow:2px 2px 0 #5a5a00}
@media (prefers-reduced-motion:no-preference){
  .splash{animation:pulse 1s infinite alternate}
  @keyframes pulse{from{scale:1}to{scale:1.06}}
}

/* ---- win95 window chrome ---- */
.win{background:var(--chrome);padding:3px;margin-bottom:24px;
  border:2px solid;border-color:var(--hilite) var(--shadow) var(--shadow) var(--hilite);
  box-shadow:1px 1px 0 #000,4px 4px 0 rgba(0,0,0,.25)}
.tbar{display:flex;justify-content:space-between;align-items:center;
  background:linear-gradient(90deg,var(--titlebar1),var(--titlebar2));
  color:#fff;font-weight:bold;font-size:12px;padding:3px 4px 3px 8px;gap:8px}
.win.risky .tbar{background:linear-gradient(90deg,var(--warnbar1),var(--warnbar2))}
.tbtns{display:flex;gap:2px}
.tbtns i{font-style:normal;width:18px;height:16px;display:inline-flex;
  align-items:center;justify-content:center;background:var(--chrome);color:#000;
  font:bold 10px Tahoma;border:2px solid;
  border-color:var(--hilite) var(--shadow) var(--shadow) var(--hilite)}
.menu{font-size:12px;padding:3px 8px;border-bottom:1px solid var(--mid)}
.menu u{text-decoration:underline}
.win-body{padding:10px}

/* ---- slips grid ---- */
.slips{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:0 20px}

/* ---- legs ---- */
.combined{display:flex;justify-content:space-between;align-items:baseline;
  background:#fff;border:2px solid;margin-bottom:10px;padding:6px 10px;
  border-color:var(--mid) var(--hilite) var(--hilite) var(--mid)}
.combined b{font-family:"VT323",monospace;font-size:30px}
.leg{margin-bottom:12px}
.leg .pick{font-weight:bold}
.leg .meta{display:flex;justify-content:space-between;color:#222;margin:2px 0 4px;
  font-family:"VT323",monospace;font-size:16px}
.pbar{height:16px;background:#fff;padding:2px;border:2px solid;
  border-color:var(--mid) var(--hilite) var(--hilite) var(--mid)}
.pbar i{display:block;height:100%;
  background:repeating-linear-gradient(90deg,var(--navy) 0 8px,transparent 8px 11px)}
.win.risky .pbar i{background:repeating-linear-gradient(90deg,#a04000 0 8px,transparent 8px 11px)}

/* ---- status bar / EV ---- */
.status{display:flex;gap:4px;margin-top:10px;font-size:11px}
.cell{flex:1;padding:3px 8px;background:var(--chrome);border:2px solid;
  border-color:var(--mid) var(--hilite) var(--hilite) var(--mid)}
.cell.ev{color:#a00000;font-weight:bold;flex:0 0 auto}

/* ---- notepad (reasoning) ---- */
.notepad .win-body{background:#fff;border:2px solid;margin:0 3px 3px;
  border-color:var(--mid) var(--hilite) var(--hilite) var(--mid);
  font-family:"VT323",monospace;font-size:17px;line-height:1.45;padding:12px 14px}
.notepad li{margin-bottom:6px;list-style:none}
.notepad li::before{content:"> ";color:var(--navy)}
.notepad .warnline{color:#a00000}

/* ---- scoreboard ---- */
.score-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:4px;margin-bottom:10px}
.score-cell{background:#fff;border:2px solid;padding:6px 8px;text-align:center;
  border-color:var(--mid) var(--hilite) var(--hilite) var(--mid)}
.score-cell b{display:block;font-family:"VT323",monospace;font-size:26px;line-height:1}
.score-cell span{font-size:10px;color:#444}
.score-cell.pos b{color:#006400}.score-cell.neg b{color:#a00000}
.settled{font-family:"VT323",monospace;font-size:16px;line-height:1.5}
.settled .w{color:#006400;font-weight:bold}.settled .l{color:#a00000;font-weight:bold}
.settled{font-size:15px;max-height:240px;overflow-y:auto}
.tab-bar{display:flex;gap:2px;margin-bottom:-1px;position:relative;z-index:1}
.tab{padding:3px 9px;background:#a0a0a0;border:2px solid;font-size:11px;font-weight:bold;cursor:pointer;
  border-color:var(--hilite) var(--shadow) var(--chrome) var(--hilite);white-space:nowrap;user-select:none}
.tab.active{background:var(--chrome);border-bottom-color:var(--chrome);padding-bottom:5px}
.tab-panel{display:none;border:2px solid;padding:8px;border-color:var(--shadow) var(--hilite) var(--hilite) var(--shadow)}
.tab-panel.active{display:block}

/* ---- error dialog for empty days ---- */
.dialog{max-width:430px;margin:0 auto 24px}
.dialog .win-body{display:flex;gap:12px;align-items:flex-start}
.dialog .icon{font-size:30px;line-height:1}
.dialog .ok{display:block;margin:12px auto 4px;padding:4px 28px;background:var(--chrome);
  font:bold 12px Tahoma;border:2px solid;
  border-color:var(--hilite) var(--shadow) var(--shadow) var(--hilite)}

/* ---- taskbar ---- */
.taskbar{position:fixed;left:0;right:0;bottom:0;height:34px;background:var(--chrome);
  border-top:2px solid var(--hilite);display:flex;align-items:center;gap:6px;
  padding:3px 6px;z-index:9}
.start{display:inline-flex;align-items:center;gap:5px;font:bold 12px Tahoma;
  padding:3px 10px;background:var(--chrome);border:2px solid;
  border-color:var(--hilite) var(--shadow) var(--shadow) var(--hilite)}
.start .flag{font-family:"Press Start 2P",monospace;font-size:9px;color:var(--grass)}
.task{font-size:11px;padding:4px 10px;background:#dcdcdc;border:2px solid;
  border-color:var(--mid) var(--hilite) var(--hilite) var(--mid);
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:46vw}
.clock{margin-left:auto;font-size:11px;padding:4px 10px;border:2px solid;
  border-color:var(--mid) var(--hilite) var(--hilite) var(--mid)}
"""

WINDOW_BTNS = '<span class="tbtns"><i>_</i><i>&#9633;</i><i>&#10005;</i></span>'


def _ticket(name: str, p: Parlay, css: str = "") -> str:
    exe = name.split("·")[0].strip().replace(" ", "_") + ".exe"
    legs = ""
    for leg in p.legs:
        legs += f"""
      <div class="leg">
        <div class="pick">{leg.label}</div>
        <div class="meta"><span>{leg.market.replace('_',' ')}</span><span>@ {leg.odds:.2f}</span></div>
        <div class="pbar" title="estimated probability"><i style="width:{leg.adj_prob*100:.0f}%"></i></div>
        <div class="meta"><span>est. probability</span><span>{leg.adj_prob*100:.0f}%</span></div>
      </div>"""
    return f"""
    <div class="win {css}">
      <div class="tbar"><span>{exe} — {name}</span>{WINDOW_BTNS}</div>
      <div class="menu"><u>F</u>ile&nbsp;&nbsp;<u>E</u>dit&nbsp;&nbsp;<u>B</u>et&nbsp;&nbsp;<u>H</u>elp</div>
      <div class="win-body">
        <div class="combined"><span>Combined odds</span><b>{p.combined_odds:.2f}</b></div>
        {legs}
        <div class="status">
          <div class="cell">Hit rate ~{p.est_probability*100:.0f}%</div>
          <div class="cell">Loses ~{(1-p.est_probability)*100:.0f}% of days</div>
          <div class="cell ev">EV {p.expected_value:+.1%}</div>
        </div>
      </div>
    </div>"""



def _stat_cells(bkt, label):
    n, w = bkt.get("n", 0), bkt.get("wins", 0)
    u = bkt.get("units", 0.0)
    ucls = "pos" if u > 0 else "neg" if u < 0 else ""
    rate = "{:.0%}".format(w / n) if n else "—"
    return (
        '<div class="score-grid">'
        '<div class="score-cell"><b>{}</b><span>{} W–L</span></div>'
        '<div class="score-cell"><b>{}</b><span>hit rate</span></div>'
        '<div class="score-cell {}"><b>{:+.2f}u</b><span>units</span></div>'
        '</div>'
    ).format(str(w) + "–" + str(n - w), label, rate, ucls, u)


def _slip_rows(history, slip_name):
    rows = [r for r in history if r.get("slip") == slip_name]
    if not rows:
        return '<div class="settled">Engar niðurstöður enn.</div>'
    lines = []
    for r in reversed(rows):
        tag = '<span class="w">WON</span>' if r["won"] else '<span class="l">LOST</span>'
        legs_parts = []
        for l in r.get("legs", []):
            chk = "&#10003;" if l["won"] else "&#10007;"
            legs_parts.append("&nbsp;&nbsp;" + chk + " " + l["label"] + " (" + l.get("score", "?") + ")")
        legs_html = "<br>".join(legs_parts)
        line = (r.get("day", "?") + " @ " + "{:.2f}".format(r.get("combined_odds", 0))
                + " \u2014 " + tag + " (" + "{:+.2f}u".format(r.get("profit", 0)) + ")"
                + "<br>" + legs_html)
        lines.append(line)
    return '<div class="settled">' + "<br><br>".join(lines) + "</div>"


def _scoreboard(sb: dict | None) -> str:
    if not sb:
        return ""

    if sb["n"] == 0:
        pend_days = sb.get("pending_days") or []
        pend = (" " + str(len(pend_days)) + " dag(ar) bíður uppgjörs.") if pend_days else ""
        body = '<div class="settled">Ekkert uppgjör enn — taflan byrjar að telja eftir fyrsta leikdag.' + pend + '</div>'
        return (
            '\n<div class="win">\n'
            '  <div class="tbar"><span>stadan.exe \u2014 Scoreboard</span>' + WINDOW_BTNS + '</div>\n'
            '  <div class="menu"><u>F</u>ile&nbsp;&nbsp;<u>V</u>iew&nbsp;&nbsp;<u>H</u>elp</div>\n'
            '  <div class="win-body">' + body + '</div>\n'
            '</div>'
        )

    history = sb.get("history", [])
    a_bkt   = sb.get("slip_a",  {"n": 0, "wins": 0, "units": 0.0})
    b_bkt   = sb.get("slip_b",  {"n": 0, "wins": 0, "units": 0.0})
    c_bkt   = sb.get("slip_c",  {"n": 0, "wins": 0, "units": 0.0})
    tot_bkt = {"n": sb["n"], "wins": sb["wins"], "units": sb["units"]}

    latest = ""
    if sb.get("latest"):
        rows = []
        for r in sb["latest"]:
            tag = '<span class="w">WON</span>' if r["won"] else '<span class="l">LOST</span>'
            leg_parts = []
            for l in r.get("legs", []):
                chk = "&#10003;" if l["won"] else "&#10007;"
                leg_parts.append("&nbsp;&nbsp;" + chk + " " + l["label"] + " (" + l.get("score", "?") + ")")
            rows.append("Slip " + r["slip"] + " @ " + "{:.2f}".format(r["combined_odds"])
                        + " \u2014 " + tag + " (" + "{:+.2f}u".format(r["profit"]) + ")"
                        + "<br>" + "<br>".join(leg_parts))
        latest = ('<div class="settled"><b>S\u00ed\u00f0asti dagur (' + str(sb["latest_day"]) + '):</b><br>'
                  + "<br>".join(rows) + "</div>")

    pend_days = sb.get("pending_days") or []
    pend = ('<div class="settled">(' + str(len(pend_days)) + ' dag(ar) b\u00ed\u00f0ur uppgj\u00f6rs)</div>') if pend_days else ""

    panels = {
        "Heild":  _stat_cells(tot_bkt, "Heild")  + latest + pend,
        "Slip A": _stat_cells(a_bkt,   "Slip A") + _slip_rows(history, "A"),
        "Slip B": _stat_cells(b_bkt,   "Slip B") + _slip_rows(history, "B"),
        "Slip C": _stat_cells(c_bkt,   "Slip C") + _slip_rows(history, "C"),
    }

    tab_names = list(panels.keys())
    tab_ids   = ["sb-" + t.replace(" ", "") for t in tab_names]

    tab_btns = "".join(
        '<span class="tab' + (" active" if i == 0 else "") + '" '
        'onclick="sbTab(this,\'' + tid + '\')">' + lbl + '</span>'
        for i, (lbl, tid) in enumerate(zip(tab_names, tab_ids)))

    tab_pnls = "".join(
        '<div class="tab-panel' + (" active" if i == 0 else "") + '" '
        'id="' + tid + '">' + panels[lbl] + '</div>'
        for i, (lbl, tid) in enumerate(zip(tab_names, tab_ids)))

    js = ("<script>\n"
          "function sbTab(el,id){\n"
          "  var w=el.closest('.win');\n"
          "  w.querySelectorAll('.tab').forEach(function(t){t.classList.remove('active')});\n"
          "  w.querySelectorAll('.tab-panel').forEach(function(p){p.classList.remove('active')});\n"
          "  el.classList.add('active');\n"
          "  document.getElementById(id).classList.add('active');\n"
          "}\n"
          "</script>")

    body = '<div class="tab-bar">' + tab_btns + '</div>' + tab_pnls + js

    return (
        '\n<div class="win">\n'
        '  <div class="tbar"><span>stadan.exe \u2014 Scoreboard</span>' + WINDOW_BTNS + '</div>\n'
        '  <div class="menu"><u>F</u>ile&nbsp;&nbsp;<u>V</u>iew&nbsp;&nbsp;<u>H</u>elp</div>\n'
        '  <div class="win-body">' + body + '</div>\n'
        '</div>'
    )

def render_report(slip_a: Parlay | None, slip_b: Parlay | None,
                  source: str, match_notes: list[str], out_path: str,
                  slip_c: Parlay | None = None, scoreboard: dict | None = None,
                  archive_href: str | None = None) -> str:
    today = date.today().strftime("%A %d %B %Y")
    tickets = ""
    if slip_a:
        tickets += _ticket("Slip A · primary", slip_a)
    if slip_b:
        tickets += _ticket("Slip B · alternate", slip_b)
    if slip_c:
        tickets += _ticket("Slip C · longshot 3–5 &#9888;", slip_c, css="risky")
    if not tickets:
        tickets = f"""
    <div class="win dialog">
      <div class="tbar"><span>bertpicker.exe</span>{WINDOW_BTNS}</div>
      <div class="win-body"><div class="icon">&#9888;</div>
        <div>No parlay of sufficiently likely legs lands in the target band today.<br><br>
        This is a valid output: the disciplined move today is <b>not to bet</b>.</div></div>
      <span class="ok">OK</span>
    </div>"""

    notes_html = "".join(f"<li>{n}</li>" for n in match_notes) \
        or "<li>No automatic reasoning generated today.</li>"

    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bertpicker 1.1 — {today}</title>
<link href="https://fonts.googleapis.com/css2?family=Press+Start+2P&family=VT323&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body><div class="wrap">

<div class="logo">BERTPICKER <small>1.1</small></div>
<div class="splash">Á ég að skjótast í búðina og sækja stuðla?</div>

<div class="slips">{tickets}</div>
{_scoreboard(scoreboard)}

<div class="win notepad">
  <div class="tbar"><span>reasoning.txt — Notepad</span>{WINDOW_BTNS}</div>
  <div class="menu"><u>F</u>ile&nbsp;&nbsp;<u>E</u>dit&nbsp;&nbsp;<u>S</u>earch&nbsp;&nbsp;<u>H</u>elp</div>
  <div class="win-body"><ul>{notes_html}
  <li class="warnline">* Velur tvo líklegustu seðla til að detta á bilinu 2.0 og 2.99 í stuðli. Notast er aðallega við 1x2, over/unders og fjölda marka. Þriðji seðilinn er vibe seðill sem er með hærri stuðul.
  Ef seðlar tapast þá bara it is what it is, gerir þetta á eigin ábyrgð kútur.</li>
  <li>Odds source: {source}. Ekki hægt að taka beint frá Epicbet/Coolbet. Stuðlarnir kunna því að vera örlítið frábrugðnir Epicbet/Coolbet - þið metið þetta bara kútar.</li>
  <li>Spilið smátt og fyrir skemmtunina. Ef þetta hættir að vera gaman: SÁÁ (saa.is) eða hjálparsími Rauða krossins 1717.</li>
  </ul></div>
</div>

</div>
<div class="taskbar">
  <span class="start"><span class="flag">&#9632;&#9632;</span>Start</span>
  <span class="task">&#127942; Bertpicker 1.1 </span>
  <span class="task">&#127942; Búðin - úrval </span>
  {f'<a class="task" style="text-decoration:none;color:#000" href="{archive_href}">&#128193; Gamlir seðlar</a>' if archive_href else ""}
  <span class="clock">{today}</span>
</div>
</body></html>"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path
