# PyInstaller spec for the desktop launcher. Run from repo root:
#   pyinstaller desktop/inventory.spec
#
# A .spec (rather than raw --add-data CLI flags) so asset bundling is explicit, not accidental —
# static/uploads/ (user data), static/reloading_data/, and static/htmls/ (gitignored dev tooling)
# must NEVER end up inside an installer. All three are gitignored so a clean CI checkout wouldn't
# have them anyway, but enumerating exact subpaths here means that's true by construction, not by
# accident.

import sys
from pathlib import Path

block_cipher = None

# SPECPATH is injected by PyInstaller into every spec's namespace (the dir containing this file)
# — used instead of a CWD-relative read since CWD depends on where `pyinstaller` was invoked from.
VERSION = (Path(SPECPATH) / '..' / 'VERSION').read_text().strip()

# Windows wants .ico, macOS wants .icns; Linux has no PyInstaller-level icon embedding (AppImage
# packaging supplies its own icon separately, once that step exists).
if sys.platform == 'win32':
    icon_path = 'windows/icon.ico'
elif sys.platform == 'darwin':
    icon_path = 'macos/icon.icns'
else:
    icon_path = None

a = Analysis(
    ['../launcher.py'],
    pathex=['..'],
    binaries=[],
    datas=[
        ('../templates', 'templates'),
        # Every top-level static/*.js and *.json a template actually references (grep templates/
        # for '/static/[^/]+\.\(js\|json\)' to re-check this list after adding a new one) — a
        # missing entry here 404s in the frozen build even though it works fine running from
        # source, since only files listed here exist under PyInstaller's _MEIPASS.
        ('../static/app.js', 'static'),
        ('../static/offline-queue.js', 'static'),
        ('../static/price-blur.js', 'static'),
        ('../static/sw.js', 'static'),
        ('../static/bc_reference.json', 'static'),
        ('../static/manifest.json', 'static'),
        ('../static/images', 'static/images'),
        ('../VERSION', '.'),
    ],
    hiddenimports=[
        # uvicorn dynamically imports its protocol/loop implementations at runtime — PyInstaller's
        # static analysis misses these unless listed explicitly (a well-known PyInstaller+uvicorn
        # gotcha), which otherwise manifests as a working build that fails only once a real HTTP
        # request comes in.
        'uvicorn.loops.auto',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan.on',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='InventoryAndReloading',
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=icon_path,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='InventoryAndReloading',
)

# macOS only: wraps the onedir COLLECT output into a real .app bundle. Without this, PyInstaller
# just leaves a plain folder of files (a .app is really just a folder with the right structure/
# Info.plist, but Finder/LaunchServices only treat it as a double-clickable app once BUNDLE()
# has arranged it that way).
if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='Guns & Reloading.app',
        icon=icon_path,
        bundle_identifier='com.chelohomelab.gunsandreloading',
        version=VERSION,
        info_plist={
            'CFBundleShortVersionString': VERSION,
            'CFBundleVersion': VERSION,
            'NSHighResolutionCapable': True,
        },
    )

# Known risk areas to smoke-test on an actual frozen build (not resolvable by static review
# alone): pypdfium2 ships a native binary and can need `--collect-all pypdfium2`; pydantic's
# Rust core (pydantic-core) and bcrypt's C extension are usually fine via PyInstaller's built-in
# hooks but should be verified on a real build rather than assumed.
