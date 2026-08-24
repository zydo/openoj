# HANDOVER TO CODEX — problems-extend authoring, PARTITION B (resumable, 2026-08-23)

You (Codex) own ONE PARTITION of the problems-extend authoring wave,
running in PARALLEL with the original session (Partition A, Claude).
This memo is resumable: a fresh Codex session should select and claim
its next shard from the canonical Codex tracker without asking the user
to assign one. Read CLAUDE.md in both repos first; this memo covers the
partition split, startup selection, conflict protocol, and authoring
loop. Everything else (brief clauses, blocked classes, conventions,
judge facts) below applies unchanged.

## PARTITION ASSIGNMENT

The corpus is split at the shard boundary **id 2001**. Shard dirs are
disjoint, so the two sides never touch each other's files:

| Side | Shards | Entries at split | Ownership |
|---|---|---|---|
| **A (Claude)** | 0001-0100 … 1401-1500 | ~646 pending | sole owner below 1501 (working 0501-0600 upward) |
| **C (Claude-C)** | 1501-1600 … 1901-2000 | 401 pending | sole owner of 1501..2000 (see HANDOVER_TO_ANOTHER_CLAUDE.md) |
| **B (Codex, you)** | 2001-2100 … 4001-4100 | 1,737 pending | sole owner from 2001 onward |

Update 2026-08-23: a THIRD session (Claude-C, a different model) now owns
shards 1501-2000, carved from A's upper range. Nothing changed for you:
your scope, tracker, and protocol are identical. The three fleets share
one account's rate limits.

**Your scope**: author every `pending` problem in shards 2001-2100
through 4001-4100, in tracker order, shard by shard. NEVER author
inside shards below 2001 — A owns them.

The tracker is intentionally SPARSE. An id absent from `partition.json`
is out of scope, commonly because it already exists in
`problems-bettercode`. Never infer the next problem by incrementing an
id, and never author an absent id. The live example is 2024, which is
not in the partition.

## STARTUP — PICK AND CLAIM THE NEXT SHARD YOURSELF

A fresh Codex session does not need a user-selected shard. After reading
the instructions and blocked evidence:

1. Parse `.localonly/codex/partition.json` and verify its bytes equal
   `json.dumps(parsed, indent=2, ensure_ascii=False) + "\n"`.
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

Partition B's Codex bookkeeping has one writer at a time. Do not run two
independent Codex sessions against `.localonly/codex/` concurrently; a
second concurrent fleet needs a separately seeded disjoint tracker and
bookkeeping directory.

## CONFLICT PROTOCOL (the part that makes parallelism safe)

These shared files have exactly ONE writer (A). You must NOT write them:

- `problems-extend/ROSTER.json` — A's tracker.
- `CORPUS-FLAGS.md` — A's corpus-flag file.
- `.adapt/concurrency.json` — A's fleet log.

Your own bookkeeping lives in files already seeded for you (all under
`openoj-problems/.localonly/codex/`, gitignored):

- `partition.json` — your tracker: all 1,737 entries with
  id/slug/status. Mark `done` / `blocked` HERE as you go (canonical
  JSON, byte-round-trip before writing). A imports your statuses into
  ROSTER.json at merge time.
