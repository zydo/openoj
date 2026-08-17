# TODO — discussed, not started

Items here are design decisions we have agreed to discuss or build later.
Nothing on this page is in progress; when work starts, move it to the task
list and delete it here.

## Import the remaining Prime problems (17 of the original 55)

BETTERCODE's 838 good problems = 790 Prime + 48 alternates. The original
import took 735 Prime; 38 of the 55 skipped landed in batch 1 (821
problems total now). Remaining 17:

**Random-output (7) — need the deterministic-modeling precedent of 381:**
382 linked-list-random-node, 384 shuffle-an-array, 398 random-pick-index,
497 random-point-in-non-overlapping-rectangles, 528 random-pick-with-weight,
710 random-pick-with-blacklist (1157 online-majority-element-in-subarray too).
(380 insert-delete-getrandom-o1 landed with the design batch.)

**Interactive / hidden-API (7) — each needs a new oracle:**
489 robot-room-cleaner (Robot oracle), 843 guess-the-word (Master oracle),
1095 find-in-mountain-array (MountainArray oracle),
1428 leftmost-column-with-at-least-a-one (BinaryMatrix oracle),
702 search-in-a-sorted-array-of-unknown-size (ArrayReader oracle),
3023 find-pattern-in-infinite-stream-i (stream oracle).
(1778 shortest-path-in-a-hidden-grid landed on the GridMaster oracle.)

**Concurrency (2) — need multi-threading semantics in the judge:**
1117 building-h2o, 1188 design-bounded-blocking-queue.

## User accounts (multi-user phase 2)

Account creation (fresh-start admin bootstrap, regular sign-up, login,
logout) and user-scoped drafts/submissions are DONE and live. Remaining:

- **Better password and user identity management** (subject to design
  discussion) — the current scrypt-with-salt scheme and fixed-name admin
  bootstrap are a baseline, not the destination.
- Admin management surface (listing/deleting accounts, resetting
  passwords) once the accounts UI grows beyond the gate.
