# MTPLX 生成模型升级总结：27B → Qwen3.6-35B-A3B

> 日期：2026-10-29 ｜ 环境：Mac Studio M5 Max / 64GB 统一内存 ｜ 引擎：mtplx 2.12.2（MLX 原生栈，mlx-lm 0.31.3 / mlx 0.32.2）
> 一句话：把常驻生成模型从 27B 稠密换成 35B-A3B 稀疏 MoE，已上线、验收通过、并补好持久化与回滚能力。

---

## 0. 起止模型

| 项目 | 旧（已停用） | 新（当前常驻） |
|---|---|---|
| 模型 | `Youssofal/Qwen3.8-27B-MTPLX-Optimized-Quality` | `mlx-community/Qwen3.6-35B-A3B-4bit` |
| 类型 | 稠密 27B | 稀疏 MoE（35B 总参 / 3B 激活） |
| 权重大小 | ~18GB（缓存 28GB 含索引） | ~20.4GB（MLX 4bit） |
| 缓存目录 | `<MTPLX_STATE_DIR>/models/Youssofal--Qwen3.8-27B-MTPLX-Optimized-Quality` | `<MTPLX_STATE_DIR>/models/mlx-community--Qwen3.6-35B-A3B-4bit` |
| 实测吞吐 | 18~25 tok/s | **~113 tok/s** |

---

## 1. 可行性评估（三个关键认知，避免踩坑）

1. **MoE 对 Apple Silicon 极友好**：35B-A3B 每次推理只激活 3B 参数，访存压力远低于"总参 35B"。决定解码速度的是激活参数，不是总参——所以它反而可能比 27B 更快（实测证明确实更快，~113 vs 18~25 tok/s）。
2. **格式陷阱（最重要）**：网上看到的 `21.9GB GGUF` 是 **llama.cpp 格式**，而 mtplx 是 **MLX 运行时**，不能直接加载 GGUF。必须用 **MLX 格式权重**（mlx-community 的 `Qwen3.6-35B-A3B-4bit`，~20.4GB）。
3. **引擎无需升级**：mtplx 2.12.2 已原生注册 `qwen3_5_moe` 架构（含 Gated-DeltaNet 线性注意力），代码里 `a3b_whole_moe.py` / `gdn_*.py` 等即为该架构实现。之前误判"要升级 llama.cpp"是张冠李戴（本栈压根不是 llama.cpp）。
4. **内存约束**：64GB 机型下 **27B 与 35B-A3B 不可同时常驻**（峰值合计 >64GB → 触发 Swap）。只能二选一 / 错峰；双模型并存需 128GB。

---

## 2. 执行步骤（方案 A：单实例原地替换）

采用"方案 A"——只改 `mtplx-serve.sh` 的 `GEN_MODEL`，中继 / 端口 / api-key / OpenWebUI 全部不动，前端零改动。

| 步骤 | 操作 | 结果 |
|---|---|---|
| 1 | 改 `mtplx-serve.sh:37` 的 `GEN_MODEL` → `mlx-community/Qwen3.6-35B-A3B-4bit` | ✅ |
| 2 | 后台预拉 MLX 权重（`HF_ENDPOINT=hf-mirror.com`，~15min / ~23MB/s），期间 27B 继续服务 | ✅ 命中缓存，切换时不重下 |
| 3 | 停旧 27B（PID <N>，SIGTERM 2s 干净退出）；端口 8000 释放；中继保留 | ✅ |
| 4 | 起 35B-A3B（权重缓存命中，只加载不重下；PID <N>→942）@127.0.0.1:8000 | ✅ |
| 5 | 全链路验收：探活 200 / 嵌入维度 2560 / 生成正确回答 | ✅ |

---

## 3. 遇到的问题与解决（按发生顺序）

| # | 问题 | 根因 | 解决 |
|---|---|---|---|
| 1 | 切换后 OpenWebUI 前端连不上 | OrbStack 桥接被关（`orbctl status`→Stopped，bridge100 私有 IP 消失），中继历史一直 `Can't assign requested address` 重试 | `orbctl start` → OrbStack Running；bridge100 IP 仍为 `<ORBSTACK_BRIDGE_IP>`（与 plist 绑定一致，无需改）；起中继；容器随 `--restart always` 自动拉起 |
| 2 | 模型"空回答" | Qwen3.6 默认走 `<thinking>` 推理块，小 `max_tokens`（如 32/64）被思考吃光，`content` 显空 | 给足 `max_tokens`（如 2048），思考结束即正常出字（实测正确答"1+1=2"） |
| 3 | `verify-mtplx.sh` 验收空跑 | 脚本硬编码旧模型名 `mtplx-qwen38-27b-optimized-quality` | 修正为 `qwen3.6-35b-a3b-4bit` 并兼容推理模型输出 |
| 4 | `launchctl load` 报 `Load failed: 5: Input/output error` | 现代 macOS 已废弃 `launchctl load`/`unload` 动词，对用户级 agent 一律返回 EIO | 改用现代命令：`launchctl bootstrap gui/$UID <plist>` + `launchctl enable gui/$UID/<label>`；卸载用 `launchctl bootout` |

