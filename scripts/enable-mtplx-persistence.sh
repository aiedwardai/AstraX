#!/bin/bash
# ==============================================================================
# enable-mtplx-persistence.sh  （通用模板 · 不含任何机器专属路径）
#
# 一键将 MTPLX + 中继接入 macOS launchd 常驻（7×24 自愈、登录自启）。
#
# ⚠️ 必须在【真实 Terminal.app】里运行，不要在任何自动化沙箱 shell 内执行。
#    （沙箱 shell 调 launchctl 会被内核拒 EIO，必然失败。）
#
# 为什么需要它：
#   若 MTPLX 与中继是「手动 nohup」进程，终端/会话一关就可能被回收，
#   OpenWebUI 会失去后端、前端失联。本脚本把它们交给 launchd：开机/登录自动拉起 + 崩溃自愈。
#
# 使用前提（请先按你的环境修改下方变量）：
#   DEPLOY_DIR   —— 部署目录（存放 mtplx-serve.sh / mtplx-relay.py 的地方）
#   PY_BIN       —— 运行中继的 Python 解释器（需 3.13+，且含标准库 socket/threading）
#   plist 文件   —— ~/Library/LaunchAgents/com.user.mtplx.plist
#                  与 com.user.mtplx-relay.plist 需事先存在
#                  且 relay plist 的 MTPLX_RELAY_BIND_IP 填好 OrbStack bridge100 的真实 IP
#
# 安全动作：
#   1) 先优雅停掉两个手动进程（避免与 launchd 实例抢端口）
#   2) 若 OrbStack 没起，先启动（中继与容器都依赖其桥接 IP）
#   3) 校验桥接 IP 未变化，否则拒绝继续（防止中继绑错地址起不来）
#   4) 用 bootstrap+enable 加载两个 plist（替代已废弃的 launchctl load，规避 EIO）
#   5) 验收：端口监听 + /v1/models 出字
#   6) 若 launchd 起不来，自动回退为手动进程，绝不让你失去服务
# ==============================================================================

set -u

# —— 按你的环境修改 ——
DEPLOY_DIR="$HOME/path/to/deploy"            # 例如存放 mtplx-serve.sh / mtplx-relay.py 的目录
PY_BIN="python3"                            # 或绝对路径：/opt/.../python3.13/bin/python3

# —— 以下通常无需改 ——
PLIST_DIR="$HOME/Library/LaunchAgents"
MTPLX_PLIST="$PLIST_DIR/com.user.mtplx.plist"
RELAY_PLIST="$PLIST_DIR/com.user.mtplx-relay.plist"
API_KEY_FILE="$HOME/.mtplx/api-key"
RELAY_LOG="$HOME/.mtplx/logs/relay.out.log"
SERVE_LOG="$HOME/.mtplx/logs/serve.log"

log()  { echo "[$(date +%H:%M:%S)] $*"; }
die()  { log "❌ $*"; exit 1; }

# ----------------------------------------------------------------------------
# 0. 前置检查
# ----------------------------------------------------------------------------
[ -f "$MTPLX_PLIST" ] || die "找不到 $MTPLX_PLIST（请先放置 plist）"
[ -f "$RELAY_PLIST" ] || die "找不到 $RELAY_PLIST（请先放置 plist）"
command -v orbctl >/dev/null 2>&1 || die "未安装 orbctl（OrbStack）"
command -v launchctl >/dev/null 2>&1 || die "未安装 launchctl"
[ -x "$PY_BIN" ] || command -v "$PY_BIN" >/dev/null 2>&1 || die "PY_BIN 不可执行: $PY_BIN"

# ----------------------------------------------------------------------------
# 1. 确保 OrbStack 运行（中继/容器依赖桥接 IP）
# ----------------------------------------------------------------------------
log "=== 1/6 确认 OrbStack ==="
if ! orbctl status 2>/dev/null | grep -qi running; then
  log "OrbStack 未运行，尝试启动..."
  orbctl start
  for i in $(seq 1 24); do
    orbctl status 2>/dev/null | grep -qi running && break
    sleep 5
  done
fi
BIP=$(ifconfig bridge100 2>/dev/null | awk '/inet /{print $2}')
log "OrbStack: $(orbctl status 2>/dev/null | head -1) | bridge100 IP: ${BIP:-未取到}"

# ----------------------------------------------------------------------------
# 2. 桥接 IP 校验（plist 里的绑定地址必须与实测一致）
# ----------------------------------------------------------------------------
log "=== 2/6 校验桥接 IP ==="
CUR=$(grep -A1 'MTPLX_RELAY_BIND_IP</key>' "$RELAY_PLIST" 2>/dev/null | grep -oE '[0-9.]+' | head -1)
if [ -z "$BIP" ]; then
  die "取不到 bridge100 IP，OrbStack 桥接未就绪，中止。"
