# Premiere Markers to YouTube Chapters

Convert a tab-delimited marker export from Adobe Premiere Pro into a chapter list
that can be pasted into a YouTube video description.

```text
00:00 Introduction
00:14 2D animated explainers
00:35 Whiteboard explainers
```

The converter has no runtime dependencies outside the Python standard library. It
preserves the source export, writes UTF-8 output beside it by default, and checks the
chapter rules that YouTube documents.

## Requirements

- Python 3.9 or newer
- An Adobe Premiere Pro marker export in tab-delimited text format

The parser supports BOM-tagged UTF-16 exports as well as UTF-8 and UTF-8 with a
byte-order mark. It recognises common English time columns such as `In Point`, `In`,
`Start`, and `Timecode`, and title columns such as `Description`, `Marker Name`, and
`Name`. If an export includes multiple title fields, `Description` takes priority to
preserve the behavior of the original converter.

## Export markers from Premiere Pro

1. Add named markers to the **sequence timeline**, not individual clips. Deselect
   clips before adding a marker if necessary.
2. Put the first marker at `00:00:00:00`, or at the sequence start when using
   `--start-timecode`.
3. Choose **File > Export > Markers** and save the tab-delimited text file.

Premiere versions and workspaces can label export fields differently. If the tool
does not recognise a column in a real export, open an issue with a small, synthetic
example that contains no client or media information.

## Run without installing

From the repository directory:

```bash
python3 premiere_markers_to_youtube.py "/path/to/markers.txt"
```

The default output is `/path/to/markers_youtube_chapters.txt`. The input file is
never changed or deleted.

Useful options:

```bash
# Choose an output path
python3 premiere_markers_to_youtube.py markers.txt --output chapters.txt

# Print chapters for piping or copying
python3 premiere_markers_to_youtube.py markers.txt --output -

# Deliberately replace an existing output
python3 premiere_markers_to_youtube.py markers.txt --force

# Format an incomplete draft without applying YouTube validation
python3 premiere_markers_to_youtube.py markers.txt --no-validate

# Convert a 29.97 non-drop-frame sequence accurately
python3 premiere_markers_to_youtube.py markers.txt --fps 29.97

# Offset a broadcast-style sequence that starts at 01:00:00:00
python3 premiere_markers_to_youtube.py markers.txt \
  --fps 29.97 --start-timecode 01:00:00:00
```

Run `python3 premiere_markers_to_youtube.py --help` for the complete CLI reference.

## Install the command

An isolated environment keeps the command separate from system Python:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
premiere-markers-to-youtube "/path/to/markers.txt"
```

There are no third-party runtime packages to install.

## YouTube validation

By default, conversion stops with an actionable error unless:

- the first chapter starts at `00:00`;
- there are at least three chapters;
- timestamps are unique and in ascending order; and
- consecutive timestamps are at least 10 seconds apart.

Those checks follow [YouTube's documented chapter
rules](https://support.google.com/youtube/answer/9884579). The tool cannot verify the
length of the final chapter because a marker export does not contain the video end
time. `--no-validate` bypasses these checks but does not make an invalid list work on
YouTube.

YouTube timestamps have whole-second precision, so timecode frames and fractional
seconds are floored. Without `--fps`, `00:01:23:12` and `00:01:23.999` both become
`01:23`. Pass the sequence rate with `--fps` when frame numbers affect elapsed time,
especially for non-drop 23.976, 29.97, 59.94, or 119.88 fps. Common decimal rates and
exact ratios such as `30000/1001` are accepted.

Semicolon drop-frame notation such as `00:01:23;12` is supported with `--fps 29.97`,
`59.94`, or `119.88`. Supplying the rate also enables frame-number and dropped-label
validation.

### Timecode limitations

- Marker exports do not include the sequence frame rate. If `--fps` is omitted, the
  converter treats the displayed `HH:MM:SS` fields as elapsed time and discards the
  frame field. Long fractional-rate non-drop timelines therefore require `--fps` for
  accurate conversion.
- The default sequence start is `00:00:00:00`. For a broadcast-style start such as
  `01:00:00:00`, pass both `--fps` and `--start-timecode 01:00:00:00`. The marker and
  start values must use identical notation, including the frame or fractional field.
- When `--fps` is used, all marker rows must use the same timecode notation.
- Frame-rate-specific validity is checked only when `--fps` is supplied.
- Only the English header names listed above are currently recognised.

The historical export layout in this repository and synthetic variants are covered
by tests. A current Premiere UI/export and Windows execution have not yet been
verified.

## Development

Run the standard-library test suite on any supported Python installation:

```bash
python3 -m unittest discover -s tests -v
```

On POSIX systems, `./scripts/check` runs the same command with deterministic test
environment settings.

Tests use synthetic marker exports and temporary directories; no Premiere project or
media is needed. See [CONTRIBUTING.md](CONTRIBUTING.md) for the development workflow
and [CHANGELOG.md](CHANGELOG.md) for notable changes.

## License

Licensed under the [MIT License](LICENSE).
