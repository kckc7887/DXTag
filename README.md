# DXTag

读取 `maidata.txt`，输出曲名、难度和基于全曲库固定标尺的五维分数。评分包含键盘、星星、技巧、体力、爆发，范围为 **0.0–10.0**，保留一位小数。

## 安装与运行

运行环境：Node.js 22 或更新版本。

从 [GitHub Releases](https://github.com/kckc7887/DXTag/releases) 下载 `dxtag-five-axis-1.0.0.tgz`，在下载目录安装：

```powershell
npm install -g ./dxtag-five-axis-1.0.0.tgz
dxtag-score "maidata.txt"
```

默认计算文件中的全部普通难度。使用 `-d` 选择一张谱面：

```powershell
dxtag-score "maidata.txt" -d master
dxtag-score "maidata.txt" -d 5 > scores.json
```

也可以直接使用 npx：

```powershell
npx --package=./dxtag-five-axis-1.0.0.tgz dxtag-score "maidata.txt" -d master
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

输出始终是 JSON 数组，每张谱面包含三个字段：

- `title`：maidata 的 `&title`；缺省时为空字符串。
- `difficulty`：`BASIC`、`ADVANCED`、`EXPERT`、`MASTER` 或 `Re:MASTER`。
- `scores`：以全曲库固定标尺计算的五项数值，可跨谱面比较。
算法版本为 `dxtag-five-axis-v1.1`。

计算失败的谱面从结果中略过，原因写入标准错误。全部失败时输出 `[]`。

| 退出码 | 含义 |
| --- | --- |
| `0` | 全部成功 |
| `1` | 部分或全部谱面计算失败 |
| `2` | 参数、文件读取／编码或普通谱槽位选择错误 |

## JavaScript 接口

将下载的安装包放在项目目录，然后安装：

```powershell
npm install ./dxtag-five-axis-1.0.0.tgz
```

包提供 ESM 接口和 TypeScript 类型声明。

```javascript
import {readFileSync} from 'node:fs';
import {scoreChart, scoreMaidata} from 'dxtag-five-axis';

const text = readFileSync('./maidata.txt', 'utf8');
const chart = scoreChart(text, 5);  // {title, difficulty, scores}
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
npm ci
npm run build
node dist/cli.mjs "maidata.txt"
```

算法与公式见 [技术文档](docs/ALGORITHM.md)。

## 发布

生成本地 npm 安装包：

```powershell
npm ci
npm pack --pack-destination dist
```

打包会通过 `prepack` 自动生成 JavaScript 与类型声明，输出 `dist/dxtag-five-axis-1.0.0.tgz`。将该文件作为对应版本的 GitHub Release 附件发布即可，无需 npm 登录。包设置为 `private`，不发布到 npm registry，但支持从本地 `.tgz` 安装。

发布内容仅包含编译产物、算法文档、README 和许可证，标尺数据已内嵌在 JavaScript 中。发布新版本前需同步更新 `package.json`、`package-lock.json` 和文档中的版本号。

## 许可

项目使用 [MIT License](LICENSE)。

Copyright (c) 2026 尘言
