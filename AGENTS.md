# DXTag agents

面向后续代理的仓库约定。默认始终遵守。

## 提交

不要执行 `git commit`、`git push`、amend、rebase，也不要改 git config。
每次做完只输出一条可复制的提交命令（含建议的 commit message）。用户自己决定是否提交。

## 发布面

本仓库是本地工具，不要加回 GitHub Actions、GitHub Pages、workflow、`GITHUB_PAGES_BASE` 或仓库名作为 Vite `base`。

网页入口：`cd web && npm install && npm run dev` → `http://localhost:4173/`。
`npm run preview` 只服务已有 `web/dist`；没有就先 `npm run build`。
`web/scripts/copy-engine.mjs` 必须在本地网页启动前把引擎和 `data/` 快照拷进 `web/public/`。

## 实质功能

保留这些，不要为了「干净」删掉：

- Python 分析器：`maimai_analyzer.py`、`catalog.py`、`community.py`、`calibrate.py`
- 本地网页：`web/`（Vite + Pyodide worker，谱面不上传）
- 命令行 `--open` 生成本地 HTML（`run.ps1`）
- `data/` 公开统计快照；`tools/` 拉数与建库
- `test_*.py` 与 `regression/` 结构回归

不要提交 `corpus/`、`maisquared/`、音频、抄谱原文、密钥。MIT 只覆盖本仓库代码。

## 产品边界

- 水 / 诈称只来自高置信水鱼 `fit_diff` vs 国服官标；禁止用 DXRating 无审核标签。
- 曲名+物量对不上官谱时仍做结构分析，但不用拟合去贴标签。
- 雷达是固定 0–100 饱和强度，不是命中率或技能概率；错位是时空结构，不是真实手序/碰撞/遮挡。
- Python 3.10+，分析器只用标准库。改 `MODEL_FEATURES` / `VERSION` / `SCHEMA_VERSION` 必须拒绝旧模型。
- 用户可见文案用中文；代码标识与提交说明可用英文。

## 改完怎么验

```bash
python3 -m unittest -v test_analyzer test_misalignment test_catalog test_community
```

动过网页时：`cd web && npm run dev`，用浏览器走上传/粘贴分析，不要只截一张静态图。
结构规则变更时同步 `test_misalignment.py` / `regression/`，不要用曲名或固定 ID 当检测条件。
