const $ = id => document.getElementById(id);
let data = {today:[], confirmed:false, sources:[], status:"unavailable"};
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
  if (n.includes("build the radar grid")) return "assets/missions/build-the-radar-grid.png";
  if (n.includes("deliver the bomb")) return "assets/missions/deliver-the-bomb.png";
  if (n.includes("destroy the encampments")) return "assets/missions/destroy-the-encampments.png";
  if (n.includes("eliminate and collect")) return "assets/missions/eliminate-and-collect.png";
  if (n.includes("evacuate the shelter")) return "assets/missions/evacuate-the-shelter.png";
  if (n.includes("fight category 2 storm")) return "assets/missions/fight-category-2-storm.png";
  if (n.includes("fight category 4 storm")) return "assets/missions/fight-the-storm-four-atlas.png";
  if (n.includes("fight category 3 storm") || n.includes("fight the storm triple atlas") || n.includes("triple atlas"))
    return "assets/missions/fight-the-storm-triple-atlas.png";
  if (n.includes("repair the shelter")) return "assets/missions/repair-the-shelter.png";
  if (n.includes("retrieve the data")) return "assets/missions/retrieve-the-data.png";
  if (n.includes("ride the lightning")) return "assets/missions/ride-the-lightning.png";
  return null;
}

function renderMissions() {
  const list = Array.isArray(data.today) ? data.today : [];
  const regionFilter = $("zone").value.toLowerCase();
  const q = $("search").value.trim().toLowerCase();
  const shown = list.filter(m =>
    (!regionFilter || String(m.zone || "").toLowerCase() === regionFilter) &&
    (!q || `${m.mission || ""} ${m.location || ""} ${m.zone || ""}`.toLowerCase().includes(q))
  );
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

  const box = $("missionsList");
  box.replaceChildren();
  if (!shown.length) {
    const e=document.createElement("div"); e.className="empty";
    const b=document.createElement("b"); b.textContent="No verified mission rows yet";
    const p=document.createElement("span"); p.textContent="The sources may only expose totals or their page structure may have changed. Check back after the next automatic update.";
    e.append(b,p); box.append(e); return;
  }

  shown.forEach(m => {
    const c=document.createElement("article"); c.className="mission";
    const h=document.createElement("div"); h.className="missionhead";
    const left=document.createElement("div"); left.className="mission-info";
    const titleRow=document.createElement("div"); titleRow.className="mission-title-row";

    // Keep the existing per-mission image mapping and image files.
    const icon=document.createElement("span");
    icon.className="mission-icon";
    icon.setAttribute("aria-hidden","true");
    const imagePath=missionImage(m.mission);
    if (imagePath) {
      const img=document.createElement("img");
      img.className="mission-icon-image";
      img.src=imagePath;
      img.alt="";
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

    const title=document.createElement("h3");
    title.textContent=m.mission || "Mission alert";
    titleRow.append(icon,title);

    // Red = region, green = in-game zone, large yellow block = power level.
    const meta=document.createElement("div");
    meta.className="mission-meta";

    const region=document.createElement("span");
    region.className="mission-region";
    region.textContent=m.zone || "Unknown region";
    meta.append(region);

    if (m.location) {
      const missionZone=document.createElement("span");
      missionZone.className="mission-zone";
      missionZone.textContent=m.location;
      meta.append(missionZone);
    }

    const pl=Number(m.powerLevel);
    if(Number.isInteger(pl) && pl>=2 && pl<=160) {
      const power=document.createElement("span");
      power.className="mission-power";
      power.setAttribute("aria-label",`Power level ${pl}`);
      const number=document.createElement("strong");
      number.className="mission-power-number";
      number.textContent=pl;
      const detail=document.createElement("span");
      detail.className="mission-power-detail";
      const bolt=document.createElement("span");
      bolt.className="mission-power-bolt";
      bolt.textContent="ϟ";
      const label=document.createElement("span");
      label.className="mission-power-label";
      label.textContent="POWER";
      detail.append(bolt,label);
      power.append(number,detail);
      meta.append(power);
    }

    left.append(titleRow,meta);

    const reward=document.createElement("div");
    reward.className="reward";
    reward.textContent=`Ⓥ ${fmt(m.vbucks)}`;
    h.append(left,reward);
    c.append(h);
    box.append(c);
  });
}

async function load() {
  $("updated").textContent="Checking saved data…";
  try {
    const r=await fetch(`data/missions.json?t=${Date.now()}`,{cache:"no-store"});
    if(!r.ok) throw Error(`HTTP ${r.status}`);
    const d=await r.json();
    data={
      today:Array.isArray(d.today)?d.today:[],
      confirmed:d.confirmed===true,
      sources:Array.isArray(d.sources)?d.sources:[],
      status:d.status||"unavailable"
    };
    $("updated").textContent=d.updatedAt
      ? `Checked ${new Date(d.updatedAt).toLocaleString()}`
      : "Waiting for first automatic check";
  } catch(e) {
    data={today:[],confirmed:false,sources:[],status:"unavailable"};
    $("updated").textContent="Could not load mission data";
  }
  renderMissions();
}
$("zone").addEventListener("change",renderMissions);
$("search").addEventListener("input",renderMissions);
$("refresh").addEventListener("click",load);
$("year").textContent=new Date().getFullYear();
load();
