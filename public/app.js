const $ = id => document.getElementById(id);
let data = {today:[], confirmed:false, sources:[], status:"unavailable"};
let soundEnabled = true;
let audioContext = null;
let toastTimer = null;

const fmt = n => Number(n || 0).toLocaleString();
const safe = value => String(value ?? "").trim();

function missionIcon(name) {
  const n = safe(name).toLowerCase();
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

/* Keep the existing mission-specific artwork. */
function missionImage(name) {
  const n = safe(name).toLowerCase();
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

function playSfx(kind = "click") {
  if (!soundEnabled) return;
  try {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return;
    if (!audioContext) audioContext = new AudioCtx();
    if (audioContext.state === "suspended") audioContext.resume();
    const osc = audioContext.createOscillator();
    const gain = audioContext.createGain();
    const now = audioContext.currentTime;
    osc.connect(gain);
    gain.connect(audioContext.destination);
    if (kind === "open") {
      osc.type = "triangle";
      osc.frequency.setValueAtTime(520, now);
      osc.frequency.exponentialRampToValueAtTime(980, now + .12);
      gain.gain.setValueAtTime(.075, now);
      gain.gain.exponentialRampToValueAtTime(.001, now + .16);
      osc.start(now); osc.stop(now + .17);
    } else if (kind === "coin") {
      osc.type = "sine";
      osc.frequency.setValueAtTime(660, now);
      osc.frequency.setValueAtTime(990, now + .09);
      osc.frequency.setValueAtTime(1320, now + .17);
      gain.gain.setValueAtTime(.07, now);
      gain.gain.exponentialRampToValueAtTime(.001, now + .28);
      osc.start(now); osc.stop(now + .29);
    } else {
      osc.type = "sine";
      osc.frequency.setValueAtTime(440, now);
      osc.frequency.exponentialRampToValueAtTime(720, now + .07);
      gain.gain.setValueAtTime(.045, now);
      gain.gain.exponentialRampToValueAtTime(.001, now + .09);
      osc.start(now); osc.stop(now + .1);
    }
  } catch (_) { /* Audio is optional; the tracker still works without it. */ }
}

function showToast(message) {
  const toast = $("toast");
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("show"), 2600);
}

async function copyText(text, successMessage = "Copied to clipboard.") {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
    } else {
      const field = document.createElement("textarea");
      field.value = text;
      field.style.position = "fixed";
      field.style.opacity = "0";
      document.body.append(field);
      field.select();
      const ok = document.execCommand("copy");
      field.remove();
      if (!ok) throw new Error("Clipboard unavailable");
    }
    playSfx("click");
    showToast(successMessage);
  } catch (_) {
    showToast("Could not copy. Please try again.");
  }
}

function missionDetails(m) {
  const parts = [safe(m.mission) || "Mission alert"];
  if (m.zone) parts.push(`Region: ${m.zone}`);
  if (m.location) parts.push(`Zone: ${m.location}`);
  if (Number.isFinite(Number(m.powerLevel)) && Number(m.powerLevel) > 0) parts.push(`Power Level: ${m.powerLevel}`);
  parts.push(`Reward: ${fmt(m.vbucks)} V-Bucks`);
  return parts.join(" | ");
}

function dailyReport() {
  const missions = Array.isArray(data.today) ? data.today : [];
  const total = missions.reduce((sum, m) => sum + (Number(m.vbucks) || 0), 0);
  if (!missions.length) {
    return "SEE-BOT DAILY REPORT\nNo verified V-Bucks mission rows are currently available. Check the tracker again after the next source update.";
  }
  const rows = missions.map((m, i) => `${i + 1}. ${missionDetails(m)}`);
  return `SEE-BOT DAILY REPORT\n${missions.length} verified mission${missions.length === 1 ? "" : "s"} • ${fmt(total)} V-Bucks total\n\n${rows.join("\n")}\n\nConfirm mission details in-game before launching:)`;
}

function openSeeBot() {
  $("seeBotText").textContent = dailyReport();
  $("seeBotModal").classList.add("open");
  $("seeBotModal").setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
  playSfx("open");
  $("seeBotClose").focus();
}

function closeSeeBot() {
  $("seeBotModal").classList.remove("open");
  $("seeBotModal").setAttribute("aria-hidden", "true");
  document.body.classList.remove("modal-open");
  playSfx("click");
  $("seeBotOpen").focus();
}

