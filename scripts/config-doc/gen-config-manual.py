#!/usr/bin/env python3
"""配置手册生成器（配置即代码 · 双输出）。

读取 config-facts.yaml（单一事实源），用同一套稳定叙述渲染两份输出：
  1) 本地速查手册   → 含真实路径 / IP，仅留本机（本地部署配置手册.md）。
  2) GitHub 脱敏手册 → 经 sanitize() 替换为 <HOME> / <ORBSTACK_BRIDGE_IP> 等占位符，
     写入 AstraX 仓库 docs/DEPLOY-MANUAL.md。

用法：
    python3 gen-config-manual.py
依赖：Python 3 + PyYAML（系统已装）。
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import config_doc_common as cdc  # noqa: E402

FACTS_PATH = cdc.resolve_facts_path(os.environ.get("MTPLX_FACTS"))
LOCAL_MANUAL = os.path.join(HERE, "本地部署配置手册.md")


def _bootstrap_block(ld: dict) -> str:
    """生成 launchd bootstrap 标准命令块（与第 4 / 5 节复用）。"""
    return (
        "UID=$(id -u)\n"
        f"launchctl bootout  gui/$UID/{ld['mtplx_label']}          2>/dev/null\n"
        f"launchctl bootout  gui/$UID/{ld['relay_label']}          2>/dev/null\n"
        f"launchctl bootstrap gui/$UID {ld['plist_dir']}/{ld['mtplx_label']}.plist\n"
        f"launchctl enable    gui/$UID/{ld['mtplx_label']}\n"
        f"launchctl bootstrap gui/$UID {ld['plist_dir']}/{ld['relay_label']}.plist\n"
        f"launchctl enable    gui/$UID/{ld['relay_label']}"
    )


def render_local(facts: dict) -> str:
    """渲染本地速查手册（真实值）。"""
    meta = facts["meta"]
    hw = facts["hardware"]
    net = facts["network"]
    ld = facts["launchd"]
    perf = facts["performance"]
    repo = facts["repo"]
    py = hw["python_bin"]

    # 模型表（按 facts 顺序渲染，状态决定图标）
    model_rows = []
    for m in facts["models"]:
        state = "✅ 在线" if m["status"] == "online" else "⏸ 缓存保留"
        model_rows.append(
            f"| **{m['role']}** | `{m['id']}` | {m['precision']}，~{m['size_gb']} GB（{m['detail']}） | {state} |"
        )
    models_table = "\n".join(model_rows)

    # 关键文件表
    file_rows = [f"| `{f['path']}` | {f['use']} |" for f in facts["key_files"]]
    files_table = "\n".join(file_rows)

    # 回滚模型 ID
    rollback = next((m for m in facts["models"] if "回滚" in m["role"]), None)
    rollback_id = rollback["id"] if rollback else ""
    gen_short = facts["models"][0]["id"].split("/")[-1]

    uid_cmd = _bootstrap_block(ld)
    uid_cmd_indented = "\n".join("    " + ln for ln in uid_cmd.splitlines())

    md = f"""# {meta['manual_title']}（落地快照 {meta['snapshot_date']}）

> {meta['generated_note']}
> 本手册是本地实际落地状态的**单一权威速查**，机器专属（含真实路径 / 桥接 IP），**仅留本机，不入公开仓库**。
> 详细设计与排障见 `归档/` 下各分册。模型升级全过程见 `归档/01-模型与MTPLX栈/MTPLX模型升级总结_27B到35B-A3B.md`。

---

## 1. 硬件与平台

| 项 | 值 |
|---|---|
| 机型 | {hw['machine']} |
| 运行时 | `{hw['runtime']}`，受管 venv：`{py}` |
| 容器运行时 | {hw['container_runtime']} |
| 参考机磁盘余量 | {hw['disk_free']} |

---

## 2. 当前模型配置

| 角色 | 模型 | 精度 / 体积 | 状态 |
|---|---|---|---|
{models_table}

