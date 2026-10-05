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
- `chartRelativeScores`：使用曲库融合后的五维值，按本谱最大值等比放大，最强维度为 10.0；仅用于比较同一谱面的五维强弱。

两组分数共用曲库的固定锚点、权重、融合、封顶和中间舍入。设曲库融合后的内部五维值为 `F`（0–100），`M` 为五维最大值：

```text
scores[axis] = Math.round(F[axis]) / 10
chartRelativeScores[axis] = M > 0 ? Math.round(F[axis] / M * 100) / 10 : 0
```

单曲换算使用最后公共分数显示舍入前的 `F`，不从已显示的 `scores` 反推。它保留曲库内部五维的比例和强弱顺序；显示舍入可能产生并列，多个封顶维度继续并列。内部五维全零时返回五个零；微小的内部正值即使在曲库公共分数中显示为 0.0，仍参与单曲比例计算。

算法版本为 `dxtag-five-axis-v1.4`，单曲版本为 `chart-relative-library-v1`；原全曲库标尺和计算结果保持不变。

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

共享的 `chartRelativeRadar(fused)` 接收五个有限的 0–100 曲库融合值，返回单曲五维分数；输入不合法时抛出异常。它与 `CHART_RELATIVE_VERSION`、`CHART_RELATIVE_POLICY` 一起由公共入口导出，供 API 与网页复用。旧的 `chartRelativeBurden` 及 `ChartRelativeResult`、`ChartRelativeAxis`、`ChartRelativeBlock`、`ChartRelativeObservations` 已移除，调用方应改用共享换算函数与曲库计算依据。`scoreChart` 的返回对象仍只有上述四个字段。

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