function renderMissions() {
  const list = Array.isArray(data.today) ? data.today : [];
  const regionFilter = $("zone").value.toLowerCase();
  const q = $("search").value.trim().toLowerCase();
  const shown = list.filter(m =>
    (!regionFilter || safe(m.zone).toLowerCase() === regionFilter) &&
    (!q || `${m.mission || ""} ${m.location || ""} ${m.zone || ""}`.toLowerCase().includes(q))
  );
  const total = list.reduce((sum, m) => sum + (Number(m.vbucks) || 0), 0);
  $("todayTotal").textContent = fmt(total);
  $("todayCount").textContent = list.length;
  $("todayBadge").textContent = list.length;

  if (data.confirmed && list.length) {
    $("todayNote").textContent = `${list.length} verified mission${list.length === 1 ? "" : "s"} detected with ${fmt(total)} V-Bucks in total rewards. Confirm each alert in-game before launching.`;
  } else if (list.length) {
    $("todayNote").textContent = `${list.length} saved mission${list.length === 1 ? "" : "s"} worth ${fmt(total)} V-Bucks. Today's details are not fully verified yet.`;
  } else {
    $("todayNote").textContent = "Mission details are currently unavailable. This does not mean there are zero V-Bucks missions.";
  }

  const box = $("missionsList");
  box.replaceChildren();
  if (!shown.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    const title = document.createElement("b");
    title.textContent = "NO MISSIONS FOUND";
    const note = document.createElement("span");
    note.textContent = list.length ? "Try another zone or search term." : "No missions available right now.";
    empty.append(title, note);
    box.append(empty);
    return;
  }

  shown.forEach(m => {
    const card = document.createElement("article");
    card.className = "mission";
    const head = document.createElement("div");
    head.className = "missionhead";
    const info = document.createElement("div");
    info.className = "mission-info";
    const titleRow = document.createElement("div");
    titleRow.className = "mission-title-row";
    const icon = document.createElement("span");
    icon.className = "mission-icon";
    icon.setAttribute("aria-hidden", "true");
    const imagePath = missionImage(m.mission);
    if (imagePath) {
      const img = document.createElement("img");
      img.className = "mission-icon-image";
      img.src = imagePath;
      img.alt = "";
      img.loading = "lazy";
      img.onerror = () => { icon.textContent = missionIcon(m.mission); };
      icon.append(img);
    } else {
      icon.textContent = missionIcon(m.mission);
    }
    const title = document.createElement("h3");
    title.textContent = m.mission || "Mission alert";
    titleRow.append(icon, title);
    info.append(titleRow);

    const reward = document.createElement("div");
    reward.className = "reward";
    const coin = document.createElement("img");
    coin.src = "vbucks-logo.png";
    coin.alt = "";
    coin.className = "vbucks-mark";
    const amount = document.createElement("span");
    amount.textContent = fmt(m.vbucks);
    reward.append(coin, amount);
    head.append(info, reward);

    const meta = document.createElement("div");
    meta.className = "mission-meta";
    const region = document.createElement("span");
    region.className = "mission-region";
    region.textContent = m.zone || "Unknown region";
    meta.append(region);

    if (m.location) {
      const location = document.createElement("span");
      location.className = "mission-zone";
      location.textContent = m.location;
      meta.append(location);
    }

    const pl = Number(m.powerLevel);
    if (Number.isInteger(pl) && pl > 0 && pl <= 160) {
      const power = document.createElement("span");
      power.className = "mission-power";
      power.setAttribute("aria-label", `Power level ${pl}`);
      const number = document.createElement("strong");
      number.className = "mission-power-number";
      number.textContent = pl;
      const bolt = document.createElement("span");
      bolt.className = "mission-power-bolt";
      bolt.setAttribute("aria-hidden", "true");
      bolt.textContent = "⚡";
      const label = document.createElement("span");
      label.className = "mission-power-label";
      label.textContent = "POWER";
      power.append(number, bolt, label);
      meta.append(power);
    }

    const footer = document.createElement("div");
    footer.className = "mission-footer";
    const status = document.createElement("span");
    status.className = "mission-status";
    status.innerHTML = '<i></i> ACTIVE ALERT';
    const copy = document.createElement("button");
    copy.type = "button";
    copy.className = "copy-mission";
    copy.textContent = "▣ COPY DETAILS";
    copy.addEventListener("click", () => copyText(`Save the World Daily Mission\n${missionDetails(m)}`, "Mission details copied."));
    footer.append(status, copy);
    card.append(head, meta, footer);
    box.append(card);
  });
}

async function load() {
  const refreshIcon = $("refreshIcon");
  $("updated").textContent = "Checking mission intel…";
  refreshIcon.classList.add("spinning");
  try {
    const response = await fetch(`data/missions.json?t=${Date.now()}`, {cache:"no-store"});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const d = await response.json();
    data = {
      today: Array.isArray(d.today) ? d.today : [],
      confirmed: d.confirmed === true,
      sources: Array.isArray(d.sources) ? d.sources : [],
      status: d.status || "unavailable"
    };
    $("updated").textContent = d.updatedAt
      ? `CHECKED ${new Date(d.updatedAt).toLocaleString()}`
      : "WAITING FOR FIRST AUTOMATIC CHECK";
  } catch (_) {
    data = {today:[], confirmed:false, sources:[], status:"unavailable"};
    $("updated").textContent = "MISSION DATA UNAVAILABLE";
  } finally {
    refreshIcon.classList.remove("spinning");
    renderMissions();
  }
}

$("zone").addEventListener("change", () => { playSfx("click"); renderMissions(); });
$("search").addEventListener("input", renderMissions);
$("refresh").addEventListener("click", () => { playSfx("click"); load(); });
$("year").textContent = new Date().getFullYear();
$("seeBotOpen").addEventListener("click", openSeeBot);
$("seeBotClose").addEventListener("click", closeSeeBot);
$("seeBotDone").addEventListener("click", closeSeeBot);
document.querySelector("[data-close-see-bot]").addEventListener("click", closeSeeBot);
$("seeBotCopy").addEventListener("click", () => copyText(dailyReport(), "See-Bot report copied."));
$("copyDaily").addEventListener("click", () => copyText(dailyReport(), "Daily mission summary copied."));
$("soundToggle").addEventListener("click", () => {
  soundEnabled = !soundEnabled;
  $("soundLabel").textContent = soundEnabled ? "SFX ON" : "SFX OFF";
  $("soundIcon").textContent = soundEnabled ? "◖))" : "◖×";
  $("soundToggle").setAttribute("aria-pressed", String(soundEnabled));
  if (soundEnabled) playSfx("click");
});
document.addEventListener("keydown", event => {
  if (event.key === "Escape" && $("seeBotModal").classList.contains("open")) closeSeeBot();
});
load();
