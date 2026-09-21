import "./style.css";

const app = document.querySelector("#app");
const BASE = import.meta.env.BASE_URL || "/";

app.innerHTML = `
  <div class="wrap">
    <header>
      <h1>DXTag</h1>
      <p>把 maidata.txt 拖进来，在浏览器里分析谱面结构、雷达和高置信拟合对照。谱面不会上传到服务器。社区抄谱与官谱不完全一致；DXRating 无审核标签不会参与判定。</p>
    </header>
    <section class="drop" id="drop">
      <strong>拖放 maidata.txt，或选择 / 粘贴文本</strong>
      <span class="fine">支持 Simai / Majdata 多难度 <code>&amp;inote_N</code>。默认分析全部非空难度。</span>
      <div class="row">
        <label class="file-btn">选择文件<input id="file" type="file" accept=".txt,text/plain" hidden /></label>
        <button id="paste-run" class="secondary" type="button">分析粘贴内容</button>
      </div>
      <textarea id="paste" placeholder="也可以直接粘贴 maidata 文本…"></textarea>
    </section>
    <div class="status" id="status">正在准备分析引擎…</div>
    <div id="result" class="hidden"></div>
    <footer>
      预估定数以国服水鱼高置信拟合为校准目标；样本不够时回退启发式，并标明置信度。日服内部定数与 Gamerch / maiノーツ解说只作对照。
    </footer>
  </div>
`;

const statusEl = document.querySelector("#status");
const resultEl = document.querySelector("#result");
const dropEl = document.querySelector("#drop");
const fileEl = document.querySelector("#file");
const pasteEl = document.querySelector("#paste");
const pasteRun = document.querySelector("#paste-run");

const worker = new Worker(`${BASE}analyzer-worker.js`);
let ready = false;
let current = null;
let svgs = {};

worker.onmessage = (event) => {
  const msg = event.data || {};
  if (msg.type === "status") statusEl.textContent = msg.text;
  if (msg.type === "ready") {
    ready = true;
    statusEl.textContent = "引擎已就绪，可以上传谱面。";
  }
  if (msg.type === "error") {
    statusEl.textContent = `分析失败：${msg.message}`;
    pasteRun.disabled = false;
  }
  if (msg.type === "result") {
    current = msg.document;
    svgs = msg.svgs || {};
    render(current.preferred_difficulty);
    statusEl.textContent = `完成：${current.title || "未命名"} · ${current.reports.length} 个难度`;
    pasteRun.disabled = false;
  }
};
worker.onerror = (err) => {
  statusEl.textContent = `引擎错误：${err.message || err}`;
};
worker.postMessage({ type: "init", base: BASE });

function setBusy(text) {
  pasteRun.disabled = true;
  statusEl.textContent = text;
}

function analyzeText(text, filename) {
  if (!text.trim()) {
    statusEl.textContent = "没有读到文本。";
    return;
  }
  setBusy("正在分析…");
  worker.postMessage({ type: "analyze", text, filename });
}

fileEl.addEventListener("change", async () => {
  const file = fileEl.files && fileEl.files[0];
  if (!file) return;
  analyzeText(await file.text(), file.name);
});
pasteRun.addEventListener("click", () => analyzeText(pasteEl.value, "paste.txt"));

["dragenter", "dragover"].forEach((type) => {
  dropEl.addEventListener(type, (event) => {
    event.preventDefault();
    dropEl.classList.add("drag");
  });
});
["dragleave", "drop"].forEach((type) => {
  dropEl.addEventListener(type, (event) => {
    event.preventDefault();
    dropEl.classList.remove("drag");
  });
});
dropEl.addEventListener("drop", async (event) => {
  const file = event.dataTransfer.files && event.dataTransfer.files[0];
  if (!file) return;
  analyzeText(await file.text(), file.name);
});

function fmt(value, digits = 1) {
  if (value == null || Number.isNaN(value)) return "—";
  return Number(value).toFixed(digits);
}

function badge(water) {
  if (!water) return "";
  if (water.code === "water") return `<span class="badge water">水</span>`;
  if (water.code === "overrated") return `<span class="badge overrated">诈称</span>`;
  if (water.code === "aligned") return `<span class="badge ok">拟合贴近官标</span>`;
  return `<span class="badge">证据不足</span>`;
}

