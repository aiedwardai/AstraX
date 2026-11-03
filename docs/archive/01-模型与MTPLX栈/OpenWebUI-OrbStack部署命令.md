# Open WebUI — OrbStack 部署精确命令

> 目标：用 OrbStack（轻量容器运行时，免 Docker Desktop）跑官方 `open-webui:main`，接入本地 MTPLX（`127.0.0.1:8000`）。
> 已确认：镜像 `ghcr.io/open-webui/open-webui:main`、端口 `-p 3000:8080`、持久化卷 `open-webui:/app/backend/data`、`WEBUI_SECRET_KEY` 必填。

---

## 0. 前置修正：MTPLX 绑定地址（关键，不处理则容器连不上）

当前 `mtplx-serve.sh` 写死 `--host 127.0.0.1`（仅回环）。Open WebUI 在容器内通过 `host.docker.internal` 访问宿主机——该域名解析到**宿主机 IP**，而回环绑定的服务**拒绝非回环来源**。因此：

- **Smart Connections / Copilot（原生 Obsidian）**：同机，`127.0.0.1:8000` 直接可用，**不受影响**。
- **Open WebUI（容器）**：必须让 MTPLX 监听非回环地址，否则连接被拒。

→ 采用 **修复方案 A**：把 MTPLX 改为 `--host 0.0.0.0`，并用防火墙把 8000 仅限本机+容器子网（见第 2 步）。
→ 若你不想放开绑定，见第 6 步 **pip 原生方案**（保持 `127.0.0.1`，零网络改动）。

---

## 1. 安装 OrbStack

```bash
# 方式一：Homebrew（推荐）
brew install --cask orbstack

# 方式二：官网下载 .dmg
# 访问 https://orbstack.dev 下载安装，首次打开完成初始化

# 验证（OrbStack 提供兼容的 docker CLI）
orbctl status
docker version
```

---

## 2. 修改 MTPLX 绑定 + 防火墙限制（修复方案 A）

编辑 `mtplx-serve.sh`，把第 35 行：
```
  --host 127.0.0.1 \
```
改为：
```
  --host 0.0.0.0 \
```
> 此改动在 Phase A（launchd 常驻）重新加载后才生效；当前会话内的子进程版仍跑旧绑定，重启 MTPLX 后再验收。

**防火墙限制（二选一）**
- **简单稳妥（推荐）**：系统设置 → 网络 → 防火墙 → 打开。配合家用路由器 NAT，外部设备默认不可达；本机回环与容器（本地）不受影响。
- **严格（pf anchor，高级）**：仅允许回环 + OrbStack 网桥子网访问 8000，其余拒绝。
  `/etc/pf.anchors/mtplx`：
  ```
  pass in on lo0 proto tcp from any to any port 8000
  pass in on bridge100 proto tcp from <ORBSTACK_BRIDGE_IP>/16 to any port 8000
  block in proto tcp from any to any port 8000
  ```
  ```bash
  sudo pfctl -ef /etc/pf.anchors/mtplx   # 临时加载（重启失效，仅供测试）
  ```
  ⚠️ `pfctl -e` 配置不当可能中断网络，请先确认 OrbStack 网桥子网（通常为 `<ORBSTACK_BRIDGE_IP>/16` 或 `10.x`），测试无误后再考虑持久化。

---

## 3. docker run 精确命令

> 前提：已完成第 2 步（MTPLX 绑 `0.0.0.0`）。`OPENAI_API_BASE_URL` 用 `host.docker.internal` 让容器回连宿主机 MTPLX。

```bash
docker run -d \
  -p 127.0.0.1:3000:8080 \
  --add-host=host.docker.internal:host-gateway \
  -v open-webui:/app/backend/data \
  -e WEBUI_SECRET_KEY="$(openssl rand -hex 32)" \
  -e OPENAI_API_BASE_URL=http://host.docker.internal:8000/v1 \
  -e OPENAI_API_KEY="$(cat <MTPLX_STATE_DIR>/api-key)" \
  -e RAG_EMBEDDING_ENGINE=openai \
  -e RAG_OPENAI_API_BASE_URL=http://host.docker.internal:8000/v1 \
  -e RAG_EMBEDDING_MODEL=Qwen3-Embedding-4B-4bit-DWQ \
  -e RAG_OPENAI_API_KEY="$(cat <MTPLX_STATE_DIR>/api-key)" \
  -e ENABLE_RAG_HYBRID_SEARCH=true \
  -e ENABLE_PERSISTENT_CONFIG=false \
  --name open-webui \
  --restart always \
  ghcr.io/open-webui/open-webui:main
```

字段说明：
- `-p 127.0.0.1:3000:8080`：UI 也只绑回环，**不暴露公网**。
- `--add-host=host.docker.internal:host-gateway`：容器内经此域名回连宿主机。
- `-v open-webui:/app/backend/data`：聊天/用户/设置持久化，更新不丢。
- `WEBUI_SECRET_KEY`：固定随机值，避免容器重建后全员登出（用 `openssl rand -hex 32` 生成一次并保存）。
- `OPENAI_API_BASE_URL` / `OPENAI_API_KEY`：注入默认 OpenAI 兼容**聊天**连接（等价于 UI 填写）。
- `RAG_EMBEDDING_ENGINE=openai` + `RAG_OPENAI_API_BASE_URL` + `RAG_EMBEDDING_MODEL`：**RAG 嵌入**独立指向 MTPLX（与聊天共用同一后端，但变量名不同，注意不是 `OPENAI_API_*`）。嵌入模型 `Qwen3-Embedding-4B-4bit-DWQ`，维度 2560 自动识别。
- `ENABLE_RAG_HYBRID_SEARCH=true`：语义 + BM25 混合检索，中文笔记召回更稳。
- `ENABLE_PERSISTENT_CONFIG=false`：**关键**——防止容器内已持久化的配置覆盖本环境变量（否则改 env 不生效）。