- `events.json` — your fleet log (milestones, blocked, rate-limit
  events; same shape as A's concurrency events).
- `blocked.md` — your blocked-evidence drafts, one section per problem
  in the CORPUS-FLAGS entry format. A imports them at merge.

Everything else is either read-only for you ( FORMAT.md, scripts/,
common/, landed bundles, the crawl sources in `~/code/lc-crawl/`) or
already partitioned (you only create dirs under
`problems-extend/<your shard>/`). Scratch scripts: prefix yours
`codex_` in `.localonly/` to avoid collisions with A's per-bundle
scratch. Do not commit anything; do not run formatters; the whole
`problems-extend/` tree is intentionally untracked until a user-driven
landing pass.

Two intentional UNCOMMITTED openoj changes exist in the working tree —
shared infrastructure you depend on, do not commit or revert:
`api/app/problems.py` (difficulty "" legal) and `runner/sql_harness.py`
(the `--` argv fix).

## THE LOOP (identical to A's)

1. Maintain as many concurrent authoring subagents as the session exposes,
   up to the user's cap of 6; remember the coordinator consumes one total
   agent slot. Refill immediately on every completion.
2. On completion: the verify gate must be green —
   `python3 /Users/dongziyu/code/openoj/.localonly/verify_solution.py
   problems-extend/<shard>/<id>_<slug>` — all 7 languages.
3. Mark `done` in YOUR `partition.json` (never ROSTER.json).
4. Refill with the next `pending` object in exact `partition.json` order.
   Assert membership/status before every brief; never increment the last
   numeric id to select work.
5. On subagent death by 429: resume instantly (context survives via
   your agent mechanism), log it in your events.json. The user manages
   rate limits externally; never wait for pool resets. NOTE: your fleet
   and A's fleet SHARE the same account rate limits — deaths may come
   from either side's consumption. Still resume instantly.
6. On inexpressibility: mark `blocked` in partition.json, file evidence
   in your blocked.md, refill. Check the blocked-class list below
   FIRST — many walls are already known; block obvious members without
   spending an agent.

## BRIEF TEMPLATE (one self-contained prompt per agent)

Essential clauses — copy the shape from any landed 0501-0533 bundle's
evident brief structure:

- Source: `/Users/dongziyu/code/lc-crawl/problems/<shard>/<id>-<slug>.md`;
  target `problems-extend/<shard>/<id>_<slug>/`.
- Mirror exemplar `problems-bettercode/0001-0100/0001_two-sum/` +
  FORMAT.md + ONE landed problems-extend sibling of the same wire
  family (grep for it; never read in-flight bundles from A's shards).
- ORIGINAL form: crawled prose verbatim into bundle grammar; diagrams
  dropped (Input/Output lines carry them); LeetCode cross-reference
  notes dropped; mangled superscripts restored (`105` -> `10⁵`); crawl
  Hints kept when present.
- **Tags verbatim from the crawl file's Topics row — never from
  memory** (briefs mis-transcribed tags repeatedly). Same for
  constraints: read the FULL crawl source.
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

## BLOCKED CLASSES — check before briefing anything

File evidence per class exists in A's CORPUS-FLAGS.md (entries 5, 6,
8, 9, 10, 11 — read it). Block obvious members without an agent; for
new walls, run the brief's STOP clause and file your own entry in
blocked.md:

- **Pointer-wired nodes** (parent/next/child/circular wiring, input or
  output): entry 5. Value-list fallbacks are identity no-ops (forbidden
  mechanical rewrites).
- **nary/quad/graph Node** (children/neighbors, 4-child quads, n-ary
  in or out): entry 6. No typed-stream kind; quad non-leaf val is
  arbitrary by spec.
- **Recursive NestedInteger unions** (nested lists of int-or-list, any
  depth): entry 10, both directions.
- **Random-output problems** (uniform-random returns; "return any
  random..."): entry 11. Exact-comparison judge cannot pin randomness.
- **Out-buffer / shared-structure** APIs (read4-style buffers, two
  lists sharing a tail): entries 8, 9.

Expect recurrences: scan each pending's crawl title/skeleton for these
shapes before writing its brief.

## CONVENTIONS (enforced via briefs; agents follow them)

- Starters: `python3 scripts/gen_starters.py <bundle-dir>` from the
  bank repo root — never hand-write (it auto-selects legacy Python
  typing for problems-extend paths).
- solutions.md: bettercode MINIMAL shape — exactly one `##` section,
  2–3 paragraphs, one `**Complexity:**` line, honest costs.
- SQL problems (type "sql"): solution.sql NO trailing semicolon (the
  executor wraps queries in `SELECT * FROM (...)`); `.sql` files end
  without a trailing newline; the dataset string carries ALL INSERTs
  for both tables; comparison "multiset"; no-semicolon rule also
  applies to starter TODO stubs only where landed siblings show it.
  Template bundles: 0175-0197, 0511, 0512.
- Design kind: void methods omit `return_type`; no-param methods carry
  `"parameters": []`. Interactive kind: mirror 0278/0374
  (provided/oracle, construct/auxiliary, query_limit). Design+tree
  combos ARE supported (0449 is the precedent).
- Iterative algorithms for anything with 10^4 depth (trees/chains):
  the judge runs Java `-Xss512k`, Node `--stack-size=512`, CPython
  default 1000 frames. 0333 is the precedent.
- 64-bit accumulation in fixed-width languages whenever intermediates
  can exceed i32 (documented headroom convention).
- Keyword renames: Rust/JS `move`/`delete` collisions get renamed
  (`make_move` 0348, `toDelete` 0420) via `entrypoints`.
- JS/TS: numeric sort comparators (default sort is lexicographic);
  BigInt for values near 10^18; Java `split(..., -1)` keeps trailing
  empties (0468 trap).

## KNOWN JUDGE FACTS

- output_kb is enforced TWICE (protocol file size and python_harness
  `_json_safe` compact-JSON length). A 10^5-element int array is
  ~289-300 KB compact; string arrays scale with content. Measure.
- The tree codec trims trailing nulls; assert serialize(parse(x)) == x
  when generating tree cases.
- The n-ary legacy codec is python-only and Java-rejected — never use.
- check.py's static tier sweeps the ADAPT tree by default and
  false-positives on locally-unformatted starter.cpp (clang-format is
  image-only). The verify gate is the authoring bar; check.py runs
  in-image at landing.

## CURRENT CHECKPOINT (Codex side, 2026-08-23 08:38 UTC)

- Partition B totals: **34 done, 1,703 pending, 0 blocked**.
- Shard 2001-2100: **34 done, 58 pending, 0 blocked** out of its 92
  rostered entries. It is the partially completed shard, so a fresh
  session MUST resume it under the startup rule above.
- The next pending tracker object is
  `2039_the-time-when-the-network-becomes-idle`.
- All 34 done objects have exactly one matching live directory under
  `problems-extend/2001-2100/`; no live non-roster directories and no
  target `__pycache__` directories existed at the checkpoint. Every
  done bundle passed an independent coordinator-run verify gate after
  its authoring agent reported green.
- No authoring agents remain active at this checkpoint.
- `partition.json` and `events.json` are canonical. `blocked.md` still
  has no Codex entries.
- One selection mistake was corrected: 2024 was chosen by numeric
  succession even though it is absent from the sparse tracker and
  already exists in `problems-bettercode`. Its duplicate was removed
  from the live extend tree and preserved recoverably at
  `.localonly/codex/quarantine_2024_maximize-the-confusion-of-an-exam`.
  Do not treat that quarantine as authored work; the event log records
  the correction.
- Original shard sizes at the split were: 2001-2100: 92, 2101-2200: 81,
  2201-2300: 76, 2301-2400: 73, 2401-2500: 63, 2501-2600: 83,
  2601-2700: 90, 2701-2800: 91, 2801-2900: 86, 2901-3000: 92,
  3001-3100: 84, 3101-3200: 84, 3201-3300: 89, 3301-3400: 89,
  3401-3500: 74, 3501-3600: 87, 3601-3700: 96, 3701-3800: 95,
  3801-3900: 97, 3901-4000: 98, 4001-4100: 17.
- MERGE (later, user-driven): A imports partition.json statuses into
  ROSTER.json, blocked.md into CORPUS-FLAGS.md, and events.json into
  the concurrency log; then one in-image format + hash-check pass over
  the whole extend tree before any commit.
