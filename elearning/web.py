"""모바일 웹앱 서버 (Flask).

폰 브라우저에서 마감 목록을 보고 자연어 질문을 할 수 있다.
- 수집 결과를 캐시(.web_cache.json)해 폰에서 빠르게 열림
- /api/refresh 로 백그라운드 재수집 (로그인·스크래핑은 수십 초 소요)
- WEB_TOKEN 설정 시 접속에 토큰 필요 (집 밖 노출 대비)

실행:  python -m elearning.web   (기본 0.0.0.0:8000)
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Flask, Response, jsonify, request

from .aggregate import collect_deadlines
from .assistant import answer_question, build_digest
from .client import EcampusClient
from .config import PROJECT_ROOT, Config
from .llm import get_llm
from .models import Deadline

KST = timezone(timedelta(hours=9))
CACHE_FILE = PROJECT_ROOT / ".web_cache.json"

app = Flask(__name__)
_cfg = Config.load()
_lock = threading.Lock()
_state: dict = {"deadlines": [], "fetched_at": None, "refreshing": False, "error": None}

# 경고: 클라우드(공개망) 배포 시 WEB_TOKEN 미설정이면 누구나 접근 가능
if _cfg.web_token:
    pass  # 보호됨


# ------------------------------------------------------------------ #
# 캐시 + 수집
# ------------------------------------------------------------------ #
def _load_cache() -> None:
    if CACHE_FILE.exists():
        try:
            data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            _state["deadlines"] = [Deadline.from_dict(d) for d in data.get("deadlines", [])]
            _state["fetched_at"] = data.get("fetched_at")
        except Exception:
            pass


def _save_cache() -> None:
    try:
        CACHE_FILE.write_text(json.dumps({
            "deadlines": [d.to_dict() for d in _state["deadlines"]],
            "fetched_at": _state["fetched_at"],
        }, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def refresh() -> None:
    """로그인·수집을 수행하고 캐시를 갱신한다 (느림, 백그라운드에서 호출)."""
    if _state["refreshing"]:
        return
    _state["refreshing"] = True
    _state["error"] = None
    try:
        client = EcampusClient(_cfg)
        if _cfg.has_login:
            client.login()
        deadlines = collect_deadlines(client, ical_url=_cfg.ical_url, scrape=_cfg.has_login)
        with _lock:
            _state["deadlines"] = deadlines
            _state["fetched_at"] = datetime.now(KST).isoformat()
            _save_cache()
    except Exception as e:
        _state["error"] = str(e)
    finally:
        _state["refreshing"] = False


def refresh_async() -> None:
    threading.Thread(target=refresh, daemon=True).start()


# ------------------------------------------------------------------ #
# 접근 토큰
# ------------------------------------------------------------------ #
def _authorized() -> bool:
    if not _cfg.web_token:
        return True
    tok = request.args.get("token") or request.cookies.get("token") or \
        request.headers.get("X-Token")
    return tok == _cfg.web_token


@app.before_request
def _guard():
    if request.path.startswith("/static"):
        return None
    if not _authorized():
        return Response("접근 토큰이 필요합니다. URL 끝에 ?token=... 를 붙이세요.", status=401)
    return None


# ------------------------------------------------------------------ #
# API
# ------------------------------------------------------------------ #
@app.get("/api/data")
def api_data():
    # 클라우드(gunicorn)에서 첫 요청 시 아직 수집 전이면 백그라운드 수집 시작
    if _state["fetched_at"] is None and not _state["refreshing"]:
        refresh_async()
    with _lock:
        items = [d.to_dict() | {"days_left": d.days_left} for d in _state["deadlines"]]
    items.sort(key=lambda x: (x["due"] is None, x["due"] or ""))
    return jsonify({
        "deadlines": items,
        "fetched_at": _state["fetched_at"],
        "refreshing": _state["refreshing"],
        "error": _state["error"],
        "mode": "정밀" if _cfg.has_login else "iCal",
    })


@app.post("/api/refresh")
def api_refresh():
    refresh_async()
    return jsonify({"ok": True})


@app.get("/api/ask")
def api_ask():
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"answer": "질문을 입력하세요."})
    with _lock:
        deadlines = list(_state["deadlines"])
    llm = get_llm()
    return jsonify({"answer": answer_question(q, deadlines, llm=llm), "ai": llm.name})


@app.get("/api/digest")
def api_digest():
    with _lock:
        deadlines = list(_state["deadlines"])
    llm = get_llm()
    return jsonify({"digest": build_digest(deadlines, llm=llm), "ai": llm.name})


@app.get("/")
def index():
    return Response(PAGE, mimetype="text/html")


# ------------------------------------------------------------------ #
# 모바일 페이지 (단일 HTML)
# ------------------------------------------------------------------ #
PAGE = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="과제마감">
<meta name="theme-color" content="#4f46e5">
<title>이러닝 과제·마감</title>
<style>
  :root { --bg:#0f1221; --card:#1a1f36; --line:#2a3152; --fg:#e8ebf7; --dim:#8a92b2;
          --indigo:#6366f1; --red:#f87171; --amber:#fbbf24; --green:#34d399; }
  * { box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
  body { margin:0; background:var(--bg); color:var(--fg);
         font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;
         padding:env(safe-area-inset-top) 0 40px; }
  header { position:sticky; top:0; background:rgba(15,18,33,.92); backdrop-filter:blur(8px);
           padding:14px 16px; border-bottom:1px solid var(--line); z-index:5; }
  h1 { font-size:18px; margin:0; display:flex; align-items:center; gap:8px; }
  .meta { font-size:12px; color:var(--dim); margin-top:4px; }
  .wrap { padding:12px 16px; max-width:640px; margin:0 auto; }
  .askbar { display:flex; gap:8px; margin:12px 0; }
  .askbar input { flex:1; background:var(--card); border:1px solid var(--line); color:var(--fg);
                  border-radius:12px; padding:12px 14px; font-size:16px; }
  .btn { background:var(--indigo); color:#fff; border:none; border-radius:12px;
         padding:12px 16px; font-size:15px; font-weight:600; }
  .btn.ghost { background:var(--card); border:1px solid var(--line); color:var(--fg); }
  .answer { background:var(--card); border:1px solid var(--line); border-radius:12px;
            padding:14px; margin-bottom:12px; white-space:pre-wrap; line-height:1.55; display:none; }
  .group { font-size:13px; color:var(--dim); margin:18px 2px 8px; font-weight:600; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:14px;
          padding:13px 14px; margin-bottom:9px; display:flex; gap:12px; align-items:center;
          text-decoration:none; color:inherit; }
  .dday { min-width:52px; text-align:center; font-weight:700; font-size:15px; }
  .d-urgent { color:var(--red); } .d-soon { color:var(--amber); } .d-ok { color:var(--dim); }
  .ci { flex:1; min-width:0; }
  .ci .t { font-weight:600; font-size:15px; }
  .ci .s { font-size:12.5px; color:var(--dim); margin-top:3px; }
  .badge { font-size:11px; padding:3px 8px; border-radius:999px; font-weight:700; white-space:nowrap; }
  .b-done { background:rgba(52,211,153,.15); color:var(--green); }
  .b-miss { background:rgba(248,113,113,.15); color:var(--red); }
  .kind { font-size:11px; color:var(--dim); }
  .tabs { display:flex; gap:8px; margin:4px 0 2px; }
  .tab { flex:1; text-align:center; padding:9px; border-radius:10px; background:var(--card);
         border:1px solid var(--line); color:var(--dim); font-size:14px; }
  .tab.on { color:#fff; background:var(--indigo); border-color:var(--indigo); }
  .empty { color:var(--dim); text-align:center; padding:30px; }
  .spin { display:inline-block; width:13px; height:13px; border:2px solid var(--dim);
          border-top-color:transparent; border-radius:50%; animation:r .8s linear infinite; }
  @keyframes r { to { transform:rotate(360deg); } }
  /* 뷰 전환 */
  .seg { display:flex; gap:8px; margin:12px 0; }
  .seg div { flex:1; text-align:center; padding:10px; border-radius:11px; background:var(--card);
             border:1px solid var(--line); color:var(--dim); font-size:15px; font-weight:600; }
  .seg div.on { color:#fff; background:var(--indigo); border-color:var(--indigo); }
  /* 캘린더 */
  .calhead { display:flex; align-items:center; justify-content:space-between; margin:6px 2px 10px; }
  .calhead b { font-size:17px; }
  .navbtn { background:var(--card); border:1px solid var(--line); color:var(--fg);
            border-radius:10px; width:40px; height:36px; font-size:16px; }
  .cal { display:grid; grid-template-columns:repeat(7,1fr); gap:5px; }
  .dow { text-align:center; font-size:12px; color:var(--dim); padding:4px 0; }
  .cell { aspect-ratio:1; background:var(--card); border:1px solid var(--line); border-radius:10px;
          padding:5px 0 0; display:flex; flex-direction:column; align-items:center; gap:3px;
          font-size:13px; color:var(--fg); position:relative; }
  .cell.empty-cell { background:transparent; border:none; }
  .cell.has { cursor:pointer; }
  .cell.today { border-color:var(--indigo); }
  .cell.sel { background:var(--indigo); border-color:var(--indigo); color:#fff; }
  .cell .dnum { font-weight:600; }
  .cell.sun .dnum { color:var(--red); } .cell.sat .dnum { color:#7aa2ff; }
  .cell.sel .dnum { color:#fff; }
  .dots { display:flex; gap:2px; flex-wrap:wrap; justify-content:center; }
  .dot { width:5px; height:5px; border-radius:50%; }
  .dot.miss { background:var(--red); } .dot.done { background:var(--green); }
  .dot.etc { background:var(--amber); }
  .seldate { font-size:14px; color:var(--dim); margin:16px 2px 8px; font-weight:600; }
</style>
</head>
<body>
<header>
  <h1>📚 과제·마감 <span id="mode" class="kind"></span></h1>
  <div class="meta" id="meta">불러오는 중…</div>
</header>
<div class="wrap">
  <div class="askbar">
    <input id="q" placeholder="예: 이번주 미제출 과제" enterkeyhint="search">
    <button class="btn" onclick="ask()">질문</button>
  </div>
  <div class="answer" id="answer"></div>
  <div class="seg">
    <div class="on" id="seg-list" onclick="setView('list')">📋 목록</div>
    <div id="seg-cal" onclick="setView('cal')">📅 캘린더</div>
  </div>

  <div id="listView">
    <div class="tabs">
      <div class="tab on" id="tab-all" onclick="setTab('all')">전체</div>
      <div class="tab" id="tab-todo" onclick="setTab('todo')">미제출만</div>
      <button class="btn ghost" onclick="refresh()" id="refbtn">↻</button>
    </div>
    <div id="list"></div>
  </div>

  <div id="calView" style="display:none">
    <div class="calhead">
      <button class="navbtn" onclick="moveMonth(-1)">‹</button>
      <b id="calTitle"></b>
      <button class="navbtn" onclick="moveMonth(1)">›</button>
    </div>
    <div class="cal" id="calGrid"></div>
    <div id="dayList"></div>
  </div>
</div>
<script>
let DATA = [], TAB = 'all';
const kmap = {assign:'과제', quiz:'퀴즈', video:'영상', lesson:'강의', event:'일정'};
function fmtDue(iso, known){
  if(!iso) return '마감미정';
  const d = new Date(iso);
  const days=['일','월','화','수','목','금','토'];
  const s = `${d.getMonth()+1}/${d.getDate()}(${days[d.getDay()]})`;
  if(!known) return s+' ~마감';
  return s+' '+String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0');
}
function ddText(dl){ if(dl==null) return '-'; const n=Math.floor(dl);
  return n===0?'D-day':(n>0?'D+'+n:'D'+n); }
function ddClass(dl){ if(dl==null) return 'd-ok'; if(dl<2) return 'd-urgent';
  if(dl<5) return 'd-soon'; return 'd-ok'; }
function group(dl){ if(dl==null) return '기타';
  if(dl<0) return '지난 마감'; if(dl<1) return '오늘'; if(dl<2) return '내일';
  if(dl<8) return '이번 주'; return '이후'; }
function render(){
  let items = DATA.slice();
  if(TAB==='todo') items = items.filter(x=>x.submitted===false);
  const box = document.getElementById('list');
  if(!items.length){ box.innerHTML='<div class="empty">표시할 마감이 없습니다.</div>'; return; }
  // 다가오는 마감을 위로(가까운 순), 지난 마감은 맨 아래(최근 지난 것 먼저)
  const grank={'오늘':0,'내일':1,'이번 주':2,'이후':3,'지난 마감':4,'기타':5};
  let html='', last=null;
  items.sort((a,b)=>{
    const ra=grank[group(a.days_left)], rb=grank[group(b.days_left)];
    if(ra!==rb) return ra-rb;
    if(ra===4) return (b.days_left) - (a.days_left);   // 지난 마감: 최근 것 먼저
    return (a.days_left??1e9)-(b.days_left??1e9);        // 그 외: 가까운 마감 먼저
  });
  for(const it of items){
    const g=group(it.days_left);
    if(g!==last){ html+=`<div class="group">${g}</div>`; last=g; }
    let badge='';
    if(it.submitted===true) badge='<span class="badge b-done">제출✓</span>';
    else if(it.submitted===false) badge='<span class="badge b-miss">미제출</span>';
    const href = it.url?`href="${it.url}" target="_blank"`:'';
    html+=`<a class="card" ${href}>
      <div class="dday ${ddClass(it.days_left)}">${ddText(it.days_left)}</div>
      <div class="ci"><div class="t">${esc(it.title)}</div>
        <div class="s">${fmtDue(it.due,it.time_known)} · ${kmap[it.kind]||it.kind} · ${esc(it.course)}</div></div>
      ${badge}</a>`;
  }
  box.innerHTML=html;
}
function esc(s){ return (s||'').replace(/[<>&]/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;'}[c])); }
function setTab(t){ TAB=t; document.getElementById('tab-all').classList.toggle('on',t==='all');
  document.getElementById('tab-todo').classList.toggle('on',t==='todo'); render(); }
const TOKEN = new URLSearchParams(location.search).get('token');
function api(p){ return p + (TOKEN?(p.includes('?')?'&':'?')+'token='+encodeURIComponent(TOKEN):''); }
async function load(){
  const r = await fetch(api('/api/data')); const j = await r.json();
  DATA = j.deadlines; render(); if(VIEW==='cal') renderCal();
  document.getElementById('mode').textContent = '· '+j.mode+' 모드';
  const t = j.fetched_at? new Date(j.fetched_at).toLocaleString('ko-KR',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}):'없음';
  document.getElementById('meta').innerHTML = (j.refreshing?'<span class="spin"></span> 갱신 중… ':'')
     + '마지막 수집: '+t + (j.error?' · <span style="color:var(--red)">오류</span>':'');
  if(j.refreshing) setTimeout(load, 3000);
}
async function refresh(){
  document.getElementById('refbtn').innerHTML='<span class="spin"></span>';
  await fetch(api('/api/refresh'),{method:'POST'});
  setTimeout(()=>{ load(); document.getElementById('refbtn').textContent='↻'; }, 1500);
}
async function ask(){
  const q=document.getElementById('q').value.trim(); if(!q) return;
  const a=document.getElementById('answer'); a.style.display='block'; a.innerHTML='<span class="spin"></span> 생각 중…';
  try{ const r=await fetch(api('/api/ask?q='+encodeURIComponent(q))); const j=await r.json();
    a.textContent=j.answer; }catch(e){ a.textContent='오류: '+e; }
}
document.getElementById('q').addEventListener('keydown',e=>{ if(e.key==='Enter') ask(); });

// ===== 캘린더 =====
let VIEW='list';
const _now=new Date();
let CY=+_now.toLocaleString('en-US',{year:'numeric',timeZone:'Asia/Seoul'});
let CM=+_now.toLocaleString('en-US',{month:'numeric',timeZone:'Asia/Seoul'})-1; // 0-기반
let SEL=null;
const TODAY=new Date().toLocaleDateString('en-CA',{timeZone:'Asia/Seoul'});
function kstDay(iso){ return iso? new Date(iso).toLocaleDateString('en-CA',{timeZone:'Asia/Seoul'}) : null; }
function setView(v){
  VIEW=v;
  document.getElementById('seg-list').classList.toggle('on',v==='list');
  document.getElementById('seg-cal').classList.toggle('on',v==='cal');
  document.getElementById('listView').style.display = v==='list'?'':'none';
  document.getElementById('calView').style.display = v==='cal'?'':'none';
  if(v==='cal') renderCal();
}
function moveMonth(d){ CM+=d; if(CM<0){CM=11;CY--;} if(CM>11){CM=0;CY++;} SEL=null; renderCal(); }
function byDay(){
  const m={};
  for(const it of DATA){ const k=kstDay(it.due); if(!k) continue; (m[k]=m[k]||[]).push(it); }
  return m;
}
function renderCal(){
  const map=byDay();
  document.getElementById('calTitle').textContent=`${CY}년 ${CM+1}월`;
  const first=new Date(CY,CM,1).getDay();        // 1일의 요일(0=일)
  const days=new Date(CY,CM+1,0).getDate();       // 이달 일수
  const dows=['일','월','화','수','목','금','토'];
  let h = dows.map((d,i)=>`<div class="dow" style="color:${i===0?'var(--red)':i===6?'#7aa2ff':'var(--dim)'}">${d}</div>`).join('');
  for(let i=0;i<first;i++) h+='<div class="cell empty-cell"></div>';
  for(let d=1; d<=days; d++){
    const ds=`${CY}-${String(CM+1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
    const items=map[ds]||[]; const dow=new Date(CY,CM,d).getDay();
    const cls=['cell']; if(items.length) cls.push('has');
    if(ds===TODAY) cls.push('today'); if(ds===SEL) cls.push('sel');
    if(dow===0) cls.push('sun'); if(dow===6) cls.push('sat');
    let dots='';
    for(const it of items.slice(0,4)){
      const c = it.submitted===false?'miss':(it.submitted===true?'done':'etc');
      dots+=`<span class="dot ${c}"></span>`;
    }
    h+=`<div class="${cls.join(' ')}" ${items.length?`onclick="selectDay('${ds}')"`:''}>
        <span class="dnum">${d}</span><span class="dots">${dots}</span></div>`;
  }
  document.getElementById('calGrid').innerHTML=h;
  renderDayList(map);
}
function selectDay(ds){ SEL=(SEL===ds?null:ds); renderCal(); }
function renderDayList(map){
  const box=document.getElementById('dayList');
  if(!SEL){ box.innerHTML='<div class="seldate">날짜를 누르면 그날 마감이 보여요.</div>'; return; }
  const items=(map||byDay())[SEL]||[];
  const [y,m,d]=SEL.split('-');
  let h=`<div class="seldate">${+m}월 ${+d}일 마감 ${items.length}건</div>`;
  items.sort((a,b)=> (a.due||'').localeCompare(b.due||''));
  for(const it of items){
    let badge='';
    if(it.submitted===true) badge='<span class="badge b-done">제출✓</span>';
    else if(it.submitted===false) badge='<span class="badge b-miss">미제출</span>';
    const href=it.url?`href="${it.url}" target="_blank"`:'';
    h+=`<a class="card" ${href}>
      <div class="dday ${ddClass(it.days_left)}">${ddText(it.days_left)}</div>
      <div class="ci"><div class="t">${esc(it.title)}</div>
        <div class="s">${fmtDue(it.due,it.time_known)} · ${kmap[it.kind]||it.kind} · ${esc(it.course)}</div></div>
      ${badge}</a>`;
  }
  box.innerHTML=h;
}
load();
</script>
</body>
</html>"""


# 모듈 임포트 시 캐시를 읽어둔다 (gunicorn/클라우드에서 즉시 표시용).
_load_cache()


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="이러닝 과제·마감 모바일 웹앱")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-refresh", action="store_true", help="시작 시 자동 수집 끄기")
    args = ap.parse_args()

    _load_cache()
    if not args.no_refresh:
        refresh_async()  # 시작하면서 백그라운드로 최신 수집

    print(f"\n  이러닝 과제·마감 웹앱 실행 중")
    print(f"  - 이 PC:       http://localhost:{args.port}")
    print(f"  - 같은 WiFi 폰: http://<이 PC의 IP>:{args.port}  (아래 안내 참고)")
    if _cfg.web_token:
        print(f"  - 접속 토큰 필요: ?token={_cfg.web_token}")
    print()
    app.run(host=args.host, port=args.port, threaded=True)


if __name__ == "__main__":
    main()
