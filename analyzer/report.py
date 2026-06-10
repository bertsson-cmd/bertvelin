"""Render the daily briefing as a single self-contained HTML file."""

from __future__ import annotations
from datetime import date

from .parlay import Parlay

CSS = """
:root{
  --night:#0f1a16; --pitch:#15291f; --line:#2a4436;
  --paper:#faf7ef; --ink:#1c1a16; --faded:#6f6a5e;
  --amber:#f0a53c; --risk:#c8442c; --ok:#1e7a4f;
}
*{box-sizing:border-box;margin:0}
body{background:var(--night);color:var(--paper);
  font-family:"IBM Plex Sans",system-ui,sans-serif;
  background-image:repeating-linear-gradient(90deg,transparent 0 119px,var(--line) 119px 120px);
  min-height:100vh;padding:48px 20px}
.wrap{max-width:920px;margin:0 auto}
header{margin-bottom:36px}
.eyebrow{font-family:"IBM Plex Mono",monospace;font-size:12px;letter-spacing:.18em;
  text-transform:uppercase;color:var(--amber)}
h1{font-family:"Archivo Narrow","Arial Narrow",sans-serif;font-weight:700;
  font-size:clamp(30px,5vw,46px);text-transform:uppercase;letter-spacing:.01em;line-height:1.05;margin-top:8px}
.sub{color:#9fb3a8;margin-top:10px;max-width:60ch;font-size:14px;line-height:1.5}
.slips{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:28px}
.ticket{background:var(--paper);color:var(--ink);border-radius:6px 6px 0 0;
  font-family:"IBM Plex Mono",monospace;position:relative;
  box-shadow:0 14px 30px rgba(0,0,0,.45)}
.ticket::after{content:"";display:block;height:14px;
  background:radial-gradient(circle at 7px -3px,transparent 8px,var(--paper) 8px);
  background-size:16px 14px;background-repeat:repeat-x}
.t-head{padding:18px 20px 12px;border-bottom:2px solid var(--ink);
  display:flex;justify-content:space-between;align-items:baseline}
.t-head .name{font-weight:700;font-size:15px;letter-spacing:.06em;text-transform:uppercase}
.t-head .odds{font-size:26px;font-weight:700}
.leg{padding:14px 20px;border-bottom:1px dashed #c9c3b4}
.leg .pick{font-size:14px;font-weight:600}
.leg .meta{display:flex;justify-content:space-between;font-size:12px;color:var(--faded);margin-top:4px}
.bar{height:5px;background:#e4dfd1;border-radius:3px;margin-top:8px;overflow:hidden}
.bar i{display:block;height:100%;background:var(--ok)}
.t-foot{padding:14px 20px 18px;font-size:12px;display:grid;gap:5px}
.t-foot .row{display:flex;justify-content:space-between}
.stamp{position:absolute;top:14px;right:16px;transform:rotate(8deg);
  border:2px solid var(--risk);color:var(--risk);border-radius:4px;
  font-size:10px;font-weight:700;letter-spacing:.14em;padding:3px 7px;opacity:.85}
.ticket.risky .t-head{border-bottom-color:var(--amber)}
.ticket.risky .bar i{background:var(--amber)}
.ticket.risky .t-head .name::after{content:" ⚠";color:var(--risk)}
.notes{margin-top:34px;background:var(--pitch);border:1px solid var(--line);
  border-radius:6px;padding:20px 22px;font-size:13px;line-height:1.6;color:#cfdcd4}
.notes h2{font-family:"Archivo Narrow",sans-serif;text-transform:uppercase;
  letter-spacing:.08em;font-size:14px;color:var(--amber);margin-bottom:8px}
.empty{background:var(--pitch);border:1px dashed var(--line);border-radius:6px;
  padding:28px;color:#9fb3a8;font-size:14px}
@media (prefers-reduced-motion:no-preference){
  .ticket{animation:drop .4s ease-out both}
  .ticket:nth-child(2){animation-delay:.12s}
  @keyframes drop{from{opacity:0;translate:0 -10px}to{opacity:1}}
}
"""


def _ticket(name: str, p: Parlay, css: str = "") -> str:
    legs = ""
    for leg in p.legs:
        legs += f"""
      <div class="leg">
        <div class="pick">{leg.label}</div>
        <div class="meta"><span>{leg.market.replace('_',' ')}</span><span>@ {leg.odds:.2f}</span></div>
        <div class="bar" title="estimated probability"><i style="width:{leg.adj_prob*100:.0f}%"></i></div>
        <div class="meta"><span>est. probability</span><span>{leg.adj_prob*100:.0f}%</span></div>
      </div>"""
    ev = p.expected_value
    return f"""
    <div class="ticket {css}">
      <div class="stamp">EV {ev:+.1%}</div>
      <div class="t-head"><span class="name">{name}</span><span class="odds">{p.combined_odds:.2f}</span></div>
      {legs}
      <div class="t-foot">
        <div class="row"><span>Estimated hit rate</span><b>{p.est_probability*100:.0f}%</b></div>
        <div class="row"><span>Implies losing</span><b>~{(1-p.est_probability)*100:.0f}% of days</b></div>
        <div class="row"><span>10 units returns</span><b>{p.combined_odds*10:.1f} if it lands, 0 if not</b></div>
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
        tickets += _ticket("Slip C · longshot 3–5", slip_c, css="risky")
    if not tickets:
        tickets = ('<div class="empty">No parlay combination of sufficiently likely legs '
                   'lands in the 2.0–2.5 band today. That is a valid output: '
                   'the disciplined move on a day like this is not to bet.</div>')

    notes_html = "".join(f"<li>{n}</li>" for n in match_notes) or "<li>No analyst notes entered today.</li>"

    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>WC26 Daily Slips — {today}</title>
<link href="https://fonts.googleapis.com/css2?family=Archivo+Narrow:wght@700&family=IBM+Plex+Mono:wght@400;600;700&family=IBM+Plex+Sans:wght@400;600&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body><div class="wrap">
<header>
  <div class="eyebrow">World Cup 2026 · daily briefing · odds: {source}</div>
  <h1>{today}</h1>
  <p class="sub">Slips A and B sit in the 2.0–2.5 band, built from the most probable
  qualifying legs after vig removal and the automatic reasoning below (weather, market
  moves, news desk). Slip C is the longshot — expect it to lose most days. The EV stamp
  is the honest number: average return per unit if the estimates are right, and it is
  negative on almost every real-world parlay.</p>
</header>
<div class="slips">{tickets}</div>
<div class="notes"><h2>Today's reasoning (auto-generated)</h2><ul>{notes_html}</ul>
<p style="margin-top:10px">Reminder: these are estimates, not predictions. Markets already
price in public team news. Stake only what you can comfortably lose, and stop if it stops
being fun — see README for responsible-gambling resources.</p></div>
</div></body></html>"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path
