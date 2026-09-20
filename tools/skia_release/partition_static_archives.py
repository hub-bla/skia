#!/usr/bin/env python3

"""Remove duplicate object files from the Apple archives embedded by Skiko.

GN component targets are complete static libraries, so each one contains its
transitive object files.  Skiko embeds several of those archives in one klib;
partitioning their members keeps one copy of every object while retaining all
objects needed by the final link.
"""

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


# Dependencies precede their consumers so the standalone dependency archive
# owns shared objects. Archives absent from a particular build are skipped.
SKIKO_ARCHIVES = (
    "icu",
    "harfbuzz",
    "png",
    "jpeg",
    "jpeg12",
    "jpeg16",
    "skcms",
    "bentleyottmann",
    "webp",
    "webp_sse41",
    "zlib",
    "expat",
    "wuffs",
    "piex",
    "dng_sdk",
    "skia",
    "skresources",
    "skunicode_core",
    "skunicode_icu",
    "skshaper",
    "skparagraph",
    "svg",
    "skia_ganesh_ext",
    "skia_graphite_ext",
    "skia_graphite_dawn_ext",
    "jsonreader",
    "sksg",
    "skottie",
)


def run(*args, capture_output=False, cwd=None):
  return subprocess.run(
      args,
      check=True,
      capture_output=capture_output,
      text=capture_output,
      cwd=cwd,
  )


def archive_architectures(archive):
  output = run("xcrun", "lipo", "-archs", archive, capture_output=True).stdout
  return output.split()


def extract_archive(archive, destination):
  destination.mkdir()
  run("xcrun", "ar", "-x", archive, capture_output=True, cwd=destination)
  return sorted(path for path in destination.iterdir() if path.is_file())


def write_archive(destination, members):
  command = ["xcrun", "ar", "-crs", destination]
  command.extend(members)
  run(*command, capture_output=True)


def partition_archives(out_dir):
  archives = [
      out_dir / f"lib{name}.a"
      for name in SKIKO_ARCHIVES
      if (out_dir / f"lib{name}.a").is_file()
  ]
  if not archives:
    raise RuntimeError(f"No Skiko static archives found in {out_dir}")

  architectures = archive_architectures(archives[0])
  seen_by_architecture = {architecture: set() for architecture in architectures}
  duplicate_count = 0

  with tempfile.TemporaryDirectory(prefix="skia-partition-") as temporary:
    temporary = Path(temporary)
    staged_archives = []
    for archive_index, archive in enumerate(archives):
      staged_slices = []
      for architecture in architectures:
        slice_path = temporary / f"{archive_index}-{architecture}.a"
        run("xcrun", "lipo", archive, "-thin", architecture, "-output", slice_path)

        extraction_dir = temporary / f"{archive_index}-{architecture}-objects"
        members = extract_archive(slice_path, extraction_dir)
        retained = []
        seen = seen_by_architecture[architecture]
        for member in members:
          digest = hashlib.sha256(member.read_bytes()).digest()
          if digest in seen:
            duplicate_count += 1
          else:
            seen.add(digest)
            retained.append(member)

        partitioned_slice = temporary / f"{archive_index}-{architecture}-partitioned.a"
        write_archive(partitioned_slice, retained)
        staged_slices.append(partitioned_slice)

      staged_archive = temporary / archive.name
      run("xcrun", "lipo", "-create", *staged_slices, "-output", staged_archive)
      staged_archives.append((archive, staged_archive))

    for archive, staged_archive in staged_archives:
      mode = archive.stat().st_mode
      shutil.copyfile(staged_archive, archive)
      os.chmod(archive, mode)

  print(
      f"Partitioned {len(archives)} archives for {', '.join(architectures)}; "
      f"removed {duplicate_count} duplicate object copies"
  )


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("out_dir", type=Path)
  args = parser.parse_args()
  partition_archives(args.out_dir.resolve())


if __name__ == "__main__":
  main()
