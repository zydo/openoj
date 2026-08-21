# Trust boundaries of the judging pipeline

Who is trusted with what, stated deliberately. This document exists
because the bundle-carried-code move (the `common/` library and
per-problem `provided/` sources assembled into every submission) made a
previously implicit assumption explicit; writing it down is the point.

## The layers

| code | origin | runs | trust class |
| --- | --- | --- | --- |
| runner harness, executors, codecs | the openoj repo (`runner/`) | inside the sandbox, beside the submission | **framework** — trusted absolutely, versioned with the repo |
| `common/` shared types | the problems repo (`openoj-problems/common/`) | inside the sandbox, compiled/executed with every submission | **problem-set content** — trusted like `cases.json` |
| `provided/<language>/` oracles & helpers | each problem bundle (`problems/<key>/provided/`) | inside the sandbox, beside the submission | **problem-set content** — same trust as the bundle's own cases |
| the submission | a solver | inside the sandbox, unprivileged | **untrusted** |

## What "trusted like cases.json" means

Testcase data has always been problem-author-controlled and has always
run inside (or directly driven) the sandbox. `common/` and `provided/`
sources occupy exactly that position: they are authored in the problems
repo, reviewed with it, and versioned with it. A malicious author of
problem content can already shape case data; giving that same author a
compiled class does not cross a new boundary — but it does raise the
stakes, which is why this is written down rather than inherited.

Concretely, the existing protections all still apply:

- submissions execute under the unprivileged runtime sandbox (rlimits,
  restricted privileges, no network) — the **submission** is confined
  there;
- `provided/` code is judged code, not judge code: it runs in the same
  confined process as the submission, so a hostile oracle cannot reach
  the worker, the host, or other jobs;
- the framework itself (`runner/`) never executes anything from the
  problems repo beyond what the executors explicitly assemble, and the
  assembly surface is exactly: `common/<language>/` and
  `problems/<key>/provided/<language>/` files, concatenated or
  compiled — never arbitrary paths, never build scripts.

## What is deliberately NOT done (yet)

- No per-problem resource accounting for `provided/` code beyond the
  submission's own limits — the oracle shares the case's time and
  memory budget, which is the intended constraint.
- No code signing or provenance chain on the problems repo; the git
  history and review process are the provenance. If the problem set is
  ever sourced from third parties, revisit this section first.
- A **versioned common-harness contract** (bundles declaring which
  common-library version they assume) remains open — see TODO.md. The
  ambient-dependency coupling it would remove is currently harmless
  because both trees move together in one repo.

## Where the boundary is enforced in code

- `api/app/main.py` `_assembly_sources` — the only place the judge
  request is populated with library sources; it reads exactly two
  well-known directories and nothing else.
- `runner/executors/*_interactive.py`, `*_design.py` — assembly is
  concatenation/compilation of the received sources; no path from the
  request is ever executed or included by reference.
- `runner/compiler_sandbox.py` / `runtime_sandbox.py` — the privilege
  split between compiler, runtime, and supervisor.
