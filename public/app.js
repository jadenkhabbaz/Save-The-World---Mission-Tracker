const $ = id => document.getElementById(id);
let data = {today:[], confirmed:false, sources:[], status:"unavailable"};
let history = {days:[]};
const fmt = n => Number(n || 0).toLocaleString();

function missionIcon(name) {
  const n = String(name || "").toLowerCase();
  if (n.includes("survivor")) return "🧑‍🚀";
  if (n.includes("storm")) return "⛈️";
  if (n.includes("bomb")) return "💣";
  if (n.includes("lightning")) return "⚡";
  if (n.includes("shelter")) return "🏠";
  if (n.includes("radar")) return "📡";
  if (n.includes("encampment")) return "🔥";
  if (n.includes("data")) return "💾";
  return "🎯";
}

function missionImage(name) {
  const n = String(name || "").toLowerCase();
  if (n.includes("evacuate the shelter")) return "assets/missions/evacuate-the-shelter.png";
  if (n.includes("fight category 2 storm")) return "assets/missions/fight-category-2-storm.png";
  return null;
}

function renderMissions() {
  const list = Array.isArray(data.today) ? data.today : [];
  const zone = $("zone").value.toLowerCase();
  const q = $("search").value.trim().toLowerCase();
  const shown = list.filter(m => (!zone || String(m.zone || "").toLowerCase() === zone) &&
    (!q || `${m.mission || ""} ${m.location || ""} ${m.zone || ""}`.toLowerCase().includes(q)));
  const total = list.reduce((s,m) => s + (Number(m.vbucks) || 0), 0);
  $("todayTotal").textContent = fmt(total);
  $("todayCount").textContent = list.length;
  $("todayBadge").textContent = list.length;

  if (data.confirmed && list.length) {
    $("todayNote").textContent = `${list.length} mission${list.length===1?"":"s"} listed with ${fmt(total)} V-Bucks in rewards. Confirm the missions in-game before launching.`;
  } else if (list.length) {
    $("todayNote").textContent = `Showing ${list.length} saved mission${list.length===1?"":"s"} worth ${fmt(total)} V-Bucks. Today's mission details have not been independently verified yet.`;
  } else if (data.status === "partial") {
    $("todayNote").textContent = "Sources were checked, but no individual mission rows could be verified. This does not mean there are zero V-Bucks missions.";
  } else {
    $("todayNote").textContent = "Mission data could not be verified from the public sources. This does not mean there are zero V-Bucks missions.";
  }

  const box = $("missionsList"); box.replaceChildren();
  if (!shown.length) {
    const e=document.createElement("div"); e.className="empty";
    const b=document.createElement("b"); b.textContent="No verified mission rows yet";
    const p=document.createElement("span"); p.textContent="The sources may only expose totals or their page structure may have changed. Check the source status below.";
    e.append(b,p); box.append(e); return;
  }
  shown.forEach(m => {
    const c=document.createElement("article"); c.className="mission";
    const h=document.createElement("div"); h.className="missionhead";
    const left=document.createElement("div"); left.className="mission-info";
    const titleRow=document.createElement("div"); titleRow.className="mission-title-row";

    const icon=document.createElement("span");
    icon.className="mission-icon";
    icon.setAttribute("aria-hidden","true");
    const imagePath=missionImage(m.mission);
    if (imagePath) {
      const img=document.createElement("img");
      img.className="mission-icon-image";
      img.src=imagePath;
      img.alt="";
      // Explicit sizing prevents the PNG's intrinsic dimensions overflowing the card.
      img.style.width="100%";
      img.style.height="100%";
      img.style.maxWidth="100%";
      img.style.maxHeight="100%";
      img.style.objectFit="contain";
      img.style.display="block";
      img.style.borderRadius="8px";
      icon.append(img);
    } else {
      icon.textContent=missionIcon(m.mission);
    }

    const title=document.createElement("h3"); title.textContent=m.mission || "Mission alert";
    titleRow.append(icon,title);
    const sub=document.createElement("p"); sub.className="mission-sub"; sub.textContent=`${m.zone||"Unknown zone"}${m.location?" · "+m.location:""}`;
    left.append(titleRow,sub);
    const reward=document.createElement("div"); reward.className="reward"; reward.textContent=`Ⓥ ${fmt(m.vbucks)}`;
    h.append(left,reward); c.append(h);
    const pl=Number(m.powerLevel);
    if(Number.isInteger(pl) && pl>=2 && pl<=160) {
      const tags=document.createElement("div"); tags.className="tags";
      const tag=document.createElement("span"); tag.className="tag"; tag.textContent=`PL ${pl}`;
      tags.append(tag); c.append(tags);
    }
    box.append(c);
  });
}

