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
- `chartRelativeScores`：该谱面五维内部的相对值；最高维度为 10.0，其余按比例换算，仅用于比较同一谱面的五维强弱。

例如《TECHNOPOLIS 2085》MASTER：

```json
[
  {
    "title": "TECHNOPOLIS 2085",
    "difficulty": "MASTER",
    "scores": {
      "键盘": 8.5,
      "星星": 5.1,
      "技巧": 8.9,
      "体力": 4.2,
      "爆发": 5.6
    },
    "chartRelativeScores": {
      "键盘": 9.5,
      "星星": 5.7,
      "技巧": 10.0,
      "体力": 4.7,
      "爆发": 6.3
    }
  }
]
```

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

两个接口在计算失败时抛出异常。`scoreMaidata` 可传入错误回调以继续计算其他谱面：

```javascript
const charts = scoreMaidata(text, undefined, error => {
  console.error(error.difficulty, error.message);
});
```

## 开发

```powershell
npm run build
npm test
```

真实谱回归通过 `DXTAG_CHARTS_DIR` 指定谱面库根目录，保留 `版本目录/曲名/maidata.txt` 的目录结构；未提供对应谱面时跳过。

```powershell
$env:DXTAG_CHARTS_DIR = '.\charts'
npm test
```

算法与公式见 [技术文档](docs/ALGORITHM.md)。

## 许可

项目使用 [MIT License](LICENSE)。

Copyright (c) 2026 尘言
