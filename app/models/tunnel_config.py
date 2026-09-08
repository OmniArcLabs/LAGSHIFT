"""مدل داده‌ی کانفیگ اتصال.

مدل عمداً مستقل از هسته است؛ انتخاب Xray یا sing-box در لایه‌ی سرویس انجام
می‌شود تا رابط کاربر درگیر نام پروتکل و موتور اجرا نشود.
"""
from dataclasses import dataclass, field


@dataclass
class TunnelConfig:
    """نماینده‌ی یک کانفیگ import‌شده یا ساخته‌شده توسط برنامه."""
    id: str                 # شناسه یکتا (برای ذخیره و انتخاب در لیست)
    name: str                # نام نمایشی (remark)
    protocol: str             # vmess | vless | trojan | shadowsocks | socks | wireguard | hysteria2 | tuic
    address: str              # آی‌پی یا دامنه‌ی سرور
    port: int
    raw_link: str = ""          # فقط برای import مجدد؛ در دیسک به‌صورت محافظت‌شده ذخیره می‌شود
    extra: dict = field(default_factory=dict)
    source: str = "manual"
