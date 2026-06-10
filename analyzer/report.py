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


def render_report(slip_a: Parlay | None, slip_b: Parlay | None,
                  source: str, match_notes: list[str], out_path: str,
                  slip_c: Parlay | None = None) -> str:
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
<title>Bertpicker 1.0 — {today}</title>
<link href="https://fonts.googleapis.com/css2?family=Press+Start+2P&family=VT323&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body><div class="wrap">

<div class="logo">BERTPICKER <small>1.0</small></div>
<div class="splash">Relatively safe!*</div>

<div class="slips">{tickets}</div>

<div class="win notepad">
  <div class="tbar"><span>reasoning.txt — Notepad</span>{WINDOW_BTNS}</div>
  <div class="menu"><u>F</u>ile&nbsp;&nbsp;<u>E</u>dit&nbsp;&nbsp;<u>S</u>earch&nbsp;&nbsp;<u>H</u>elp</div>
  <div class="win-body"><ul>{notes_html}</ul>
  <li class="warnline">*Slips A/B = most probable combos in the 2.0–2.5 band; Slip C is a
  longshot and loses most days. EV is the honest number — negative on almost every real
  parlay, because a parlay multiplies the bookmaker margin too. Markets already price
  public news. Stake small, only what you can afford to lose; if it stops being fun:
  SÁÁ (saa.is) or Red Cross helpline 1717.</li>
  <li>Odds source: {source}. Check the real Epicbet price before placing.</li>
  </div>
</div>

</div>
<div class="taskbar">
  <span class="start"><span class="flag">&#9632;&#9632;</span>Start</span>
  <span class="task">&#127942; Bertpicker 1.0 — daily briefing</span>
  <span class="clock">{today}</span>
</div>
</body></html>"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path
