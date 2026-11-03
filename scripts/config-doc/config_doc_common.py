"""配置文档共用模块：事实加载与脱敏。

本模块被 gen-config-manual.py（生成器）与 audit-config.py（审计）共用，
确保"脱敏规则"与"事实加载"只有一份实现，避免分叉漂移。

设计意图（配置即代码）：
- config-facts.yaml 是易变事实的单一事实源（SSOT）。
- 本地手册含真实路径 / IP；公开仓库版必须经 sanitize() 脱敏。
"""
from __future__ import annotations

import getpass
import os
import re
import socket

import yaml

# 真实家目录，如 /Users/ailab。脱敏时统一替换为 <HOME>。
HOME = os.path.expanduser("~")


def load_facts(path: str) -> dict:
    """读取 SSOT 事实源（YAML），返回字典。"""
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def resolve_facts_path(explicit: str | None = None) -> str:
    """解析事实源路径，保证同一份脚本在本地与仓库副本都能工作。

    优先级：环境变量 MTPLX_FACTS → 同目录 config-facts.yaml（真实） →
    同目录 config-facts.example.yaml（脱敏示例）。返回首个存在的文件；
    都不存在时回退到 config-facts.yaml（后续 load 会报错提示）。
    """
    if explicit:
        return explicit
    here = os.path.dirname(os.path.abspath(__file__))
    for name in ("config-facts.yaml", "config-facts.example.yaml"):
        candidate = os.path.join(here, name)
        if os.path.exists(candidate):
            return candidate
    return os.path.join(here, "config-facts.yaml")


def current_user_host() -> tuple[str, str]:
    """返回 (用户名, 主机名)，用于脱敏 user@host 形态。"""
    return getpass.getuser(), socket.gethostname()


def sanitize(text: str, bridge_ip: str | None = None) -> str:
    """将机器专属值替换为占位符，供公开仓库使用。

    脱敏规则（集中一处，便于审计）：
      - 家目录路径        → <HOME>
      - OrbStack 桥接 IP  → <ORBSTACK_BRIDGE_IP>
      - user@host         → <user>@<host>
      - 纯数字 PID        → <PID>
    """
    text = text.replace(HOME, "<HOME>")
    if bridge_ip:
        text = text.replace(bridge_ip, "<ORBSTACK_BRIDGE_IP>")
    user, host = current_user_host()
    # 仅替换与当前真实 user@host 完全一致的片段，避免误伤普通文本。
    text = re.sub(rf"\b{re.escape(user)}@{re.escape(host)}\b", "<user>@<host>", text)
    # PID 形态（如 "PID 656"）脱敏为 "PID <PID>"。
    text = re.sub(r"\bPID\s+\d+\b", "PID <PID>", text)
    return text
