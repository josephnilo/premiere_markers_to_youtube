import os
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path
import unittest

import premiere_markers_to_youtube as converter


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "premiere_markers_to_youtube.py"
FIXTURE = ROOT / "tests" / "fixtures" / "premiere_markers.tsv"
BROADCAST_FIXTURE = ROOT / "tests" / "fixtures" / "broadcast_markers.tsv"


class ParsingTests(unittest.TestCase):
    def test_historical_premiere_layout_and_unicode(self):
        chapters = converter.parse_export(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(
            converter.format_chapters(chapters),
            "00:00 Introduction\n"
            "00:14 2D Animated Explainer Videos\n"
            "00:35 Café & Whiteboard Explainers\n"
            "1:02:03 Questions & Answers\n",
        )

    def test_decodes_utf16_utf8_and_utf8_bom(self):
        text = FIXTURE.read_text(encoding="utf-8")
        for encoding in ("utf-16", "utf-8", "utf-8-sig", "utf-16-le", "utf-16-be"):
            with self.subTest(encoding=encoding):
                self.assertEqual(converter.decode_export(text.encode(encoding)), text)

    def test_named_columns_can_be_in_a_different_order(self):
        text = (
            "Marker Name\tMarker Type\tStart\n"
            "  Intro  \tChapter\t00:00:00.000\n"
            "Second   chapter\tChapter\t00:00:10.999\n"
            '"A title\nwith whitespace"\tChapter\t00:00:20:12\n'
        )
        chapters = converter.parse_export(text)
        self.assertEqual(
            converter.format_chapters(chapters),
            "00:00 Intro\n00:10 Second chapter\n00:20 A title with whitespace\n",
        )

    def test_description_keeps_historical_priority_over_marker_name(self):
        text = (
            "Description\tIn Point\tMarker Name\n"
            "Longer note\t00:00:00:00\tChapter title\n"
        )
        chapters = converter.parse_export(text)
        self.assertEqual(converter.format_chapters(chapters), "00:00 Longer note\n")

    def test_header_only_is_rejected(self):
        with self.assertRaisesRegex(converter.ConversionError, "header but no markers"):
            converter.parse_export("In Point\tDescription\n")

    def test_empty_input_is_rejected(self):
        with self.assertRaisesRegex(converter.ConversionError, "input file is empty"):
            converter.decode_export(b"")

    def test_missing_header_is_rejected(self):
        with self.assertRaisesRegex(converter.ConversionError, "timecode column"):
            converter.parse_export("Foo\tDescription\n00:00\tIntro\n")

    def test_malformed_timecode_is_rejected_with_row(self):
        with self.assertRaisesRegex(converter.ConversionError, "row 2: invalid timecode"):
            converter.parse_export("In Point\tDescription\nnot-a-time\tIntro\n")

    def test_empty_title_is_rejected(self):
        with self.assertRaisesRegex(converter.ConversionError, "row 2: chapter title is empty"):
            converter.parse_export("In Point\tDescription\n00:00:00:00\t \n")

    def test_invalid_encoding_is_rejected(self):
        with self.assertRaisesRegex(converter.ConversionError, "not valid UTF-16 or UTF-8"):
            converter.decode_export(b"\x80\x81\x82")

    def test_malformed_quoted_tsv_is_rejected(self):
        text = 'In Point\tDescription\n00:00:00:00\t"unterminated\n'
        with self.assertRaisesRegex(
            converter.ConversionError, "malformed tab-delimited input"
        ):
            converter.parse_export(text)

    def test_duplicate_recognised_header_is_rejected(self):
        text = "In Point\tIn Point\tDescription\n00:00:00:00\t00:00:00:00\tIntro\n"
        with self.assertRaisesRegex(converter.ConversionError, "duplicate timecode"):
            converter.parse_export(text)

    def test_negative_and_out_of_range_timecodes_are_rejected(self):
        cases = (
            ("-00:00:01:00", "invalid timecode"),
            ("00:60:00:00", "minutes must be"),
            ("00:00:60:00", "seconds must be"),
            ("00:00:00:frames", "invalid timecode"),
        )
        for timecode, message in cases:
            with self.subTest(timecode=timecode):
                with self.assertRaisesRegex(converter.ConversionError, message):
                    converter.parse_timecode(timecode, 2)

    def test_subsecond_fields_are_floored(self):
        self.assertEqual(converter.parse_timecode("00:00:09.999", 2), 9)
        self.assertEqual(converter.parse_timecode("00:00:09;29", 2), 9)
        self.assertEqual(converter.parse_timecode("00:00:10.000", 2), 10)

    def test_common_fractional_frame_rates_are_exact_rationals(self):
        self.assertEqual(converter.parse_fps("23.976"), Fraction(24000, 1001))
        self.assertEqual(converter.parse_fps("29.97"), Fraction(30000, 1001))
        self.assertEqual(converter.parse_fps("30000/1001"), Fraction(30000, 1001))

    def test_invalid_frame_rates_are_rejected(self):
        for value in ("0", "-24", "24.5", "not-a-rate"):
            with self.subTest(value=value):
                with self.assertRaises(converter.ConversionError):
                    converter.parse_fps(value)

    def test_fps_corrects_long_non_drop_timecodes(self):
        cases = (
            ("24", 3600),
            ("23.976", 3603),
            ("29.97", 3603),
            ("59.94", 3603),
        )
        for fps, expected in cases:
            with self.subTest(fps=fps):
                self.assertEqual(
                    converter.parse_timecode(
                        "01:00:00:00", 2, fps=converter.parse_fps(fps)
                    ),
                    expected,
                )

    def test_drop_frame_validation_uses_supplied_fps(self):
        fps = converter.parse_fps("29.97")
        self.assertEqual(converter.parse_timecode("01:00:00;00", 2, fps=fps), 3600)
        self.assertEqual(converter.parse_timecode("00:01:00;02", 2, fps=fps), 60)
        with self.assertRaisesRegex(converter.ConversionError, "invalid dropped-frame"):
            converter.parse_timecode("00:01:00;00", 2, fps=fps)
        with self.assertRaisesRegex(converter.ConversionError, "drop-frame timecode"):
            converter.parse_timecode(
                "00:01:00;00", 2, fps=converter.parse_fps("24")
            )

    def test_fps_validates_frame_number(self):
        with self.assertRaisesRegex(converter.ConversionError, "frame number must be"):
            converter.parse_timecode(
                "00:00:00:24", 2, fps=converter.parse_fps("24")
            )

    def test_start_timecode_offsets_non_drop_sequence(self):
        fps = converter.parse_fps("29.97")
        self.assertEqual(
            converter.parse_timecode(
                "01:00:00:00", 2, fps=fps, start_timecode="01:00:00:00"
            ),
            0,
        )
        self.assertEqual(
            converter.parse_timecode(
                "01:00:10:00", 3, fps=fps, start_timecode="01:00:00:00"
            ),
            10,
        )

    def test_start_timecode_requires_matching_notation(self):
        fps = converter.parse_fps("29.97")
        mismatches = (
            ("01:00:10:00", "01:00:00"),
            ("01:00:10", "01:00:00:00"),
            ("01:00:10.000", "01:00:00:00"),
            ("01:00:10:00", "01:00:00;00"),
        )
        for marker, start in mismatches:
            with self.subTest(marker=marker, start=start):
                with self.assertRaisesRegex(converter.ConversionError, "same notation"):
                    converter.parse_timecode(
                        marker, 2, fps=fps, start_timecode=start
                    )

    def test_start_timecode_accepts_matching_notation(self):
        fps = converter.parse_fps("29.97")
        cases = (
            ("01:00:10", "01:00:00", 10),
            ("01:00:10.500", "01:00:00.500", 10),
            ("01:00:10:00", "01:00:00:00", 10),
            ("01:00:10;00", "01:00:00;00", 10),
        )
        for marker, start, expected in cases:
            with self.subTest(marker=marker, start=start):
                self.assertEqual(
                    converter.parse_timecode(
                        marker, 2, fps=fps, start_timecode=start
                    ),
                    expected,
                )

    def test_fps_rejects_mixed_marker_notation(self):
        text = (
            "In Point\tDescription\n"
            "00:00:00:00\tIntroduction\n"
            "00:00:10;00\tSecond chapter\n"
            "00:00:20:00\tThird chapter\n"
        )
        with self.assertRaisesRegex(converter.ConversionError, "mixed notation"):
            converter.parse_export(text, fps=converter.parse_fps("29.97"))


class ValidationTests(unittest.TestCase):
    def chapter(self, seconds, row):
        return converter.Chapter(seconds, f"Chapter {row}", row)

    def test_valid_chapters(self):
        converter.validate_youtube_chapters(
            [self.chapter(0, 2), self.chapter(10, 3), self.chapter(20, 4)]
        )

    def test_empty_chapter_list_is_rejected(self):
        with self.assertRaisesRegex(converter.ConversionError, "at least three"):
            converter.validate_youtube_chapters([])

    def test_requires_zero_start(self):
        with self.assertRaisesRegex(converter.ConversionError, "must start at 00:00"):
            converter.validate_youtube_chapters(
                [self.chapter(1, 2), self.chapter(11, 3), self.chapter(21, 4)]
            )

    def test_requires_three_chapters(self):
        with self.assertRaisesRegex(converter.ConversionError, "at least three"):
            converter.validate_youtube_chapters([self.chapter(0, 2), self.chapter(10, 3)])

    def test_rejects_duplicate_timestamps(self):
        with self.assertRaisesRegex(converter.ConversionError, "duplicate timestamps"):
            converter.validate_youtube_chapters(
                [self.chapter(0, 2), self.chapter(10, 3), self.chapter(10, 4)]
            )

    def test_rejects_out_of_order_timestamps(self):
        with self.assertRaisesRegex(converter.ConversionError, "not in ascending order"):
            converter.validate_youtube_chapters(
                [self.chapter(0, 2), self.chapter(20, 3), self.chapter(10, 4)]
            )

    def test_rejects_short_chapter(self):
        with self.assertRaisesRegex(converter.ConversionError, "less than 10 seconds"):
            converter.validate_youtube_chapters(
                [self.chapter(0, 2), self.chapter(9, 3), self.chapter(20, 4)]
            )


class CommandLineTests(unittest.TestCase):
    def run_cli(self, *arguments, cwd=None):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, arguments)],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )

    def make_export(self, directory):
        source = Path(directory) / "markers.txt"
        source.write_bytes(FIXTURE.read_text(encoding="utf-8").encode("utf-16"))
        return source

    def test_default_output_preserves_input(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.make_export(directory)
            original = source.read_bytes()
            result = self.run_cli(source, cwd=directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(source.read_bytes(), original)
            output = Path(directory) / "markers_youtube_chapters.txt"
            self.assertEqual(
                output.read_text(encoding="utf-8"),
                "00:00 Introduction\n"
                "00:14 2D Animated Explainer Videos\n"
                "00:35 Café & Whiteboard Explainers\n"
                "1:02:03 Questions & Answers\n",
            )

    def test_stdout_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.make_export(directory)
            result = self.run_cli(source, "--output", "-", cwd=directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(result.stdout.startswith("00:00 Introduction\n"))
            self.assertEqual(sorted(Path(directory).iterdir()), [source])

    def test_existing_output_requires_force(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.make_export(directory)
            output = Path(directory) / "chapters.txt"
            output.write_text("keep me", encoding="utf-8")
            result = self.run_cli(source, "-o", output, cwd=directory)
            self.assertEqual(result.returncode, 1)
            self.assertIn("output already exists", result.stderr)
            self.assertEqual(output.read_text(encoding="utf-8"), "keep me")
            forced = self.run_cli(source, "-o", output, "--force", cwd=directory)
            self.assertEqual(forced.returncode, 0, forced.stderr)
            self.assertTrue(output.read_text(encoding="utf-8").startswith("00:00"))

    def test_missing_input_has_clean_error(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_cli("missing.tsv", cwd=directory)
            self.assertEqual(result.returncode, 1)
            self.assertIn("error: cannot read missing.tsv", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_no_validate_formats_draft(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "draft.tsv"
            source.write_text(
                "In Point\tDescription\n00:00:05:00\tDraft\n", encoding="utf-8"
            )
            rejected = self.run_cli(source, "-o", "-", cwd=directory)
            self.assertEqual(rejected.returncode, 1)
            accepted = self.run_cli(source, "-o", "-", "--no-validate", cwd=directory)
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            self.assertEqual(accepted.stdout, "00:05 Draft\n")

    def test_malformed_tsv_produces_no_output(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "broken.tsv"
            source.write_text(
                'In Point\tDescription\n00:00:00:00\t"unterminated\n',
                encoding="utf-8",
            )
            result = self.run_cli(source, cwd=directory)
            self.assertEqual(result.returncode, 1)
            self.assertIn("malformed tab-delimited input", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertEqual(sorted(Path(directory).iterdir()), [source])

    def test_output_cannot_be_input_even_with_force(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.make_export(directory)
            original = source.read_bytes()
            result = self.run_cli(source, "--output", source, "--force", cwd=directory)
            self.assertEqual(result.returncode, 1)
            self.assertIn("input and output paths must be different", result.stderr)
            self.assertEqual(source.read_bytes(), original)

    def test_hard_link_output_cannot_overwrite_input(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.make_export(directory)
            original = source.read_bytes()
            output = Path(directory) / "same-inode.txt"
            os.link(source, output)
            result = self.run_cli(source, "--output", output, "--force", cwd=directory)
            self.assertEqual(result.returncode, 1)
            self.assertIn("input and output paths must be different", result.stderr)
            self.assertEqual(source.read_bytes(), original)

    def test_missing_output_directory_has_clean_error(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.make_export(directory)
            output = Path(directory) / "missing" / "chapters.txt"
            result = self.run_cli(source, "--output", output, cwd=directory)
            self.assertEqual(result.returncode, 1)
            self.assertIn("error: cannot write", result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_help_and_version(self):
        help_result = self.run_cli("--help")
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        normalised_help = " ".join(help_result.stdout.split())
        self.assertIn("<input stem>_youtube_chapters.txt", normalised_help)
        version_result = self.run_cli("--version")
        self.assertEqual(version_result.returncode, 0, version_result.stderr)
        self.assertIn(converter.__version__, version_result.stdout)

    def test_start_timecode_requires_fps(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.make_export(directory)
            result = self.run_cli(
                source, "--start-timecode", "01:00:00:00", cwd=directory
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("--start-timecode requires --fps", result.stderr)

    def test_fps_and_start_timecode_convert_broadcast_sequence(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "broadcast.tsv"
            source.write_text(
                BROADCAST_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8"
            )
            result = self.run_cli(
                source,
                "--fps",
                "29.97",
                "--start-timecode",
                "01:00:00:00",
                "--output",
                "-",
                cwd=directory,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                result.stdout,
                "00:00 Introduction\n00:10 Second chapter\n00:20 Third chapter\n",
            )


if __name__ == "__main__":
    unittest.main()