fi
if [ "$CUR" != "$BIP" ]; then
  die "桥接 IP 已变：plist=$CUR 实测=$BIP。请先编辑 $RELAY_PLIST 的 MTPLX_RELAY_BIND_IP 再运行本脚本。"
fi
log "桥接 IP 一致 ($BIP) ✅"

# ----------------------------------------------------------------------------
# 3. 停掉手动 nohup 进程（先腾端口，再交给 launchd）
# ----------------------------------------------------------------------------
log "=== 3/6 停手动进程（腾端口）==="
pkill -f "mtplx-relay.py"     2>/dev/null && log "已停手动 relay"  || log "无手动 relay"
pkill -f "mtplx.server.openai" 2>/dev/null && log "已停手动 MTPLX" || log "无手动 MTPLX"
sleep 2

# ----------------------------------------------------------------------------
# 4. 加载 plist 到 launchd（bootstrap 替代 load，规避 EIO）
# ----------------------------------------------------------------------------
log "=== 4/6 加载 plist 到 launchd（bootstrap 替代 load，规避 EIO）==="
UID=$(id -u)
MTPLX_LABEL="com.user.mtplx"
RELAY_LABEL="com.user.mtplx-relay"
launchctl bootout "gui/$UID/$MTPLX_LABEL" 2>/dev/null
launchctl bootout "gui/$UID/$RELAY_LABEL" 2>/dev/null
launchctl bootstrap "gui/$UID" "$MTPLX_PLIST" 2>&1 && launchctl enable "gui/$UID/$MTPLX_LABEL" && log "✅ MTPLX 已 bootstrap+enable" || log "⚠️ MTPLX bootstrap 失败（见上）"
launchctl bootstrap "gui/$UID" "$RELAY_PLIST" 2>&1 && launchctl enable "gui/$UID/$RELAY_LABEL" && log "✅ relay 已 bootstrap+enable"   || log "⚠️ relay bootstrap 失败（见上）"

# ----------------------------------------------------------------------------
# 5. 验收（等待启动 + 端口 + 模型）
# ----------------------------------------------------------------------------
log "=== 5/6 验收（最多等 ~40s 让权重加载）==="
API_KEY=$(cat "$API_KEY_FILE" 2>/dev/null)
MODEL_OK=""
for i in $(seq 1 20); do
  if curl -s --noproxy '*' -H "Authorization: Bearer $API_KEY" \
       http://127.0.0.1:8000/v1/models 2>/dev/null | grep -q "qwen3.6-35b-a3b-4bit"; then
    MODEL_OK="yes"; break
  fi
  sleep 2
done

RELAY_LINES=$(lsof -nP -iTCP:8000 -sTCP:LISTEN 2>/dev/null | grep -c "bridge100" || true)
OWUI_OK=$(curl -s --noproxy '*' http://127.0.0.1:3000/health 2>/dev/null)

if [ "$MODEL_OK" = "yes" ]; then
  log "✅ MTPLX 已通过 launchd 起来，模型 qwen3.6-35b-a3b-4bit 在线"
else
  log "⚠️ launchd 版 MTPLX 未在预期时间内就绪，触发手动回退..."
fi
log "relay 桥接监听计数: $RELAY_LINES（应 ≥1）"
log "OWUI /health: $OWUI_OK"

# ----------------------------------------------------------------------------
# 6. 回退保障：若 launchd 没起来，恢复手动进程，绝不让服务消失
# ----------------------------------------------------------------------------
log "=== 6/6 回退保障 ==="
if [ "$MODEL_OK" != "yes" ]; then
  log "launchd 起不来 → 重启手动 MTPLX / relay 兜底"
  nohup "$DEPLOY_DIR/mtplx-serve.sh" > "$SERVE_LOG" 2>&1 &
  sleep 1
  cd "$HOME/.mtplx" 2>/dev/null || true
  MTPLX_RELAY_BIND_IP="$BIP" \
    "$PY_BIN" "$DEPLOY_DIR/mtplx-relay.py" > "$RELAY_LOG" 2>&1 &
  log "已重启手动兜底进程，请稍候在浏览器验证 http://127.0.0.1:3000"
  log "（launchd 失败多为沙箱/权限问题，真实 Terminal 直接运行本脚本通常成功）"
else
  log "✅ 全链路已由 launchd 接管。可关闭本终端，服务将持续运行。"
fi
log "=== 完成 ==="
