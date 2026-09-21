# DXTag

在浏览器或命令行里分析舞萌 `maidata.txt`：结构难点、雷达和高置信难度对照。谱面只在本机解析。

## 它会给出什么

- 12 轴结构雷达（密度、爆发、交互、纵连、扫键/转圈、位移、节奏、滑条、错位、一笔画、协同、触摸）
- 难点时间段与源码行号（拍划 / 海底捞 / 错位 / Wifi 等）
- 预估定数：有足够高置信样本时使用岭回归去贴近**国服水鱼拟合定数**；否则回退启发式并标明置信度
- 国服官标 + 高置信拟合；日服内部定数并排显示
- **水 / 诈称只来自「高置信拟合 vs 国服官标」**，不用 DXRating 无审核标签
- 若抄谱物量能对上官谱，附加日服社群解说对照（Gamerch 等），术语译成中国玩家常用说法

社区玩家抄谱和官方谱面不一定完全一致。对不上物量的谱面仍然做结构分析，但**不会**用拟合定数去贴标签。

## 网页（本地）

```bash
python3 -m unittest -v test_analyzer test_misalignment test_catalog test_community
cd web && npm install && npm run dev
```

开发服务器默认 `http://localhost:4173/`。`npm run dev` 会先把 Python 引擎和 `data/` 快照拷进 `web/public/`。

生产构建预览（可选）：

```bash
cd web && npm run build && npm run preview
```

`vite preview` 只服务已构建的 `web/dist`，没有 `dist` 时先 `npm run build`。

## 命令行

Python 3.10+，只有标准库。

```bash
python3 maimai_analyzer.py path/to/maidata.txt --open
python3 maimai_analyzer.py path/to/maidata.txt --catalog data/catalog.json --percentiles data/percentiles.json --model data/model.json
```

用本地已知定数再训练（不会联网）：

```bash
python3 calibrate.py calibration.csv --out data/model.json
```

## 离线曲库快照

公开统计可以重新拉取，**不要把 maisquared 谱面原文提交进仓库**：

```bash
python3 tools/fetch_public.py
# 可选：只下载 maidata.txt
python3 tools/ingest_maisquared.py
python3 tools/build_catalog.py
```

`data/catalog.json` 是水鱼曲库 + 拟合统计 + 日服内部定数的压缩快照。`data/model.json` 只有在高置信抄谱样本足够、且交叉验证优于启发式时才会作为默认模型。

## 许可

代码为 MIT（见 `LICENSE`）。谱面、歌曲、Gamerch 条目和公开统计仍属于各自权利人；本仓库不重新分发音频或抄谱原文。
