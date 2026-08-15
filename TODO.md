# TODO — discussed, not started

Items here are design decisions we have agreed to discuss or build later.
Nothing on this page is in progress; when work starts, move it to the task
list and delete it here.

## Import the 48 BETTERCODE 替代题 alternatives

DONE — all 48 imported into openoj-problems: 43 plain function problems
(full 7-language pipeline), 4 design/class problems (python3+java via the
design invocation), and 1810 minimum-path-cost-in-a-hidden-grid (python3+
java via the new interactive framework). Every bundle: reference-computed
expected values, ≥12 hidden cases, all solutions verified per case in every
language, formatter-clean. End state: 735 + 48 = **783 problems**.

## Multi-user support (guest sessions → accounts)

Guest sessions DONE (phase 1):

- First visit lands on a **"Continue as guest"** page — the only entrance
  until accounts exist.
- A guest is an HttpOnly cookie session with an **idle expiry of 1 hour**;
  expired sessions and everything they own (drafts, submissions) are purged.
- Editor drafts are server-side and session-scoped: they persist per problem
  and survive refreshes; a mid-use expiry returns the visitor to the gate
  with a notice. Submission history is strictly per-session too — rows
  recorded before sessions existed (NULL session) are invisible to guests.

Later, openwebui-style **user accounts**, persisted in the container's
storage:
  - **Fresh-start flow**: on first startup with no previous account data,
    show an admin sign-up page asking to set the admin password (the admin
    username is fixed: `admin`) to create the admin account. The admin
    account has the highest privilege.
  - After that, conventional username + password (no email), password
    typed twice.
  - `admin` is a reserved username.
  - Normal (non-admin) accounts can also be created.
  - Non-guest account data is persisted and **isolated**: a non-admin user
    never sees another non-admin user's data (submissions, drafts, state).
  - Account state attaches to the **user, not the login session**: drafts,
    last language selection per problem, and submission history are stored
    under the user id — signing in again from any device or session
    restores all of it. Ephemeral session scoping stays guest-only.

## Tolerance comparison for float returns

DONE — the judge supports `comparison: "close"` (string, default 1e-9
relative+absolute per scalar, recursive through nested lists/objects; or
`{"mode": "close", "tolerance": …}` for a custom tolerance). The 15
float-returning bundles are switched to close mode; expected values were
already the Python-reference values, and all 15 verify green across every
language. The frontend shows `Expected <value> ±1e-9` for close problems.

## Interactive problem framework

DONE — invocation type `"interactive"`: the judge builds an oracle object
from the case's hidden state and hands it to the solution (python3 + java
only). First oracle: `GridMaster` (canMove/move/isTarget with a query
budget, default 1M per case), used by 1810 Minimum Path Cost in a Hidden
Grid — the 48th BETTERCODE 替代题, now imported. New oracles are added as
harness classes (runner/python_harness.py + runner/java/<Oracle>.java).

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
