# TODO — discussed, not started

Items here are design decisions we have agreed to discuss or build later.
Nothing on this page is in progress; when work starts, move it to the task
list and delete it here.

## Import the 48 BETTERCODE 替代题 alternatives (next up)

BETTERCODE.md lists 838 problems; the Prime import (735, all solved in 7
languages) folded series into one representative and excluded all 48
替代题. All of them are wanted. Breakdown and plan (was Task #9):

- **42 plain function problems → full 7-language pipeline**: author
  statement.md/cases.json/reference solution, generate starters, port
  solutions to all languages, verify every case with
  `.localonly/verify_solution.py`, format with the pinned toolchain.
  Includes best-time-to-buy-and-sell-stock iii/iv/with-cooldown/
  with-transaction-fee, two-sum-ii, single-number ii/iii, jump-game
  iv/vi/viii, house-robber iii/iv, basic-calculator ii/iii, coin-change-ii,
  course-schedule ii/iii/iv, linked-list-cycle-ii,
  lowest-common-ancestor-of-a-binary-tree, number-of-islands-ii (per-query
  array function), stone-game ii/vi, word-ladder, trapping-rain-water-ii,
  cherry-pickup, distinct-subsequences-ii,
  egg-drop-with-2-eggs-and-n-floors, create-components-with-same-value,
  erect-the-fence-ii, longest-increasing-subsequence-ii,
  longest-special-path-ii, maximum-number-of-events-that-can-be-attended-ii,
  minimum-weighted-subgraph-with-the-required-paths-ii,
  next-greater-element ii/iv, palindrome-partitioning ii/iii,
  parallel-courses ii/iii, separate-squares-ii, ugly-number-iii,
  last-stone-weight-ii.
- **5 design/class problems → python3+java only** (typed wrappers lack
  design-invocation support; bundles carry `starter.py`+`starter.java` and
  matching solutions): my-calendar-iii,
  insert-delete-getrandom-o1-duplicates-allowed,
  range-sum-query-mutable, range-sum-query-2d-mutable.
- **1 interactive problem, deferred** pending the interactive framework
  (see below): minimum-path-cost-in-a-hidden-grid.
- Use LeetCode ids as bundle keys (no collisions possible). Authoring
  standard: same as the Prime set — reference-computed expected values,
  ≥10 hidden cases, formatter-clean, `check.py --skip-runtime` green.
- End state: 735 + 47 = 782 problems.

## Multi-user support (guest sessions → accounts)

Guest sessions DONE (phase 1):

- First visit lands on a **"Continue as guest"** page — the only entrance
  until accounts exist.
- A guest is an HttpOnly cookie session with an **idle expiry of 1 hour**;
  expired sessions and everything they own (drafts, submissions) are purged.
- Editor drafts are server-side and session-scoped: they persist per problem
  and survive refreshes; a mid-use expiry returns the visitor to the gate
  with a notice. Pre-session (legacy) submissions remain visible to all.

Later, openwebui-style **user accounts**, persisted in the container's
storage:
  - First start prompts to create the admin account: conventional
    username + password (no email), password typed twice.
  - `admin` is a reserved username.
  - Normal (non-admin) accounts can also be created.
  - Non-guest account data is persisted and **isolated**: a non-admin user
    never sees another non-admin user's data (submissions, drafts, state).

## Tolerance comparison for float returns

DONE — the judge supports `comparison: "close"` (string, default 1e-9
relative+absolute per scalar, recursive through nested lists/objects; or
`{"mode": "close", "tolerance": …}` for a custom tolerance). The 15
float-returning bundles are switched to close mode; expected values were
already the Python-reference values, and all 15 verify green across every
language. The frontend shows `Expected <value> ±1e-9` for close problems.

## Interactive problem framework

Needed to judge `minimum-path-cost-in-a-hidden-grid` (the one deferred
BETTERCODE 替代题): the solution queries a hidden oracle (`GridMaster`
API), so the judge must mediate a multi-turn protocol per case instead of
one function call. Design questions: protocol between wrapper and harness,
how the oracle is encoded per case, and limits modeling (query count?).

## Trim bundled flat problem set after the openoj-problems migration

DONE — the 733 flat `problems/*.md` files duplicated in openoj-problems were
deleted; `problems/` now keeps only the offline fallback (`0001_two-sum.md`,
`0002_add-two-numbers.md`). The full set is served via `OPENOJ_PROBLEMS`
(the cache in `./.cache`).

## Expose and document the REST API

DONE — `docs/API.md` documents the full surface (sessions, problems, drafts,
run, submit, submissions, comparison modes, errors, limits). The API is
always reachable same-origin through the web UI; an opt-in direct endpoint
(`api.openoj.dongziyu.com`) is enabled with
`OPENOJ_CADDY_EXTRA=./deploy/api.caddy` (caddy imports the extra site block;
default mounts an empty file). Auth/rate limiting stays open until accounts
exist — guest sessions are the only gate, so edge rate limiting is on the
operator.

## JS/TS exact serialization of large i64 returns

DONE — the JS/TS wrappers now serialize return values through a custom
`openojSerialize` that emits integer doubles beyond 2^53 as exact decimal
digits (`BigInt(value).toString()`), instead of `JSON.stringify`'s lossy
exponent notation. Verified: 3749 js/ts 20/20 (the 2^62 case included), 0001
js/ts regression-clean, test suite green.
