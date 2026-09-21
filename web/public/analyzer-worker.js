/* global loadPyodide */
importScripts("https://cdn.jsdelivr.net/pyodide/v0.27.4/full/pyodide.js");

let pyodide = null;
let base = "/";

async function readPublic(path) {
  const url = new URL(String(path).replace(/^\//, ""), self.location.origin + base);
  const res = await fetch(url);
  if (!res.ok) return null;
  return await res.text();
}

async function boot() {
  postMessage({ type: "status", text: "正在加载 Python 运行时…" });
  pyodide = await loadPyodide({ indexURL: "https://cdn.jsdelivr.net/pyodide/v0.27.4/full/" });
  for (const name of ["maimai_analyzer.py", "catalog.py", "community.py"]) {
    const src = await readPublic(`engine/${name}`);
    if (!src) throw new Error(`缺少 engine/${name}`);
    pyodide.FS.writeFile(name, src);
  }
  pyodide.FS.writeFile("catalog.json", (await readPublic("data/catalog.json")) || "{}");
  pyodide.FS.writeFile("percentiles.json", (await readPublic("data/percentiles.json")) || "{}");
  pyodide.FS.writeFile("model.json", (await readPublic("data/model.json")) || "null");
  postMessage({ type: "status", text: "正在载入分析器…" });
  await pyodide.runPythonAsync(`
import json
from maimai_analyzer import analyze_maidata, radar_svg, density_svg

def _load(path):
    raw = open(path, encoding="utf-8").read()
    if not raw or raw == "null":
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    return data

CATALOG = _load("catalog.json") or None
PERCENTILES = _load("percentiles.json") or None
MODEL = _load("model.json")
if isinstance(MODEL, dict) and MODEL.get("prefer_over_heuristic") is False:
    MODEL = None

def analyze_text(text, origin):
    doc = analyze_maidata(text, origin=origin, model=MODEL, catalog=CATALOG, percentiles=PERCENTILES)
    svgs = {}
    for report in doc["reports"]:
        svgs[str(report["difficulty"])] = {"radar": radar_svg(report), "density": density_svg(report)}
    return json.dumps({"document": doc, "svgs": svgs}, ensure_ascii=False)
`);
  postMessage({ type: "ready" });
}

self.onmessage = async (event) => {
  const msg = event.data || {};
  try {
    if (msg.type === "init") {
      base = msg.base || "/";
      await boot();
      return;
    }
    if (msg.type === "analyze") {
      if (!pyodide) await boot();
      postMessage({ type: "status", text: "正在解析谱面…" });
      pyodide.globals.set("INPUT_TEXT", msg.text);
      pyodide.globals.set("INPUT_ORIGIN", msg.filename || "<uploaded>");
      const raw = await pyodide.runPythonAsync("analyze_text(INPUT_TEXT, INPUT_ORIGIN)");
      postMessage({ type: "result", ...JSON.parse(raw) });
    }
  } catch (err) {
    postMessage({ type: "error", message: String(err && err.stack ? err.stack : err) });
  }
};
