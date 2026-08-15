# PyInstaller spec for the desktop launcher. Run from repo root:
#   pyinstaller desktop/inventory.spec
#
# A .spec (rather than raw --add-data CLI flags) so asset bundling is explicit, not accidental —
# static/uploads/ (user data), static/reloading_data/, and static/htmls/ (gitignored dev tooling)
# must NEVER end up inside an installer. All three are gitignored so a clean CI checkout wouldn't
# have them anyway, but enumerating exact subpaths here means that's true by construction, not by
# accident.

import sys

block_cipher = None

# .ico is Windows-only (macOS wants .icns, which doesn't exist yet — that leg of the build matrix
# still ships with PyInstaller's default icon; not this task's scope).
icon_path = 'windows/icon.ico' if sys.platform == 'win32' else None

a = Analysis(
    ['../launcher.py'],
    pathex=['..'],
    binaries=[],
    datas=[
        ('../templates', 'templates'),
        ('../static/app.js', 'static'),
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

# Known risk areas to smoke-test on an actual frozen build (not resolvable by static review
# alone): pypdfium2 ships a native binary and can need `--collect-all pypdfium2`; pydantic's
# Rust core (pydantic-core) and bcrypt's C extension are usually fine via PyInstaller's built-in
# hooks but should be verified on a real build rather than assumed.
