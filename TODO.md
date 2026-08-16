# TODO — discussed, not started

Items here are design decisions we have agreed to discuss or build later.
Nothing on this page is in progress; when work starts, move it to the task
list and delete it here.

## Import the 55 remaining Prime problems

BETTERCODE's 838 good problems = 790 Prime + 48 alternates. The original
import took only 735 Prime; the 55 skipped below are all design-class,
random, or interactive problems the judge could not handle at the time.
Current state: 783 in openoj-problems (735 Prime + all 48 alternates);
importing these 55 reaches the full 838. Most are now unblocked by this
session's design invocation (py3+java) and the interactive GridMaster
framework; the ones needing new oracles or concurrency support are marked.

**Plain design (37) — ready via the design invocation (py3+java):**
146 lru-cache, 155 min-stack, 173 binary-search-tree-iterator,
208 implement-trie-prefix-tree, 211 design-add-and-search-words-data-structure,
297 serialize-and-deserialize-binary-tree, 303 range-sum-query-immutable,
304 range-sum-query-2d-immutable, 355 design-twitter,
380 insert-delete-getrandom-o1 (see random note), 432 all-oone-data-structure,
460 lfu-cache, 588 design-in-memory-file-system,
642 design-search-autocomplete-system, 703 kth-largest-element-in-a-stream,
715 range-module, 729 my-calendar-i, 759 employee-free-time,
855 exam-room, 895 maximum-frequency-stack, 901 online-stock-span,
981 time-based-key-value-store, 1032 stream-of-characters,
1146 snapshot-array, 1352 product-of-the-last-k-numbers,
1381 design-a-stack-with-increment-operation, 1396 design-underground-system,
1845 seat-reservation-manager, 1912 design-movie-rental-system,
2034 stock-price-fluctuation, 2276 count-integers-in-intervals,
2286 booking-concert-tickets-in-groups, 2353 design-a-food-rating-system,
2642 design-graph-with-shortest-path-calculator, 3408 design-task-manager,
3508 implement-router, 528 random-pick-with-weight (random note).

**Random-output (6) — need the deterministic-modeling precedent of 381:**
380 insert-delete-getrandom-o1, 382 linked-list-random-node,
384 shuffle-an-array, 398 random-pick-index,
497 random-point-in-non-overlapping-rectangles, 528 random-pick-with-weight,
710 random-pick-with-blacklist (1157 online-majority-element-in-subarray too).

**Interactive / hidden-API (8) — 1778 is ready (GridMaster exists); the rest
need new oracles:**
1778 shortest-path-in-a-hidden-grid (READY — GridMaster framework in place),
489 robot-room-cleaner (Robot oracle), 843 guess-the-word (Master oracle),
1095 find-in-mountain-array (MountainArray oracle),
1428 leftmost-column-with-at-least-a-one (BinaryMatrix oracle),
702 search-in-a-sorted-array-of-unknown-size (ArrayReader oracle),
3023 find-pattern-in-infinite-stream-i (stream oracle).

**Concurrency (2) — need multi-threading semantics in the judge:**
1117 building-h2o, 1188 design-bounded-blocking-queue.

## User accounts (multi-user phase 2)

Guest sessions (phase 1) are done; the backend user layer exists but is
hidden from the UI. Remaining:

- The UI itself: a **fresh-start flow** — on first startup with no previous
  account data, show an admin sign-up page asking to set the admin password
  (the admin username is fixed: `admin`) to create the admin account with
  the highest privilege. After that, conventional username + password (no
  email), password typed twice. `admin` is a reserved username; normal
  (non-admin) accounts can also be created. A login button stays visible in
  guest mode for login or sign-up.
- Account data is persisted and **isolated**: a non-admin user never sees
  another non-admin user's data (submissions, drafts, state).
- Account state attaches to the **user, not the login session**: drafts,
  last language selection per problem, and submission history are stored
  under the user id — signing in again from any device or session restores
  all of it. Ephemeral session scoping stays guest-only. (Backend scope
  keys already implement this; surface it.)
- **Better password and user identity management** (subject to design
  discussion) — the current scrypt-with-salt scheme and fixed-name admin
  bootstrap are a baseline, not the destination.
