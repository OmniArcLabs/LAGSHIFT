"""Encrypted and atomic persistence for imported connection profiles."""
from __future__ import annotations

import hashlib
import base64
import json
import os
from dataclasses import asdict
from typing import List

from app.models.tunnel_config import TunnelConfig
from app.services import app_paths, secure_storage


def _configs_file():
    return app_paths.migrated_file("tunnel_configs.json")


def _decode_document(text: str) -> list:
    document = json.loads(text)
    if isinstance(document, list):  # legacy plaintext format
        return document
    if document.get("version") != 2 or not document.get("protected"):
        raise ValueError("فرمت فایل کانفیگ شناخته‌شده نیست")
    plaintext = secure_storage.unprotect(document["payload"])
    return json.loads(plaintext.decode("utf-8"))


def load_configs() -> List[TunnelConfig]:
    path = _configs_file()
    if not path.exists():
        return []
    try:
        raw = _decode_document(path.read_text(encoding="utf-8"))
        configs = []
        changed = isinstance(json.loads(path.read_text(encoding="utf-8")), list)
        for item in raw:
            item.setdefault("source", "manual")
            if item.get("protocol") == "wireguard" and "warp" in item.get("name", "").lower():
                item["source"] = "warp"
                extra = item.setdefault("extra", {})
                if not extra.get("reserved") and extra.get("client_id"):
                    try:
                        extra["reserved"] = list(base64.b64decode(extra["client_id"]))
                        changed = True
                    except Exception:
                        pass
                if extra.get("client_ipv4") and "/" not in extra["client_ipv4"]:
                    extra["client_ipv4"] += "/32"
                    changed = True
            configs.append(TunnelConfig(**item))
        # Migrate legacy plaintext and incomplete WARP records after a successful read.
        if changed:
            warps = [c for c in configs if c.source == "warp"]
            if len(warps) > 1:
                newest = warps[-1]
                configs = [c for c in configs if c.source != "warp"] + [newest]
            save_configs(configs)
        return configs
    except Exception:
        return []


def save_configs(configs: List[TunnelConfig]) -> None:
    path = _configs_file()
    plaintext = json.dumps([asdict(c) for c in configs], ensure_ascii=False).encode("utf-8")
    document = {
        "version": 2,
        "protected": True,
        "payload": secure_storage.protect(plaintext),
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def config_fingerprint(config: TunnelConfig) -> str:
    identity = {
        "protocol": config.protocol,
        "address": config.address.lower(),
        "port": config.port,
        "raw": config.raw_link.strip(),
        "extra": config.extra,
    }
    payload = json.dumps(identity, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def add_config(configs: List[TunnelConfig], new_config: TunnelConfig) -> List[TunnelConfig]:
    configs = list(configs)
    if new_config.source == "warp":
        # WARP uses a shared Anycast endpoint. Keep one renewable profile instead
        # of presenting each account registration as a new "server".
        configs = [c for c in configs if not (
            c.source == "warp" or
            (c.protocol == "wireguard" and "warp" in c.name.lower())
        )]
    fingerprint = config_fingerprint(new_config)
    if not any(config_fingerprint(item) == fingerprint for item in configs):
        configs.append(new_config)
    save_configs(configs)
    return configs


def remove_config(configs: List[TunnelConfig], config_id: str) -> List[TunnelConfig]:
    result = [c for c in configs if c.id != config_id]
    save_configs(result)
    return result
