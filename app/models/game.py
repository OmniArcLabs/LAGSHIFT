"""مدل بازی‌های دلخواه کاربر"""
from dataclasses import dataclass, field


@dataclass
class Game:
    """یک بازی که کاربر به لیست خودش اضافه کرده"""
    name: str
    process_name: str = ""            # نام پروسه (برای تشخیص خودکار، مثلاً VALORANT-Win64-Shipping.exe)
    notes: str = ""
    preferred_dns_name: str = ""      # اسم پروفایل DNS ترجیحی (خالی = بدون ترجیح)
    preferred_tunnel_id: str = ""     # id کانفیگ تانل ترجیحی (خالی = بدون ترجیح)
    connection_mode: str = "balanced" # balanced | competitive | stability | udp
    connection_strategy: str = "smart" # smart | dns | tunnel
    route_mode: str = "process"        # process | system
    auto_connect: bool = False         # اتصال خودکار پس از شناسایی پروسه
    route_profile: dict = field(default_factory=dict)  # داده محلی Game Route Profile Beta
