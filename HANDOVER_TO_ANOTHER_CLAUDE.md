# HANDOVER TO CLAUDE-C — problems-extend authoring, PARTITION C (resumable, 2026-08-23)

You (Claude-C) own ONE PARTITION of the problems-extend authoring wave,
running in PARALLEL with two other sessions: Partition A (the original
Claude coordinator) and Partition B (Codex). This memo is resumable: a
fresh Claude-C session should select and claim its next shard from its
canonical tracker without asking the user. Read CLAUDE.md in both repos
first; this memo covers the partition split, startup selection, conflict
protocol, and the authoring loop.

## PARTITION ASSIGNMENT

The corpus is split at TWO shard boundaries. Shard dirs are disjoint, so
the three sides never touch each other's files:

| Side | Shards | Entries at split | Ownership |
|---|---|---|---|
| **A (Claude, original)** | 0001-0100 … 1401-1500 | ~646 pending | sole owner below 1501 (working 0501-0600 upward) |
| **C (Claude-C, you)** | 1501-1600 … 1901-2000 | 401 pending | sole owner of 1501..2000 |
| **B (Codex)** | 2001-2100 … 4001-4100 | 1,737 pending | sole owner from 2001 onward |

**Your scope**: author every `pending` problem in shards 1501-1600
through 1901-2000, in tracker order, shard by shard. NEVER author inside
shards below 1501 (A owns them and is active there) or from 2001 up
(Codex owns them).

The tracker is intentionally SPARSE. An id absent from your
`partition.json` is out of scope. Never infer the next problem by
incrementing an id, and never author an absent id.

## STARTUP — PICK AND CLAIM THE NEXT SHARD YOURSELF

A fresh Claude-C session does not need a user-selected shard:

1. Parse `openoj-problems/.localonly/claude-c/partition.json` and verify
   its bytes equal `json.dumps(parsed, indent=2, ensure_ascii=False) + "\n"`.
2. If a shard has both completed (`done` or `blocked`) and `pending`
   entries, resume the LOWEST such partially completed shard. Otherwise,
   select the LOWEST shard containing any `pending` entry.
3. Within that shard, select work ONLY from its `pending` objects in the
   exact JSON order. Before briefing an agent, assert the `(id, slug)`
   object exists and is still `pending`; do not use numeric succession.
4. Append a canonical milestone event to `events.json` naming the shard,
   current counts, and session capacity. This is the claim; statuses stay
   `pending` until their verify gates pass.
5. If the target directory already exists for a pending object, treat it
   as interrupted work: inspect and verify it before deciding whether to
   resume authoring. Do not overwrite it blindly.
6. Start the fleet immediately. Do not ask the user which shard to pick.

Partition C's bookkeeping has one writer at a time. Do not run two
independent Claude-C sessions against `.localonly/claude-c/`
concurrently; a second concurrent fleet needs a separately seeded
disjoint tracker and bookkeeping directory.

## CONFLICT PROTOCOL (what makes three-way parallelism safe)

These shared files have exactly ONE writer (A). You must NOT write them:

- `problems-extend/ROSTER.json` — A's tracker.
- `CORPUS-FLAGS.md` — A's corpus-flag file.
- `.adapt/concurrency.json` — A's fleet log.
- `.localonly/codex/` — Codex's bookkeeping (read-only for you).
- `.localonly/claude-c/` is YOURS alone.

Your own bookkeeping (already seeded for you, gitignored):

- `partition.json` — your tracker: all 401 entries with id/slug/status.
  Mark `done` / `blocked` HERE as you go (canonical JSON, byte-round-trip
  before writing). A imports your statuses into ROSTER.json at merge.
- `events.json` — your fleet log (milestones, blocked, rate-limit events).
- `blocked.md` — your blocked-evidence drafts, one section per problem in
  the CORPUS-FLAGS entry format. A imports them at merge.

