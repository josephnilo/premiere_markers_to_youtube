# Local CI

Python 3.11 standard library only. The current conversion CLI deletes its input
after exporting chapters. Tests therefore create UTF-16 TSV files in private temporary
directories; no original Premiere exports or media are used.

Run `./ci/run.sh` in a disposable source checkout. Dependency preparation is a
separate trusted step; the check command never installs packages or calls live
services. Linux validation targets Ubuntu Air ARM64.

No Actions runner is added or admitted by this change. Automatic Actions checks
remain unavailable under the current selected private runner policy. This entrypoint
is ready for review and manual local execution; it is not a branch protection check.
No hosted runner, deployment, upload, merge or paid API is involved.