---

## 4. 性能与能力结果

- **吞吐**：生成 **~113 tok/s**（含推理），远超 benchmark 保守规划 30~50 tok/s，印证 MoE 低激活优势。
- **内存**：权重常驻 ~20.5GB，Swap 仅 ~642MB，无颠簸。
- **多模态**：`/v1/models` 显示 `supports_vision: true`（输入含 image）——35B-A3B 经 MTPLX **原生支持看图**，无需单独 mmproj 投影文件（当前栈是纯文本管线，启用看图需后续接线 VLM 入口）。

---

## 5. 持久化（关键收尾）

**问题**：MTPLX(942) 与中继(2049) 切换后都是**手动 nohup 进程、未接入 launchd**；WorkBuddy 会话关闭后可能被回收 → OpenWebUI 再次失联。

**交付**：一键脚本 `enable-mtplx-persistence.sh`（已 chmod +x、语法校验通过）：
- 自动起 OrbStack → 校验桥接 IP 未变 → 停手动进程 → `bootstrap`+`enable` 加载两个 plist（先 `bootout` 保幂等）→ 验收 `/v1/models` → **失败自动回退手动进程**（绝不让服务消失）。
- **必须在真实 Terminal.app 运行**（`launchctl` 在 WorkBuddy 沙箱 shell 内会被内核拒 EIO）。

**用户执行命令**（真实 Terminal）：
```bash
bash <DEPLOY_DIR>/enable-mtplx-persistence.sh
# 或手动：pkill 旧进程 → launchctl bootout/bootout → bootstrap gui/$UID + enable
```
验证：看到 `python3` 监听 `127.0.0.1:8000` 与 `<ORBSTACK_BRIDGE_IP>:8000` 两条即成功。

---

## 6. 回滚能力（27B 仍可一键切回）

- 27B 权重**未删除**，仍完整缓存于 `<MTPLX_STATE_DIR>/models/Youssofal--Qwen3.8-27B-MTPLX-Optimized-Quality`（28GB）。
- 切回：把 `mtplx-serve.sh:37` 的 `GEN_MODEL` 改回 `Youssofal/Qwen3.8-27B-MTPLX-Optimized-Quality`，停 35B-A3B 后重启即可（权重已缓存，不重下）。
- ⚠️ 注意：原 27B 曾以 `--generation-mode mtp --profile turbo` 加速参数运行；`serve.sh` 只传基础参数，切回会丢失 MTP 加速（吞吐略低于当初峰值）。若要完全还原，需在 serve.sh 补回那几个 flag。

---

## 7. 文档变更清单

| 文件 | 改动 |
|---|---|
| `mtplx-serve.sh` | `GEN_MODEL` → 35B-A3B |
| `verify-mtplx.sh` | 模型名修正 + 兼容推理输出 |
| `benchmarks/RESULTS.md` | 新增 35B-A3B 档位行 + MoE 注释 |
| `OpenWebUI容器访问MTPLX方案.md` | 模型 ID 更新；第七节状态表更正（均为手动 nohup）；新增第八节 2026-10-29 切换+恢复记录；手动步骤改 bootstrap |
| `OpenWebUI-OrbStack部署命令.md` | 第 4、5 节 Model ID 同步为 35B-A3B |
| `com.user.mtplx-relay.plist` | 注释从 `launchctl load` 改为 `bootstrap/enable` |
| （新增）`enable-mtplx-persistence.sh` | launchd 持久化一键脚本 |
| （新增）`MTPLX模型升级总结_27B到35B-A3B.md` | 本文件 |

---

## 8. 待办 / 注意

- [ ] 用户需在真实 Terminal 跑 `enable-mtplx-persistence.sh`，把 MTPLX + 中继交给 launchd 常驻（否则会话关闭即失联）。
- [ ] 浏览器 `http://127.0.0.1:3000` 把对话模型切到 `qwen3.6-35b-a3b-4bit`（旧 27B ID 已不存在）。
- [ ] 64GB 机型下 27B 与 35B-A3B 不可同时常驻。
- [ ] 若启用 35B-A3B 看图，需后续接线 VLM 入口（当前纯文本管线）。
