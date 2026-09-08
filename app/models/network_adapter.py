"""مدل داده‌ی آداپتور شبکه"""
from dataclasses import dataclass, field
from typing import List


@dataclass
class NetworkAdapter:
    """نماینده‌ی یک آداپتور شبکه در ویندوز (وای‌فای، اترنت و ...)"""
    name: str                      # نام آداپتور (مثلاً Wi-Fi, Ethernet)
    description: str               # توضیح سخت‌افزاری
    is_enabled: bool = True        # آیا آداپتور فعاله
    current_dns: List[str] = field(default_factory=list)  # DNS فعلی


@dataclass
class DnsProfile:
    """یک پروفایل DNS آماده (مثلاً Cloudflare, Google, Gaming DNS)"""
    name: str
    primary: str
    secondary: str = ""
    description: str = ""
    doh_url: str = ""  # آدرس DNS-over-HTTPS، اگه خالی باشه یعنی DoH پشتیبانی نمی‌شه
    region: str = "global"  # global | iran
    purpose: str = "general"  # general | anti_sanction


# چند پروفایل پیش‌فرض معروف برای شروع + DNSهای بیشتر مخصوص گیمینگ/ایران (فاز ۴)
DEFAULT_DNS_PROFILES: List[DnsProfile] = [
    DnsProfile("Cloudflare", "1.1.1.1", "1.0.0.1", "DNS جهانی سریع و امن", "https://1.1.1.1/dns-query"),
    DnsProfile("Google", "8.8.8.8", "8.8.4.4", "DNS جهانی پایدار و شناخته‌شده", "https://dns.google/dns-query"),
    DnsProfile("Quad9 Secure", "9.9.9.9", "149.112.112.112", "DNS جهانی امن با مسدودسازی دامنه‌های مخرب", "https://dns.quad9.net/dns-query"),
    DnsProfile("AdGuard Unfiltered", "94.140.14.140", "94.140.14.141", "DNS جهانی بدون فیلتر؛ مناسب بازی و CDN", "https://unfiltered.adguard-dns.com/dns-query"),
    DnsProfile("OpenDNS", "208.67.222.222", "208.67.220.220", "DNS جهانی عمومی"),
    DnsProfile("Shecan", "178.22.122.100", "185.51.200.2", "DNS ایرانی مخصوص دسترسی به سرویس‌های تحریم‌شده", "https://free.shecan.ir/dns-query", "iran", "anti_sanction"),
    DnsProfile("Electro", "78.157.42.100", "78.157.42.101", "DNS ایرانی مخصوص بازی و رفع تحریم", "", "iran", "anti_sanction"),
    DnsProfile("403 Online", "10.202.10.202", "10.202.10.102", "DNS ایرانی برای سرویس‌های تحریم‌شده توسعه‌دهندگان", "https://dns.403.online/dns-query", "iran", "anti_sanction"),
    DnsProfile("Radar Game", "10.202.10.10", "10.202.10.11", "DNS ایرانی مخصوص بازی", "", "iran", "anti_sanction"),
    DnsProfile("Begzar", "185.55.226.26", "185.55.225.25", "DNS ایرانی برای دسترسی به سرویس‌های تحریم‌شده", "", "iran", "anti_sanction"),
    DnsProfile("Shelter", "91.92.255.160", "91.92.255.242", "DNS ایرانی برای دسترسی به سرویس‌های تحریم‌شده", "", "iran", "anti_sanction"),
]
