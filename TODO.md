# TODO — discussed, not started

Items here are design decisions we have agreed to discuss or build later.
Nothing on this page is in progress; when work starts, move it to the task
list and delete it here.

## Import the remaining Prime problems (8 of the original 55; 828 live)

BETTERCODE's 838 good problems = 790 Prime + 48 alternates. The original
import took 735 Prime; 38 landed in batch 1 and the 7 random-output
problems landed with statistical judging (828 total now). Remaining 8:

**Interactive / hidden-API (6) — each needs a new oracle:**
489 robot-room-cleaner (Robot oracle), 843 guess-the-word (Master oracle),
1095 find-in-mountain-array (MountainArray oracle),
1428 leftmost-column-with-at-least-a-one (BinaryMatrix oracle),
702 search-in-a-sorted-array-of-unknown-size (ArrayReader oracle),
3023 find-pattern-in-infinite-stream-i (stream oracle).

**Concurrency (2) — need multi-threading semantics in the judge:**
1117 building-h2o, 1188 design-bounded-blocking-queue.

## Multi-solution bundles

The `solution_dfs`/`solution_bfs` convention is fully wired (judge,
check.py, Solutions tab, fastest-variant baseline) with 0200 as the
exemplar. Remaining: identify the problems with genuinely distinct
equal-performance approaches (two-pointer vs hash, DP vs greedy,
Union-Find vs BFS/DFS, patience vs DP for LIS, ...) and author the
variant sets across all seven languages.

## User accounts (multi-user phase 2)

Account creation (fresh-start admin bootstrap, regular sign-up, login,
logout) and user-scoped drafts/submissions are DONE and live. Remaining:

- **Better password and user identity management** (subject to design
  discussion) — the current scrypt-with-salt scheme and fixed-name admin
  bootstrap are a baseline, not the destination.
- Admin management surface (listing/deleting accounts, resetting
  passwords) once the accounts UI grows beyond the gate.
