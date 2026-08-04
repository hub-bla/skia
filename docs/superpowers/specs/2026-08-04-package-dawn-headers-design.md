# Package Dawn Headers for Graphite-Dawn Artifacts

## Goal

Release archives built with Graphite-Dawn must contain Dawn's checked-in public headers from
`third_party/externals/dawn/include`. Archives built without Graphite-Dawn must remain unchanged.

## Design

`tools/skia_release/archive.py` will use the existing `--enable-graphite-dawn` argument exposed by
`common.create_parser()`. When enabled, the archive's globs will include
`third_party/externals/dawn/include/**/*`. The existing generated-header glob under the target's
output directory remains unchanged.

The Graphite-Dawn archive invocations in `.github/workflows/build_for_skiko.yml` will pass
`--enable-graphite-dawn` alongside the same build variants that already pass it to `build.py`:

- macOS targets only within the Apple matrix;
- WASM targets;
- Windows targets.

Linux, Android, iOS, iOS Simulator, tvOS, and tvOS Simulator archives will not receive the flag and
will not package Dawn's checked-in headers.

## Verification

Add a focused archive-glob test or equivalent lightweight check proving that the Dawn include glob
is present only when `--enable-graphite-dawn` is enabled. Run the affected Python test or syntax
check and inspect the final diff to confirm that build and archive flags remain aligned.
