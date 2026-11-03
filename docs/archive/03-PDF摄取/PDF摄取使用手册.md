# PDF 双轨摄取使用手册

> 配套设计文档：`PDF摄取方案与安全审计.md`
> 配套代码：`ingest.py`（摄取主程序）、`ocr_bench.py`（参数调优基准工具）
> 适用环境：macOS Apple Silicon（arm64，已实测于 M5 Max）、Python 3.13 隔离 venv
> 最后更新：2026-10-19

---

## 0. 这东西是干什么的

把 PDF 变成**带 YAML frontmatter 的规范 Markdown**，供下游知识库（Obsidian Smart Connections / 其他 RAG）检索。

它解决两类 PDF：

| 类型 | 特征 | 走哪条轨道 | 怎么处理 |
|---|---|---|---|
| **文本型** | 自带可选中文字层（正常导出的报告、论文） | 文本轨道 | PyMuPDF 直接抽取，**秒级** |
| **扫描型** | 本质是图片（影印书、扫描合同） | OCR 轨道 | 本机原生 PaddleOCR 识别，**较慢** |

脚本会自动判定走哪条轨，你通常不需要管。

**设计原则**：只负责"PDF → Markdown"，不做任何检索/嵌入/问答——下游爱用哪个知识库都行，吃的是同一份 `processed/*.md`。

---

## 1. 环境前提（本机已就绪）

| 项 | 值 | 说明 |
|---|---|---|
| Python | 3.13（托管版） | 隔离 venv，不污染系统 |
| venv 解释器 | `<HOME>/.workbuddy/binaries/python/envs/default/bin/python` | 所有命令的前缀 |
| 核心依赖 | `pymupdf==1.28.2`、`paddlepaddle==3.3.1`、`paddleocr==3.7.0`、`paddlex==3.7.2` | 见 `requirements-pdf.txt` |
| 外部依赖 | **无** brew / **无** Docker | 纯 pip 进 venv，零系统级改动 |

> 若需要在另一台机器重建：`<HOME>/.workbuddy/binaries/python/envs/default/bin/pip install -r requirements-pdf.txt`

---

## 2. 目录约定

```
<DEPLOY_DIR>/
├── ingest.py                      # 摄取主程序
├── ocr_bench.py                   # OCR 参数调优基准（高级，可选）
├── requirements-pdf.txt           # 依赖锁定
├── .gitignore                     # raw/ 与 searchable/ 不入 Git
└── 02_data/
    ├── raw/                       # 【放这里】原始 PDF（不入 Git）
    ├── processed/                 # 【产物】规范 Markdown（可入 vault / Git）
    │   └── searchable/            # 【产物】可搜索 PDF（不入 Git）
    └── ...
```

**关键约定**：
- 把要处理的 PDF 丢进 `02_data/raw/`。
- 产物是 `02_data/processed/<原名>.md`。
- 原始 PDF 与可搜索 PDF **不进 Git / 不进 Obsidian vault 同步**（避免二进制膨胀），只有 `processed/*.md` 文本适合同步。

---

## 3. 快速上手（3 步）

```bash
# ① 进入项目目录
cd "<DEPLOY_DIR>"

# ② 把 PDF 放进 raw（或直接指定任意路径）
cp 某文件.pdf 02_data/raw/

# ③ 跑摄取（自动判定文本轨 / OCR 轨）
<HOME>/.workbuddy/binaries/python/envs/default/bin/python ingest.py --file 02_data/raw/某文件.pdf
```

跑完后会看到类似日志：

```
[16:05:22] 待处理 1 个 PDF
[16:05:22] (1/1) 处理 某文件.pdf
[16:05:22] 某文件.pdf: 30 页, 采样20页 平均360.9字符, 有文字页占比0.73 -> 轨道: text
[16:05:23]   产出 某文件.md (11236 字符)
[16:05:23] ========================================================
[16:05:23] OK 某文件.pdf: 轨道=text, 30/30 页, 11236 字符, 1.0s
```

结果在 `02_data/processed/某文件.md`。

---

## 4. 完整命令与参数

### 4.1 两种入口

```bash
# 单个文件
python ingest.py --file <路径.pdf>

# 整个目录（默认 02_data/raw，递归找 *.pdf）
python ingest.py --dir 02_data/raw
```

