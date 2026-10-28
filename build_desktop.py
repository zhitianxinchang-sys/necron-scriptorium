import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VENV_PYTHON = ROOT / ".desktop-build" / "venv" / "Scripts" / "python.exe"
DIST = ROOT / "dist"
WORK = ROOT / ".desktop-build" / "pyinstaller"


def main():
    if not VENV_PYTHON.exists():
        raise SystemExit("请先创建 .desktop-build/venv 并安装 pywebview、pyinstaller。")
    if not (ROOT / "assets" / "icon.ico").exists():
        raise SystemExit("缺少 assets/icon.ico")
    shutil.rmtree(WORK, ignore_errors=True)
    command = [
        str(VENV_PYTHON), "-m", "PyInstaller",
        "--noconfirm", "--clean", "--windowed", "--onefile",
        "--name", "太空死灵作家助手",
        "--icon", str(ROOT / "assets" / "icon.ico"),
        "--distpath", str(DIST),
        "--workpath", str(WORK),
        "--specpath", str(WORK),
        "--add-data", f"{ROOT / 'static'};static",
        "--add-data", f"{ROOT / 'skills'};skills",
        "--collect-all", "webview",
        "--collect-all", "clr_loader",
        "--collect-all", "pythonnet",
        "--hidden-import", "webview.platforms.edgechromium",
        str(ROOT / "desktop.py"),
    ]
    subprocess.run(command, cwd=ROOT, check=True)
    exe = DIST / "太空死灵作家助手.exe"
    if not exe.exists():
        raise SystemExit("打包完成但未找到 EXE")
    print(f"BUILD_OK {exe} {exe.stat().st_size}")


if __name__ == "__main__":
    main()
