# 第二大脑（Obsidian `brain` vault）— Smart Connections + Copilot 精确配置指南

> 目标：在本地 MTPLX（`127.0.0.1:8000`，27B 聊天 + 4B 嵌入）之上，把 `~/Documents/obsidian/brain` 变成可语义检索、可对话的第二大脑。
> 适用：macOS / Obsidian 已装 / `brain` vault 已建 / MTPLX 已在线。

---

## 0. 版本事实（必读，决定选型）

| 组件 | 当前状态 | 对本案的含义 |
|---|---|---|
| **Smart Connections 核心（免费）** | 自带**本地嵌入模型**，零配置即可做语义检索/相关笔记；**不校验外部 API** | 免费即可满足"语义检索"；无需自定义端点也能跑 |
| **Smart Chat（聊天）** | 已移至 **Smart Chat Pro（付费）** | 免费核心版不能"聊 vault" |
| **Copilot for Obsidian（免费）** | 支持 `Custom OpenAI` 端点，可做 vault QA | 免费实现"笔记对话"的最佳选择 |

结论：第二大脑 = **Smart Connections（检索）+ Copilot（对话）** 两个免费插件的组合。
（若你愿意付费，可改用 Smart Chat Pro 把检索+对话合一，但本地模型接入方式相同。）

---

## 1. 组件分工（一个能力一个主负责人）

- **Smart Connections** → 语义检索 / 打开笔记时推荐相关笔记 / 全库向量索引。
- **Copilot** → 在侧边栏与 vault 对话，基于笔记上下文回答（RAG）。
- 两者**共用同一后端** `http://127.0.0.1:8000/v1`，不重复知识库、不各维护一套地址。

统一参数（全文复用）：
- Base URL：`http://127.0.0.1:8000/v1`
- API Key：读取 `<MTPLX_STATE_DIR>/api-key` 的内容（MTPLX 校验此 key，必须填真值）
- 聊天模型：`mtplx-qwen38-27b-optimized-quality`
- 嵌入模型：`Qwen3-Embedding-4B-4bit-DWQ`（维度 2560，插件通常自动识别，无需手填）

> 取 key 的一条命令：`cat <MTPLX_STATE_DIR>/api-key`

---

## 2. 安装（社区插件）

Obsidian → 设置 → 第三方插件 → 关闭安全模式 → 浏览 → 分别搜索并安装：
1. `Smart Connections`
2. `Copilot`

安装后启用，左侧出现各自配置面板。

---

## 3. Smart Connections 配置字段清单

### 3a. 免费默认（推荐先跑通，零配置）
启用后 Smart Connections 会用**内置本地嵌入模型**自动索引 vault。
- 无需填任何 Base URL / Key。
- 打开任意笔记 → 右侧边栏出现「相关笔记」即成功。
- 首次索引：`Ctrl/Cmd+P` → `Smart Connections: Build Index`（或 `Rebuild Index`）。

### 3b. 指定用 MTPLX 的 Qwen3-Embedding-4B（自定义 OpenAI 兼容端点）
> 适用场景：你想让嵌入模型与 Open WebUI / 其他工具统一为同一个 `Qwen3-Embedding-4B`，或免费核心版未提供你要的自定义端点（部分新版把自定义嵌入收进 Pro）。**先试 3a，再决定是否走 3b。**

**Settings UI 字段（按你安装的版本，路径可能是以下之一）：**
- 旧版：`设置 → Smart Connections → AI Model → Custom OpenAI Configuration`
- 新版（Smart Environment）：`设置 → Smart Connections → Smart Environment → Embeddings → OpenAI Compatible`

| UI 字段 | 填写值 |
|---|---|
| Base URL / API Base | `http://127.0.0.1:8000/v1` |
| API Key | `cat <MTPLX_STATE_DIR>/api-key` 的内容 |
| Embedding Model / Model ID | `Qwen3-Embedding-4B-4bit-DWQ` |
| Dimensions（如要求） | `2560` |

