import "./style.css";
import {
  DIFF_LABELS,
  chartAssetId,
  difficultiesOf,
  fetchChart,
  loadCatalog,
  searchSongs,
  slotFromLxnsDifficulty,
} from "./lxns.js";

const app = document.querySelector("#app");
const BASE = import.meta.env.BASE_URL || "/";

app.innerHTML = `
  <div class="wrap">
    <header>
      <h1>DXTag</h1>
      <p>从落雪曲库选曲，或把 maidata.txt 拖进来，在浏览器里分析谱面结构、雷达和高置信拟合对照。谱面从落雪拉到本机解析，不会回传。社区抄谱与官谱不完全一致；DXRating 无审核标签不会参与判定。</p>
    </header>
    <section class="lxns" id="lxns">
      <strong>从落雪曲库选曲</strong>
      <span class="fine">点难度会拉取该标准/DX 整份抄谱再分析。抄谱仍可能对不上官谱物量；水/诈称仍只用水鱼高置信拟合。</span>
      <label class="field-label" for="lxns-q">搜索曲目</label>
      <input id="lxns-q" type="search" placeholder="曲名、别名、艺术家或曲目 ID…" autocomplete="off" disabled />
      <div class="fine" id="lxns-meta">正在载入落雪曲目列表…</div>
      <div id="lxns-results" class="lxns-results" hidden></div>
    </section>
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
      预估定数以国服水鱼高置信拟合为校准目标；样本不够时回退启发式，并标明置信度。日服内部定数与 Gamerch / maiノーツ解说只作对照。落雪只提供抄谱原文，不参与水/诈称判定。
    </footer>
  </div>
`;

const statusEl = document.querySelector("#status");
const resultEl = document.querySelector("#result");
const dropEl = document.querySelector("#drop");
const fileEl = document.querySelector("#file");
const pasteEl = document.querySelector("#paste");
const pasteRun = document.querySelector("#paste-run");
const lxnsQuery = document.querySelector("#lxns-q");
const lxnsMeta = document.querySelector("#lxns-meta");
const lxnsResults = document.querySelector("#lxns-results");

const worker = new Worker(`${BASE}analyzer-worker.js`);
let ready = false;
let busy = false;
let current = null;
let svgs = {};
let pendingSlot = null;

worker.onmessage = (event) => {
  const msg = event.data || {};
  if (msg.type === "status") statusEl.textContent = msg.text;
  if (msg.type === "ready") {
    ready = true;
    statusEl.textContent = "引擎已就绪，可以选曲或上传谱面。";
  }
  if (msg.type === "error") {
    statusEl.textContent = `分析失败：${msg.message}`;
    setIdle();
  }
  if (msg.type === "result") {
    current = msg.document;
    svgs = msg.svgs || {};
    const selected = pendingSlot;
    pendingSlot = null;
    render(selected ?? current.preferred_difficulty);
    statusEl.textContent = `完成：${current.title || "未命名"} · ${current.reports.length} 个难度`;
    setIdle();
  }
};
worker.onerror = (err) => {
  statusEl.textContent = `引擎错误：${err.message || err}`;
  setIdle();
};
worker.postMessage({ type: "init", base: BASE });

function setIdle() {
  busy = false;
  pasteRun.disabled = false;
  lxnsResults.querySelectorAll("button").forEach((button) => {
    button.disabled = false;
  });
}

function setBusy(text) {
  busy = true;
  pasteRun.disabled = true;
  lxnsResults.querySelectorAll("button").forEach((button) => {
    button.disabled = true;
  });
  statusEl.textContent = text;
}

function analyzeText(text, filename, preferredSlot = null) {
  if (!text.trim()) {
    pendingSlot = null;
    statusEl.textContent = "没有读到文本。";
    setIdle();
    return;
  }
  if (!ready) {
    pendingSlot = null;
    statusEl.textContent = "引擎还没就绪。";
    setIdle();
    return;
  }
  pendingSlot = preferredSlot;
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

function typeLabel(type) {
  if (type === "dx") return "DX";
  if (type === "utage") return "宴会场";
  return "标准";
}

function diffButtonLabel(type, row) {
  if (type === "utage") {
    const kanji = (row.kanji || "宴").trim();
    return `${kanji} ${row.level || ""}`.trim();
  }
  const name = DIFF_LABELS[row.difficulty] || `难度${row.difficulty}`;
  return `${name} ${row.level || ""}`.trim();
}

function renderSearch() {
  const hits = searchSongs(lxnsQuery.value);
  if (!hits.length) {
    lxnsResults.hidden = true;
    lxnsResults.innerHTML = "";
    lxnsMeta.textContent = lxnsQuery.value.trim()
      ? "没有匹配到曲目。"
      : "输入曲名、别名、艺术家或 ID。";
    return;
  }
  lxnsMeta.textContent = `显示 ${hits.length} 首`;
  lxnsResults.hidden = false;
  lxnsResults.innerHTML = hits
    .map(({ song, aliases }) => {
      const diffs = difficultiesOf(song);
      const groups = [
        ["standard", diffs.standard],
        ["dx", diffs.dx],
        ["utage", diffs.utage],
      ].filter(([, rows]) => rows.length);
      const aliasHint = aliases.slice(0, 3).join(" / ");
      return `
        <article class="lxns-song">
          <div>
            <h3>${escapeHtml(song.title || "未命名")}</h3>
            <p class="fine">${escapeHtml(song.artist || "未知艺术家")} · #${song.id}${aliasHint ? ` · ${escapeHtml(aliasHint)}` : ""}</p>
          </div>
          ${groups
            .map(
              ([type, rows]) => `
            <div class="lxns-diffs">
              <span class="lxns-type">${typeLabel(type)}</span>
              ${rows
                .map(
                  (row) =>
                    `<button type="button" data-song="${song.id}" data-type="${type}" data-diff="${row.difficulty}"${busy ? " disabled" : ""}>${escapeHtml(diffButtonLabel(type, row))}</button>`,
                )
                .join("")}
            </div>`,
            )
            .join("")}
        </article>
      `;
    })
    .join("");
}

lxnsQuery.addEventListener("input", renderSearch);

lxnsResults.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-song]");
  if (!button || busy) return;
  if (!ready) {
    statusEl.textContent = "引擎还没就绪，请稍后再点难度。";
    return;
  }
  const songId = Number(button.dataset.song);
  const type = button.dataset.type;
  const diff = Number(button.dataset.diff);
  const chartId = chartAssetId(songId, type);
  const slot = slotFromLxnsDifficulty(diff);
  try {
    setBusy(`正在从落雪拉取 #${chartId}…`);
    const text = await fetchChart(chartId);
    analyzeText(text, `lxns-${chartId}.txt`, slot);
  } catch (err) {
    pendingSlot = null;
    statusEl.textContent = err && err.message ? err.message : String(err);
    setIdle();
  }
});

loadCatalog()
  .then((data) => {
    lxnsQuery.disabled = false;
    lxnsMeta.textContent = `已载入 ${data.songs.length} 首落雪曲目。输入曲名、别名、艺术家或 ID。`;
  })
  .catch((err) => {
    lxnsMeta.textContent = `落雪曲目列表加载失败：${err.message || err}`;
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
