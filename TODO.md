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

Serve multiple users:

- First visit lands on a **"Continue as guest"** page. Keep this entrance
  even after accounts exist — it is the only way in until login is built.
- A guest is a cookie session (or equivalent temporary identity) with an
  **idle expiry of ~1 hour**. Session-local storage persists editor state
  per problem and survives page refreshes; after the idle timeout the
  session is cleared and the visitor must "Continue as guest" again.
- Later, openwebui-style **user accounts**, persisted in the container's
  storage:
  - First start prompts to create the admin account: conventional
    username + password (no email), password typed twice.
  - `admin` is a reserved username.
  - Normal (non-admin) accounts can also be created.
  - Non-guest account data is persisted and **isolated**: a non-admin user
    never sees another non-admin user's data (submissions, drafts, state).

## Tolerance comparison for float returns

15 problems return floats under `comparison: "exact"`, which is fragile
across compilers/hardware (FMA fusion, rounding order — already bit us on
1230 toss-strange-coins, 2548, and 0399 evaluate-division, and 0837
new-21-game's expected values even depend on Python ≥3.12's
Neumaier-compensated `sum()`, forcing a compensated-summation port in all
7 languages). Proposal: a `comparison: "close"` mode with an explicit
tolerance (e.g. `1e-9` relative), applied per scalar in nested results,
then re-generate the affected bundles' expected values. Needs a sweep of
the affected bundles and a judge/UI story for presenting near-miss values.

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

The submission API (`POST /api/run`, `POST /api/submit`,
`GET /api/problems…`) exists and is used by the web UI, but is not
documented or exposed as a public interface. Work items:

- **Expose** the API for external/scripted callers (e.g. route `/api/*`
  through the caddy edge proxy alongside the web UI; decide ports and
  whether exposure is opt-in).
- Decide **auth/rate limiting** before it is internet-facing (guest
  sessions and accounts from the multi-user design tie in here).
- Write API docs (or OpenAPI annotations surfacing in `/docs`).
- This also unblocks scripted/CI use beyond the openoj-problems workflow.

## JS/TS exact serialization of large i64 returns

A case in 3749 (expected 2^62) cannot pass in JS/TS: the wrapper serializes
via `JSON.stringify`, whose canonical string for doubles beyond 2^53 parses
back to a different integer. If more such cases appear, either add a
big-int-safe serializer to the JS/TS wrappers or re-cap those cases.