**旧版 `data.json` 参考格式**（位于 `~/Documents/obsidian/brain/.obsidian/plugins/smart-connections/data.json`，仅供对照，以 UI 为准）：
```json
{
  "providers": [
    {
      "name": "mtplx-local",
      "baseUrl": "http://127.0.0.1:8000/v1",
      "apiKey": "在此粘贴 <MTPLX_STATE_DIR>/api-key 的内容",
      "models": ["Qwen3-Embedding-4B-4bit-DWQ", "mtplx-qwen38-27b-optimized-quality"]
    }
  ]
}
```

---

## 4. Copilot 配置字段清单（vault 对话，免费）

`设置 → Copilot → Model Settings`：

| UI 字段 | 填写值 |
|---|---|
| Model Provider | `Custom OpenAI` |
| Base URL | `http://127.0.0.1:8000/v1` |
| Model | `mtplx-qwen38-27b-optimized-quality` |
| API Key | `cat <MTPLX_STATE_DIR>/api-key` 的内容 |
| Embeddings Model（用于 vault QA） | `Qwen3-Embedding-4B-4bit-DWQ` |
| Base URL（Embeddings，若单独填） | `http://127.0.0.1:8000/v1` |

对话时使用 **Vault QA / Chat with vault** 模式，Copilot 会先嵌入并检索当前 vault 再回答。

---

## 5. 索引与验收命令

```bash
# 1) 确认 MTPLX 嵌入端点可用（应在 brain vault 外先验证）
APIKEY=$(cat <MTPLX_STATE_DIR>/api-key)
curl -s --max-time 15 -H "Authorization: Bearer $APIKEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"Qwen3-Embedding-4B-4bit-DWQ","input":"测试向量"}' \
  http://127.0.0.1:8000/v1/embeddings | head -c 200
# 期望：返回 "data":[{"embedding":[...],"index":0}] 且向量长度 2560

# 2) Smart Connections：在 Obsidian 内 Build Index，观察右下角进度
# 3) Copilot：打开聊天 → Vault QA → 问"总结我写过关于 X 的内容"，验证引用了真实笔记
```

**验收标准（PASS 条件）**
- Smart Connections 侧边栏能列出与当前笔记相关的历史笔记；
- Copilot Vault QA 的回答能正确引用 `brain` vault 中的具体内容（非泛泛而谈）；
- 全程无外部网络请求（全部走 `127.0.0.1:8000`）。

---

## 6. 安全要点

- API Key 会以明文存于 `.obsidian/plugins/*/data.json`。它是本机随机生成的 loopback 保护密钥，外泄风险低，但**不要把 `.obsidian` 同步到公开仓库**。
- 所有端点均为 `127.0.0.1`（回环），**不暴露公网**；不要改成 `0.0.0.0`。
- 嵌入索引存于 vault 内 `.smart-env/`，随 vault 同步（iCloud/Obsidian Sync）即可，无需跨设备重算。

## 7. 决策已定：方案 Y（Obsidian 原生）— Copilot 为 vault 对话主工具

> **已选定方案 Y**。聊天留在 Obsidian 内，由 **Copilot** 承担 vault 对话；**Smart Connections** 负责"相关笔记"语义检索；**Open WebUI 仅作通用对话工作台**（不启用 vault 知识库 RAG）。

理由：
- **零同步维护**——Copilot 直读活 vault，笔记改完立刻能问到；避免 Open WebUI RAG 副本索引的同步缺口。
- **避免双索引**——若 Open WebUI 也建 vault RAG，同一 vault 会出现两份嵌入索引（Smart Connections 一份 + Open WebUI 一份），违背"一个能力一个主负责人、不重复建设知识库"。

→ 因此本节第 4 节 **Copilot 配置为本案主路径**；Open WebUI 的 vault RAG（见 `OpenWebUI-OrbStack部署命令.md` 第 3b 节）在方案 Y 下**不启用**，仅作为未来可选扩展保留。Open WebUI 仍按原计划承担日常通用对话 / 模型切换 / 文档对话。