function render(selected) {
  if (!current) return;
  const reports = current.reports;
  const report = reports.find((row) => row.difficulty === selected) || reports[0];
  const cat = report.catalog || {};
  const pred = report.prediction || {};
  const cn = cat.cn || {};
  const jp = cat.jp || {};
  const water = cat.water || {};
  const method = pred.calibrated ? "岭回归 · 高置信语料" : "启发式（未校准或样本不足）";
  const svg = svgs[String(report.difficulty)] || {};
  resultEl.classList.remove("hidden");
  resultEl.innerHTML = `
    <div class="tabs">
      ${reports.map((row) => `<button type="button" data-d="${row.difficulty}" class="${row.difficulty === report.difficulty ? "active" : ""}">${row.difficulty_name}</button>`).join("")}
    </div>
    <div class="grid">
      <div class="card">
        <h2>${escapeHtml(current.title || "未命名")} · ${escapeHtml(report.difficulty_name)}</h2>
        <div class="kpis">
          <div class="kpi"><span>预估定数</span><b>${pred.estimated_level == null ? "禁用" : fmt(pred.estimated_level)}</b></div>
          <div class="kpi"><span>方法</span><b style="font-size:1rem">${escapeHtml(method)}</b></div>
          <div class="kpi"><span>国服官标 / 拟合</span><b>${cn.ds == null ? "—" : fmt(cn.ds)}${cat.fit_confidence && cat.fit_confidence.usable ? " / " + fmt(cat.fit_confidence.fit_diff, 2) : ""}</b></div>
          <div class="kpi"><span>日服内部定数</span><b>${jp.internal == null ? "—" : fmt(jp.internal)}</b></div>
        </div>
        <p>${badge(water)} <span class="fine">${escapeHtml(water.detail || "")}</span></p>
        <p class="fine">${cat.matched ? `匹配 ${escapeHtml(cat.title || "")} · ${escapeHtml(cat.type || "")} · 物量误差 ${fmt((cat.count_error || 0) * 100, 2)}%` : escapeHtml(cat.reason || "未匹配曲库")}</p>
        ${svg.radar ? `<img class="svg" alt="雷达" src="${svgUrl(svg.radar)}" />` : ""}
        ${svg.density ? `<img class="svg" alt="密度" src="${svgUrl(svg.density)}" />` : ""}
      </div>
      <div class="card">
        <h2>结构难点</h2>
        <ul class="list">
          ${(report.community_terms || []).map((row) => `<li>${escapeHtml(row.term)} <span class="badge">${row.count}</span></li>`).join("") || "<li>没有足够的配置片段</li>"}
        </ul>
        <h2>雷达对照</h2>
        <ul class="list">
          ${(report.radar || []).map((axis) => `<li>${escapeHtml(axis.label)}：${fmt(axis.score)}${axis.peer_percentile == null ? "" : ` · 同等级约 P${fmt(axis.peer_percentile, 0)}`}</li>`).join("")}
        </ul>
        <h2>日服社群对照</h2>
        ${cat.community ? `<p class="fine">${escapeHtml(cat.community.role || "")} 来源：<a href="${escapeHtml(cat.community.url || "#")}" target="_blank" rel="noreferrer">${escapeHtml(cat.community.source || "wiki")}</a></p>
          <ul class="list">${(cat.community.bullets_zh || cat.community.bullets || []).map((b) => `<li>${escapeHtml(b)}</li>`).join("")}</ul>` : `<p class="fine">没有蒸馏过的日服解说；结构结论仍以左侧检测为准。</p>`}
      </div>
    </div>
    <div class="card" style="margin-top:16px">
      <h2>时间段证据</h2>
      ${(report.pattern_summary || []).map((row) => `
        <details>
          <summary>${escapeHtml(row.zh || row.label)} · ${row.count} 段</summary>
          <ul class="list">
            ${(report.patterns || []).filter((p) => p.label === row.label).slice(0, 24).map((p) => `<li>${fmt(p.start, 2)}–${fmt(p.end, 2)}s · 行 ${p.line || "?"} · ${escapeHtml(p.evidence || "")}</li>`).join("")}
          </ul>
        </details>`).join("") || "<p class='fine'>没有展开项</p>"}
      ${(report.warnings || []).map((w) => `<p class="warn">${escapeHtml(w)}</p>`).join("")}
    </div>
  `;
  resultEl.querySelectorAll(".tabs button").forEach((button) => {
    button.addEventListener("click", () => render(Number(button.dataset.d)));
  });
}

function svgUrl(svg) {
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

void ready;
