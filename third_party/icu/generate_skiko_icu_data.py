#!/usr/bin/env python3

import argparse
import os
from pathlib import Path
import platform
import shutil
import subprocess


SCRIPT_DIR = Path(__file__).resolve().parent
SKIA_ROOT = SCRIPT_DIR.parent.parent
ICU_ROOT = SKIA_ROOT / "third_party" / "externals" / "icu"
WINDOWS_CONFIGURE_PATCH = SCRIPT_DIR / "skiko_windows" / "configure.patch"


def shell_path(path):
    path = Path(path)
    if platform.system() != "Windows":
        return path.as_posix()
    return f"/{path.drive[0].lower()}{path.as_posix()[2:]}"


def bash_command():
    if platform.system() != "Windows":
        return "bash"

    git = shutil.which("git.exe") or shutil.which("git")
    if git:
        for directory in Path(git).resolve().parents:
            git_bash = directory / "usr" / "bin" / "bash.exe"
            if git_bash.is_file():
                return str(git_bash)
    raise SystemExit("Git Bash is required to configure ICU on Windows")


def msvc_environment():
    vswhere = Path(os.environ["ProgramFiles(x86)"]) / (
        "Microsoft Visual Studio/Installer/vswhere.exe"
    )
    if not vswhere.is_file():
        raise SystemExit("Visual Studio's vswhere.exe is required on Windows")

    installation = subprocess.check_output(
        [
            str(vswhere),
            "-latest",
            "-products",
            "*",
            "-requires",
            "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
            "-property",
            "installationPath",
        ],
        text=True,
    ).strip()
    vcvarsall = Path(installation) / "VC/Auxiliary/Build/vcvarsall.bat"
    if not vcvarsall.is_file():
        raise SystemExit("Could not find vcvarsall.bat")

    variables = subprocess.check_output(
        ["cmd.exe", "/d", "/s", "/c", f'call "{vcvarsall}" x64 >nul && set'],
        text=True,
    )
    env = os.environ.copy()
    for line in variables.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            env[key] = value
    return env


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build a filtered ICU data package from Skia's pinned ICU."
    )
    parser.add_argument("--filter", required=True, type=Path)
    parser.add_argument("--filter-patch", required=True, type=Path)
    parser.add_argument("--apply-cast-patch", action="store_true")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--build-dir", required=True, type=Path)
    return parser.parse_args()


def main():
    args = parse_args()
    source_filter = args.filter.resolve()
    filter_patch = args.filter_patch.resolve()
    output_file = args.output.resolve()
    build_dir = args.build_dir.resolve()
    configure = ICU_ROOT / "source" / "runConfigureICU"
    patch_locale = ICU_ROOT / "cast" / "patch_locale.sh"
    host_system = platform.system()

    if not source_filter.is_file():
        raise SystemExit(f"Missing ICU data filter: {source_filter}")
    if not filter_patch.is_file():
        raise SystemExit(f"Missing ICU data filter patch: {filter_patch}")
    if not configure.is_file():
        raise SystemExit(f"Missing pinned ICU checkout at {ICU_ROOT}")
    if args.apply_cast_patch and not patch_locale.is_file():
        raise SystemExit(f"Missing Chromium ICU locale patch at {patch_locale}")
    if host_system == "Windows" and not WINDOWS_CONFIGURE_PATCH.is_file():
        raise SystemExit(
            f"Missing Windows ICU configuration patch: {WINDOWS_CONFIGURE_PATCH}"
        )
    if build_dir == Path(build_dir.anchor):
        raise SystemExit(f"Refusing to use {build_dir} as the build directory")

    configure_platform = {
        "Darwin": "MacOSX",
        "Linux": "Linux/gcc",
        "Windows": "MSYS/MSVC",
    }.get(host_system)
    if configure_platform is None:
        raise SystemExit(
            f"Filtered ICU data generation is not supported on {host_system}"
        )
    bash = bash_command()

    shutil.rmtree(build_dir, ignore_errors=True)
    build_dir.mkdir(parents=True)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    filter_file = build_dir / "filter.json"
    shutil.copyfile(source_filter, filter_file)
    subprocess.run(
        ["git", "apply", str(filter_patch)],
        cwd=build_dir,
        check=True,
    )

    # Chromium's make_data_all.sh applies the Cast break-iterator patch before
    # generating its Android and iOS packages. We apply it to an isolated source
    # copy so the generated package matches that flow without modifying the
    # pinned ICU checkout.
    source_root = build_dir / "icu"
    shutil.copytree(ICU_ROOT / "source", source_root / "source")
    if host_system == "Windows":
        subprocess.run(
            ["git", "apply", str(WINDOWS_CONFIGURE_PATCH)],
            cwd=source_root / "source",
            check=True,
        )
    if args.apply_cast_patch:
        shutil.copytree(ICU_ROOT / "cast", source_root / "cast")
        subprocess.run(
            [bash, shell_path(source_root / "cast" / "patch_locale.sh")],
            cwd=source_root,
            check=True,
        )

    icu_build_dir = build_dir / "build"
    icu_build_dir.mkdir()
    configure = source_root / "source" / "runConfigureICU"

    env = msvc_environment() if host_system == "Windows" else os.environ.copy()
    env["ICU_DATA_FILTER_FILE"] = shell_path(filter_file)

    subprocess.run(
        [
            bash,
            shell_path(configure),
            configure_platform,
            "--disable-tests",
            "--disable-samples",
            "--disable-layoutex",
            "--enable-rpath",
            "--prefix=" + shell_path(build_dir / "install"),
        ],
        cwd=icu_build_dir,
        env=env,
        check=True,
    )
    subprocess.run(
        ["make", "-j", str(os.cpu_count() or 1)],
        cwd=icu_build_dir,
        env=env,
        check=True,
    )

    packages = list(
        (icu_build_dir / "data" / "out" / "tmp").glob("icudt*l.dat")
    )
    if len(packages) != 1:
        raise SystemExit(
            f"Expected one little-endian ICU package, found {len(packages)}"
        )

    shutil.copyfile(packages[0], output_file)
    print(f"{output_file}: {output_file.stat().st_size} bytes")


if __name__ == "__main__":
    main()