> ⚠️ **格式陷阱**：网上 `21.9GB GGUF` 是 llama.cpp 格式，本 MLX 栈**不能直接加载**，必须用 MLX 权重。
> ✅ **引擎已原生支持** `qwen3_5_moe` 架构（含 Gated-DeltaNet 线性注意力），无需升级 `mtplx`。
> 💡 35B-A3B 为推理模型，默认走 `<thinking>` 思考块；小 `max_tokens`（如 64）会被思考吃光而"看似空回答"，给足（如 2048）即正常出字；其 `supports_vision: true`（原生支持看图，无需单独 mmproj）。

---

## 3. 服务拓扑与网络

```
本机 macOS（M5 Max / 64GB）
┌─────────────────────────┐         ┌──────────────────────────────┐
│ MTPLX 守护进程           │         │ OrbStack 容器 (Linux VM)       │
│ {net['gen_bind']}          │         │  Open WebUI :3000 (仅回环)     │
│ 生成 35B-A3B + 嵌入 4B   │◄─┐      │     │                          │
│ api-key 鉴权            │  │      │     │ host.docker.internal:8000  │
└─────────────────────────┘  │      │     ▼                          │
                             │      │  TCP 中继 mtplx-relay.py        │
  原生前端（同机 Obsidian）    │      │  监听 bridge100 真实 IP:8000     │
  Smart Connections/Copilot ──┘      │  （如 {net['relay_bind_ip']}）           │
  直连 {net['gen_bind']}/v1            └──────────────────────────────┘
```

- **生成 / 嵌入服务**：仅绑 `{net['gen_bind']}`，api-key 落盘 `{net['api_key_path']}`（权限 600）。
- **中继** `mtplx-relay.py`：纯标准库 TCP 转发，绑 OrbStack 桥接宿主侧真实 IP（`{net['orbstack_bridge']}` 接口，本机实测 `{net['relay_bind_ip']}`），**不暴露到 en0 / Wi‑Fi / 局域网**。容器内经 `host.docker.internal` → OrbStack 虚拟路由 `{net['virtual_route']}` → 投递到桥接 IP → 中继 → 回环 MTPLX。
- **OpenWebUI**：`-p {net['openwebui_port']}:8080`，UI 仅回环，不暴露公网。

---

## 4. 进程托管（launchd 常驻方案）

| 组件 | 托管方式 | 监听 |
|---|---|---|
| MTPLX | launchd（`{ld['mtplx_label']}`，KeepAlive，RunAtLoad） | `{net['gen_bind']}` |
| 中继 | launchd（`{ld['relay_label']}`，KeepAlive） | `{net['relay_bind_ip']}:{net['relay_bind_port']}`（需 OrbStack 桥接在线） |
| OpenWebUI | 容器 `--restart always` | `{net['openwebui_port']}` |

> ⚠️ **现代 macOS 已废弃 `launchctl load`/`unload`**（对用户级 job 一律报 `Load failed: 5: Input/output error`）。**正确命令**：
> ```bash
> {uid_cmd}
> ```
> **一键接管（含失败回退）**：在真实 Terminal 运行 `bash {HERE}/enable-mtplx-persistence.sh`（WorkBuddy 沙箱 shell 会被内核拒 EIO，勿在对话内执行）。
> 注：实际运行态（PID / 是否在跑）由 `audit-config.py` 实时核验，见第 11 节。

---

## 5. 前端（OpenWebUI）状态与恢复

> 若 `OrbStack` 处于 **Stopped**，桥接 IP `{net['relay_bind_ip']}` 消失，中继套接字 CLOSED，OWUI 容器未起。**模型 API 自身正常**（`:8000` 在服）。

**恢复步骤（真实 Terminal）**：
```bash
# 1) 启动 OrbStack（桥接 IP 通常仍是 {net['relay_bind_ip']}，无需改绑定）
orbctl start
# 2) 停旧手动进程，避免端口冲突
pkill -f mtplx-relay.py; pkill -f mtplx.server.openai; sleep 2
# 3) 用 bootstrap 起中继 + MTPLX（或运行 enable-mtplx-persistence.sh 一键）
{uid_cmd_indented}
# 4) 验证：lsof -nP -iTCP:8000 -sTCP:LISTEN 应见 python3 @{net['relay_bind_ip']}:8000
#    curl -s --noproxy '*' http://{net['openwebui_port']}/health  → {{"status":true}}
```
> 浏览器开 `http://{net['openwebui_port']}` → 把对话模型切到 **`{gen_short}`**（旧 `mtplx-qwen38-27b-optimized-quality` 已不存在）。