不传 `--file` 也不传 `--dir` 时，**默认处理 `02_data/raw/`** 下的全部 PDF。

### 4.2 参数一览

| 参数 | 默认值 | 作用 | 何时用 |
|---|---|---|---|
| `--file <路径>` | 无 | 指定单个 PDF | 处理某个具体文件 |
| `--dir <目录>` | `02_data/raw` | 批量处理目录下全部 PDF | 一次性消化整批 |
| `--out <目录>` | `02_data/processed` | Markdown 输出目录 | 想输出到别处 |
| `--max-pages <N>` | 全部 | 只处理前 N 页 | **测试/试跑**大扫描书时先用它探一下 |
| `--ocr-quality` | `balanced` | OCR 档位：`fast`/`balanced`/`quality` | 见第 5 节 |
| `--ocr-dpi <整数>` | 随档位(150/200) | 覆盖渲染 DPI | 极致画质或极致速度微调 |
| `--searchable` | 关 | 额外产出可搜索 PDF | 想要一个"可 Ctrl+F 检索"的 PDF 副本 |
| `--force` | 关 | 覆盖已存在的同名 md | 重跑/换档位时 |

### 4.3 常用组合示例

```bash
# 整目录批量（日常最常用）
python ingest.py --dir 02_data/raw

# 先探一本 400 页扫描书的前 10 页，确认效果（不花一小时）
python ingest.py --file 02_data/raw/大书.pdf --max-pages 10

# 清晰印刷体想更快 → fast 档
python ingest.py --file 02_data/raw/大书.pdf --ocr-quality fast

# 既要文字层 md，又要可搜索 PDF 副本
python ingest.py --file 02_data/raw/大书.pdf --searchable

# 换档位重跑，必须加 --force 否则跳过已存在 md
python ingest.py --file 02_data/raw/大书.pdf --ocr-quality quality --force
```

---

## 5. OCR 质量档位怎么选

三个档位在**识别质量几乎无损**的前提下，时间和内存差异巨大（实测于 M5 Max，侯捷扫描书，414 页）：

| 档位 | 模型 | DPI | 速度 | 峰值内存 | 414 页全书耗时 | 适用 |
|---|---|---|---|---|---|---|
| `fast` | PP-OCRv6_tiny | 150 | ~1.35s/页 | ~1.8 GB | **约 9.5 分钟** | 清晰印刷体、批量书稿（推荐起步） |
| `balanced`（默认） | PP-OCRv6_small | 150 | ~3.6s/页 | ~2.1 GB | 约 25 分钟 | 通用、质量速度均衡 |
| `quality` | PP-OCRv6_medium | 200 | ~14s/页 | ~8.9 GB | 约 97 分钟 | 小字号、劣质扫描、高保真需求 |

**选择指引**：
- 不确定 → 先用 `balanced`（默认）。
- 大批量清晰书稿 → `fast`（省 2.7 倍时间，肉眼看不出质量差异）。
- 古书/复印件/字号极小 → `quality`。

> **调优实测结论**：模型降档是主导杠杆（medium→tiny 提速 10 倍、内存降至 1/5）；DPI 200→150 是有效次级杠杆；线程数与检测边长上限在 paddlex 3.7 下**完全无效**，已从脚本移除，无需再调。

---

## 6. 典型工作流

### 场景 A：日常批量入库
把 PDF 全丢进 `02_data/raw/`，然后一句搞定：
```bash
python ingest.py --dir 02_data/raw
```

### 场景 B：首次接入一本大扫描书（防踩坑）
先用 `--max-pages 10` 试跑，确认识别质量与轨道判定正确，再全书跑：
```bash
python ingest.py --file 02_data/raw/大书.pdf --max-pages 10        # 探路
python ingest.py --file 02_data/raw/大书.pdf --ocr-quality fast    # 全书
```

### 场景 C：想要可检索的 PDF 副本
```bash
python ingest.py --file 02_data/raw/大书.pdf --searchable
# 产出：02_data/processed/大书.md  +  02_data/processed/searchable/大书.searchable.pdf
```

---

## 7. 输出产物解析

### 7.1 Markdown 结构
每个产物是带 frontmatter 的 Markdown：

