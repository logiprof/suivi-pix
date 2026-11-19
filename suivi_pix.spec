# -*- mode: python ; coding: utf-8 -*-
# Construction de l'app Mac :  python3 -m PyInstaller --noconfirm suivi_pix.spec
import os
import re

with open(os.path.join("src", "server.py"), encoding="utf-8") as f:
    VERSION = re.search(r'^VERSION = "([^"]+)"', f.read(), re.M).group(1)

a = Analysis(
    ["src/server.py"],
    datas=[("src/index.html", ".")],
    excludes=["tkinter", "unittest", "pydoc", "doctest", "lib2to3"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Suivi Pix",
    console=False,
    target_arch=os.environ.get("TARGET_ARCH", "universal2"),
    argv_emulation=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Suivi Pix")
app = BUNDLE(
    coll,
    name="Suivi Pix.app",
    icon="assets/AppIcon.icns",
    bundle_identifier="ch.logiprof.suivi-pix",
    version=VERSION,
    info_plist={
        "CFBundleName": "Suivi Pix",
        "CFBundleDisplayName": "Suivi Pix",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "LSMinimumSystemVersion": "11.0",
        # Pas d'icone dans le Dock : l'interface est la page du navigateur
        "LSUIElement": True,
        "NSHighResolutionCapable": True,
        "NSHumanReadableCopyright": "logiprof",
    },
)
