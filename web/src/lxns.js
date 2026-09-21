const API = "/lxns-api";
const CHART = "/lxns-chart";
const RESULT_LIMIT = 20;
export const DIFF_LABELS = ["BASIC", "ADVANCED", "EXPERT", "MASTER", "Re:MASTER"];

let catalog = null;
let catalogPromise = null;

function unwrap(json) {
  if (!json || typeof json !== "object") return json;
  if (json.success === false) {
    throw new Error(json.message || "落雪接口失败");
  }
  if (json.data != null && json.songs == null && json.aliases == null) {
    return json.data;
  }
  return json;
}

function norm(text) {
  return String(text || "")
    .normalize("NFKC")
    .toLowerCase()
    .replace(/\s+/g, "");
}

export function chartAssetId(songId, type) {
  const id = Number(songId);
  if (!Number.isFinite(id)) throw new Error("无效曲目 ID");
  if (id >= 100000) return id;
  if (String(type).toLowerCase() === "dx") return id + 10000;
  return id;
}

export function slotFromLxnsDifficulty(levelIndex) {
  const n = Number(levelIndex);
  if (!Number.isFinite(n)) return null;
  return n + 2;
}

export function difficultiesOf(song) {
  const diffs = (song && song.difficulties) || {};
  return {
    standard: Array.isArray(diffs.standard) ? diffs.standard : [],
    dx: Array.isArray(diffs.dx) ? diffs.dx : [],
    utage: Array.isArray(diffs.utage) ? diffs.utage : [],
  };
}

export async function loadCatalog() {
  if (catalog) return catalog;
  if (catalogPromise) return catalogPromise;
  catalogPromise = (async () => {
    const [listRes, aliasRes] = await Promise.all([
      fetch(`${API}/song/list`),
      fetch(`${API}/alias/list`),
    ]);
    if (!listRes.ok) {
      throw new Error(`无法获取落雪曲目列表（${listRes.status}）`);
    }
    const list = unwrap(await listRes.json());
    const songs = Array.isArray(list.songs) ? list.songs : [];
    if (!songs.length) throw new Error("落雪曲目列表为空。");

    let aliases = [];
    if (aliasRes.ok) {
      const aliasJson = unwrap(await aliasRes.json());
      if (Array.isArray(aliasJson.aliases)) aliases = aliasJson.aliases;
      else if (Array.isArray(aliasJson)) aliases = aliasJson;
    }

    const aliasesById = new Map();
    for (const row of aliases) {
      const id = Number(row.song_id);
      if (!Number.isFinite(id)) continue;
      aliasesById.set(id, Array.isArray(row.aliases) ? row.aliases : []);
    }

    catalog = { songs, aliasesById };
    return catalog;
  })().catch((err) => {
    catalogPromise = null;
    throw err;
  });
  return catalogPromise;
}

export function searchSongs(query, limit = RESULT_LIMIT) {
  if (!catalog) return [];
  const raw = String(query || "").trim();
  if (!raw) return [];
  const qn = norm(raw);
  const qid = /^\d+$/.test(raw) ? Number(raw) : null;
  const scored = [];
  for (const song of catalog.songs) {
    if (song.disabled) continue;
    const aliases = catalog.aliasesById.get(song.id) || [];
    const titleN = norm(song.title);
    const artistN = norm(song.artist);
    const aliasHit = aliases.find((alias) => norm(alias).includes(qn));
    let score = Infinity;
    if (qid != null && song.id === qid) score = 0;
    else if (titleN === qn) score = 1;
    else if (titleN.startsWith(qn)) score = 2;
    else if (titleN.includes(qn)) score = 3;
    else if (aliasHit && norm(aliasHit) === qn) score = 4;
    else if (aliasHit) score = 5;
    else if (artistN.includes(qn)) score = 6;
    else if (qid != null && String(song.id).startsWith(String(qid))) score = 7;
    if (score === Infinity) continue;
    scored.push({ score, song, aliases });
  }
  scored.sort((a, b) => a.score - b.score || a.song.id - b.song.id);
  return scored.slice(0, limit);
}

export async function fetchChart(chartId) {
  const res = await fetch(`${CHART}/${chartId}.txt`);
  if (res.status === 404) {
    throw Object.assign(new Error("落雪没有这份抄谱（常见于未收录或宴会场）。仍可上传 maidata。"), {
      code: "not_found",
    });
  }
  if (!res.ok) throw new Error(`拉取抄谱失败（${res.status}）`);
  const text = await res.text();
  const trimmed = text.trim();
  if (!trimmed || trimmed.startsWith("<")) {
    throw Object.assign(new Error("落雪没有这份抄谱（常见于未收录或宴会场）。仍可上传 maidata。"), {
      code: "not_found",
    });
  }
  return text;
}