### 3b. 启用 vault 知识库问答（RAG，可替代 Copilot）
> **方案 Y 决策提示**：已选定方案 Y（Obsidian 原生），vault 对话由 **Copilot** 负责，Open WebUI 仅作通用对话工作台。本节 RAG 配置为**可选能力**，方案 Y 下**默认不启用**——若你不建 vault 知识库，可删除 docker run 中的 `RAG_EMBEDDING_ENGINE` / `RAG_OPENAI_API_BASE_URL` / `RAG_EMBEDDING_MODEL` / `RAG_OPENAI_API_KEY` / `ENABLE_RAG_HYBRID_SEARCH` 五个变量，使配置更精简、且避免与 Smart Connections 形成第二份 vault 索引。

Open WebUI 内置 Documents/RAG，可把 `brain` vault 作为知识库做"基于笔记的问答"，从而**取代 Copilot** 承担 vault 对话（仅在你想改用统一聊天面时启用）。上面 docker run 已注入 RAG 嵌入配置。

导入 vault 步骤：
1. 浏览器开 `http://127.0.0.1:3000` → 头像 → **Workspace → Knowledge** → 新建知识库（如 `brain`）。
2. `+ → Upload files`：把 `~/Documents/obsidian/brain` 下的 `.md` 批量加入（Web UI 不支持整目录拖入，需逐个/框选文件；文件多可借 API 批量 `POST /api/v1/files/`）。
3. 新建对话 → 输入框 `#` 选择该知识库（或绑到某模型）；提问即自动检索并引用来源。

⚠️ **同步缺口（务必知悉）**：Open WebUI RAG 是 vault 的**一份副本索引**，不会自动监听 Obsidian 编辑。笔记更新后需重新上传/重嵌对应文件，否则问答基于旧内容。若你要求"改完笔记立刻能问到"，Copilot（直读活 vault）更合适；若接受定期重导，Open WebUI 单聊天面更省事。

验收：上传后看 MTPLX 日志出现 `/v1/embeddings` 请求；对话引用了 `brain` 真实笔记段落。

---

## 4. 首次启动与模型接入

```bash
open http://127.0.0.1:3000
```
1. 注册**管理员账户**（首个注册者即管理员）。
2. 头像 → Settings → Admin Settings → Connections → `Manage OpenAI API Connections` 旁的 `+`。
   - URL：`http://host.docker.internal:8000/v1`
   - Key：`<MTPLX_STATE_DIR>/api-key` 内容
   - 保存后模型应从 `/v1/models` 自动列出；若未列出，手动添加 Model ID：`qwen3.6-35b-a3b-4bit`（2026-10-29 已从 27B 切换，旧 `mtplx-qwen38-27b-optimized-quality` 已不存在）
3. 新建对话，选该模型，验证流式输出。

---

## 5. 验收命令

```bash
# 容器健康
curl -s http://127.0.0.1:3000/health
# 容器日志（排错）
docker logs open-webui --tail 30
# 确认 MTPLX 仍在线（回环 + 非回环都应通，验证第 2 步生效）
curl -s -H "Authorization: Bearer $(cat <MTPLX_STATE_DIR>/api-key)" http://127.0.0.1:8000/v1/models | head -c 200
```

**PASS 条件**：`/health` 返回 ok；Web UI 能列出 `qwen3.6-35b-a3b-4bit` 并正常对话；仅 `127.0.0.1` 可访问。

---

## 6. 备选：pip 原生（保持 `127.0.0.1`，零网络改动）

若你不想放开 MTPLX 绑定，用 pip 在宿主机原生跑 Open WebUI，直接走 `127.0.0.1:8000`，无需容器网络：

```bash
VENV=<HOME>/.workbuddy/binaries/python/envs/openwebui
<HOME>/.workbuddy/binaries/python/versions/3.13.12/bin/python3 -m venv "$VENV"
"$VENV/bin/pip" install open-webui
OPENAI_API_BASE_URL=http://127.0.0.1:8000/v1 \
OPENAI_API_KEY="$(cat <MTPLX_STATE_DIR>/api-key)" \
"$VENV/bin/open-webui" serve --host 127.0.0.1 --port 3000
```
- 最安全（MTPLX 保持回环），但首次 `pip install open-webui` 依赖重、构建较慢。
- 访问方式同上：`http://127.0.0.1:3000`。

---

## 7. 安全要点

- 端口一律绑 `127.0.0.1`（UI 与 MTPLX），**绝不 `0.0.0.0` 暴露公网**；远程访问留到 Phase D 用 Tailscale，不在本步开放。
- MTPLX 放开到 `0.0.0.0` 仅为满足容器回连，必须配合第 2 步防火墙，否则等同暴露到 LAN。
- `WEBUI_SECRET_KEY` 固定保存；`<MTPLX_STATE_DIR>/api-key` 不提交仓库。
