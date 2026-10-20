# DXTag

读取 `maidata.txt`，计算键盘、星星、技巧、体力、爆发五维分数。各项使用全曲库固定标尺，范围为 **0.0–10.0**，保留一位小数。

版本：**1.0.0** · 运行环境：**Node.js 22 或更新版本**

## 安装

从源码安装命令行工具：

```powershell
git clone https://github.com/kckc7887/DXTag.git
cd DXTag
npm ci
npm run build
npm install -g .
```

## 命令行

```powershell
dxtag-score "maidata.txt"
dxtag-score "maidata.txt" --all
dxtag-score "maidata.txt" -d 5
dxtag-score "maidata.txt" -d master
dxtag-score "maidata.txt" -d 3,5,8
dxtag-score "maidata.txt" -d expert -d 5,8 > scores.json
```

| 参数 | 含义 |
| --- | --- |
| `<maidata.txt>` | 一个 maidata 文件的路径 |
| `-d`、`--difficulty` | 单个槽位或逗号分隔的槽位列表，支持重复传入 |
| `--all` | 文件中全部正文非空的槽位，与 `-d` 互斥 |
| `--json` | JSON 输出，与默认输出一致 |
| `-h`、`--help` | 帮助 |

省略选择参数时计算全部槽位。选择结果按编号去重、升序排列。

槽位字段采用 `&inote_N=`，`N` 为十进制正安全整数，范围为 `1`–`9007199254740991`，首位为 `1`–`9`。以下槽位同时提供名称别名，名称匹配忽略大小写。

| 槽位 | 名称参数 | 结果名称 |
| --- | --- | --- |
| 1 | `easy` | `EASY` |
| 2 | `basic` | `BASIC` |
| 3 | `advanced` | `ADVANCED` |
| 4 | `expert` | `EXPERT` |
| 5 | `master` | `MASTER` |
| 6 | `remaster`、`re:master` | `Re:MASTER` |
| 7 | `utage` | `UTAGE` |
| 其他正安全整数 | 数字编号 | `inote_N` |

文件编码支持 UTF-8、带 BOM 的 UTF-8，以及带 BOM 的 UTF-16 LE／BE。

## 结果与错误

CLI 向标准输出写入 JSON 数组，五维数值固定显示一位小数。每项包含以下字段：

| 字段 | 类型 | 内容 |
| --- | --- | --- |
| `title` | `string` | maidata 的 `&title`，缺省为空字符串 |
| `slot` | `number` | `inote_N` 的槽位编号 |
| `difficulty` | `string` | 槽位对应的结果名称 |
| `scores` | `AxisScores` | 键盘、星星、技巧、体力、爆发五项分数 |

逐谱解析或计算失败时，CLI 将槽位和错误写入标准错误，并继续处理其余选择项。结果数组包含成功项；全部计算失败时输出 `[]`。

| 退出码 | 含义 |
| --- | --- |
| 0 | 全部成功 |
| 1 | 部分或全部谱面解析、计算失败 |
| 2 | 参数、文件读取、编码或槽位选择错误 |

槽位选择错误包括非法编号、空选择、缺失槽位和指定槽位正文为空。选择检查在逐谱计算前完成。

## JavaScript API

完成上述源码构建后，在应用项目目录安装本地 DXTag 仓库。以下命令适用于应用项目与 DXTag 目录同级的布局：

```powershell
npm install ../DXTag
```

包提供 ESM 接口及 TypeScript 类型声明。API 接收已解码的完整 maidata 文本，所有函数同步返回。

```javascript
import {readFileSync} from 'node:fs';
import {listDifficulties, scoreChart, scoreMaidata} from 'dxtag';

const text = readFileSync('./maidata.txt', 'utf8');
const slots = listDifficulties(text);
const chart = scoreChart(text, 5);
const selected = scoreMaidata(text, [3, 5, 8]);
const all = scoreMaidata(text, 'all');
```

| 函数 | 返回值 |
| --- | --- |
| `listDifficulties(text)` | 正文非空的槽位编号数组，按编号升序排列 |
| `scoreChart(text, difficulty)` | 指定槽位的 `ChartScores` |
| `scoreMaidata(text, selection?, onError?)` | 选择槽位的 `ScoreResult` |

`selection` 接受一个数字编号、只读编号数组或 `'all'`；省略时计算全部。`scoreChart` 的错误直接抛出。`scoreMaidata` 的选择错误直接抛出，逐谱错误由 `onError` 接收；省略回调时遇到首个计算错误即抛出。

```javascript
const results = scoreMaidata(text, 'all', error => {
  console.error(error.slot, error.difficulty, error.message);
});
```

| 导出 | 定义 |
| --- | --- |
| `AXES` | 五轴名称与顺序 |
| `DIFFICULTIES` | 1–7 槽位的显示名称 |
| `ALGORITHM_VERSION`、`SCALE_VERSION` | 项目统一版本，来源为 `package.json` 的 `version` |
| `Difficulty` | 数字槽位类型，运行时要求正安全整数 |
| `DifficultySelection` | 单个 `Difficulty`、只读编号数组或 `'all'` |
| `AxisScores` | 以五轴名称为键、分数为值的对象 |
| `ChartScores` | `{title, slot, difficulty, scores}` |
| `ScoreResult` | `ChartScores[]` |
| `ScoreError` | `{slot, difficulty, message}` |

## 算法

数据结构、时间坐标、公式和参数见 [算法文档](docs/ALGORITHM.md)。

## 许可证

[MIT License](LICENSE) · Copyright (c) 2026 尘言
