# Build the modified checkout with Windows Python and PyInstaller.
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, copy_metadata

build_root = Path(SPECPATH)
osam_data, osam_binaries, osam_imports = collect_all("osam")
# imgviz 2 uses importlib.metadata.version() at import time. Include metadata
# for the complete runtime dependency graph, plus imgviz's fonts and images.
datas = collect_data_files("labelme") + collect_data_files("imgviz")
datas += copy_metadata("labelme", recursive=True) + osam_data

a = Analysis(
    [str(build_root / "portable_entry.py")],
    pathex=[str(build_root)],
    binaries=osam_binaries,
    datas=datas,
    hiddenimports=osam_imports + ["portable_smoke"],
    hookspath=[],
    hooksconfig={"matplotlib": {"backends": ["Agg"]}},
    runtime_hooks=[],
    excludes=["PyQt5", "PyQt6", "PySide2", "tkinter", "IPython", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Labelme-7.9.1-layout.2-Windows-x64",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(build_root.parent / "labelme" / "icons" / "icon.ico"),
)
