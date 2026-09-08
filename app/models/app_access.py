"""مدل پروفایل‌های آماده برای دسترسی برنامه‌ها و لانچرها."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AppAccessProfile:
    id: str
    name: str
    symbol: str
    color: str
    description: str
    process_names: tuple[str, ...]
    registry_names: tuple[str, ...]
    login_domains: tuple[str, ...]
    download_domains: tuple[str, ...]
    service_domains: tuple[str, ...] = ()
    category: str = "launcher"
    web_only: bool = False
    launch_url: str = ""

    def domains_for(self, mission: str) -> tuple[str, ...]:
        if mission == "login":
            values = self.login_domains
        elif mission == "download":
            values = self.download_domains or self.service_domains
        else:
            values = self.login_domains + self.service_domains + self.download_domains
        return tuple(dict.fromkeys(domain.strip().lower() for domain in values if domain.strip()))


DEFAULT_APP_ACCESS_PROFILES: tuple[AppAccessProfile, ...] = (
    AppAccessProfile(
        id="discord", name="Discord", symbol="DS", color="#5865F2",
        description="ورود، API، CDN و Voice",
        process_names=("discord.exe",), registry_names=("discord",),
        login_domains=("discord.com", "gateway.discord.gg"),
        download_domains=("cdn.discordapp.com",), service_domains=("discordapp.com",),
        category="communication",
    ),
    AppAccessProfile(
        id="steam", name="Steam", symbol="ST", color="#66C0F4",
        description="ورود، Store، Community و دانلود",
        process_names=("steam.exe", "steamwebhelper.exe"), registry_names=("steam",),
        login_domains=("store.steampowered.com", "steamcommunity.com"),
        download_domains=("cdn.cloudflare.steamstatic.com", "clientconfig.akamai.steamstatic.com"),
        service_domains=("api.steampowered.com",),
    ),
    AppAccessProfile(
        id="epic", name="Epic Games", symbol="EP", color="#FFFFFF",
        description="حساب کاربری، Store و دانلود",
        process_names=("epicgameslauncher.exe", "epicwebhelper.exe"), registry_names=("epic games launcher",),
        login_domains=("www.epicgames.com", "account-public-service-prod.ol.epicgames.com"),
        download_domains=("download.epicgames.com",),
        service_domains=("launcher-public-service-prod06.ol.epicgames.com",),
    ),
    AppAccessProfile(
        id="ea", name="EA app", symbol="EA", color="#FF4747",
        description="ورود حساب، Library و سرویس آنلاین",
        process_names=("eadesktop.exe", "ealauncher.exe", "eabackgroundservice.exe"),
        registry_names=("ea app", "electronic arts"),
        login_domains=("accounts.ea.com", "www.ea.com"),
        download_domains=("origin-a.akamaihd.net",),
        service_domains=("service-aggregation-layer.juno.ea.com",),
    ),
    AppAccessProfile(
        id="battlenet", name="Battle.net", symbol="BN", color="#148EFF",
        description="ورود، Agent و دریافت بازی",
        process_names=("battle.net.exe",), registry_names=("battle.net", "blizzard"),
        login_domains=("account.battle.net", "battle.net"),
        download_domains=("blizzard.com",), service_domains=("oauth.battle.net",),
    ),
    AppAccessProfile(
        id="ubisoft", name="Ubisoft Connect", symbol="UB", color="#00A6FF",
        description="ورود، Store و Ubisoft Services",
        process_names=("ubisoftconnect.exe", "upc.exe"), registry_names=("ubisoft connect",),
        login_domains=("connect.ubisoft.com", "account.ubisoft.com"),
        download_domains=("static3.cdn.ubi.com",), service_domains=("public-ubiservices.ubi.com",),
    ),
    AppAccessProfile(
        id="spotify", name="Spotify", symbol="SP", color="#1ED760",
        description="ورود، API و پخش آنلاین",
        process_names=("spotify.exe",), registry_names=("spotify",),
        login_domains=("accounts.spotify.com", "open.spotify.com"),
        download_domains=("audio-fa.scdn.co",), service_domains=("api.spotify.com",), category="media",
    ),
    AppAccessProfile(
        id="xbox", name="Xbox", symbol="XB", color="#107C10",
        description="ورود Microsoft، Store و Gaming Services",
        process_names=("xboxpcapp.exe",), registry_names=("xbox", "gaming services"),
        login_domains=("login.live.com", "www.xbox.com"),
        download_domains=("displaycatalog.mp.microsoft.com",), service_domains=("xsts.auth.xboxlive.com",),
    ),
    AppAccessProfile(
        id="riot", name="Riot Client", symbol="RT", color="#D1363A",
        description="ورود، Client و سرویس‌های Riot",
        process_names=("riotclientservices.exe", "riotclientux.exe"), registry_names=("riot client",),
        login_domains=("auth.riotgames.com", "www.riotgames.com"),
        download_domains=("lol.dyn.riotcdn.net",), service_domains=("clientconfig.rpg.riotgames.com",),
    ),
    AppAccessProfile(
        id="rockstar", name="Rockstar Games", symbol="RS", color="#FCAF17",
        description="Social Club، Launcher و دانلود",
        process_names=("rockstarservice.exe", "socialclubhelper.exe"),
        registry_names=("rockstar games launcher", "social club"),
        login_domains=("signin.rockstargames.com", "socialclub.rockstargames.com"),
        download_domains=("patches.rockstargames.com", "gamedownloads-rockstargames-com.akamaized.net"),
        service_domains=("prod.ros.rockstargames.com",),
    ),
    AppAccessProfile(
        id="soundcloud", name="SoundCloud", symbol="SC", color="#FF5500",
        description="ورود، API و پخش موسیقی",
        process_names=("soundcloud.exe",), registry_names=("soundcloud",),
        login_domains=("soundcloud.com", "secure.soundcloud.com"),
        download_domains=("cf-media.sndcdn.com", "i1.sndcdn.com"),
        service_domains=("api-v2.soundcloud.com",), category="media", web_only=True,
        launch_url="https://soundcloud.com/",
    ),
    AppAccessProfile(
        id="vscode", name="VS Code", symbol="<>" , color="#23A9F2",
        description="ورود، Marketplace، افزونه‌ها و آپدیت",
        process_names=("code.exe", "code - insiders.exe"),
        registry_names=("microsoft visual studio code", "visual studio code insiders"),
        login_domains=("github.com", "login.microsoftonline.com"),
        download_domains=("update.code.visualstudio.com", "vscode.download.prss.microsoft.com"),
        service_domains=("marketplace.visualstudio.com", "api.github.com"), category="developer",
    ),
    AppAccessProfile(
        id="unity", name="Unity", symbol="UN", color="#20252B",
        description="Unity Hub، ورود، لایسنس، Package Manager و دانلود Editor",
        process_names=("unity hub.exe", "unity.exe"),
        registry_names=("unity hub", "unity editor"),
        login_domains=("id.unity.com", "api.unity.com"),
        download_domains=("download.unity3d.com", "packages.unity.com"),
        service_domains=("license.unity3d.com", "services.api.unity.com"), category="developer",
    ),
    AppAccessProfile(
        id="amd", name="AMD Adrenalin", symbol="AMD", color="#ED1C24",
        description="بررسی آپدیت و دریافت امن درایورهای AMD",
        process_names=("radeonsoftware.exe", "amdsoftware.exe"),
        registry_names=("amd software", "amd adrenalin"),
        login_domains=("www.amd.com",),
        download_domains=("drivers.amd.com", "download.amd.com"),
        service_domains=("www.amd.com",), category="driver",
    ),
    AppAccessProfile(
        id="nvidia", name="NVIDIA", symbol="NV", color="#76B900",
        description="ورود NVIDIA App، بررسی آپدیت و دانلود درایور",
        process_names=("nvidia app.exe", "nvidiaapp.exe"),
        registry_names=("nvidia app", "nvidia geforce experience"),
        login_domains=("login.nvgs.nvidia.com", "www.nvidia.com"),
        download_domains=("international.download.nvidia.com", "us.download.nvidia.com"),
        service_domains=("api-prod.nvidia.com", "ota.nvidia.com"), category="driver",
    ),
    AppAccessProfile(
        id="chatgpt", name="ChatGPT", symbol="AI", color="#10A37F",
        description="ورود، وب‌اپ و API سرویس‌های OpenAI",
        process_names=("chatgpt.exe",), registry_names=("chatgpt", "openai"),
        login_domains=("auth.openai.com", "chatgpt.com"),
        download_domains=("cdn.oaistatic.com", "files.oaiusercontent.com"),
        service_domains=("api.openai.com", "ab.chatgpt.com"), category="ai", web_only=True,
        launch_url="https://chatgpt.com/",
    ),
    AppAccessProfile(
        id="claude", name="Claude", symbol="CL", color="#D97757",
        description="ورود، وب‌اپ و API سرویس Anthropic",
        process_names=("claude.exe",), registry_names=("claude", "anthropic"),
        login_domains=("claude.ai", "console.anthropic.com"),
        download_domains=("claude.ai",),
        service_domains=("api.anthropic.com", "anthropic.com"), category="ai", web_only=True,
        launch_url="https://claude.ai/",
    ),
    AppAccessProfile(
        id="gemini", name="Gemini", symbol="GM", color="#4E8CFF",
        description="ورود و سرویس‌های وب و API گوگل Gemini",
        process_names=(), registry_names=(),
        login_domains=("gemini.google.com", "accounts.google.com"),
        download_domains=("lh3.googleusercontent.com",),
        service_domains=("generativelanguage.googleapis.com",), category="ai", web_only=True,
        launch_url="https://gemini.google.com/",
    ),
    AppAccessProfile(
        id="copilot", name="Copilot", symbol="CP", color="#7B61FF",
        description="ورود و سرویس وب Microsoft Copilot",
        process_names=("copilot.exe",), registry_names=("microsoft copilot",),
        login_domains=("copilot.microsoft.com", "login.live.com"),
        download_domains=("r.bing.com",),
        service_domains=("edgeservices.bing.com", "sydney.bing.com"), category="ai", web_only=True,
        launch_url="https://copilot.microsoft.com/",
    ),
    AppAccessProfile(
        id="perplexity", name="Perplexity", symbol="PX", color="#20B8A6",
        description="ورود، جست‌وجو و API سرویس Perplexity",
        process_names=("perplexity.exe",), registry_names=("perplexity",),
        login_domains=("www.perplexity.ai",),
        download_domains=("pplx-res.cloudinary.com",),
        service_domains=("api.perplexity.ai",), category="ai", web_only=True,
        launch_url="https://www.perplexity.ai/",
    ),
)
