# 本地部署配置手册 — MTPLX AI 实验室（落地快照 2026-11-03）

> 本手册由 config-facts.yaml + gen-config-manual.py 自动生成，请勿手改。
> 本手册是本地实际落地状态的**单一权威速查**，机器专属（含真实路径 / 桥接 IP），**仅留本机，不入公开仓库**。
> 详细设计与排障见 `归档/` 下各分册。模型升级全过程见 `归档/01-模型与MTPLX栈/MTPLX模型升级总结_27B到35B-A3B.md`。

---

## 1. 硬件与平台

| 项 | 值 |
|---|---|
| 机型 | Mac Studio（Apple M5 Max，18 核，64 GB 统一内存） |
| 运行时 | `mtplx 2.12.2（基于 mlx-lm 0.31.3 / mlx 0.32.2）`，受管 venv：`<HOME>/.workbuddy/binaries/python/versions/3.13.12/bin/python3` |
| 容器运行时 | OrbStack（orbctl / 兼容 docker CLI） |
| 参考机磁盘余量 | ~768 GB |

---

## 2. 当前模型配置

| 角色 | 模型 | 精度 / 体积 | 状态 |
|---|---|---|---|
| **生成（当前主力）** | `mlx-community/Qwen3.6-35B-A3B-4bit` | MLX 4bit，~19 GB（35B 总参 / 3B 激活 MoE） | ✅ 在线 |
| **生成（回滚保留）** | `Youssofal/Qwen3.8-27B-MTPLX-Optimized-Quality` | MLX，~28 GB（权重仍缓存，未删；64GB 机型与 35B-A3B 不可同时常驻） | ⏸ 缓存保留 |
| **嵌入（同进程）** | `mlx-community/Qwen3-Embedding-4B-4bit-DWQ` | MLX 4bit DWQ，~2.1 GB（维度 2560） | ✅ 在线 |

> ⚠️ **格式陷阱**：网上 `21.9GB GGUF` 是 llama.cpp 格式，本 MLX 栈**不能直接加载**，必须用 MLX 权重。
> ✅ **引擎已原生支持** `qwen3_5_moe` 架构（含 Gated-DeltaNet 线性注意力），无需升级 `mtplx`。
> 💡 35B-A3B 为推理模型，默认走 `<thinking>` 思考块；小 `max_tokens`（如 64）会被思考吃光而"看似空回答"，给足（如 2048）即正常出字；其 `supports_vision: true`（原生支持看图，无需单独 mmproj）。

---

## 3. 服务拓扑与网络

```
本机 macOS（M5 Max / 64GB）
┌─────────────────────────┐         ┌──────────────────────────────┐
│ MTPLX 守护进程           │         │ OrbStack 容器 (Linux VM)       │
│ 127.0.0.1:8000          │         │  Open WebUI :3000 (仅回环)     │
│ 生成 35B-A3B + 嵌入 4B   │◄─┐      │     │                          │
│ api-key 鉴权            │  │      │     │ host.docker.internal:8000  │
└─────────────────────────┘  │      │     ▼                          │
                             │      │  TCP 中继 mtplx-relay.py        │
  原生前端（同机 Obsidian）    │      │  监听 bridge100 真实 IP:8000     │
  Smart Connections/Copilot ──┘      │  （如 <ORBSTACK_BRIDGE_IP>）           │
  直连 127.0.0.1:8000/v1            └──────────────────────────────┘
```

- **生成 / 嵌入服务**：仅绑 `127.0.0.1:8000`，api-key 落盘 `~/.mtplx/api-key`（权限 600）。
- **中继** `mtplx-relay.py`：纯标准库 TCP 转发，绑 OrbStack 桥接宿主侧真实 IP（`bridge100` 接口，本机实测 `<ORBSTACK_BRIDGE_IP>`），**不暴露到 en0 / Wi‑Fi / 局域网**。容器内经 `host.docker.internal` → OrbStack 虚拟路由 `0.250.250.254` → 投递到桥接 IP → 中继 → 回环 MTPLX。
- **OpenWebUI**：`-p 127.0.0.1:3000:8080`，UI 仅回环，不暴露公网。

---

## 4. 进程托管（launchd 常驻方案）

| 组件 | 托管方式 | 监听 |
|---|---|---|
| MTPLX | launchd（`com.user.mtplx`，KeepAlive，RunAtLoad） | `127.0.0.1:8000` |
| 中继 | launchd（`com.user.mtplx-relay`，KeepAlive） | `<ORBSTACK_BRIDGE_IP>:8000`（需 OrbStack 桥接在线） |
| OpenWebUI | 容器 `--restart always` | `127.0.0.1:3000` |

> ⚠️ **现代 macOS 已废弃 `launchctl load`/`unload`**（对用户级 job 一律报 `Load failed: 5: Input/output error`）。**正确命令**：
> ```bash
> UID=$(id -u)
launchctl bootout  gui/$UID/com.user.mtplx          2>/dev/null
launchctl bootout  gui/$UID/com.user.mtplx-relay          2>/dev/null
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.user.mtplx.plist
launchctl enable    gui/$UID/com.user.mtplx
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.user.mtplx-relay.plist
launchctl enable    gui/$UID/com.user.mtplx-relay
> ```
> **一键接管（含失败回退）**：在真实 Terminal 运行 `bash <HOME>/WorkBuddy/服务器部署相关/enable-mtplx-persistence.sh`（WorkBuddy 沙箱 shell 会被内核拒 EIO，勿在对话内执行）。
> 注：实际运行态（PID / 是否在跑）由 `audit-config.py` 实时核验，见第 11 节。

