# 方案文档归档索引（脱敏镜像）

> 归档日期：2026-11-03
> 归档范围：工作区根目录落盘的全部「方案 / 设计 / 总结 / 手册 / 架构图」类文档
> 目的：清理根目录 clutter，按主题分类沉淀，便于跨会话追溯
> 发布说明：本 `docs/archive/` 为本地归档的**脱敏镜像**——个人绝对路径、`192.168` 私有 IP、`~/...` 状态目录、进程 PID 等已泛化为占位符后随仓库公开发布；本地原版含机器专属信息，仅留本地、不入仓库。

## 归档结构

```
归档/
├── 01-模型与MTPLX栈/        本地大模型服务栈（MTPLX）与 OpenWebUI 接入
│   ├── MTPLX本地AI实验室栈文档.md
│   ├── MTPLX模型升级总结_27B到35B-A3B.md   ← 最近主线：27B→Qwen3.6-35B-A3B(MoE)
│   ├── OpenWebUI容器访问MTPLX方案.md
│   ├── OpenWebUI-OrbStack部署命令.md
│   └── 7x24运行实施手册.md
├── 02-AI实验室部署/         整体实验室建设、设计、安全审计、硬件配置
│   ├── 个人AI实验室建设与部署方案.md
│   ├── AI实验室部署设计与安全审计.md
│   ├── AI实验室部署目标架构图.html
│   └── 当前电脑功能与配置总结.md
├── 03-PDF摄取/              PDF 摄取管线方案与手册
│   ├── PDF摄取使用手册.md
│   └── PDF摄取方案与安全审计.md
├── 04-第二大脑/             第二大脑（SmartConnections / 跨区同步）方案与架构图
│   ├── 第二大脑-SmartConnections配置指南.md
│   ├── 第二大脑-跨区同步与本地模型方案.md
│   ├── 第二大脑-跨区同步与本地模型方案.html
│   ├── 第二大脑部署架构图.md
│   └── 第二大脑部署架构图.html
├── 05-图像视频生成/         图像与视频生成接入方案
│   └── 图像与视频生成接入方案.md
└── 06-工作小结/            阶段性小结
    └── 2026-10-15-工作小结.md
```

## 刻意保留在工作区原位（未归档）

| 文件 | 原因 |
|---|---|
| `rule.md` | 项目约定权威文件（角色/工作流/编码规范），被本地记忆引用，应保持原位 |
| `MTPLX本地AI实验室栈文档_副本.md` | **冗余副本**，与 `01-模型与MTPLX栈/` 内正本内容重复，建议直接删除（未自动删除以防误判） |
| `mtplx-serve.sh` / `verify-mtplx.sh` / `enable-mtplx-persistence.sh` / `mtplx-relay.py` / `ingest.py` / `ocr_bench.py` | 运维脚本，保持原位随用随调 |
| `*.log` / `requirements-pdf.txt` / `*.txt` | 运行日志与依赖清单，非方案文档 |
| `.workbuddy/memory/` | 本地工作记忆，不入归档 |

## 同步到 GitHub 的脱敏版本

公开仓库 `github.com/aiedwardai/AI-Lab`（**已重命名为 AstraX**）的 `mtplx-apple-silicon-local-ai-lab/` 子目录持有本栈的**脱敏通用版**：
- `scripts/mtplx-serve.sh.example`、`scripts/verify-mtplx.sh.example`、`scripts/enable-mtplx-persistence.sh`（占位变量版）
- `docs/MODEL-UPGRADE-2026-10-29.md`（升级说明）
- `benchmarks/RESULTS.md`（含 35B-A3B 档位实测 ~113 tok/s）

本 `docs/archive/` 为上述本地归档的**脱敏镜像**（个人路径/IP 已泛化），随本仓库公开发布；本地原版仍含机器专属信息，仅留本地。

## 最近主线任务快照（截至归档日）

- 模型已升级至 **Qwen3.6-35B-A3B（MoE，MLX 4bit，~19G 权重）**，当前 API 服务在线（PID <N> @ 127.0.0.1:8000）。
- 旧 27B 权重（28G）保留可回滚；64GB 机型下两模型不可同时常驻。
- GitHub 提交 `88a92a9` 已推送并被远端保留；远端后叠 `5cb4c88` 将仓库更名 AstraX。
- **已知运行时缺口**：OpenWebUI 前端当前不可访问——`OrbStack` 处于 Stopped，桥接 IP 消失，relay 套接字 CLOSED。需 `orbctl start` + 重启 relay 恢复（恢复步骤见 `01-模型与MTPLX栈/OpenWebUI容器访问MTPLX方案.md` 第八节）。
