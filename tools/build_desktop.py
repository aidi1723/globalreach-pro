from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


APP_NAME = "GlobalReach PRO"
PRODUCT_SLUG = "GlobalReachPro"
APP_VERSION = "2026.04.14"
ENTRY_STEM = "main"

EXCLUDED_IMPORT_TARGETS = [
    "pandas.tests",
    "pandas.conftest",
    "numpy.tests",
    "numpy.conftest",
    "pytest",
    "pytest_asyncio",
    "sqlalchemy",
    "IPython",
    "jupyter",
    "notebook",
    "matplotlib",
]


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build desktop distributables for GlobalReach PRO.")
    parser.add_argument(
        "--target",
        choices=["auto", "macos", "windows"],
        default="auto",
        help="Build target. Defaults to the current platform.",
    )
    parser.add_argument(
        "--backend",
        choices=["auto", "nuitka", "pyinstaller"],
        default="auto",
        help="Build backend. Defaults to a platform-appropriate backend.",
    )
    parser.add_argument(
        "--output-dir",
        default="dist/desktop",
        help="Output directory for generated artifacts.",
    )
    parser.add_argument(
        "--create-dmg",
        action="store_true",
        help="Create a macOS dmg after building the .app bundle.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove previous build output before starting.",
    )
    return parser.parse_args()


def resolve_target(raw_target: str) -> str:
    if raw_target != "auto":
        return raw_target
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("win"):
        return "windows"
    raise SystemExit("当前平台暂未配置桌面安装包打包脚本。")


def resolve_backend(raw_backend: str, target: str) -> str:
    if raw_backend != "auto":
        return raw_backend
    if target == "macos":
        return "pyinstaller"
    return "nuitka"


def base_nuitka_command(output_dir: Path) -> list[str]:
    root = project_root()
    main_script = root / "main.py"
    command = [
        sys.executable,
        "-m",
        "nuitka",
        "--standalone",
        "--plugin-enable=tk-inter",
        "--assume-yes-for-downloads",
        "--include-package=app",
        "--include-package=customtkinter",
        "--include-package=darkdetect",
        "--include-module=pandas",
        "--include-package=openpyxl",
        "--include-package-data=customtkinter",
        "--include-package-data=openpyxl",
        f"--output-dir={output_dir}",
        f"--output-filename={PRODUCT_SLUG}",
        f"--product-name={APP_NAME}",
        f"--file-description={APP_NAME}",
        f"--product-version={APP_VERSION}",
        str(main_script),
    ]
    command.extend(f"--nofollow-import-to={target}" for target in EXCLUDED_IMPORT_TARGETS)
    return command


def replace_path(source: Path, destination: Path) -> None:
    if not source.exists() or source == destination:
        return
    if destination.exists():
        if destination.is_dir():
            shutil.rmtree(destination)
        else:
            destination.unlink()
    source.rename(destination)


def normalize_output_artifacts(output_dir: Path) -> None:
    replace_path(output_dir / f"{ENTRY_STEM}.app", output_dir / f"{PRODUCT_SLUG}.app")
    replace_path(output_dir / f"{ENTRY_STEM}.dist", output_dir / f"{PRODUCT_SLUG}.dist")
    replace_path(output_dir / f"{ENTRY_STEM}.build", output_dir / f"{PRODUCT_SLUG}.build")
    replace_path(output_dir / f"{ENTRY_STEM}.exe", output_dir / f"{PRODUCT_SLUG}.exe")


def build_macos(output_dir: Path, create_dmg: bool) -> None:
    command = base_nuitka_command(output_dir) + [
        "--macos-create-app-bundle",
        "--macos-app-icon=none",
    ]
    run_command(command, cwd=project_root())
    normalize_output_artifacts(output_dir)

    if not create_dmg:
        return

    app_bundle = output_dir / f"{PRODUCT_SLUG}.app"
    if not app_bundle.exists():
        raise SystemExit(f"未找到 app 产物：{app_bundle}")
    dmg_path = output_dir / f"{PRODUCT_SLUG}-{APP_VERSION}.dmg"
    create_macos_dmg(app_bundle, dmg_path)


def build_windows(output_dir: Path) -> None:
    command = base_nuitka_command(output_dir) + [
        "--windows-console-mode=disable",
    ]
    run_command(command, cwd=project_root())
    normalize_output_artifacts(output_dir)


def build_macos_with_pyinstaller(output_dir: Path, create_dmg: bool) -> None:
    root = project_root()
    spec_dir = output_dir / "_pyinstaller_spec"
    work_dir = output_dir / "_pyinstaller_work"
    config_dir = root / ".pyinstaller-cache"
    spec_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        f"--name={PRODUCT_SLUG}",
        f"--distpath={output_dir}",
        f"--workpath={work_dir}",
        f"--specpath={spec_dir}",
        str(root / "main.py"),
    ]
    run_command(command, cwd=root, extra_env={"PYINSTALLER_CONFIG_DIR": str(config_dir)})

    if not create_dmg:
        return

    app_bundle = output_dir / f"{PRODUCT_SLUG}.app"
    if not app_bundle.exists():
        raise SystemExit(f"未找到 app 产物：{app_bundle}")
    dmg_path = output_dir / f"{PRODUCT_SLUG}-{APP_VERSION}.dmg"
    create_macos_dmg(app_bundle, dmg_path)


def create_macos_dmg(app_bundle: Path, dmg_path: Path) -> None:
    staging_dir = dmg_path.parent / "_dmg_staging"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)
    staged_bundle = staging_dir / app_bundle.name
    shutil.copytree(app_bundle, staged_bundle)
    run_command(
        [
            "hdiutil",
            "create",
            "-volname",
            APP_NAME,
            "-srcfolder",
            str(staging_dir),
            "-ov",
            "-format",
            "UDZO",
            str(dmg_path),
        ],
        cwd=project_root(),
    )
    shutil.rmtree(staging_dir, ignore_errors=True)


def run_command(command: list[str], cwd: Path, extra_env: dict[str, str] | None = None) -> None:
    print("$", " ".join(command))
    env = os.environ.copy()
    env.setdefault("NUITKA_CACHE_DIR", str(project_root() / ".nuitka-cache"))
    if extra_env:
        env.update(extra_env)
    subprocess.run(command, cwd=cwd, check=True, env=env)


def main() -> None:
    args = parse_args()
    target = resolve_target(args.target)
    backend = resolve_backend(args.backend, target)
    output_dir = project_root() / args.output_dir

    if args.clean and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if target == "macos":
        if backend == "pyinstaller":
            build_macos_with_pyinstaller(output_dir, create_dmg=args.create_dmg)
            return
        if backend == "nuitka":
            build_macos(output_dir, create_dmg=args.create_dmg)
            return
        raise SystemExit(f"不支持的 macOS 打包后端：{backend}")
    if target == "windows":
        if backend != "nuitka":
            raise SystemExit("Windows 打包当前仅支持 Nuitka。")
        build_windows(output_dir)
        return
    raise SystemExit(f"不支持的打包目标：{target}")


if __name__ == "__main__":
    main()