function renderSources() {
  const box=$("sourceStatus"); box.replaceChildren();
  (data.sources||[]).forEach(s=>{
    const c=document.createElement("article"); c.className="source-card";
    const h=document.createElement("div"); h.className="source-head";
    const a=document.createElement("a"); a.href=s.url||"#"; a.target="_blank"; a.rel="noopener"; a.textContent=s.name||"Mission source";
    const status=document.createElement("span"); status.className="source-pill "+(s.ok?"ok":"bad"); status.textContent=s.ok?"Fetched":"Unavailable";
    h.append(a,status);
    const p=document.createElement("p"); p.textContent=s.status||"No status";
    const details=document.createElement("div"); details.className="source-totals";
    const labels=[["today","Today"],["yesterday","Yesterday"],["last7Days","7 days"],["last30Days","30 days"],["thisYear","This year"]];
    let any=false;
    labels.forEach(([key,label])=>{if(s.summary&&s.summary[key]!==undefined){any=true;const x=document.createElement("span");x.textContent=`${label}: ${fmt(s.summary[key])} V-Bucks`;details.append(x);}});
    if(!any){const x=document.createElement("span");x.textContent=s.ok?"No historical totals parsed from this page":"No data available";details.append(x);}
    c.append(h,p,details); box.append(c);
  });
}

function renderHistory() {
  const box=$("historyList"); box.replaceChildren();
  const days=(history.days||[]).slice().sort((a,b)=>(b.date||"").localeCompare(a.date||""));
  $("historyUpdated").textContent=days.length?`${days.length} saved day${days.length===1?"":"s"} · Updated ${history.updatedAt?new Date(history.updatedAt).toLocaleString():"—"}`:"No daily snapshots saved yet";
  if(!days.length){const e=document.createElement("div");e.className="empty";e.textContent="The archive will fill after the scheduled updater successfully runs. Historical totals imported from source websites appear in the source cards above.";box.append(e);return;}
  days.slice(0,60).forEach(d=>{
    const row=document.createElement("article");row.className="history-row";
    const date=document.createElement("b");date.textContent=d.date||"Unknown date";
    const missions=d.missions||[];
    const count=document.createElement("span");count.textContent=`${missions.length} individual mission${missions.length===1?"":"s"}`;
    const total=document.createElement("strong");total.textContent=missions.length?`Ⓥ ${fmt(missions.reduce((n,m)=>n+(Number(m.vbucks)||0),0))}`:"Mission details unavailable";
    const status=document.createElement("span");status.className="source-pill "+(d.confirmed?"ok":"bad");status.textContent=d.confirmed?"Verified rows":"Partial / no rows";
    row.append(date,count,total,status);box.append(row);
  });
}

async function load() {
  $("updated").textContent="Checking saved data…";
  try {
    const r=await fetch(`data/missions.json?t=${Date.now()}`,{cache:"no-store"});
    if(!r.ok) throw Error(`HTTP ${r.status}`);
    const d=await r.json();
    data={today:Array.isArray(d.today)?d.today:[],confirmed:d.confirmed===true,sources:Array.isArray(d.sources)?d.sources:[],status:d.status||"unavailable"};
    $("updated").textContent=d.updatedAt?`Checked ${new Date(d.updatedAt).toLocaleString()}`:"Waiting for first automatic check";
  } catch(e) {
    data={today:[],confirmed:false,sources:[],status:"unavailable"};
    $("updated").textContent="Could not load mission data";
  }
  try { const r=await fetch(`data/history.json?t=${Date.now()}`,{cache:"no-store"}); if(r.ok) history=await r.json(); } catch(e) {}
  renderMissions(); renderSources(); renderHistory();
}
$("zone").addEventListener("change",renderMissions);
$("search").addEventListener("input",renderMissions);
$("refresh").addEventListener("click",load);
$("year").textContent=new Date().getFullYear();
load();
