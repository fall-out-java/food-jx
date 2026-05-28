"""
Build portable package with PyInstaller.
Run: python build.py
"""

import os
import shutil
import site
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT / "dist"
BUILD_DIR = ROOT / "build"
SPEC_NAME = "food-jx.spec"

# Data files to bundle
DATA_DIRS = {
    "output": "output",    # keep output structure
    "temp": "temp",
}

# Whisper models cache directory
WHISPER_CACHE = Path.home() / ".cache" / "whisper"


def clean():
    """Clean previous build artifacts."""
    for d in [DIST_DIR, BUILD_DIR]:
        if d.exists():
            shutil.rmtree(d)
    (ROOT / SPEC_NAME).unlink(missing_ok=True)
    print("  ✓ 已清理旧构建")


def build():
    """Run PyInstaller."""
    # Ensure PyInstaller is installed
    try:
        import PyInstaller
    except ImportError:
        print("正在安装 PyInstaller …")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "pyinstaller"],
            check=True, capture_output=True,
        )

    # Build command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onedir",
        "--name=food-jx",
        "--windowed",         # no console window
        "--clean",
        "--noconfirm",
        "--add-data", f"{ROOT / 'main.py'};.",
        "--add-data", f"{ROOT / 'src'};src",
        "--add-data", f"{ROOT / 'urls.txt'};.",
        "--distpath", str(DIST_DIR),
        "--workpath", str(BUILD_DIR),
        # Exclude unneeded torch/whisper backends to reduce size
        "--exclude-module", "torchvision",
        "--exclude-module", "tensorflow",
        "--exclude-module", "matplotlib",
        "--exclude-module", "pandas",
        "--exclude-module", "numpy",
        str(ROOT / "main.py"),
    ]

    print(f"正在构建包（首次约 3-5 分钟）…")
    subprocess.run(cmd, check=True)
    print(f"  ✓ 构建完成: {DIST_DIR / 'food-jx'}")


def bundle_models():
    """Copy Whisper model and FFmpeg into the dist folder."""
    dist_app = DIST_DIR / "food-jx"

    # Whisper model
    if WHISPER_CACHE.exists():
        models_dst = dist_app / "models" / "whisper"
        models_dst.mkdir(parents=True, exist_ok=True)
        for f in WHISPER_CACHE.glob("*"):
            if f.is_file():
                shutil.copy2(f, models_dst / f.name)
                print(f"  ✓ 已打包模型: {f.name}")
        print(f"  模型目录: {models_dst}")
    else:
        print("  ⚠ Whisper 模型缓存未找到，首次运行时会自动下载")

    # FFmpeg (bundled via imageio_ffmpeg, handled at runtime)
    print("  ✓ FFmpeg 将在运行时自动加载（通过 imageio_ffmpeg）")


def post_build():
    """Post-build steps: copy config, create launcher, etc."""
    dist_app = DIST_DIR / "food-jx"

    # Create _internal/data symlink or copy
    # (PyInstaller puts data under _internal for --onedir)
    data_src = ROOT / "urls.txt"
    shutil.copy2(data_src, dist_app / "urls.txt")

    print(f"\n打包完成！")
    print(f"输出目录: {dist_app}")
    print(f"总大小: {_dir_size(dist_app) / 1024 / 1024:.1f} MB")
    print(f"\n启动方式: 双击 dist/food-jx/food-jx.exe")
    print(f"或运行: dist/food-jx/food-jx.exe")


def _dir_size(path: Path) -> int:
    total = 0
    for f in path.rglob("*"):
        if f.is_file():
            total += f.stat().st_size
    return total


def main():
    print("food-jx 打包工具")
    print("=" * 40)

    clean()
    build()
    bundle_models()
    post_build()

    print("\n提示: 如需压缩分发，建议用 7z 打包 dist/food-jx 文件夹")
    print("      压缩后可减少约 40-50% 体积")


if __name__ == "__main__":
    main()
