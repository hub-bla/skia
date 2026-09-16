#!/usr/bin/env python3
"""Report object files present in more than one static archive (read only)."""

import argparse
import hashlib
import pathlib
import shutil
import subprocess
import tempfile


CORE_LIBRARIES = [
    'svg', 'skparagraph', 'skresources', 'skshaper', 'skunicode_icu',
    'skunicode_core', 'skia', 'wuffs', 'icu', 'harfbuzz', 'png', 'jpeg',
    'webp', 'webp_sse41', 'zlib', 'expat',
]
EXTENSION_LIBRARIES = [
    'skia_ganesh_ext', 'skia_graphite_ext', 'skottie', 'sksg', 'jsonreader',
]


def ar(*args):
  # llvm-ar can retrieve COFF members whose names contain directories. GNU ar,
  # which is first on PATH in the Windows MSYS environment, lists such members
  # but cannot read them back by their listed name.
  archive_tool = shutil.which('llvm-ar') or 'ar'
  return subprocess.check_output([archive_tool, *map(str, args)])


def archive_slice(archive, temporary_files):
  """Returns an ar-readable archive, thinning Mach-O universal archives."""
  if not shutil.which('lipo'):
    return archive
  archs = subprocess.run(
      ['lipo', '-archs', str(archive)], capture_output=True, text=True)
  if archs.returncode != 0:
    return archive
  architectures = archs.stdout.split()
  if len(architectures) <= 1:
    return archive
  temporary = tempfile.NamedTemporaryFile(suffix='.a', delete=False)
  temporary.close()
  temporary_files.append(pathlib.Path(temporary.name))
  subprocess.check_call(
      ['lipo', '-thin', architectures[0], str(archive), '-output', temporary.name])
  return pathlib.Path(temporary.name)


def members(archive, temporary_files):
  archive = archive_slice(archive, temporary_files)
  return [name for name in ar('-t', archive).decode().splitlines()
          if name.endswith(('.o', '.obj'))]


def skiko_archives(out_dir, target, build_type):
  """Returns only the archives linked by Skiko for one release target."""
  libraries = list(CORE_LIBRARIES)
  if target in ('macos', 'ios', 'iosSim', 'tvos', 'tvosSim', 'linux'):
    libraries += ['piex', 'dng_sdk'] + EXTENSION_LIBRARIES
  elif target == 'android':
    libraries += ['skia_ganesh_ext', 'skottie', 'sksg', 'jsonreader']
  elif target == 'windows':
    libraries += [
        'skia_ganesh_ext', 'd3d12allocator', 'skia_graphite_ext',
        'skottie', 'sksg', 'jsonreader',
    ]
    if build_type == 'Debug':
      libraries += ['spvtools', 'spvtools_val']
  elif target == 'wasm':
    libraries += [
        'bentleyottmann', 'freetype2', 'jpeg12', 'jpeg16', 'skcms', 'brotli',
        'skia_ganesh_ext', 'skottie', 'sksg', 'jsonreader',
    ]

  archives = []
  for library in libraries:
    candidates = [
        out_dir / f'lib{library}.a',
        out_dir / f'lib{library}.wasm.a',
        out_dir / f'{library}.lib',
        out_dir / f'lib{library}.lib',
    ]
    archive = next((path for path in candidates if path.is_file()), None)
    if not archive:
      raise FileNotFoundError(
          f'Skiko links {library}, but no archive was found in {out_dir}')
    archives.append(archive)
  return archives


def main():
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument(
      '--out-dir',
      type=pathlib.Path,
      help='Build output directory used with --skiko-target.')
  parser.add_argument(
      '--skiko-target',
      choices=('macos', 'ios', 'iosSim', 'tvos', 'tvosSim', 'linux', 'android',
               'windows', 'wasm'),
      help='Check only the archives that Skiko links for this target.')
  parser.add_argument('--build-type', choices=('Debug', 'Release'))
  parser.add_argument('archives', nargs='*', type=pathlib.Path)
  args = parser.parse_args()

  archives = args.archives
  if args.skiko_target:
    if not args.out_dir or not args.build_type:
      parser.error('--skiko-target requires --out-dir and --build-type')
    archives += skiko_archives(args.out_dir, args.skiko_target, args.build_type)
  elif args.out_dir:
    parser.error('--out-dir requires --skiko-target')
  if not archives:
    parser.error('provide archive paths or --out-dir')

  temporary_files = []
  archive_slices = {}
  try:
    by_name = {}
    for archive in archives:
      archive_slices[archive] = archive_slice(archive, temporary_files)
      for member in members(archive_slices[archive], temporary_files):
        # GN prefixes an object with its target name in the archive.
        source_name = member.split('.', 1)[-1]
        by_name.setdefault(source_name, []).append((archive, member))

    duplicates = []
    for source_name, locations in sorted(by_name.items()):
      if len({archive for archive, _ in locations}) < 2:
        continue
      by_hash = {}
      for archive, member in locations:
        digest = hashlib.sha256(
            ar('-p', archive_slices[archive], member)).hexdigest()
        by_hash.setdefault(digest, []).append((archive, member))
      for copies in by_hash.values():
        if len({archive for archive, _ in copies}) > 1:
          duplicates.append((source_name, copies))

    if duplicates:
      print('Object | Archives and members')
      print('--- | ---')
      for source_name, copies in duplicates:
        print(f'{source_name} | ' + ', '.join(
            f'{archive}:{member}' for archive, member in copies))
    else:
      print(f'No duplicate objects across {len(archives)} archives')
    return bool(duplicates)
  finally:
    for temporary in temporary_files:
      temporary.unlink(missing_ok=True)


if __name__ == '__main__':
  raise SystemExit(main())
