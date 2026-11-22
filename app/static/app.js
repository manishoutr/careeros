/* CareerOS frontend - plain fetch against /api/*. No build step. */
const $ = (sel) => document.querySelector(sel);

// --- tabs ---
document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    $("#tab-" + btn.dataset.tab).classList.add("active");
    if (btn.dataset.tab === "tailor") loadTailorJobs();
  });
});

async function api(path, options = {}) {
  const res = await fetch(path, options);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (e) {}
    throw new Error(detail);
  }
  return res.json();
}

// --- health badge ---
api("/api/health").then((h) => {
  const badge = $("#mode-badge");
  badge.textContent = h.llm_mode === "claude" ? "Claude connected" : "Offline mode";
  badge.classList.toggle("claude", h.llm_mode === "claude");
});

// --- profile ---
let currentProfile = null;

function renderProfile(p) {
  currentProfile = p;
  const div = $("#profile-view");
  if (!p) { div.innerHTML = "<p class='hint'>No profile yet.</p>"; return; }
  div.innerHTML = `
    <div class="card">
      <div class="field-row"><label>Name</label><input id="p-name" value="${esc(p.name)}"></div>
      <div class="field-row"><label>Skills (comma-separated, editable)</label>
        <input id="p-skills" value="${esc(p.skills.join(", "))}"></div>
      <div class="field-row"><label>Experience</label>
        ${p.experience.map((e, i) => `
          <input data-exp="${i}" value="${esc(e.title)} at ${esc(e.company)} (${esc(e.period)})" class="exp-input">`).join("") || "<p class='hint'>None detected</p>"}
      </div>
      <div class="field-row"><label>Education</label>
        ${p.education.map((e) => `<div>${esc(e.degree)}${e.institution ? " - " + esc(e.institution) : ""} ${esc(e.year)}</div>`).join("") || "<p class='hint'>None detected</p>"}
      </div>
    </div>`;
  $("#save-profile").classList.remove("hidden");
}

function esc(s) {
  return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
}

$("#upload-btn").addEventListener("click", async () => {
  const file = $("#resume-file").files[0];
  if (!file) { $("#upload-status").textContent = "Choose a file first."; return; }
  const fd = new FormData();
  fd.append("file", file);
  $("#upload-status").textContent = "Parsing...";
  try {
    const profile = await api("/api/profile/resume", { method: "POST", body: fd });
    $("#upload-status").textContent = "Parsed. Review and correct below.";
    renderProfile(profile);
  } catch (e) {
    $("#upload-status").textContent = "Error: " + e.message;
  }
});

$("#save-profile").addEventListener("click", async () => {
  if (!currentProfile) return;
  currentProfile.name = $("#p-name").value;
  currentProfile.skills = $("#p-skills").value.split(",").map((s) => s.trim()).filter(Boolean);
  document.querySelectorAll(".exp-input").forEach((inp) => {
    const i = Number(inp.dataset.exp);
    const m = inp.value.match(/^(.*?)\s+at\s+(.*?)\s*\((.*?)\)\s*$/);
    if (m) currentProfile.experience[i] = { ...currentProfile.experience[i], title: m[1], company: m[2], period: m[3] };
  });
  try {
    await api("/api/profile", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(currentProfile),
    });
    $("#save-status").textContent = "Saved.";
  } catch (e) {
    $("#save-status").textContent = "Error: " + e.message;
  }
});

api("/api/profile").then(renderProfile).catch(() => renderProfile(null));

// --- search ---
function scoreBar(label, value) {
  const pct = Math.round(value * 100);
  return `<div class="scorebar">${label} ${pct}%<div class="bar"><div class="fill" style="width:${pct}%"></div></div></div>`;
}