---

## 6. 客户端接入

- **Obsidian（Smart Connections / Copilot，原生同机）**：Base URL `{facts['clients']['obsidian']['base_url']}`，Key 用 `{net['api_key_path']}` 内容，聊天模型 `{facts['clients']['obsidian']['chat_model']}`，嵌入 `{facts['clients']['obsidian']['embed_model']}`。不受回环限制。
- **OpenWebUI（容器）**：经中继够到 MTPLX（见第 5 节）。

---

## 7. 性能实测

| 指标 | 值 |
|---|---|
| 生成吞吐（含推理思考） | **{perf['throughput_toks']}**（远超 27B 的 18–25 tok/s；印证 MoE 仅激活 3B 在 MLX 上的优势） |
| Swap 占用 | ~{perf['swap_mb']} MB，无颠簸 |
| 上下文窗口 | {perf['ctx_window']}（256k） |

---

## 8. 回滚到 27B（如需）

1. 改 `mtplx-serve.sh` 的 `GEN_MODEL` → `{rollback_id}`（权重已缓存，重启即加载、不重下）。
2. 停 35B-A3B 再起 27B（**64GB 不可同时常驻**两者）。
3. OpenWebUI / Obsidian 内把模型 ID 切回旧值。

---

## 9. 知识库 / 代码仓库

- 本地部署文档 + 脱敏版已推送至 **`{repo['github']}`**。
- 本地（机器专属、含路径/IP）文档统一归档于 `{repo['local_archive']}`，本手册为落地速查。

---

## 10. 关键文件清单（本地）

| 文件 | 用途 |
|---|---|
{files_table}

---

## 11. 运维命令速查

```bash
# 服务存活
pgrep -f 'python3 -P -m mtplx.server.openai'   # 生成服务 PID
pgrep -f mtplx-relay.py                        # 中继 PID
lsof -nP -iTCP:8000 -sTCP:LISTEN               # 端口监听
orbctl status                                   # OrbStack 状态

# 模型在线校验
API_KEY=$(cat {net['api_key_path']})
curl -s --noproxy '*' -H "Authorization: Bearer $API_KEY" http://{net['gen_bind']}/v1/models

# OpenWebUI 健康
curl -s --noproxy '*' http://{net['openwebui_port']}/health

# 配置漂移审计（文档 vs 现实）
python3 {HERE}/audit-config.py
```

---

*本手册由 `config-facts.yaml` 经 `gen-config-manual.py` 自动生成。重大变更（换模型 / 改绑定 / 升引擎）后请改 facts 并重生手册，再同步 `归档/` 分册。*
"""
    return md


def render_github(facts: dict, local_md: str) -> str:
    """由本地手册脱敏产出公开仓库版。"""
    bridge_ip = facts["network"]["relay_bind_ip"]
    return cdc.sanitize(local_md, bridge_ip=bridge_ip)


def main() -> None:
    facts = cdc.load_facts(FACTS_PATH)
    local_md = render_local(facts)

    # 写本地速查手册（仅当事实源为真实值时；示例数据不生成含秘手册）
    is_example = FACTS_PATH.endswith("example.yaml")
    if not is_example:
        with open(LOCAL_MANUAL, "w", encoding="utf-8") as fh:
            fh.write(local_md)
        print(f"[OK] 本地手册已生成：{LOCAL_MANUAL}")
    else:
        print("[SKIP] 示例事实源不生成本地速查手册（避免含占位符的手册入库）")

    # 写脱敏版到仓库
    repo_path = facts["repo"].get("local_path")
    if repo_path:
        github_md = render_github(facts, local_md)
        out = os.path.join(repo_path, "docs", "DEPLOY-MANUAL.md")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(github_md)
        print(f"[OK] 脱敏手册已生成：{out}")
    else:
        print("[SKIP] 未配置 repo.local_path，跳过 GitHub 脱敏手册生成。")


if __name__ == "__main__":
    main()