Everything else is read-only for you (FORMAT.md, scripts/, common/,
landed bundles, the crawl sources in `~/code/lc-crawl/`) or already
partitioned (you only create dirs under `problems-extend/<your shard>/`).
Scratch scripts: prefix yours `claude-c_` in `.localonly/` to avoid
collisions. Do not commit anything; do not run formatters; the whole
`problems-extend/` tree is intentionally untracked until a user-driven
landing pass.

Two intentional UNCOMMITTED openoj changes exist in the working tree —
shared infrastructure you depend on, do not commit or revert:
`api/app/problems.py` (difficulty "" legal) and `runner/sql_harness.py`
(the `--` argv fix).

## THE LOOP

1. Maintain as many concurrent authoring subagents as the session
   exposes, up to the user's cap of 6; remember the coordinator consumes
   one total agent slot. Refill immediately on every completion.
2. On completion: the verify gate must be green —
   `python3 /Users/dongziyu/code/openoj/.localonly/verify_solution.py
   problems-extend/<shard>/<id>_<slug>` — all 7 languages.
3. Mark `done` in YOUR `partition.json` (never ROSTER.json).
4. Refill with the next `pending` object in exact tracker order. Assert
   membership/status before every brief.
5. On subagent death by 429: resume instantly (context survives via
   SendMessage if your harness provides it), log it in your events.json.
   The user manages rate limits externally; never wait for pool resets.
   NOTE: three fleets now SHARE one account's rate limits — deaths may
   come from either other side's consumption. Still resume instantly.
6. On inexpressibility: mark `blocked` in partition.json, file evidence
   in your blocked.md, refill. Check the blocked-class list below FIRST
   — many walls are already known; block obvious members without
   spending an agent.

## BRIEF TEMPLATE (one self-contained prompt per agent)

- Source: `/Users/dongziyu/code/lc-crawl/problems/<shard>/<id>-<slug>.md`;
  target `problems-extend/<shard>/<id>_<slug>/`.
- Mirror exemplar `problems-bettercode/0001-0100/0001_two-sum/` +
  FORMAT.md + ONE LANDED problems-extend sibling of the same wire family.
  Good landed exemplars by family: 0501 (tree), 0564 (big-int string
  math), 0572 (two tree params, iterative proof), 0578/0580/0584/0586
  (SQL), 0532/0442 (hash counting), 0546 (hard DP + brute oracle),
  0535/0449 (design/free-format pins), 0374/0278 (interactive), 0553
  (string construction). Never read in-flight bundles (A is active in
  0501-0600; anything not yet `done` in ROSTER terms may be in flight).
- ORIGINAL form: crawled prose verbatim into bundle grammar; diagrams
  dropped (Input/Output lines carry them); LeetCode cross-reference
  notes dropped; mangled superscripts restored (`105` -> `10⁵`); crawl
  Hints kept when present.
- **Tags verbatim from the crawl file's Topics row — never from memory**
  (briefs mis-transcribed tags repeatedly). Same for constraints: read
  the FULL crawl source.
- problem.json: schema_version 1, common_version 1, reference_solution
  "", difficulty "" (UNSET — always, for every problems-extend bundle).
- Canonical algorithm sketched in the brief; hidden cases >= 12 with
  named coverage; independent ORACLE cross-check for every expected;
  measured output_kb when outputs are large (tiers 64/256/512/1024/
  2048 — the judge enforces the cap on compact JSON).
- Determinism PIN (bridge sentence in the statement) for any-order /
  any-of outputs; restate example outputs under the pin when needed.
- Verify gate until green. NO ROSTER.json writes (mark partition.json
  yourself after the gate), no formatters, no git, no sub-agents,
  nothing outside the target dir + your `.localonly` scratch; clean
  __pycache__.
- Starters: `python3 scripts/gen_starters.py <bundle-dir>` from the bank
  repo root — never hand-write.

## BLOCKED CLASSES — check before briefing anything

Evidence per class in A's CORPUS-FLAGS.md (entries 5, 6, 8, 9, 10, 11 —
read it). Block obvious members without an agent; for new walls, run the
brief's STOP clause and file your own entry in blocked.md:

