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


def require_tool(name):
    tool = shutil.which(name)
    if tool is None:
        raise SystemExit(f"Missing required ICU data build tool: {name}")
    return Path(tool)


def msys_path(path, cygpath):
    return subprocess.check_output(
        [str(cygpath), "-u", str(path)],
        text=True,
    ).strip()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build a filtered ICU data package from Skia's pinned ICU."
    )
    parser.add_argument("--filter", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--build-dir", required=True, type=Path)
    return parser.parse_args()


def main():
    args = parse_args()
    filter_file = args.filter.resolve()
    output_file = args.output.resolve()
    build_dir = args.build_dir.resolve()
    configure = ICU_ROOT / "source" / "runConfigureICU"

    if not filter_file.is_file():
        raise SystemExit(f"Missing ICU data filter: {filter_file}")
    if not configure.is_file() or not os.access(configure, os.X_OK):
        raise SystemExit(f"Missing pinned ICU checkout at {ICU_ROOT}")
    if build_dir == Path(build_dir.anchor):
        raise SystemExit(f"Refusing to use {build_dir} as the build directory")

    host_system = platform.system()
    host_platform = {
        "Darwin": "MacOSX",
        "Linux": "Linux/gcc",
        "Windows": "MinGW",
    }.get(host_system)
    if host_platform is None:
        raise SystemExit(f"ICU data generation is not supported on {host_system}")

    shutil.rmtree(build_dir, ignore_errors=True)
    build_dir.mkdir(parents=True)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["ICU_DATA_FILTER_FILE"] = str(filter_file)
    configure_command = [str(configure), host_platform]
    make = "make"
    if host_system == "Windows":
        # ICU's data sources are UTF-8. MinGW otherwise derives the default
        # charset from the Windows environment, which can make genrb reject
        # non-ASCII source text.
        env["CPPFLAGS"] = " ".join(
            value
            for value in (env.get("CPPFLAGS"), "-DU_CHARSET_IS_UTF8=1")
            if value
        )
        make = str(require_tool("make"))
        bash = require_tool("bash")
        cygpath = require_tool("cygpath")
        configure_command = [
            str(bash),
            msys_path(configure, cygpath),
            host_platform,
        ]

    subprocess.run(
        configure_command
        + [
            "--disable-tests",
            "--disable-samples",
            "--disable-layoutex",
            "--enable-rpath",
            "--prefix="
            + (
                msys_path(build_dir / "install", cygpath)
                if host_system == "Windows"
                else str(build_dir / "install")
            ),
        ],
        cwd=build_dir,
        env=env,
        check=True,
    )
    subprocess.run(
        [make, "-j", str(os.cpu_count() or 1)],
        cwd=build_dir,
        check=True,
    )

    packages = list((build_dir / "data" / "out" / "tmp").glob("icudt*l.dat"))
    if len(packages) != 1:
        raise SystemExit(
            f"Expected one little-endian ICU package, found {len(packages)}"
        )

    shutil.copyfile(packages[0], output_file)
    print(f"{output_file}: {output_file.stat().st_size} bytes")


if __name__ == "__main__":
    main()
