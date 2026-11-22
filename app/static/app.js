/* CareerOS frontend - Launchpad UI. Plain fetch against /api/*. No build step. */
const $ = (sel) => document.querySelector(sel);

function esc(s) {
  return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
}

async function api(path, options = {}) {
  const res = await fetch(path, options);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (e) {}
    throw new Error(detail);
  }
  return res.json();
}

// --- views (persistent sidebar) ---
function showView(name) {
  document.querySelectorAll(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === "view-" + name));
  if (name === "studio") loadTailorJobs();
}
document.querySelectorAll(".nav-item").forEach((btn) => {
  btn.addEventListener("click", () => showView(btn.dataset.view));
});

// --- health badge ---
api("/api/health").then((h) => {
  const badge = $("#mode-badge");
  badge.textContent = (h.llm_mode === "claude" ? "Claude connected" : "Offline mode") + " · fictional jobs";
  badge.classList.toggle("claude", h.llm_mode === "claude");
});

// --- profile ---
let currentProfile = null;
let lastDraft = null;

function renderProfile(p) {
  currentProfile = p;
  const div = $("#profile-view");
  const status = $("#rail-status");
  if (!p) {
    div.innerHTML = "<p class='hint'>No profile yet.</p>";
    status.innerHTML = "<small>No profile yet</small>";
    return;
  }
  status.innerHTML = `<small><b>${esc(p.name || "Profile")}</b><br>Profile ready<br>${p.skills.length} skills on file</small>`;
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
    renderProfile(currentProfile);
  } catch (e) {
    $("#save-status").textContent = "Error: " + e.message;
  }
});

api("/api/profile").then(renderProfile).catch(() => renderProfile(null));

// --- search (split view: results | why this matches) ---
let remoteOnly = false;
let lastResults = [];
let selectedIdx = null;

$("#remote-toggle").addEventListener("click", () => {
  remoteOnly = !remoteOnly;
  $("#remote-toggle").classList.toggle("on", remoteOnly);
  $("#remote-toggle").setAttribute("aria-pressed", String(remoteOnly));
  if ($("#search-input").value.trim()) runSearch();
});

function bar(label, value) {
  const pct = Math.round(value * 100);
  return `<div class="bar-label">${label} · ${pct}</div><div class="bar"><div class="fill" style="width:${pct}%"></div></div>`;
}

function renderResults() {
  const col = $("#search-results");
  col.innerHTML = lastResults.map((r, i) => `
    <div class="card ${i === selectedIdx ? "selected" : ""}" data-idx="${i}">
      <div class="card-head"><h3>${esc(r.job.title)}</h3><span class="score-inline">${Math.round(r.scores.total * 100)}</span></div>
      <div class="meta">${esc(r.job.company)} · ${esc(r.job.location)} · ${esc(r.job.job_type)} · ${esc(r.job.level)}</div>
      ${i === selectedIdx ? `<div>${r.job.skills.map((s) => `<span class="chip">${esc(s)}</span>`).join("")}</div>` : ""}
    </div>`).join("");
  col.querySelectorAll(".card").forEach((c) => {
    c.addEventListener("click", () => selectResult(Number(c.dataset.idx)));
  });
}

function selectResult(i) {
  selectedIdx = i;
  renderResults();
  const r = lastResults[i];
  const reasons = r.reasons.filter((x) => !x.startsWith("Remote requested"));
  $("#match-panel").classList.remove("hidden");
  $("#match-panel").innerHTML = `
    <small class="panel-label">Why this matches</small>
    <div class="score-row">
      <span class="score">${Math.round(r.scores.total * 100)}</span>
      <span class="score-sub">/ 100<br>${esc(r.job.title)} · ${esc(r.job.company)}</span>
    </div>
    ${bar("Relevance", r.scores.relevance)}
    ${bar("Skills", r.scores.skills)}
    ${bar("Location", r.scores.location)}
    ${bar("Experience", r.scores.experience)}
    <ul class="reasons">${reasons.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
    <button class="btn" id="tailor-cta">Tailor my resume</button>`;
  $("#tailor-cta").addEventListener("click", () => {
    showView("studio");
    tailorForJob(r.job.id);
  });
}