$("#search-btn").addEventListener("click", async () => {
  const q = $("#search-input").value.trim();
  if (!q) return;
  $("#search-results").innerHTML = "<p class='hint'>Searching...</p>";
  try {
    const data = await api("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: q, k: 10 }),
    });
    if (!data.results.length) {
      $("#search-results").innerHTML = "<p class='hint'>No jobs in the catalogue matched.</p>";
      return;
    }
    $("#search-results").innerHTML = data.results.map((r) => `
      <div class="card">
        <h3>${esc(r.job.title)}</h3>
        <div class="meta">${esc(r.job.company)} · ${esc(r.job.location)} · ${esc(r.job.job_type)} · ${esc(r.job.level)}</div>
        <div>${r.job.skills.map((s) => `<span class="chip">${esc(s)}</span>`).join("")}</div>
        <div class="scorebars">
          ${scoreBar("Relevance", r.scores.relevance)}${scoreBar("Skills", r.scores.skills)}
          ${scoreBar("Location", r.scores.location)}${scoreBar("Experience", r.scores.experience)}
          ${scoreBar("Total", r.scores.total)}
        </div>
        <ul class="reasons">${r.reasons.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
      </div>`).join("");
  } catch (e) {
    $("#search-results").innerHTML = "<p class='hint'>Error: " + esc(e.message) + "</p>";
  }
});

// --- assistant ---
function addMsg(who, text, trace) {
  const log = $("#chat-log");
  const div = document.createElement("div");
  div.className = "msg " + (who === "You" ? "user" : "assistant");
  div.innerHTML = `<span class="who">${who}</span>${esc(text)}` +
    (trace && trace.length ? `<div class="trace">tools: ${trace.map((t) => esc(t.tool)).join(", ")}</div>` : "");
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}

$("#chat-btn").addEventListener("click", async () => {
  const msg = $("#chat-input").value.trim();
  if (!msg) return;
  $("#chat-input").value = "";
  addMsg("You", msg);
  try {
    const res = await api("/api/assistant/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: msg }),
    });
    addMsg(res.mode === "claude" ? "CareerOS (Claude)" : "CareerOS (offline)", res.answer, res.tool_trace);
  } catch (e) {
    addMsg("CareerOS", "Error: " + e.message);
  }
});

$("#chat-input").addEventListener("keydown", (e) => { if (e.key === "Enter") $("#chat-btn").click(); });
$("#search-input").addEventListener("keydown", (e) => { if (e.key === "Enter") $("#search-btn").click(); });

// --- tailor ---
async function loadTailorJobs() {
  try {
    const jobs = await api("/api/jobs");
    $("#tailor-job").innerHTML = jobs.map((j) =>
      `<option value="${j.id}">${esc(j.title)} - ${esc(j.company)}</option>`).join("");
  } catch (e) {
    $("#tailor-job").innerHTML = "<option>No jobs ingested</option>";
  }
}

$("#tailor-btn").addEventListener("click", async () => {
  const jobId = Number($("#tailor-job").value);
  if (!jobId) { $("#tailor-output").innerHTML = "<p class='hint'>Pick a job first.</p>"; return; }
  $("#tailor-output").innerHTML = "<p class='hint'>Building draft...</p>";
  try {
    const res = await api("/api/tailor", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_id: jobId }),
    });
    $("#tailor-output").innerHTML = `
      <h3 style="margin-top:12px">Draft for ${esc(res.job.title)} at ${esc(res.job.company)}</h3>
      <pre class="draft">${esc(JSON.stringify(res.draft, null, 2))}</pre>
      <h3 style="margin-top:12px">Changes to review (${res.changes.length})</h3>
      ${res.changes.map((c) => `
        <div class="change">
          <span class="kind">${esc(c.section)} · ${esc(c.change)}</span>
          <span class="before">${esc(c.before)}</span>
          <span class="after">${esc(c.after)}</span>
          <span class="source">Source: ${esc(c.source)}</span>
        </div>`).join("")}`;
  } catch (e) {
    $("#tailor-output").innerHTML = "<p class='hint'>Error: " + esc(e.message) + "</p>";
  }
});
