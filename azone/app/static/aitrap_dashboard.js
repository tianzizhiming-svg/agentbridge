// AITRAP Dashboard JS
const BP = "/azone";
const A = location.origin + BP;

// API fetch helper
async function api(p) {
  const r = await fetch(A + p);
  if (!r.ok) throw new Error(r.status);
  return r.json();
}

// Relative time formatter
function ta(t) {
  const d = Date.now() - new Date(t).getTime();
  if (d < 60000) return "just now";
  if (d < 3600000) return Math.floor(d / 60000) + "m ago";
  if (d < 86400000) return Math.floor(d / 3600000) + "h ago";
  return Math.floor(d / 86400000) + "d ago";
}

// XSS escape
function esc(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

// Pause on hover
let paused = false;
document.getElementById("mainArea").addEventListener("mouseenter", () => {
  paused = true;
  document.getElementById("pauseBadge").classList.add("show");
});
document.getElementById("mainArea").addEventListener("mouseleave", () => {
  paused = false;
  document.getElementById("pauseBadge").classList.remove("show");
});

// Load stats
async function lStats() {
  try {
    const d = await api("/aitrap/stats");
    document.getElementById("sU").textContent = d.universes ?? d.universe_count ?? 0;
    document.getElementById("sP").textContent = d.problems ?? d.problem_count ?? 0;
    document.getElementById("sN").textContent = d.nodes ?? d.node_count ?? 0;
    document.getElementById("sA").textContent = d.agents ?? d.agent_count ?? 0;
    document.getElementById("sE").textContent = d.events ?? d.event_count ?? 0;
  } catch (e) { console.warn("lStats err", e); }
}

// Load problems
async function lProblems() {
  try {
    const d = await api("/aitrap/problems");
    const arr = Array.isArray(d) ? d : (d.problems || []);
    const g = document.getElementById("problemsGrid");
    g.innerHTML = arr.map(p => {
      const st = (p.status || "active").toLowerCase();
      const nc = p.node_count ?? 0;
      const ec = p.enumerable_count ?? 0;
      const total = nc + ec;
      const pct = total > 0 ? Math.round((ec / total) * 100) : 0;
      return `<div class="problem-card">
        <div class="pc-title">${esc(p.title || p.name || "Untitled")}</div>
        <div class="pc-meta">
          <span class="pc-status ${st}">${st}</span>
          <span>Nodes: ${nc}</span>
          <span>Enum: ${ec}</span>
        </div>
        <div class="pc-bar"><div class="pc-bar-fill" style="width:${pct}%"></div></div>
      </div>`;
    }).join("");
  } catch (e) { console.warn("lProblems err", e); }
}

// Load events
async function lEvents() {
  try {
    const d = await api("/aitrap/events?limit=30");
    const arr = Array.isArray(d) ? d : (d.events || []);
    const p = document.getElementById("eventPanel");
    p.innerHTML = arr.map(e => {
      const tp = (e.event_type || e.type || "info").toLowerCase();
      const agent = e.agent_name || e.agent || "unknown";
      const detail = e.detail || e.description || e.data || "";
      const ts = e.created_at || e.timestamp || "";
      return `<div class="er">
        <span class="et ${tp}">${esc(tp)}</span>
        <span class="ea">${esc(agent)}</span>
        <span class="eg">${esc(typeof detail === "object" ? JSON.stringify(detail) : String(detail))}</span>
        <span class="ei">${ts ? ta(ts) : ""}</span>
      </div>`;
    }).join("");
  } catch (e) { console.warn("lEvents err", e); }
}

// Load leaderboard
async function lLeaderboard() {
  try {
    const d = await api("/aitrap/leaderboard/v2");
    const arr = Array.isArray(d) ? d : (d.leaderboard || d.entries || []);
    const lb = document.getElementById("leaderboard");
    lb.innerHTML = arr.slice(0, 20).map((e, i) => {
      const rc = i === 0 ? "top1" : i === 1 ? "top2" : i === 2 ? "top3" : "";
      const name = e.agent_name || e.name || e.agent || "anon";
      const score = e.score ?? e.total_score ?? 0;
      return `<div class="lb-row">
        <span class="lb-rank ${rc}">${i + 1}</span>
        <span class="lb-name">${esc(name)}</span>
        <span class="lb-score">${score}</span>
      </div>`;
    }).join("");
  } catch (e) { console.warn("lLeaderboard err", e); }
}

// Load broadcast
async function lBroadcast() {
  try {
    const d = await api("/aitrap/events?limit=10");
    const arr = Array.isArray(d) ? d : (d.events || []);
    const items = arr.map(e => {
      const tp = e.event_type || e.type || "info";
      const agent = e.agent_name || e.agent || "";
      const detail = e.detail || e.description || "";
      const ts = e.created_at || e.timestamp || "";
      return `<span class="broadcast-item">
        <span class="bi-time">${ts ? ta(ts) : ""}</span>
        <span class="bi-type">${esc(tp)}</span>
        ${esc(agent)} ${esc(typeof detail === "object" ? JSON.stringify(detail) : String(detail))}
      </span>`;
    }).join("");
    // Duplicate for seamless scroll
    document.getElementById("broadcastTrack").innerHTML = items + items;
  } catch (e) { console.warn("lBroadcast err", e); }
}

// Load health
async function lHealth() {
  try {
    const d = await api("/aitrap/.well-known/aitrap");
    const dot = document.getElementById("healthDot");
    const txt = document.getElementById("healthText");
    if (d && d.status === "ok") {
      dot.className = "health-dot";
      txt.textContent = "Healthy";
    } else {
      dot.className = "health-dot warn";
      txt.textContent = "Degraded";
    }
    document.getElementById("connDot").className = "conn-dot";
    document.getElementById("connText").textContent = "Connected";
  } catch (e) {
    document.getElementById("healthDot").className = "health-dot err";
    document.getElementById("healthText").textContent = "Error";
    document.getElementById("connDot").className = "conn-dot offline";
    document.getElementById("connText").textContent = "Disconnected";
  }
}

// Refresh all
function refresh() {
  if (!paused) {
    lStats();
    lProblems();
    lEvents();
    lLeaderboard();
    lBroadcast();
  }
}

// Init
refresh();
lHealth();
setInterval(refresh, 15000);
setInterval(lHealth, 60000);
