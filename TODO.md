# TODO — discussed, not started

Items here are design decisions we have agreed to discuss or build later.
Nothing on this page is in progress; when work starts, move it to the task
list and delete it here.

## Self-contained problem bundles

Today a problem is not fully described by its own directory. Adding an
interactive problem means editing the *framework*: a new oracle class in
`runner/interactive_oracles.py` and `runner/java/InteractiveOracles.java`,
entries in both harness dispatch tables (`_build_oracle`,
`ORACLE_AUXILIARY`, `buildOracle`, `auxiliaryArguments`), and a row in
`gen_starters.py`'s `INTERACTIVE_ORACLES`. The adaptation program makes
this concrete: renaming a problem's own oracle — which is part of that
problem's public API — forces a change to the judge.

The goal is a bundle that carries everything specific to itself, so the
problems repository is portable and a problem can be added without
touching the judge.

**Two kinds of harness, with different homes:**

- **Common harness** — the shared vocabulary every problem may use:
  `ListNode`, `TreeNode`, n-ary `Node`, `NestedInteger`, and the codecs
  that encode and decode them (`runner/leetcode_types.py`, the typed
  binary encoder, `runner/java/{ListNode,TreeNode}.java`). This is
  language-runtime plumbing and stays in the framework, but it should
  become a **versioned contract** that a bundle can declare it needs,
  rather than an implicit ambient dependency.
- **Problem-specific harness** — code that exists to serve one problem's
  context and is reusable nowhere else: the eight interactive oracles
  (~450 lines across both languages), and anything similar a future
  problem invents. This belongs **inside the bundle**.

**Sketch of the bundle-carried form:**

```
problems/0489_.../
  harness/oracle.py
  harness/Oracle.java
  problem.json      # invocation.harness declares the entry points:
                    #   class name, how to build it from the case state,
                    #   which case keys ride as extra method arguments,
                    #   whether the final state is the verdict
```

The judge would load these into the submission's namespace exactly the
way it already injects `TreeNode`, and the dispatch tables collapse into
a declared contract read from `problem.json`.

**What has to be worked out first:**

- **Trust boundary.** Harness code runs inside the sandbox next to the
  submission. It is problem-author code, trusted the way `cases.json` is
  trusted — but that trust is currently implicit in "it ships in the
  judge image" and would become explicit in "it ships in the problem
  repo". Worth stating deliberately rather than inheriting.
- **Sharing.** `GridMaster` serves two problems today. Bundle-carried
  harness means either duplicating it or introducing a shared-harness
  concept, which reopens the coupling from the other side.
- **Starter generation.** `gen_starters.py` needs the harness's type
  names to emit signatures; it would read them from the manifest instead
  of its own table.
- **Compilation.** Java harness classes currently compile into the image
  at build time; per-bundle classes would compile per job, which costs
  time on every interactive submission unless cached.

Related: ADAPT.md's oracle section, which renames the eight oracles and
keeps the old names as aliases until cutover.

## User accounts (multi-user phase 2)

Account creation (fresh-start admin bootstrap, regular sign-up, login,
logout) and user-scoped drafts/submissions are done and live. Remaining:

- **Better password and user identity management** (subject to design
  discussion) — the current scrypt-with-salt scheme and fixed-name admin
  bootstrap are a baseline, not the destination.
- Admin management surface (listing/deleting accounts, resetting
  passwords) once the accounts UI grows beyond the gate.

## Multi-solution bundles, beyond the first 42

The convention is fully wired (judge, check.py, Solutions tab,
fastest-variant baseline) and 42 problems carry named variants across all
seven languages. Extending it is open-ended content work: find further
problems whose approaches are genuinely distinct and comparable, and
author the variant sets.
