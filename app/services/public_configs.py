"""
لیست منابع کانفیگ عمومی/کامیونیتی — این‌ها سرور خود اپ نیستن،
صرفاً لینک به منابع متن‌باز و شناخته‌شده‌ای هستن که کانفیگ‌های V2Ray/Xray
رایگان و به‌روز منتشر می‌کنن. کاربر باید خودش لینک نهایی رو از اونجا کپی و
تو تب «تانل» import کنه.

⚠️ هشدار مهم که باید تو UI هم نشون داده بشه:
این منابع توسط این اپ مدیریت یا تضمین نمی‌شن. پایداری، امنیت و در دسترس بودن‌شون
متغیره. استفاده از کانفیگ شخصی همچنان پیشنهاد اصلیه.
"""
from dataclasses import dataclass


@dataclass
class PublicConfigSource:
    name: str
    description: str
    url: str


PUBLIC_CONFIG_SOURCES = [
    PublicConfigSource(
        name="V2Ray-Configs (کامیونیتی متن‌باز)",
        description="لیست به‌روزشونده‌ی کانفیگ‌های رایگان V2Ray/Xray، جمع‌آوری‌شده از منابع عمومی",
        url="https://github.com/topics/v2ray-configs",
    ),
    PublicConfigSource(
        name="Cloudflare WARP (رایگان و رسمی)",
        description="سرویس رسمی Cloudflare — امن‌تر از منابع ناشناس، ولی رفع تحریم تضمین‌شده نداره",
        url="https://1.1.1.1/",
    ),
]

# سقف پیشنهادی روزانه (فقط نمایشی؛ اجرای فنی/enforcement نداره)
SUGGESTED_DAILY_LIMIT_MB = 2000  # ۲ گیگابایت
