"""RingBinder — the patient-intake dashboard.

A lightweight single-page client served by the same app. It consumes the REST
API (`GET /patients`, `PUT`, `DELETE`) and a small `GET /dashboard/calls` JSON
endpoint, so it demonstrates the API being used end-to-end. Search, click-to-
expand detail, inline edit, soft-delete, and 15s auto-refresh are all client-side.

"RingBinder" is a dashboard-only brand name; the API/project keep their own names.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from . import crud
from .db import get_db

router = APIRouter(tags=["dashboard"])


def _fmt_dt(value) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M UTC")
    return "" if value is None else str(value)


@router.get("/dashboard/calls")
def dashboard_calls(db: Session = Depends(get_db)):
    logs = crud.recent_call_logs(db, limit=8)
    return JSONResponse(
        content=[
            {
                "when": _fmt_dt(lg.created_at),
                "phone": lg.phone_number or "",
                "summary": lg.summary or "",
                "transcript": lg.transcript or "",
            }
            for lg in logs
        ]
    )


_PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RingBinder</title>
<style>
  :root{
    --bg:#06120b; --panel:#0e2116; --panel2:#0b1a11; --row:#0c1d13;
    --border:rgba(159,239,0,.16); --text:#d8f6c6; --muted:#88a97a;
    --lime:#9fef00; --lime-dim:#7cc400; --danger:#ff6b6b;
    color-scheme:dark;
  }
  *{box-sizing:border-box}
  body{margin:0;background:
      radial-gradient(1200px 500px at 15% -10%, #0f2a19 0%, transparent 60%),
      var(--bg);
    color:var(--text);
    font:17px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
    padding:28px clamp(16px,4vw,56px);}
  a{color:var(--lime)}
  header{display:flex;align-items:center;gap:16px;margin-bottom:6px;flex-wrap:wrap}
  .logo{flex:0 0 auto;filter:drop-shadow(0 0 10px rgba(159,239,0,.25))}
  .brand h1{margin:0;font-size:32px;letter-spacing:.5px;color:var(--lime);
    text-shadow:0 0 18px rgba(159,239,0,.25)}
  .brand .tag{color:var(--muted);font-size:14px;margin-top:2px}
  .live{margin-left:auto;display:flex;align-items:center;gap:8px;color:var(--muted);font-size:14px}
  .dot{width:9px;height:9px;border-radius:50%;background:var(--lime);
    box-shadow:0 0 0 0 rgba(159,239,0,.6);animation:pulse 2s infinite}
  @keyframes pulse{0%{box-shadow:0 0 0 0 rgba(159,239,0,.5)}70%{box-shadow:0 0 0 10px rgba(159,239,0,0)}100%{box-shadow:0 0 0 0 rgba(159,239,0,0)}}
  .counts{color:var(--lime-dim);font-size:15px;margin:10px 0 22px;font-variant-numeric:tabular-nums}
  .controls{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px}
  input,select{background:var(--panel2);color:var(--text);border:1px solid var(--border);
    border-radius:10px;padding:11px 14px;font-size:15px;outline:none}
  input:focus,select:focus{border-color:var(--lime);box-shadow:0 0 0 3px rgba(159,239,0,.12)}
  #search{flex:1;min-width:220px}
  .card{background:var(--panel);border:1px solid var(--border);border-radius:16px;
    padding:18px 18px 8px;margin-bottom:26px;overflow-x:auto}
  .card h2{font-size:16px;margin:2px 0 14px;color:var(--lime);text-transform:uppercase;letter-spacing:.08em}
  table{width:100%;border-collapse:collapse;font-size:15px}
  th,td{text-align:left;padding:12px 12px;border-bottom:1px solid var(--border);white-space:nowrap}
  th{font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);font-weight:600}
  tr:last-child td{border-bottom:none}
  .prow{cursor:pointer}
  .prow:hover{background:var(--row)}
  .mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--lime-dim)}
  .badge{font-size:12px;padding:3px 10px;border-radius:999px;white-space:nowrap;font-weight:600}
  .badge.registered{background:rgba(159,239,0,.16);color:var(--lime)}
  .badge.draft{background:rgba(230,180,80,.2);color:#ffd166}
  .btn{background:transparent;border:1px solid var(--border);color:var(--text);
    border-radius:8px;padding:6px 12px;font-size:13px;cursor:pointer}
  .btn:hover{border-color:var(--lime);color:var(--lime)}
  .btn.danger:hover{border-color:var(--danger);color:var(--danger)}
  .btn.primary{background:var(--lime);color:#06120b;border-color:var(--lime);font-weight:700}
  .detail{background:var(--panel2)}
  .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px 26px;padding:6px 2px 10px}
  .grid label{display:block;color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.05em;margin-bottom:3px}
  .grid .val{font-size:15px}
  .grid input,.grid select{width:100%}
  .actions{display:flex;gap:10px;margin:10px 2px 6px}
  .empty{color:var(--muted);padding:16px}
  pre{white-space:pre-wrap;margin:0;font-size:13.5px;max-height:300px;overflow:auto;color:#cdeeb6}
  .csummary{font-weight:700;color:var(--lime);margin-bottom:6px}
  .ctime{color:var(--muted);font-size:13px}
  footer{color:var(--muted);text-align:center;font-size:15px;margin:10px 0 24px;font-style:italic}
  .flash{position:fixed;left:50%;bottom:22px;transform:translateX(-50%);background:var(--panel);
    border:1px solid var(--lime);color:var(--lime);padding:10px 18px;border-radius:10px;
    opacity:0;transition:opacity .2s;pointer-events:none}
  .flash.show{opacity:1}
  .flash.err{border-color:var(--danger);color:var(--danger)}
</style></head>
<body>
  <header>
    <svg class="logo" width="46" height="46" viewBox="0 0 44 44" role="img" aria-label="RingBinder logo">
      <rect x="1.5" y="1.5" width="41" height="41" rx="12" fill="#0e2116" stroke="#9fef00" stroke-width="2"/>
      <g fill="#9fef00">
        <rect x="11" y="18" width="3.4" height="8" rx="1.7"/>
        <rect x="16.3" y="13.5" width="3.4" height="17" rx="1.7"/>
        <rect x="21.6" y="9.5" width="3.4" height="25" rx="1.7"/>
        <rect x="26.9" y="13.5" width="3.4" height="17" rx="1.7"/>
        <rect x="32.2" y="18" width="3.4" height="8" rx="1.7"/>
      </g>
    </svg>
    <div class="brand">
      <h1>RingBinder</h1>
      <div class="tag">Voice patient intake &middot; every ring, filed.</div>
    </div>
    <div class="live"><span class="dot"></span><span id="liveLabel">live</span></div>
  </header>

  <div class="counts" id="counts">loading&hellip;</div>

  <div class="controls">
    <input id="search" type="search" placeholder="Search by name or phone&hellip;" autocomplete="off">
    <select id="statusFilter">
      <option value="all">All</option>
      <option value="registered">Registered</option>
      <option value="draft">In progress</option>
    </select>
  </div>

  <div class="card">
    <h2>Patients</h2>
    <table id="ptable"><thead><tr>
      <th>Status</th><th>ID</th><th>Name</th><th>DOB</th><th>Phone</th>
      <th>Location</th><th>Lang</th><th>Created</th><th></th>
    </tr></thead><tbody id="tbody"></tbody></table>
    <div class="empty" id="pempty" style="display:none">No patients match. Call the number to register one.</div>
  </div>

  <div class="card">
    <h2>Recent Calls</h2>
    <div id="calls"><div class="empty">Loading call transcripts&hellip;</div></div>
  </div>

  <footer id="quote"></footer>
  <div class="flash" id="flash"></div>

<script>
const QUOTES = [
  "No patients were kept on hold in the making of this database.",
  "Avery never sighs when you spell your name a third time.",
  "HIPAA-adjacent, caffeine-free, and awake at 3 a.m.",
  "Your call is genuinely important to us. That's the whole app.",
  "We spell your name right the first time. Usually.",
  "Zero hold music. You're welcome.",
  "Powered by good vibes and a ten-digit phone number.",
  "Ask about our 0.0% chance of transferring you to another department.",
  "If this were a real clinic, the coffee would be worse.",
  "Every ring, filed. Even the weird ones."
];
const EDITABLE = ["first_name","last_name","date_of_birth","sex","phone_number","email",
  "address_line_1","address_line_2","city","state","zip_code","insurance_provider",
  "insurance_member_id","preferred_language","emergency_contact_name","emergency_contact_phone"];
const LABELS = {first_name:"First name",last_name:"Last name",date_of_birth:"Date of birth",
  sex:"Sex",phone_number:"Phone",email:"Email",address_line_1:"Address 1",address_line_2:"Address 2",
  city:"City",state:"State",zip_code:"ZIP",insurance_provider:"Insurance",insurance_member_id:"Member ID",
  preferred_language:"Language",emergency_contact_name:"Emergency contact",emergency_contact_phone:"Emergency phone"};
const SEX = ["Male","Female","Other","Decline to Answer"];

let PATIENTS = [];
const expanded = new Set();
const editing = new Set();

const $ = id => document.getElementById(id);
const S = v => (v==null ? "" : String(v));

function flash(msg, isErr){
  const f = $("flash"); f.textContent = msg; f.className = "flash show" + (isErr?" err":"");
  setTimeout(()=>{ f.className = "flash" + (isErr?" err":""); }, 2600);
}

async function loadPatients(){
  try{
    const r = await fetch("/patients?status=all");
    const j = await r.json();
    PATIENTS = (j && j.data) || [];
    render(); counts();
  }catch(e){ flash("Could not load patients", true); }
}

function counts(){
  const reg = PATIENTS.filter(p=>p.status==="registered").length;
  $("counts").textContent = reg + " registered · " + (PATIENTS.length-reg) + " in progress · live from the database · demo data is fictional";
}

function filtered(){
  const q = $("search").value.trim().toLowerCase();
  const st = $("statusFilter").value;
  return PATIENTS.filter(p=>{
    if(st!=="all" && p.status!==st) return false;
    if(!q) return true;
    return (S(p.first_name)+" "+S(p.last_name)+" "+S(p.phone_number)).toLowerCase().includes(q);
  });
}

function cell(text, cls){ const td=document.createElement("td"); if(cls)td.className=cls; td.textContent=text; return td; }

function render(){
  const rows = filtered();
  const tb = $("tbody"); tb.innerHTML = "";
  $("ptable").style.display = rows.length ? "" : "none";
  $("pempty").style.display = rows.length ? "none" : "block";
  for(const p of rows){
    const tr = document.createElement("tr"); tr.className="prow";
    const badge = document.createElement("td");
    badge.innerHTML = '<span class="badge '+(p.status==="registered"?"registered":"draft")+'">'+
      (p.status==="registered"?"registered":"in progress")+'</span>';
    tr.appendChild(badge);
    tr.appendChild(cell(S(p.patient_id).slice(0,8),"mono"));
    tr.appendChild(cell((S(p.first_name)+" "+S(p.last_name)).trim() || "—"));
    tr.appendChild(cell(S(p.date_of_birth)||"—"));
    tr.appendChild(cell(S(p.phone_number)||"—","mono"));
    tr.appendChild(cell([S(p.city),S(p.state)].filter(Boolean).join(", ")+" "+S(p.zip_code)));
    tr.appendChild(cell(S(p.preferred_language)||"—"));
    tr.appendChild(cell(S(p.created_at).replace("T"," ").slice(0,16)));
    const act = document.createElement("td");
    const view = document.createElement("button"); view.className="btn"; view.textContent = expanded.has(p.patient_id)?"Hide":"View";
    act.appendChild(view); tr.appendChild(act);
    tr.onclick = e => { if(e.target.tagName!=="BUTTON"||e.target===view){ toggle(p.patient_id); } };
    tb.appendChild(tr);
    if(expanded.has(p.patient_id)) tb.appendChild(detailRow(p));
  }
}

function toggle(id){ expanded.has(id)?expanded.delete(id):expanded.add(id); editing.delete(id); render(); }

function detailRow(p){
  const tr = document.createElement("tr"); tr.className="detail";
  const td = document.createElement("td"); td.colSpan = 9;
  const grid = document.createElement("div"); grid.className="grid";
  const isEdit = editing.has(p.patient_id);
  for(const f of EDITABLE){
    const wrap = document.createElement("div");
    const lab = document.createElement("label"); lab.textContent = LABELS[f]; wrap.appendChild(lab);
    if(isEdit){
      let inp;
      if(f==="sex"){ inp=document.createElement("select");
        ["",...SEX].forEach(o=>{const op=document.createElement("option");op.value=o;op.textContent=o||"—";if(S(p[f])===o)op.selected=true;inp.appendChild(op);});
      } else { inp=document.createElement("input"); inp.type = f==="date_of_birth"?"date":"text"; inp.value=S(p[f]); }
      inp.dataset.field=f; inp.className="editf"; wrap.appendChild(inp);
    } else {
      const v=document.createElement("div"); v.className="val"; v.textContent=S(p[f])||"—"; wrap.appendChild(v);
    }
    grid.appendChild(wrap);
  }
  td.appendChild(grid);
  const actions = document.createElement("div"); actions.className="actions";
  if(isEdit){
    const save=document.createElement("button"); save.className="btn primary"; save.textContent="Save";
    save.onclick=()=>saveEdit(p, td); actions.appendChild(save);
    const cancel=document.createElement("button"); cancel.className="btn"; cancel.textContent="Cancel";
    cancel.onclick=()=>{editing.delete(p.patient_id);render();}; actions.appendChild(cancel);
  } else {
    const edit=document.createElement("button"); edit.className="btn"; edit.textContent="Edit";
    edit.onclick=()=>{editing.add(p.patient_id);render();}; actions.appendChild(edit);
    const del=document.createElement("button"); del.className="btn danger"; del.textContent="Delete";
    del.onclick=()=>doDelete(p); actions.appendChild(del);
  }
  td.appendChild(actions);
  tr.appendChild(td);
  return tr;
}

async function saveEdit(p, td){
  const changed = {};
  td.querySelectorAll(".editf").forEach(inp=>{
    const f=inp.dataset.field, v=inp.value.trim();
    if(v !== S(p[f])) changed[f] = v;
  });
  if(!Object.keys(changed).length){ editing.delete(p.patient_id); render(); return; }
  try{
    const r = await fetch("/patients/"+p.patient_id, {method:"PUT",
      headers:{"content-type":"application/json"}, body:JSON.stringify(changed)});
    const j = await r.json();
    if(!r.ok){ flash((j.error&&j.error.message)||"Update failed", true); return; }
    flash("Saved");
    editing.delete(p.patient_id); await loadPatients();
  }catch(e){ flash("Update failed", true); }
}

async function doDelete(p){
  const name=(S(p.first_name)+" "+S(p.last_name)).trim()||"this record";
  if(!confirm("Soft-delete "+name+"? (sets deleted_at; not a hard delete)")) return;
  try{
    const r = await fetch("/patients/"+p.patient_id, {method:"DELETE"});
    if(!r.ok){ const j=await r.json(); flash((j.error&&j.error.message)||"Delete failed",true); return; }
    flash("Deleted"); expanded.delete(p.patient_id); await loadPatients();
  }catch(e){ flash("Delete failed", true); }
}

async function loadCalls(){
  try{
    const r = await fetch("/dashboard/calls"); const data = await r.json();
    const box = $("calls");
    if(!data.length){ box.innerHTML='<div class="empty">No call transcripts yet.</div>'; return; }
    box.innerHTML="";
    for(const c of data){
      const d=document.createElement("div"); d.style.padding="10px 2px"; d.style.borderBottom="1px solid var(--border)";
      const t=document.createElement("div"); t.className="ctime"; t.textContent=c.when+(c.phone?"  ·  "+c.phone:""); d.appendChild(t);
      if(c.summary){ const s=document.createElement("div"); s.className="csummary"; s.textContent=c.summary; d.appendChild(s); }
      const pre=document.createElement("pre"); pre.textContent=c.transcript||"(no transcript)"; d.appendChild(pre);
      box.appendChild(d);
    }
  }catch(e){ /* keep prior */ }
}

function rotateQuote(){ $("quote").textContent = "“"+QUOTES[Math.floor(Math.random()*QUOTES.length)]+"”"; }

function refreshAll(){ loadPatients(); loadCalls(); rotateQuote(); }

$("search").addEventListener("input", render);
$("statusFilter").addEventListener("change", render);
rotateQuote(); loadPatients(); loadCalls();
setInterval(refreshAll, 15000);
</script>
</body></html>"""


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    return HTMLResponse(_PAGE)
