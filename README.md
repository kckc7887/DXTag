# DXTag

读取 `maidata.txt`，输出曲名、难度和两组五维分数：相对于全曲库，以及相对于该谱面自身。评分包含键盘、星星、技巧、体力、爆发，范围为 **0.0–10.0**，保留一位小数。

## 安装与运行

运行环境：Node.js 22 或更新版本。

```powershell
npm ci
npm run build
node dist/cli.mjs "maidata.txt"
```

默认计算文件中的全部普通难度。使用 `-d` 选择一张谱面：

```powershell
node dist/cli.mjs "maidata.txt" -d master
node dist/cli.mjs "maidata.txt" -d 5 > scores.json
npm run --silent score -- "maidata.txt" -d master
```

| Simai 槽位 | 难度参数 |
| --- | --- |
| `inote_2` | `basic` 或 `2` |
| `inote_3` | `advanced` 或 `3` |
| `inote_4` | `expert` 或 `4` |
| `inote_5` | `master` 或 `5` |
| `inote_6` | `remaster`、`re:master` 或 `6` |

参数不区分大小写。`--json` 与默认输出相同，`--help` 显示帮助。

输入编码支持 UTF-8（含 BOM）及带 BOM 的 UTF-16 LE／BE。

## 输出

输出始终是 JSON 数组，每张谱面包含四个字段：

- `title`：maidata 的 `&title`；缺省时为空字符串。
- `difficulty`：`BASIC`、`ADVANCED`、`EXPERT`、`MASTER` 或 `Re:MASTER`。
- `scores`：以全曲库固定标尺计算的五项数值，可跨谱面比较。
- `chartRelativeScores`：沿用曲库锚点和权重，将各观察量被封顶截去的超标部分补回，再按本谱最大值换算；最强维度为 10.0，仅用于比较同一谱面的五维强弱。

曲库分数的固定锚点、权重、融合、封顶和舍入保持原样。单曲分支同时保留每个观察量的封顶前归一值 `n = raw / anchor × 100`，以原融合权重补回 `max(0, n − 100)`。设曲库融合值为 `F`（0–100），本轴加权超标量为 `E`：

```text
scores[axis] = Math.round(F[axis]) / 10
U[axis] = F[axis] + E[axis]
M = max(U 的五维)
chartRelativeScores[axis] = M > 0 ? Math.round(U[axis] / M * 100) / 10 : 0
```

基础五维和星星主轴的超标量权重为 1；Touch、锁手、星星技巧、节奏和星星突增沿用各自的原融合权重。超标量和单曲原值 `U` 不封顶、不提前舍入。这样多个曲库维度即使都显示为 10.0，仍能按其超标程度区分；原值相等或显示舍入后相同的维度仍可并列。

单曲换算不从已显示的 `scores` 反推，也不把大于 100 的输入直接代入原乘法融合公式。没有超标量时沿用曲库内部五维的比例；`U` 全零时返回五个零。原始观测、封顶量和分数的完整关系见算法文档。

算法版本为 `dxtag-five-axis-v1.5`，单曲版本为 `chart-relative-library-v2`；原全曲库标尺和计算结果保持不变。

计算失败的谱面从结果中略过，原因写入标准错误。全部失败时输出 `[]`。

| 退出码 | 含义 |
| --- | --- |
| `0` | 全部成功 |
| `1` | 部分或全部谱面计算失败 |
| `2` | 参数、文件读取／编码或普通谱槽位选择错误 |

## JavaScript 接口

```javascript
import {readFileSync} from 'node:fs';
import {scoreChart, scoreMaidata} from './dist/index.mjs';

const text = readFileSync('./maidata.txt', 'utf8');
const chart = scoreChart(text, 5);  // {title, difficulty, scores, chartRelativeScores}
const charts = scoreMaidata(text); // 同一结构的数组
```

公共入口导出 `normalizeLegacyRadar(features, anchors)` 和 `projectLibraryRadar(baselineRaw, starRaw, supportRaw)`：前者返回封顶前的基础归一值，后者接收同为 0–100 标尺单位但允许超出 100 的原始归一值，统一返回曲库融合值 `fused`、加权超标量 `excess`、单曲原值 `chartRelativeSource` 和 `chartRelativeScores`，并保留曲库归一明细。API 和网页共用该入口。

`chartRelativeRadar(source)` 只负责将五个有限非负的单曲原值映射为 0–10；调用方应传入 `projectLibraryRadar` 的 `chartRelativeSource`，而不是已封顶的 `fused`。共享版本和口径由 `CHART_RELATIVE_VERSION`、`CHART_RELATIVE_POLICY` 标识。`scoreChart` 的返回对象仍只有上述四个字段。

两个接口在计算失败时抛出异常。`scoreMaidata` 可传入错误回调以继续计算其他谱面：

```javascript
const charts = scoreMaidata(text, undefined, error => {
  console.error(error.difficulty, error.message);
});
```

## 开发

```powershell
npm run build
```

算法与公式见 [技术文档](docs/ALGORITHM.md)。

## 许可

项目使用 [MIT License](LICENSE)。

Copyright (c) 2026 尘言
