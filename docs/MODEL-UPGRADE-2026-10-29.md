# 模型升级记录：27B → Qwen3.6-35B-A3B（2026-10-29）

> 适用范围：MTPLX Apple Silicon 本地 AI 实验室栈（MLX 原生，`mtplx` 引擎）。
> 本文档为**脱敏通用版**，不含任何机器专属路径 / 私有 IP / 进程号。

## 一、为什么换

| 项目 | 旧（稠密 27B） | 新（稀疏 MoE 35B-A3B） |
|---|---|---|
| 全称 | Qwen3.8-27B-MTPLX-Optimized-Quality | Qwen3.6-35B-A3B |
| 架构 | 稠密 Transformer | 稀疏 MoE：350 亿总参 / **仅 30 亿激活**（top-8 路由）+ Gated-DeltaNet 线性注意力 |
| 推荐权重 | MLX 4bit ~18GB | **MLX 4bit `mlx-community/Qwen3.6-35B-A3B-4bit` ~20.4GB** |
| 原生上下文 | — | 262K |
| 多模态 | 纯文本 | 原生支持图像/视频输入（`/v1/models` 标 `supports_vision: true`，无需单独 mmproj） |

**核心结论**：MoE 每 token 只激活 3B 专家权重，决定解码速度的访存量大幅下降，因此在 Apple Silicon 上 **35B-A3B 反而比稠密 27B 更快**。

## 二、三个必须知道的事实（避坑）

1. **必须用 MLX 权重，不能直接加载 GGUF。**
   网上常见的 `21.9GB GGUF` 是 llama.cpp 格式，而本栈是 **MLX 原生**，无法加载。请改用 `mlx-community/Qwen3.6-35B-A3B-4bit`（均匀 4bit，~20.4GB）。同系列还有 `-4bit-DWQ`、`-OptiQ-4bit`（后者自带 MTP 加速头，可与 `mtplx` 的 MTP 配合再提速）。

2. **引擎无需升级。**
   `mtplx` 2.12.2（mlx-lm 0.31.3 / mlx 0.32.2）**已原生支持 `qwen3_5_moe` 架构**（含 Gated-DeltaNet），直接可跑，无需换引擎。

3. **推理型模型会"先思考后回答"。**
   Qwen3.6 默认产出 `<thinking>` 思考块；若 `max_tokens` 太小（如 32），预算被思考吃光，`content` 字段会显空——这**不是故障**。给足预算（如 768~2048）即正常出字；OpenWebUI 会单独渲染思考块。

## 三、切换步骤（单实例替换，最简）

1. 改 `scripts/mtplx-serve.sh.example` 的 `GEN_MODEL` → `mlx-community/Qwen3.6-35B-A3B-4bit`（并同步到你的实际 `mtplx-serve.sh`）。
2. 预拉权重（不中断旧模型服务）：
   ```bash
   export HF_ENDPOINT=https://hf-mirror.com   # 官方源不可达时的镜像绕行
   mtplx pull mlx-community/Qwen3.6-35B-A3B-4bit
   ```
3. 停旧 27B → 起 35B-A3B（权重已缓存，只加载不重下）→ 用 `verify-mtplx.sh.example` 验收。
4. OpenWebUI 内把对话模型切到 `qwen3.6-35b-a3b-4bit`（旧 ID 已不存在）。

## 四、内存与性能实测（Mac Studio M5 Max / 64GB）

| 指标 | 数值 |
|---|---|
| 权重常驻 | ~20.4GB（Q4 级别 MLX） |
| 生成吞吐 | **~113 tok/s**（含推理思考块；规划保守值 30~50 tok/s） |
| Swap 占用 | ~642MB，无颠簸 |
| 与 27B 同驻 | **不可**：64GB 机型下二者峰值合计 >64GB，必须二选一或错峰 |

## 五、运维坑位（已解决）

- **`launchctl load` 报 `Load failed: 5: Input/output error`**：
  现代 macOS 已废弃 `load`/`unload` 动词。改用 `launchctl bootstrap gui/$UID <plist>` + `enable`（见 `scripts/enable-mtplx-persistence.sh`）。
- **OpenWebUI 失联**：
  多数情况是 OrbStack 桥接被关（`orbctl status`→Stopped，本机无 `192.168.*` 桥接 IP），中继 `Can't assign requested address` 循环。恢复：`orbctl start` → 确认 `ifconfig bridge100` 的真实 IP 填进 relay plist 的 `MTPLX_RELAY_BIND_IP` → 起中继。容器随 `--restart always` 会自动拉起。
- **中继绑定地址**：容器内 `host.docker.internal` 解析到 OrbStack 魔法路由地址（宿主接口上不存在），**不可**直接填进 `MTPLX_RELAY_BIND_IP`；中继要绑的是宿主 `bridge100` 接口的真实 IP。

## 六、回滚

把 `GEN_MODEL` 改回 `Youssofal/Qwen3.8-27B-MTPLX-Optimized-Quality` 即可（权重仍缓存在本地，重启即加载、不重下）。64GB 下两模型不可同时常驻，需停一个再起另一个。
