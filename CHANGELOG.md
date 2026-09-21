# DXTag changelog

## 1.2.0

- 浏览器内上传 maidata.txt：本地 Vite + Pyodide，谱面不离开本机。
- 曲库匹配要求物量接近公开统计，才使用水鱼拟合定数。
- 拟合必须过样本数 / 标准差门槛；水/诈称另需更大样本和与官标的差距。
- 日→中术语表；Gamerch 解说只作成品对照。
- 同等级雷达百分位（有校准语料时）与 0–100 饱和强度分开显示。
- JSON `schema_version` 3；模型 `analyzer_version` 1.2.0，旧模型拒绝加载。

v1.1 错位结构修复见 `CHANGELOG.v1.1.md`。