async function runSearch() {
  let q = $("#search-input").value.trim();
  if (!q) return;
  if (remoteOnly && !/\bremote\b/i.test(q)) q += " remote";
  $("#search-results").innerHTML = "<p class='hint'>Searching...</p>";
  $("#match-panel").classList.add("hidden");
  selectedIdx = null;
  try {
    const data = await api("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: q, k: 10 }),
    });
    lastResults = data.results;
    const note = data.results.length && data.results[0].reasons[0].startsWith("Remote requested")
      ? data.results[0].reasons[0] : null;
    $("#result-meta").textContent = data.results.length
      ? `${data.results.length} fictional results${note ? " · " + note : ""}`
      : "No jobs in the catalogue matched";
    if (!data.results.length) {
      $("#search-results").innerHTML = "<p class='hint'>No jobs in the catalogue matched.</p>";
      return;
    }
    renderResults();
    selectResult(0);
  } catch (e) {
    $("#search-results").innerHTML = "<p class='hint'>Error: " + esc(e.message) + "</p>";
  }
}

$("#search-btn").addEventListener("click", runSearch);
$("#search-input").addEventListener("keydown", (e) => { if (e.key === "Enter") runSearch(); });

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

// --- resume studio ---
async function loadTailorJobs() {
  try {
    const jobs = await api("/api/jobs");
    $("#tailor-job").innerHTML = jobs.map((j) =>
      `<option value="${j.id}">${esc(j.title)} - ${esc(j.company)}</option>`).join("");
  } catch (e) {
    $("#tailor-job").innerHTML = "<option>No jobs ingested</option>";
  }
}

function tailorForJob(jobId) {
  const sel = $("#tailor-job");
  if ([...sel.options].some((o) => Number(o.value) === jobId)) {
    sel.value = String(jobId);
    $("#tailor-btn").click();
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
    lastDraft = res.draft;
    const d = res.draft;
    $("#tailor-output").innerHTML = `
      <h3 style="margin-top:12px">Draft for ${esc(res.job.title)} at ${esc(res.job.company)}</h3>
      <div class="card resume">
        <h3 class="r-name">${esc(d.name)}</h3>
        <div class="meta">Target: ${esc(d.target_role)}</div>
        <p class="r-summary">${esc(d.summary)}</p>
        <h4>Skills</h4>
        <div>${(d.skills || []).map((x) => `<span class="chip">${esc(x)}</span>`).join("")}</div>
        <h4>Experience</h4>
        ${(d.experience || []).map((e) => `
          <div class="r-entry"><strong>${esc(e.title)}</strong> - ${esc(e.company)}
            <span class="meta">${esc(e.period)}</span></div>`).join("") || "<p class='hint'>None</p>"}
        <h4>Education</h4>
        ${(d.education || []).map((e) => `
          <div class="r-entry">${esc(e.degree)}${e.institution ? " - " + esc(e.institution) : ""} ${esc(e.year || "")}</div>`).join("") || "<p class='hint'>None</p>"}
      </div>
      <button id="download-draft" class="btn secondary" style="margin:8px 0">Download draft as .txt</button>
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

function draftToText(d) {
  const lines = [d.name, "Target: " + d.target_role, "", d.summary, "", "SKILLS",
    (d.skills || []).join(", "), "", "EXPERIENCE"];
  (d.experience || []).forEach((e) => lines.push(`${e.title} - ${e.company} (${e.period})`));
  lines.push("", "EDUCATION");
  (d.education || []).forEach((e) =>
    lines.push(`${e.degree}${e.institution ? " - " + e.institution : ""} ${e.year || ""}`.trim()));
  return lines.join("\n");
}

document.addEventListener("click", (e) => {
  if (e.target.id !== "download-draft" || !lastDraft) return;
  const blob = new Blob([draftToText(lastDraft)], { type: "text/plain" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "tailored-resume.txt";
  a.click();
  URL.revokeObjectURL(a.href);
});
