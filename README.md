# OpenOJ

OpenOJ is a single-user, containerized coding judge with a LeetCode-style
class-and-method workflow. It runs untrusted Python 3.14.7, Java 21.0.12,
C++20 with G++ 14.2.0, TypeScript 7.0.2 on Node 22.23.2, JavaScript on
Node 22.23.2, Go 1.24.4, and Rust 1.85.0 submissions, keeps problem packages
outside the application images, and persists submission history in a Docker
volume.

## Start it

```bash
docker compose up --build
```

Open <http://localhost:8080>. Set `OPENOJ_PORT` to publish another port:

```bash
OPENOJ_PORT=9090 docker compose up --build
```

The editor uses Monaco's language services and local worker bundles, so grammar
highlighting, bracket matching, and indentation guides do not depend on a CDN.
The first visit follows the operating system's light/dark preference; the
header toggle saves an explicit browser-local override. Draft code is also
saved in browser storage. Submitted code and verdict history are stored in the
`openoj_data` volume.

## Problem packages

Problems are mounted read-only from `./problems` by default. Sideload another
set without rebuilding images:

```bash
OPENOJ_PROBLEMS_PATH=/absolute/path/to/problems docker compose up --build
```

Each problem is one self-contained, flattened Markdown document:

```text
problems/
└── 0001_two-sum.md
```

The filename schema is `<zero-padded id>_<slug>.md`. Its id and slug must match
the document's level-one title and metadata. Every document must contain these
level-two headings exactly once and in this order:

```text
# <id>. <title>
## Metadata
## Description
## Hints
## Invocation
## Limits
## Languages
## Starters
## Test Cases
```

`Metadata`, `Hints`, `Invocation`, `Limits`, and `Languages` each contain one
fenced `json` block. `Starters` contains one `### <language key>` heading and
one code fence for every language, in the same order as `Languages`. `Test
Cases` contains ordered `### Public` and `### Hidden` headings, each with one
JSON array of `{input, expected}` objects. Missing, duplicated, unknown, or
reordered schema headings are rejected instead of being guessed.

The document is the language-agnostic source of truth for the problem
statement, hints, LeetCode-style invocation, ordered parameters and codecs,
comparison strategy, resource limits, adapters, starters, and testcase corpus.
Function inputs use positional argument arrays (`[[2,7,11,15], 9]` for Two
Sum). Design problems use `{"actions": [...], "params": [...]}` sequences.

Static-language function wrappers use the same neutral `value_type` shapes on
parameters and return values. The initial schema supports signed 32/64-bit
integers, finite numbers, booleans, UTF-8 strings, and nested arrays. The API
never sends expected values to the runner; executor plugins encode testcase
inputs into a typed binary stream and serialize only the submitted function's
result back to JSON.

The API renders only `## Description`; schema data, starters, and testcases do
not cross into the problem pane. Starter templates are neither global nor
standalone source files. Enabled templates use explicit not-implemented
statements so extracted skeletons remain syntactically valid before a user
fills them in.

The runner is language-pluggable. Each executor implements a small interface
that prepares or compiles source, returns the per-test command/environment, and
encodes the neutral testcase payload. Sandboxing, queueing, verdicts, storage,
and the HTTP API remain language-independent.

Python currently supplies `json`, `list_node`, `tree_node`, `nary_tree`,
`nested_integer_list`, and `html_parser` input codecs. Their wire forms match
LeetCode conventions, and the familiar `ListNode`, `TreeNode`, `Node`,
`NestedInteger`, and `HtmlParser` names are injected into submitted modules.
Java 21 supports the neutral `json` codec, including primitive values, arrays,
nested arrays, collections, and maps. Its executor compiles once per submission
with annotation processing disabled, then starts a fresh JVM for each testcase.
C++, TypeScript, Go, and Rust compile once with generated wrappers derived from
the neutral typed signature, then start a fresh process for each testcase.
JavaScript uses the same generated wrapper on Node without a compile step.

The bundled Two Sum demo has three visible and fifteen hidden cases covering
duplicates, zeros, negative values, non-adjacent answers, minimum input size,
and integer boundaries. It is adapted from the user-provided LeetCode reference
and links back to the source.

## Judging and time limits

The document's `## Limits` `time_ms` is a nominal per-testcase deadline. At runner startup,
each executor runs a deterministic language-specific benchmark. The runner
scales that language's deadline by its score and clamps the factor to
`0.75x–3.0x`, keeping results reasonable across different machines without
allowing an arbitrarily slow host to disable the limit.

Both wall-clock and CPU limits are enforced. An infinite loop is killed as a
process group, remaining cases are skipped, and any processes left behind by a
submission UID are terminated. Memory, process count, open files, output size,
and core dumps are limited independently.

Inspect the current calibration with:

```bash
docker compose logs runner
```

## Security boundary

The assertion system is deliberately outside the execution container:

- The API reads expected answers and compares results; expected data is never
  placed in a runner request.
- The runner container has no network namespace and does not mount problem or
  persistence volumes.
- Queue directories are inaccessible to the unprivileged submission UID.
- Every testcase starts a fresh isolated language process with a read-only root
  filesystem, a private scratch directory, dropped privileges, `no-new-privileges`,
  Docker resource limits, and POSIX rlimits.
- Hidden inputs, expected values, stdout, exception text, and per-case timing
  are never returned to the browser.
- The API and web containers do not receive the Docker socket.

The trusted runner supervisor starts as container UID 10000, not root. A
dedicated supervisor-only Python executable carries exactly `CHOWN`, `KILL`,
`SETUID`, `SETGID`, and `DAC_OVERRIDE`; the last capability exists only so it
can remove per-job trees created with hostile permissions. General Python does
not carry them. The supervisor has no network, writable root filesystem,
Docker socket, problem mount, or persistence mount.
Submission source is never imported into it. Before any hostile compiler or
runtime executes, the child changes to UID/GID 65534, explicitly empties its
permitted/effective/inheritable capability sets, and enables
`no-new-privileges`. The general `/tmp` remains `noexec`; compiled programs live
only in a per-job directory on an ephemeral executable tmpfs and are deleted
after the job.

Every compiler has independent CPU, address-space, file, descriptor, process,
and wall-clock limits. Java annotation processing and Go CGO/network module
resolution are disabled. The whole runner remains networkless, read-only, and
bounded by a 768 MB memory cgroup even where managed toolchains require a larger
virtual-address allowance.

Docker build arguments pin Python, Node, and TypeScript versions. The runner
also pins the complete Debian package revisions for G++, Go, OpenJDK, Rust,
and the capability utility. A package repository change therefore fails the
image build instead of silently selecting a different compiler.

This is defense in depth for hostile code, but ordinary Docker containers share
the host kernel. An internet-facing deployment should place the runner on a
dedicated disposable VM or node and add a stronger runtime such as gVisor,
Kata Containers, or Firecracker, plus ingress rate limits. That keeps a future
container-runtime or kernel escape away from the API and stored submissions.

## Persistence

SQLite data lives at `/data/openoj.sqlite3` in the `openoj_data` named volume.
Normal `docker compose down` and image rebuilds preserve it. The judge queue is
a separate transient volume and contains no expected answers.

## Verification

```bash
python3.14 -m pytest -q
cd frontend && npm run build && npm audit --omit=dev
docker compose config --quiet
```