- **Pointer-wired nodes** (parent/next/child/circular wiring, input or
  output): entry 5 (0116/0117/0138/0426/0430/0510). Value-list fallbacks
  are identity no-ops (forbidden mechanical rewrites).
- **nary/quad/graph Node** (children/neighbors, 4-child quads, n-ary in
  or out): entry 6 (0133/0427..0431/0558/0559/0589/0590). No typed-stream
  kind; quad non-leaf val arbitrary by spec.
- **Out-buffer / shared-structure APIs** (read4-style buffers, two lists
  sharing a tail): entries 8, 9 (0157/0158/0160).
- **Recursive NestedInteger unions** (nested lists of int-or-list, any
  depth): entry 10 (0339/0364/0385), both directions.
- **Random-output problems** (uniform-random returns): entry 11
  (0478/0519). Exact-comparison judge cannot pin randomness.

Expect recurrences: scan each pending's crawl title/skeleton for these
shapes before writing its brief.

## CONVENTIONS (enforce via briefs)

- solutions.md: bettercode MINIMAL shape — exactly one `##` section,
  2-3 paragraphs, one `**Complexity:**` line, honest costs.
- SQL problems (type "sql"): solution.sql NO trailing semicolon (the
  executor wraps queries in `SELECT * FROM (...)`); `.sql` files end
  without a trailing newline; the dataset string carries ALL INSERTs for
  all tables; comparison "multiset"; sqlite ROUND is half-away-from-zero
  on exact binary doubles and returns a float on the wire (0550's
  measured note). Exemplars: 0175-0197, 0511/0512, 0569-0586.
- Design kind: void methods omit `return_type`; no-param methods carry
  `"parameters": []`. Interactive kind: mirror 0278/0374. Design+tree
  combos ARE supported (0449).
- Iterative algorithms for anything with depth beyond ~1000 (trees/
  chains): the judge runs Java `-Xss512k`, Node `--stack-size=512`,
  CPython default 1000 frames — even at bound 2000 (0572's proof).
- 64-bit accumulation in fixed-width languages whenever intermediates
  can exceed i32, even when the final answer provably fits (documented
  headroom convention; 0563 is the counterexample story).
- Keyword renames: Rust/JS `move`/`delete` collisions renamed via
  `entrypoints` (`make_move` 0348, `toDelete` 0420).
- JS/TS: numeric sort comparators; BigInt (0483) or string arithmetic
  (0564) for values near 10^18; Java `split(..., -1)` keeps trailing
  empties (0468).
- Iterative everywhere at depth; the tree codec trims trailing nulls
  (assert serialize(parse(x)) == x when generating tree cases).

## KNOWN JUDGE FACTS

- output_kb is enforced TWICE (protocol file size and python_harness
  `_json_safe` compact-JSON length). A 10^5-element int array is
  ~289-300 KB compact; measure, don't guess.
- The n-ary legacy codec is python-only and Java-rejected — never use.
- check.py sweeps the ADAPT tree by default and false-positives on
  locally-unformatted starter.cpp (clang-format is image-only). The
  verify gate is the authoring bar.
- Two string-array and two-matrix params both work end-to-end (0539,
  0311/0568); design+string (0449/0535) and interactive (0274/0374) are
  proven.

## STATE AT HANDOVER (your side)

- Nothing in shards 1501-2000 is authored; your partition.json has all
  401 entries `pending`.
- Shard sizes (pending): 1501-1600: 94, 1601-1700: 83, 1701-1800: 79,
  1801-1900: 81, 1901-2000: 64.
- A is concurrently landing ~7 problems/hour from 0501 upward; Codex
  runs from 2001 up. You should sustain a similar rate on yours.
- MERGE (later, user-driven): A imports partition.json statuses into
  ROSTER.json, blocked.md into CORPUS-FLAGS.md, and events.json into the
  concurrency log; then one in-image format + hash-check pass over the
  whole extend tree before any commit.
