# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from importlib.metadata import distribution
import sys

root = Path(SPECPATH)


def package_file(distribution_name, suffix):
    package = distribution(distribution_name)
    for item in package.files or []:
        if str(item).replace("\\", "/").endswith(suffix):
            return str(package.locate_file(item))
    raise RuntimeError(f"Required license missing: {distribution_name}/{suffix}")


license_data = [
    (str(root / "LICENSE"), "licenses"),
    (str(root / "THIRD_PARTY_NOTICES.md"), "licenses"),
    (str(root / "LICENSE-LGPL-3.0.txt"), "licenses/qt"),
    (str(root / "LICENSE-GPL-3.0.txt"), "licenses/qt"),
    (str(root / "LICENSE-OFL-1.1.txt"), "licenses/fonts/Vazirmatn"),
    (package_file("psutil", ".dist-info/LICENSE"), "licenses/psutil"),
    (package_file("cryptography", ".dist-info/licenses/LICENSE"), "licenses/cryptography"),
    (package_file("cryptography", ".dist-info/licenses/LICENSE.APACHE"), "licenses/cryptography"),
    (package_file("cryptography", ".dist-info/licenses/LICENSE.BSD"), "licenses/cryptography"),
    (str(Path(sys.base_prefix) / "LICENSE.txt"), "licenses/python"),
    (str(root / "SECURITY.md"), "docs"),
    (str(root / "PRIVACY.md"), "docs"),
    (str(root / "QUICKSTART.md"), "docs"),
    (str(root / "RELEASE_NOTES.md"), "docs"),
    (str(root / "SBOM.cdx.json"), "docs"),
]

a = Analysis(
    [str(root / "main.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[
        (str(root / "app" / "resources" / "fonts" / "*.ttf"), "app/resources/fonts"),
        (str(root / "app" / "resources" / "branding" / "*.svg"), "app/resources/branding"),
        (str(root / "app" / "resources" / "branding" / "*.png"), "app/resources/branding"),
        (str(root / "app" / "resources" / "app_icons" / "*.svg"), "app/resources/app_icons"),
        (str(root / "app" / "resources" / "domestic_traffic_catalog.json"), "app/resources"),
        *license_data,
    ],
    hiddenimports=[],
    excludes=[
        "app.services.config_parser",
        "app.services.subscription_service",
        "app.services.tunnel_service",
        "app.services.tunnel_storage_service",
        "app.services.warp_service",
    ],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LAGSHIFT",
    icon=str(root / "app" / "resources" / "branding" / "lagshift.ico"),
    version=str(root / "app" / "resources" / "version_info.txt"),
    console=False,
    # The UI stays unelevated. A schema-limited one-shot helper requests UAC only
    # for approved network changes.
    uac_admin=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="LAGSHIFT",
)
