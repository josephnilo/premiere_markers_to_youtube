# Changelog

All notable changes to this project will be documented here.

## [Unreleased]

### Added

- Installable `premiere-markers-to-youtube` console command.
- Validation for YouTube's first-chapter, count, order, duplicate, and minimum-gap
  rules.
- UTF-8, UTF-8 BOM, UTF-16, drop-frame syntax, fractional timecode, Unicode title,
  and videos-longer-than-one-hour support.
- Frame-rate-aware conversion for integer and common 1000/1001 non-drop rates via
  `--fps`, plus non-zero sequence offsets via `--start-timecode`.
- Automated standard-library tests, synthetic fixtures, contribution instructions,
  and a repeatable local check command.
- `--output`, `--force`, and `--no-validate` command-line options.
- MIT license with package metadata.

### Changed

- The input marker export is preserved instead of being deleted.
- Output is written directly as UTF-8 without shared temporary files.
- Columns are selected by header name instead of fixed positions.
- `Description` remains the preferred chapter title if an export also contains a
  `Marker Name` column.
- The default output name is `<input stem>_youtube_chapters.txt`.

### Fixed

- Path handling no longer depends on forward-slash string splitting.
- Quoted titles, whitespace, non-ASCII text, malformed rows, and missing files receive
  deterministic handling and useful errors.
- Blank chapter titles are rejected instead of producing unusable output.
