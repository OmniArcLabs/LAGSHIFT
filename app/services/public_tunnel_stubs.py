"""Fail-closed placeholders used only by the public package.

They keep the shared view-model source importable while legacy custom-tunnel,
subscription and undocumented registration modules are excluded from the build.
"""
from __future__ import annotations

from types import SimpleNamespace


def _blocked(*_args, **_kwargs):
    raise RuntimeError("این قابلیت در نسخه عمومی LAGSHIFT وجود ندارد")


class NullTunnelProcess:
    def start(self, *_args, **_kwargs):
        return False, "موتور تانل در نسخه عمومی وجود ندارد"

    def stop(self):
        return None

    def is_running(self):
        return False


def _unavailable(*_args, **_kwargs):
    return SimpleNamespace(
        available=False, latency_ms=-1, jitter_ms=-1, packet_loss_pct=100.0,
        error="موتور تانل در نسخه عمومی وجود ندارد",
    )


class ConfigParser:
    parse_link = staticmethod(_blocked)


class Subscription:
    fetch = staticmethod(_blocked)


class Storage:
    load_configs = staticmethod(lambda: [])
    add_config = staticmethod(lambda configs, _config: list(configs))
    remove_config = staticmethod(
        lambda configs, config_id: [item for item in configs if item.id != config_id]
    )


class Tunnel:
    HTTP_PORT = 10809
    TunnelProcess = NullTunnelProcess
    probe_config = staticmethod(_unavailable)
    trial_config = staticmethod(_unavailable)
    measure_http_path = staticmethod(_unavailable)


class LegacyWarp:
    WIREGUARD_PORTS = ()
    register_warp_account = staticmethod(_blocked)


config_parser = ConfigParser()
subscription_service = Subscription()
tunnel_storage_service = Storage()
tunnel_service = Tunnel()
warp_service = LegacyWarp()
