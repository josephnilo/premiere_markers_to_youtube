"""Convert an Adobe Premiere Pro marker export to YouTube chapters."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from fractions import Fraction
import io
from pathlib import Path
import re
import sys
from typing import Iterable, List, Optional, Sequence


__version__ = "0.2.0"

FPS_ALIASES = {
    "23.976": Fraction(24000, 1001),
    "23.98": Fraction(24000, 1001),
    "29.97": Fraction(30000, 1001),
    "59.94": Fraction(60000, 1001),
    "119.88": Fraction(120000, 1001),
}
DROP_FRAME_RATES = {
    Fraction(30000, 1001): 2,
    Fraction(60000, 1001): 4,
    Fraction(120000, 1001): 8,
}

TIME_HEADERS = (
    "in point",
    "in",
    "start",
    "start time",
    "timecode",
    "time code",
    "time",
)
TITLE_HEADERS = (
    "description",
    "marker name",
    "name",
    "title",
    "comment",
    "comments",
)


class ConversionError(ValueError):
    """Raised when an export cannot produce a valid chapter list."""


@dataclass(frozen=True)
class Chapter:
    seconds: int
    title: str
    row_number: int


def _normalise_header(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


def _find_column(headers: Sequence[str], accepted: Sequence[str], label: str) -> int:
    for preferred_name in accepted:
        matches = [
            index for index, value in enumerate(headers) if value == preferred_name
        ]
        if len(matches) > 1:
            raise ConversionError(
                f"found duplicate {label} columns named {preferred_name!r}"
            )
        if matches:
            return matches[0]
    choices = ", ".join(accepted)
    raise ConversionError(
        f"could not find a {label} column in the header "
        f"(recognised names: {choices})"
    )


def decode_export(contents: bytes) -> str:
    """Decode the UTF-16 Premiere default and common UTF-8 variants."""
    if not contents:
        raise ConversionError("input file is empty")

    if contents.startswith((b"\xff\xfe", b"\xfe\xff")):
        candidates = ("utf-16",)
    elif contents.startswith(b"\xef\xbb\xbf"):
        candidates = ("utf-8-sig",)
    elif b"\x00" in contents[:200]:
        even_nuls = contents[:200:2].count(0)
        odd_nuls = contents[1:200:2].count(0)
        candidates = ("utf-16-be",) if even_nuls > odd_nuls else ("utf-16-le",)
    else:
        candidates = ("utf-8-sig",)

    for encoding in candidates:
        try:
            return contents.decode(encoding)
        except UnicodeDecodeError:
            pass
    raise ConversionError("input is not valid UTF-16 or UTF-8 text")


def parse_fps(value: str) -> Fraction:
    """Parse an integer, common decimal alias, or exact rational frame rate."""
    try:
        fps = FPS_ALIASES[value] if value in FPS_ALIASES else Fraction(value)
    except (ValueError, ZeroDivisionError) as error:
        raise ConversionError(
            f"invalid frame rate {value!r}; use a value such as 24, 29.97, or 30000/1001"
        ) from error
    if fps <= 0:
        raise ConversionError("frame rate must be greater than zero")
    nominal = int(fps + Fraction(1, 2))
    if nominal < 1 or abs(fps - nominal) > Fraction(1, 10):
        raise ConversionError(
            f"unsupported frame rate {value!r}; expected an integer rate or its "
            "1000/1001 counterpart"
        )
    return fps


def _absolute_timecode_seconds(
    value: str, row_number: int, fps: Optional[Fraction]
) -> tuple[Fraction, Optional[str]]:
    """Return the absolute time represented by a timecode and its frame separator."""
    value = value.strip()
    premiere_match = re.fullmatch(
        r"(?P<hours>\d+):(?P<minutes>\d{2}):(?P<seconds>\d{2})"
        r"(?:(?P<separator>[:;])(?P<frames>\d{1,3})|\.(?P<fraction>\d{1,3}))?",
        value,
    )
    short_match = re.fullmatch(r"(?P<minutes>\d+):(?P<seconds>\d{2})", value)

    if premiere_match:
        hours = int(premiere_match.group("hours"))
        minutes = int(premiere_match.group("minutes"))
        seconds = int(premiere_match.group("seconds"))
    elif short_match:
        hours = 0
        minutes = int(short_match.group("minutes"))
        seconds = int(short_match.group("seconds"))
    else:
        raise ConversionError(
            f"row {row_number}: invalid timecode {value!r}; expected "
            "HH:MM:SS:FF, HH:MM:SS;FF, HH:MM:SS, or MM:SS"
        )

    if minutes >= 60 and premiere_match:
        raise ConversionError(f"row {row_number}: minutes must be between 00 and 59")
    if seconds >= 60:
        raise ConversionError(f"row {row_number}: seconds must be between 00 and 59")
    displayed_seconds = hours * 3600 + minutes * 60 + seconds

    if not premiere_match:
        return Fraction(displayed_seconds), None

    fraction = premiere_match.group("fraction")
    if fraction is not None:
        return (
            Fraction(displayed_seconds) + Fraction(int(fraction), 10 ** len(fraction)),
            ".",
        )

    frames_text = premiere_match.group("frames")
    separator = premiere_match.group("separator")
    if frames_text is None or fps is None:
        return Fraction(displayed_seconds), separator

    frames = int(frames_text)
    nominal_fps = int(fps + Fraction(1, 2))
    if frames >= nominal_fps:
        raise ConversionError(
            f"row {row_number}: frame number must be between 00 and {nominal_fps - 1:02d}"
        )

    if separator == ";":
        dropped_frames = DROP_FRAME_RATES.get(fps)
        if dropped_frames is None:
            raise ConversionError(
                f"row {row_number}: semicolon drop-frame timecode requires "
                "29.97, 59.94, or 119.88 fps"
            )
        if minutes % 10 != 0 and seconds == 0 and frames < dropped_frames:
            raise ConversionError(f"row {row_number}: invalid dropped-frame label {value!r}")
        # Drop-frame labels intentionally track displayed clock time. At whole-second
        # YouTube precision, using the label avoids a one-second boundary artifact
        # from the tiny residual 1000/1001 timing difference.
        return Fraction(displayed_seconds) + Fraction(frames, fps), separator

    total_frames = displayed_seconds * nominal_fps + frames
    return Fraction(total_frames, 1) / fps, separator


def parse_timecode(
    value: str,
    row_number: int,
    fps: Optional[Fraction] = None,
    start_timecode: Optional[str] = None,
) -> int:
    """Return whole elapsed seconds from Premiere or YouTube-style timecode."""
    absolute, separator = _absolute_timecode_seconds(value, row_number, fps)
    if start_timecode is None:
        elapsed = absolute
    else:
        start, start_separator = _absolute_timecode_seconds(start_timecode, 0, fps)
        if separator != start_separator:
            raise ConversionError(
                f"row {row_number}: marker and start timecodes must use the same notation"
            )
        elapsed = absolute - start
    if elapsed < 0:
        raise ConversionError(f"row {row_number}: timecode occurs before the sequence start")
    return elapsed.numerator // elapsed.denominator


def parse_export(
    text: str,
    fps: Optional[Fraction] = None,
    start_timecode: Optional[str] = None,
) -> List[Chapter]:
    """Parse a tab-delimited Premiere marker export."""
    try:
        rows = list(
            csv.reader(io.StringIO(text, newline=""), delimiter="\t", strict=True)
        )
    except csv.Error as error:
        raise ConversionError(f"malformed tab-delimited input: {error}") from error
    if not rows:
        raise ConversionError("input file is empty")

    header_index = next(
        (index for index, row in enumerate(rows) if any(cell.strip() for cell in row)),
        None,
    )
    if header_index is None:
        raise ConversionError("input file contains no marker data")

    raw_headers = rows[header_index]
    headers = [_normalise_header(value) for value in raw_headers]
    time_index = _find_column(headers, TIME_HEADERS, "timecode")
    title_index = _find_column(headers, TITLE_HEADERS, "chapter title")
    required_index = max(time_index, title_index)

    chapters: List[Chapter] = []
    export_separator: Optional[str] = None
    separator_seen = False
    for row_index, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        if not any(cell.strip() for cell in row):
            continue
        if len(row) <= required_index:
            raise ConversionError(f"row {row_index}: missing timecode or chapter title column")

        title = " ".join(row[title_index].split())
        if not title:
            raise ConversionError(f"row {row_index}: chapter title is empty")
        if fps is not None:
            _, current_separator = _absolute_timecode_seconds(
                row[time_index], row_index, fps
            )
            if separator_seen and current_separator != export_separator:
                raise ConversionError(
                    f"row {row_index}: marker timecodes use mixed notation"
                )
            export_separator = current_separator
            separator_seen = True
        seconds = parse_timecode(
            row[time_index], row_index, fps=fps, start_timecode=start_timecode
        )
        chapters.append(Chapter(seconds=seconds, title=title, row_number=row_index))

    if not chapters:
        raise ConversionError("input contains a header but no markers")
    return chapters


def validate_youtube_chapters(chapters: Sequence[Chapter]) -> None:
    """Validate the rules YouTube can verify without knowing video duration."""
    if not chapters:
        raise ConversionError("YouTube requires at least three chapters")
    if chapters[0].seconds != 0:
        raise ConversionError(
            f"first chapter must start at 00:00 (row {chapters[0].row_number})"
        )
    if len(chapters) < 3:
        raise ConversionError("YouTube requires at least three chapters")

    for previous, current in zip(chapters, chapters[1:]):
        if current.seconds == previous.seconds:
            raise ConversionError(
                f"rows {previous.row_number} and {current.row_number} have duplicate timestamps"
            )
        if current.seconds < previous.seconds:
            raise ConversionError(
                f"row {current.row_number}: timestamps are not in ascending order"
            )
        if current.seconds - previous.seconds < 10:
            raise ConversionError(
                f"rows {previous.row_number} and {current.row_number} are less than "
                "10 seconds apart"
            )


def format_timestamp(total_seconds: int) -> str:
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def format_chapters(chapters: Iterable[Chapter]) -> str:
    return "".join(
        f"{format_timestamp(chapter.seconds)} {chapter.title}\n" for chapter in chapters
    )


def convert_file(
    path: Path,
    validate: bool = True,
    fps: Optional[Fraction] = None,
    start_timecode: Optional[str] = None,
) -> str:
    try:
        contents = path.read_bytes()
    except OSError as error:
        raise ConversionError(f"cannot read {path}: {error.strerror or error}") from error
    chapters = parse_export(
        decode_export(contents), fps=fps, start_timecode=start_timecode
    )
    if validate:
        validate_youtube_chapters(chapters)
    return format_chapters(chapters)


def default_output_path(input_path: Path) -> Path:
    return input_path.with_name(f"{input_path.stem}_youtube_chapters.txt")


def paths_refer_to_same_file(input_path: Path, output_path: Path) -> bool:
    """Compare paths safely, including symlinks and hard links."""
    try:
        if input_path.resolve() == output_path.resolve():
            return True
        if input_path.exists() and output_path.exists():
            return input_path.samefile(output_path)
    except (OSError, RuntimeError) as error:
        raise ConversionError(f"cannot compare input and output paths: {error}") from error
    return False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert an Adobe Premiere Pro marker export to YouTube chapters."
    )
    parser.add_argument("input", type=Path, help="tab-delimited marker export")
    parser.add_argument(
        "-o",
        "--output",
        help="output file (default: <input stem>_youtube_chapters.txt; use - for stdout)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace an existing output file",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="format markers without enforcing YouTube's chapter rules",
    )
    parser.add_argument(
        "--fps",
        metavar="RATE",
        help="sequence frame rate, e.g. 24, 29.97, or 30000/1001",
    )
    parser.add_argument(
        "--start-timecode",
        metavar="TIMECODE",
        help="sequence start timecode; requires --fps",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    output_path: Optional[Path]
    if args.output == "-":
        output_path = None
    elif args.output:
        output_path = Path(args.output)
    else:
        output_path = default_output_path(args.input)

    try:
        fps = parse_fps(args.fps) if args.fps else None
        if args.start_timecode and fps is None:
            raise ConversionError("--start-timecode requires --fps")
        if output_path is not None and paths_refer_to_same_file(args.input, output_path):
            raise ConversionError("input and output paths must be different")
        rendered = convert_file(
            args.input,
            validate=not args.no_validate,
            fps=fps,
            start_timecode=args.start_timecode,
        )
        if output_path is None:
            sys.stdout.write(rendered)
        else:
            try:
                mode = "w" if args.force else "x"
                with output_path.open(mode, encoding="utf-8", newline="\n") as output_file:
                    output_file.write(rendered)
            except FileExistsError as error:
                raise ConversionError(
                    f"output already exists: {output_path} (use --force to replace it)"
                ) from error
            except OSError as error:
                raise ConversionError(
                    f"cannot write {output_path}: {error.strerror or error}"
                ) from error
            print(f"Wrote {len(rendered.splitlines())} chapters to {output_path}")
    except ConversionError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
