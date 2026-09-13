# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from importlib.metadata import distribution

root = Path(SPECPATH)


def package_licenses(distribution_name):
    package = distribution(distribution_name)
    rows = []
    for item in package.files or []:
        normalized = str(item).replace("\\", "/")
        if "/licenses/" in normalized.casefold() or normalized.casefold().endswith("/license"):
            rows.append((str(package.locate_file(item)), f"licenses/{distribution_name}"))
    return rows


datas = [
    (str(root / "app/resources/fonts/*.ttf"), "app/resources/fonts"),
    (str(root / "app/resources/branding/*.svg"), "app/resources/branding"),
    (str(root / "app/resources/branding/*.png"), "app/resources/branding"),
    (str(root / "app/resources/app_icons/*.svg"), "app/resources/app_icons"),
    (str(root / "app/resources/domestic_traffic_catalog.json"), "app/resources"),
    (str(root / "app/resources/iran_network_allocations.json"), "app/resources"),
    (str(root / "LICENSE"), "licenses"),
    (str(root / "THIRD_PARTY_NOTICES.md"), "licenses"),
    (str(root / "PRIVACY.md"), "docs"),
    (str(root / "SECURITY.md"), "docs"),
    (str(root / "QUICKSTART.md"), "docs"),
    *package_licenses("psutil"),
    *package_licenses("cryptography"),
]

a = Analysis(
    [str(root / "main.py")], pathex=[str(root)], binaries=[], datas=datas,
    hiddenimports=["PySide6.QtSvg"],
    excludes=[
        "app.services.config_parser", "app.services.subscription_service",
        "app.services.tunnel_service", "app.services.tunnel_storage_service",
        "app.services.warp_service", "winreg", "winsound",
    ],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="LAGSHIFT",
    console=False, target_arch=None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="LAGSHIFT")
app = BUNDLE(
    coll,
    name="LAGSHIFT.app",
    icon=str(root / "build/macos/LAGSHIFT.icns"),
    bundle_identifier="com.omniarc.lagshift",
    info_plist={
        "CFBundleDisplayName": "LAGSHIFT",
        "CFBundleShortVersionString": "1.2.0",
        "CFBundleVersion": "1200",
        "LSMinimumSystemVersion": "13.0",
        "LSApplicationCategoryType": "public.app-category.utilities",
        "NSHighResolutionCapable": True,
    },
)
