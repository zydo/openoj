# OpenOJ

OpenOJ is a containerized coding judge with a LeetCode-style
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
header toggle saves an explicit browser-local override. Visitors work in
ephemeral guest sessions: editor drafts are stored server-side per session
and survive refreshes, and both drafts and submission history are scoped to
the session (idle-expiring after an hour). Submission records persist in the
`openoj_data` volume.

## Problem packages

OpenOJ loads problems from two package formats. The canonical, split format
is one directory per problem (this is what
[openoj-problems](https://github.com/zydo/openoj-problems) uses):

```text
problems/
└── 0001-0100/           id-range shards of 100 (problems repo; the
    └── 0001_pair-sum/   bundled fallback set is a single bundle)
        ├── problem.json     metadata, invocation schema, limits
        ├── cases.json       testcase corpus ({public, hidden} display grouping)
        ├── statement.md     pure-prose statement with a fixed heading grammar
        ├── starter.py       generated from problem.json — never handcrafted
        └── solution.*       recommended solutions (not served by the API)
```

The flat single-file format (`0001_two-sum.md` with `## Metadata`,
`## Description`, … `## Test Cases` sections) is still supported; the
bundled `./problems` fallback set now uses the split format. Both formats can coexist in one directory;
the split format's statement grammar is `# <Title>`, required `## Description`
with `### Example N` and `### Constraints` (optional for SQL problems), and
optional `## Hints` with `### Hint N` headings.

Problems are mounted read-only from `./problems` by default. Sideload another
set without rebuilding images:

```bash
OPENOJ_PROBLEMS_PATH=/absolute/path/to/problems docker compose up --build
```

### Selecting a problem set with `OPENOJ_PROBLEMS`

**The default problem set is `zydo/openoj-problems`** — a plain
`docker compose up --build` clones it into `./.cache` on first start (and
afterwards only refreshes when the remote actually moved). To use something
else, set `OPENOJ_PROBLEMS`. The specification follows git's disambiguation
convention: a bare two-segment `owner/name` **always means GitHub**; a local
directory with that shape must be referenced explicitly and never shadows
the shorthand.

```bash
docker compose up --build                                          # default: zydo/openoj-problems
OPENOJ_PROBLEMS=zydo/openoj-problems@v1.2.0       docker compose up --build  # pinned branch/tag
OPENOJ_PROBLEMS=https://github.com/myname/set.git docker compose up --build  # full git URL
OPENOJ_PROBLEMS=./name/repo                       docker compose up --build  # local, explicit
OPENOJ_PROBLEMS=/problems                         docker compose up --build  # force the bundled 2-problem set
```

An unreachable remote keeps the cached revision (or fails loudly on a cold
cache), and `/problems` forces the bundled offline fallback without touching
the network.

Accepted forms:

- `owner/name[@ref]` — a GitHub repository, optionally pinned to a branch or
  tag (`release/v2`-style refs work).
- `https://host/owner/name.git[#ref]` (or `http://`) — a full git URL, pinned
  via a `#ref` fragment.
- `git@host:owner/name.git` — an SSH git URL (read access to the
  fetcher container's deploy key required).
- `/abs/path`, `./rel`, `../rel`, `~/rel`, `file:///abs/path` — a local
  directory. Relative and home paths resolve inside the `api` container, so
  pair them with a bind mount.

Remote sets are cloned (shallow) into a git-ignored `./.cache` directory
next to this repo (override with `OPENOJ_PROBLEMS_CACHE_DIR`); the clone's
commit hash is recorded in `.openoj-commit`. On each start the fetcher asks
the remote for its current hash for the pinned ref with one `ls-remote`:
if it matches the record, nothing is re-fetched; if it moved, the ref is
fetched and the working tree hard-reset to converge; if the remote is
unreachable (offline start) the cached revision is kept. The API container
itself has no external network — a one-shot `problems-fetcher` service (the
only component allowed to reach github.com) maintains the cache before the
API starts, and a missing cache fails startup loudly rather than silently
serving a different set. Local sets are used in place with no caching: bind
mounts update in realtime. In both cases,
if the resolved repository contains a `problems/` subdirectory, it is used as
the package root; otherwise the repository root is. When `OPENOJ_PROBLEMS`
is unset, problems come from the `OPENOJ_PROBLEMS_DIR` mount as before.

The fallback problem set (used when `OPENOJ_PROBLEMS` is unset) is one
sharded bundle:

```text
problems/
└── 0001-0100/
    └── 0001_pair-sum/
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
parameters and return values. The schema supports signed 32/64-bit integers,
finite numbers, booleans, UTF-8 strings, nested arrays, and LeetCode-style
linked lists (`linked_list`) and binary trees (`binary_tree`) carried as value
and level-order arrays. The API never sends expected values to the runner;
executor plugins encode testcase inputs into a typed binary stream and
serialize only the submitted function's result back to JSON.

The API renders only `## Description`; schema data, starters, and testcases do
not cross into the problem pane. Starter templates are neither global nor
standalone source files. Enabled templates use explicit not-implemented
statements so extracted skeletons remain syntactically valid before a user
fills them in.

The runner is language-pluggable. Each executor implements a small interface
that prepares or compiles source, returns the per-test command/environment, and
encodes the neutral testcase payload. Sandboxing, queueing, verdicts, storage,
and the HTTP API remain language-independent.

Python currently supplies `json`, `list_node`, `tree_node`,
`list_node_array`, `tree_node_array`, `nary_tree`,
and `html_parser` input codecs. Their wire forms match LeetCode conventions,
and the familiar `ListNode`, `TreeNode`, `Node`, and
`HtmlParser` names are injected into submitted modules. Java 21 supports the
`json`, `list_node`, `tree_node`, `list_node_array`, and `tree_node_array`
codecs, injecting the matching node classes. Its executor compiles once per
submission with annotation processing disabled, then starts a fresh JVM for
each testcase. C++, TypeScript, Go, Rust, and JavaScript use generated
wrappers derived from the neutral typed signature; the wrapper supplies
`ListNode`/`TreeNode` definitions for tree and linked-list problems (Rust
starters define them, following LeetCode convention), builds the structures
from the wire arrays, and serializes returned nodes back to level-order
arrays. C++, TypeScript, Go, and Rust compile once per submission, then start
a fresh process for each testcase; JavaScript runs the same generated wrapper
on Node without a compile step.

SQL problems are single `SELECT` queries judged against SQLite. Their
invocation carries the schema DDL in `sql.schema`, each testcase's `dataset`
value seeds the tables with `INSERT` statements, and the harness returns the
query's rows for row-set or exact-order comparison. SQL problems list only
`SQL` in their languages block, so the editor's language selector shows SQL
alone, and non-SQL problems never offer it.

At startup the runner calibrates every executor, then a background thread
pre-warms and periodically re-warms the compilers (rustc, g++, go build,
javac, tsc) by building throwaway programs. First submissions therefore pay
the same compile cost as later ones — Go additionally shares one persistent
build cache across submissions so its standard library is compiled once per
container, not once per job.

The bundled Two Sum demo has three visible and fifteen hidden cases covering
duplicates, zeros, negative values, non-adjacent answers, minimum input size,
and integer boundaries. The remaining problem set was imported from a curated
LeetCode selection: statements and hints were adapted locally, difficulty
labels (H1–H5) come from the curated source, and every testcase's expected
value was produced by running a reference solution.

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

### Reference-relative timing

Absolute milliseconds mean nothing across machines, so accepted submissions
are also compared against the problem's built-in solution. When a submission
is accepted and the problem bundle ships a `solution.<ext>` for the submitted
language, the judge immediately runs that reference through the same
container, the same calibrated executor, and the same cases, and the response
carries `reference_runtime_ms` alongside the user's `runtime_ms`. The UI
shows the ratio ("162% of reference"). The comparison is same-language by
construction, indicative rather than precise for very fast solutions, and
best-effort: without a bundled reference, or if the reference run cannot be
completed, the ratio is simply omitted.

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

## Data conventions

The JSON wire shapes for linked lists, trees, and design/interactive cases,
the typed binary stream the compiled-language wrappers read, and the
comparison modes are documented in [docs/CODECS.md](docs/CODECS.md).

## REST API

The judge's HTTP API (problems, run, submit, submissions, guest sessions,
drafts) is available to scripted callers — see [docs/API.md](docs/API.md) for
endpoints, the session model, and the opt-in direct-API endpoint.

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
