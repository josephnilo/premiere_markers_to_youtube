# Contributing

Thanks for helping improve Premiere Markers to YouTube Chapters.

## Development setup

The application and tests use only the Python standard library. Python 3.9 or newer
is required.

```bash
git clone https://github.com/josephnilo/premiere_markers_to_youtube.git
cd premiere_markers_to_youtube
python3 -m unittest discover -s tests -v
```

POSIX users can run the equivalent `./scripts/check` shortcut.

Installing the project into a virtual environment is optional:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --no-deps -e .
```

## Making a change

1. Keep conversion logic separate from command-line input/output so it can be tested.
2. Add or update a regression test in `tests/`.
3. Use synthetic marker names and metadata. Do not commit Premiere projects, client
   names, unpublished titles, media, or real production exports.
4. Run `./scripts/check` before opening a pull request.
5. Update the README or changelog when behavior visible to users changes.

The project intentionally has no third-party runtime dependencies. A new dependency
should solve a concrete problem that cannot reasonably be handled by the standard
library, and its maintenance and security cost should be explained in the pull
request.

## Reporting export-format problems

Include the Python version, operating system, exact command, error message, and a
minimal synthetic export that reproduces the issue. Preserve its delimiter and text
encoding, but replace all real production data.

## License

Contributions are accepted under the repository's [MIT License](LICENSE).
