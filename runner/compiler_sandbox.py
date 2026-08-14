import os
import resource
import sys

from privileges import drop_privileges


COMPILER_UID = 65534
COMPILER_GID = 65534
INVALID_EXIT_CODE = 126


def main() -> int:
    if len(sys.argv) < 4:
        print("Invalid compiler sandbox command", file=sys.stderr)
        return INVALID_EXIT_CODE

    try:
        memory_mb = int(sys.argv[1])
        max_processes = int(sys.argv[2])
    except ValueError:
        print("Invalid compiler sandbox limits", file=sys.stderr)
        return INVALID_EXIT_CODE
    if not 32 <= memory_mb <= 4096 or not 1 <= max_processes <= 64:
        print("Compiler sandbox limits are out of range", file=sys.stderr)
        return INVALID_EXIT_CODE

    command = sys.argv[3:]
    memory = memory_mb * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    resource.setrlimit(resource.RLIMIT_CPU, (10, 11))
    resource.setrlimit(
        resource.RLIMIT_FSIZE,
        (32 * 1024 * 1024, 32 * 1024 * 1024),
    )
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    resource.setrlimit(resource.RLIMIT_NPROC, (max_processes, max_processes))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    drop_privileges(COMPILER_UID, COMPILER_GID)
    os.execvpe(command[0], command, os.environ)
    return 126


if __name__ == "__main__":
    raise SystemExit(main())