---

## 5. 前端（OpenWebUI）状态与恢复

> 若 `OrbStack` 处于 **Stopped**，桥接 IP `<ORBSTACK_BRIDGE_IP>` 消失，中继套接字 CLOSED，OWUI 容器未起。**模型 API 自身正常**（`:8000` 在服）。

**恢复步骤（真实 Terminal）**：
```bash
# 1) 启动 OrbStack（桥接 IP 通常仍是 <ORBSTACK_BRIDGE_IP>，无需改绑定）
orbctl start
# 2) 停旧手动进程，避免端口冲突
pkill -f mtplx-relay.py; pkill -f mtplx.server.openai; sleep 2
# 3) 用 bootstrap 起中继 + MTPLX（或运行 enable-mtplx-persistence.sh 一键）
    UID=$(id -u)
    launchctl bootout  gui/$UID/com.user.mtplx          2>/dev/null
    launchctl bootout  gui/$UID/com.user.mtplx-relay          2>/dev/null
    launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.user.mtplx.plist
    launchctl enable    gui/$UID/com.user.mtplx
    launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.user.mtplx-relay.plist
    launchctl enable    gui/$UID/com.user.mtplx-relay
# 4) 验证：lsof -nP -iTCP:8000 -sTCP:LISTEN 应见 python3 @<ORBSTACK_BRIDGE_IP>:8000
#    curl -s --noproxy '*' http://127.0.0.1:3000/health  → {"status":true}
```
> 浏览器开 `http://127.0.0.1:3000` → 把对话模型切到 **`Qwen3.6-35B-A3B-4bit`**（旧 `mtplx-qwen38-27b-optimized-quality` 已不存在）。

---

## 6. 客户端接入

- **Obsidian（Smart Connections / Copilot，原生同机）**：Base URL `http://127.0.0.1:8000/v1`，Key 用 `~/.mtplx/api-key` 内容，聊天模型 `qwen3.6-35b-a3b-4bit`，嵌入 `Qwen3-Embedding-4B-4bit-DWQ`。不受回环限制。
- **OpenWebUI（容器）**：经中继够到 MTPLX（见第 5 节）。

---

## 7. 性能实测

| 指标 | 值 |
|---|---|
| 生成吞吐（含推理思考） | **~113 tok/s**（远超 27B 的 18–25 tok/s；印证 MoE 仅激活 3B 在 MLX 上的优势） |
| Swap 占用 | ~642 MB，无颠簸 |
| 上下文窗口 | 262144（256k） |

---

## 8. 回滚到 27B（如需）

1. 改 `mtplx-serve.sh` 的 `GEN_MODEL` → `Youssofal/Qwen3.8-27B-MTPLX-Optimized-Quality`（权重已缓存，重启即加载、不重下）。
2. 停 35B-A3B 再起 27B（**64GB 不可同时常驻**两者）。
3. OpenWebUI / Obsidian 内把模型 ID 切回旧值。

---

## 9. 知识库 / 代码仓库

- 本地部署文档 + 脱敏版已推送至 **`github.com/aiedwardai/AstraX`**。
- 本地（机器专属、含路径/IP）文档统一归档于 `归档/`，本手册为落地速查。

---

## 10. 关键文件清单（本地）

| 文件 | 用途 |
|---|---|
| `<HOME>/WorkBuddy/服务器部署相关/mtplx-serve.sh` | 单实例守护启动脚本（方案 C：全 MLX 原生栈） |
| `<HOME>/WorkBuddy/服务器部署相关/verify-mtplx.sh` | 双模型全链路一键验收 |
| `<HOME>/WorkBuddy/服务器部署相关/mtplx-relay.py` | 纯标准库 TCP 中继（容器够到仅回环 MTPLX） |
| `<HOME>/WorkBuddy/服务器部署相关/enable-mtplx-persistence.sh` | launchd 常驻一键脚本（bootstrap + 失败回退） |
| `~/Library/LaunchAgents/com.user.mtplx.plist` | launchd 定义（MTPLX） |
| `~/Library/LaunchAgents/com.user.mtplx-relay.plist` | launchd 定义（中继，含 MTPLX_RELAY_BIND_IP） |
| `~/.mtplx/models/` | 模型权重缓存（35B-A3B + 27B 两份 + 嵌入 4B） |
| `~/.mtplx/api-key` | MTPLX 鉴权密钥（权限 600） |

---

## 11. 运维命令速查

```bash
# 服务存活
pgrep -f 'python3 -P -m mtplx.server.openai'   # 生成服务 PID
pgrep -f mtplx-relay.py                        # 中继 PID
lsof -nP -iTCP:8000 -sTCP:LISTEN               # 端口监听
orbctl status                                   # OrbStack 状态

# 模型在线校验
API_KEY=$(cat ~/.mtplx/api-key)
curl -s --noproxy '*' -H "Authorization: Bearer $API_KEY" http://127.0.0.1:8000/v1/models

# OpenWebUI 健康
curl -s --noproxy '*' http://127.0.0.1:3000/health

# 配置漂移审计（文档 vs 现实）
python3 <HOME>/WorkBuddy/服务器部署相关/audit-config.py
```

---

*本手册由 `config-facts.yaml` 经 `gen-config-manual.py` 自动生成。重大变更（换模型 / 改绑定 / 升引擎）后请改 facts 并重生手册，再同步 `归档/` 分册。*
