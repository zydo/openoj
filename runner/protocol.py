"""The judge protocol line: submission-facing harnesses in every
scripting language emit their verdict on this one channel."""

import sys

# The judge protocol line prefers the dedicated protocol fd so submission
# code cannot forge verdicts on stdout; it falls back to stdout when the fd
# is absent (local authoring tooling runs harnesses without it).
PROTOCOL_FD = 63


def emit_protocol(line: str) -> None:
    import os

    payload = (line + "\n").encode("utf-8")
    try:
        os.write(PROTOCOL_FD, payload)
    except OSError:
        sys.stdout.write(line + "\n")
