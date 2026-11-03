#!/usr/bin/env python3
"""配置实时审计（安全网 · 只读不写）。

探测本机真实状态（launchctl / plist / 模型缓存 / 桥接 IP），与 config-facts.yaml 对比，
输出"文档 vs 现实"差异清单。脚本**只读取、绝不修改**任何配置。

用法：
    python3 audit-config.py
退出码：
    0 = 无漂移（文档与真实状态一致）
    1 = 检测到漂移（供定时任务判定后提醒）
设计说明（沙箱友好）：
    launchctl / du 等在 WorkBuddy 沙箱内可能被内核拒绝（EIO），此时对应检查标记为
    [SKIP] 而非 [DRIFT]，避免误报；真正的不一致（如模型缺失、桥接 IP 变更）才会告警。
"""
from __future__ import annotations

import os
import plistlib
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import config_doc_common as cdc  # noqa: E402

FACTS_PATH = cdc.resolve_facts_path(os.environ.get("MTPLX_FACTS"))
MODELS_DIR = os.path.expanduser("~/.mtplx/models")
PLIST_DIR = os.path.expanduser("~/Library/LaunchAgents")


def _run(cmd: list[str]) -> str:
    """执行命令并返回 stdout；失败返回空串（供上层判定 SKIP）。"""
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return res.stdout
    except Exception:
        return ""


def launchctl_labels() -> set[str] | None:
    """返回已加载的 launchd label 集合；无法执行则返回 None（SKIP）。"""
    out = _run(["launchctl", "list"])
    if not out:
        return None
    labels: set[str] = set()
    for line in out.splitlines():
        parts = line.split()
        if parts and parts[-1].startswith("com.user"):
            labels.add(parts[-1])
    return labels


def read_plist(label: str) -> dict | None:
    path = os.path.join(PLIST_DIR, label + ".plist")
    if not os.path.exists(path):
        return None
    with open(path, "rb") as fh:
        return plistlib.load(fh)


def plist_relay_bind_ip(plist: dict | None) -> str | None:
    if not plist:
        return None
    return plist.get("EnvironmentVariables", {}).get("MTPLX_RELAY_BIND_IP")


def bridge100_ip() -> str | None:
    out = _run(["ifconfig", "bridge100"])
    m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", out)
    return m.group(1) if m else None


def model_cache_sizes() -> dict[str, float]:
    """返回 {归一化目录名: 体积GB}；目录不可读或 du 失败则整体返回空（SKIP）。"""
    if not os.path.isdir(MODELS_DIR):
        return {}
    result: dict[str, float] = {}
    for name in os.listdir(MODELS_DIR):
        d = os.path.join(MODELS_DIR, name)
        if not os.path.isdir(d):
            continue
        out = _run(["du", "-sk", d])
        if not out:
            return {}  # du 失败（沙箱限制）→ 整体跳过模型体积核验
        try:
            kb = int(out.split()[0])
            result[name] = round(kb / (1024 * 1024), 1)
        except (ValueError, IndexError):
            return {}
    return result


def normalize(model_id: str) -> str:
    """将 HuggingFace 模型 ID 归一化为本地缓存目录名（'/' → '--'）。"""
    return model_id.replace("/", "--")


def main() -> None:
    facts = cdc.load_facts(FACTS_PATH)
    net = facts["network"]
    ld = facts["launchd"]
    drifts: list[str] = []
    lines: list[str] = []

    # 1) launchd 加载状态
    labels = launchctl_labels()
    if labels is None:
        lines.append("[SKIP] launchd 状态需在真实 Terminal 复核（沙箱限制 EIO）")
    else:
        for label in [ld["mtplx_label"], ld["relay_label"]]:
            ok = label in labels
            lines.append(
                f"[{'OK' if ok else 'DRIFT'}] launchd 加载 {label}: "
                f"{'已加载' if ok else '未加载（期望常驻）'}"
            )
            if not ok:
                drifts.append(f"launchd 未加载 {label}")

    # 2) 中继绑定 IP：facts ↔ plist ↔ 真实 bridge100
    relay_plist = read_plist(ld["relay_label"])
    plist_ip = plist_relay_bind_ip(relay_plist)
    actual_ip = bridge100_ip()
    lines.append(f"[INFO] facts 中继绑定 IP: {net['relay_bind_ip']}")
    if plist_ip is None:
        lines.append("[SKIP] relay plist 未找到（无法比对绑定 IP）")
    else:
        ok = plist_ip == net["relay_bind_ip"]
        lines.append(f"[{'OK' if ok else 'DRIFT'}] relay plist 绑定 IP: {plist_ip}")
        if not ok:
            drifts.append(f"relay plist 绑定 IP={plist_ip} ≠ facts={net['relay_bind_ip']}")
    if actual_ip:
        ok = actual_ip == net["relay_bind_ip"]
        lines.append(f"[{'OK' if ok else 'WARN'}] bridge100 实际 IP: {actual_ip}")
        if not ok:
            drifts.append(
                f"bridge100 实际 IP={actual_ip} ≠ facts={net['relay_bind_ip']}（OrbStack 可能重置桥接）"
            )
    else:
        lines.append("[WARN] bridge100 不存在（OrbStack 未运行？）")

    # 3) 模型缓存：facts 期望 vs 磁盘
    caches = model_cache_sizes()
    if not caches:
        lines.append("[SKIP] 模型缓存体积核验需在真实 Terminal 复核（沙箱限制）")
    else:
        for m in facts["models"]:
            if m.get("status") not in ("online", "cached"):
                continue
            norm = normalize(m["id"])
            if norm in caches:
                actual = caches[norm]
                exp = float(m["size_gb"])
                ok = abs(actual - exp) <= max(2.0, exp * 0.15)
                tag = "OK" if ok else "WARN"
                lines.append(
                    f"[{tag}] 模型 {m['id']}: 磁盘 {actual} GB（期望 ~{exp} GB）"
                )
                if not ok:
                    drifts.append(f"模型 {m['id']} 体积 {actual} GB 与期望 {exp} GB 偏差过大")
            else:
                lines.append(f"[DRIFT] 模型 {m['id']}: 磁盘缓存缺失（期望 {m['status']}）")
                drifts.append(f"模型 {m['id']} 磁盘缓存缺失")

    # 4) api-key 存在性
    key_path = os.path.expanduser(net["api_key_path"])
    ok = os.path.exists(key_path)
    lines.append(f"[{'OK' if ok else 'DRIFT'}] api-key 存在: {net['api_key_path']}")
    if not ok:
        drifts.append("api-key 文件缺失")

    print("=== MTPLX 配置审计（文档 vs 现实） ===")
    for ln in lines:
        print(ln)
    print()
    if drifts:
        print(f"STATUS: DRIFT（{len(drifts)} 项）")
        for d in drifts:
            print(f"  - {d}")
        sys.exit(1)
    print("STATUS: OK（文档与真实状态一致）")
    sys.exit(0)


if __name__ == "__main__":
    main()