```markdown
---
source_file: 大书.pdf
source_path: <HOME>/.../02_data/raw/大书.pdf
sha256: 3f2a...（溯源/去重用）
pages: 414
processed_pages: 414
track: ocr            # text 或 ocr
ocr_dpi: 150          # 仅 OCR 轨有此行
ingested_at: 2026-10-19T16:05:22+08:00
---

# 大书

## Page 1

（该页识别/抽取出的文本）

## Page 2
...
```

- `## Page N` 分节便于下游按页分块与溯源。
- `track` 标明走的是哪条轨（text 直抽 / ocr 识别）。

### 7.2 可搜索 PDF
`--searchable` 会在原 PDF 上叠加**不可见但可选中**的文字层，另存为新文件。适合"想在 PDF 阅读器里 Ctrl+F"的场景。主检索数据以 `*.md` 为准。

---

## 8. 三种触发方式（架构预留）

`ingest.py` 的命令行入口对三种触发器通用：

| 触发器 | 形态 | 状态 |
|---|---|---|
| **手动批量** | 你直接跑命令 | ✅ 已就绪 |
| **launchd 目录监听** | 放 `raw/` 自动摄取，常驻 watchdog（待实现） | 预留接口 |
| **Hermes 晨报集成** | 作为采集环节自动消化 PDF（依赖 Hermes 安装） | 预留接口 |

手动之外的触发器，调用方只需复用同一命令行（`ingest.py --dir 02_data/raw`），StdOut 已带时间戳、适合被 launchd 的 `StandardOutPath` 接管。

---

## 9. 排错与已知问题

| 现象 | 原因 / 说明 | 处理 |
|---|---|---|
| 首次运行某档位很慢 | PaddleOCR 首次会下载模型权重（缓存在 `~/.paddleocr`） | 等一次即可，之后秒级启动 |
| 报 `No engine bindings registered` | 写了 `PP-OCRv6_mobile_det` | **v6 系列无 mobile**，档位是 medium/small/tiny，改用三档之一 |
| 机器卡死/内存爆 | 三个预处理模型全开（默认）会吃 40GB+ | 脚本已**默认全关**，正常不会触发；勿手动开启 |
| 加密/损坏 PDF | 无法打开 | 脚本记录错误并跳过，不中断整批 |
| 已存在 md 被跳过 | 防重复 | 加 `--force` 覆盖 |
| 可搜索 PDF 个别字乱码 | 文字层坐标近似换算导致（如「排版ζ；术：」） | 仅影响可搜索层，**主文本 md 不受影响**；如需修复坐标映射可单独处理 |

**arm64 专属注意**：
- MKLDNN 崩溃坑是 x86 专属，Apple Silicon 不受影响，可放心用 Paddle 3.x。
- 官方 Docker 镜像**不支持 Apple Silicon**，本方案走原生 pip，正好规避。

---

## 10. 实测性能基线（M5 Max · 2026-10-16 部署测试）

| 样本 | 页数 | 轨道 | 耗时 | 字符数 |
|---|---|---|---|---|
| 智能驾驶2023年度报告 | 30 | text | ~1s | 11,236 |
| 侯捷《Word排版艺术》 | 414 | ocr (fast) | 570s（9.5min） | 335,220 |

OCR 单页速度：`fast`≈1.35s、`balanced`≈3.6s、`quality`≈14s（详见第 5 节表）。

---

## 11. 安全与合规要点

- **本地零出境**：OCR 全程进程内调用，文字不上任何云端；L3 高敏 PDF（合同/财务/健康）可本地安全处理。
- **不入公网**：无 HTTP OCR 服务，不存在"误暴露 0.0.0.0"风险面。
- **二进制隔离**：原始 PDF 与可搜索 PDF 经 `.gitignore` 排除，不经 Git / vault 同步外泄；只有 `processed/*.md` 文本出同步。
- **供应链**：依赖版本已钉死于 `requirements-pdf.txt`（官方 wheel，校验来源）。

---

## 附：一句话速记

> **丢进 `raw/` → 跑 `python ingest.py --dir 02_data/raw` → 拿 `processed/*.md`。扫描书慢就用 `--ocr-quality fast`，想可检索就加 `--searchable`。**
