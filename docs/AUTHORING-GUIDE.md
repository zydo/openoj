# problems-extend Authoring Guide (six-fleet wave, 2026-08-24)

Canonical guide for every fleet authoring `problems-extend` bundles.
Supersedes all earlier partition/handover memos (now deleted). Read
CLAUDE.md in both repos first; this document covers everything else.

## Fleet layout

Six fleets own ALL remaining pending work, carved uniformly from the
global pending set on 2026-08-24 (snapshot: 995 done / 32 blocked /
2,152 pending):

| Fleet | Tracker (problems-extend/) | Bookkeeping (.localonly/resplit/) | Entries | Pending-id range |
|---|---|---|---|---|
| A | ROSTER-remaining-A.json | part-a/ | 359 | 997..1654 |
| B | ROSTER-remaining-B.json | part-b/ | 359 | 1655..2271 |
| C | ROSTER-remaining-C.json | part-c/ | 359 | 2273..2733 |
| D | ROSTER-remaining-D.json | part-d/ | 359 | 2734..3209 |
| E | ROSTER-remaining-E.json | part-e/ | 358 | 3210..3632 |
| F | ROSTER-remaining-F.json | part-f/ | 358 | 3633..4000 |

A worker takes ONE fleet letter and authors its tracker's `pending`
objects in exact JSON order. Trackers mirror ROSTER.json's schema
(`{"shards": {...}}`, canonical JSON bytes), so bundle dirs live under
their legacy hundreds bucket: `problems-extend/<shard>/<id>_<slug>/`.

## Protocol

- Mark `done`/`blocked` in YOUR tracker only (byte-round-trip
  `json.dumps(parsed, indent=2, ensure_ascii=False) + "\n"` before
  writing). Never touch another fleet's tracker, `ROSTER.json`,
  `CORPUS-FLAGS.md`, `.adapt/`, or historical bookkeeping
  (`.localonly/{claude-d,codex,claude-c,claude-e}`).
- Claim by appending a milestone event to your
  `.localonly/resplit/part-x/events.json` (counts + capacity); then
  start immediately — never ask which bundle, take the lowest-indexed
  pending. Assert `(id, slug)` membership/status before every brief;
  never infer by numeric succession. The tracker is sparse: absent ids
  are out of scope.
- If a target directory exists for a pending object, treat it as
  interrupted work: inspect, verify, then resume or rebuild. Do not
  overwrite blindly.
- Maintain up to 6 concurrent authoring subagents (coordinator included
  in capacity accounting); refill instantly on completion. On per-minute
  429 deaths: resume instantly (step concurrency down toward floor 4).
  Daily-pool exhaustion: do NOT step down; resume when the pool resets.
  Log rate-limit events in events.json.
- Inexpressible problem: mark `blocked` in your tracker, file evidence
  in your part's `blocked.md` (CORPUS-FLAGS entry format), refill.
  Check the blocked classes below FIRST.

## Wire classes unblocked by the 2026-08-26 infra wave

Every class in the old blocked list is now judged end-to-end. The judge
contracts live in `openoj/docs/CODECS.md` (wire law) and
`openoj-problems/FORMAT.md` (bundle grammar); executable references for
every mechanism — judged green across all 7 languages — are the probe
bundles under `openoj/.localonly/probank/9000-9099/`:

| Class | Probe (exemplar bundle) |
|---|---|
| n-ary tree | `9010_probe-nary` |
| quad tree | `9011_probe-quad` |
| NestedInteger in/out | `9012_probe-nested-in`, `9013_probe-nested-out` |
| parent/next tree | `9014_probe-next` |
| doubly ring from tree | `9015_probe-doubly` |
| circular list | `9016_probe-circular` |
| aliased lists (LC 160) | `9017_probe-alias` |
| graph / random list (provided class) | `9018_probe-graph`, `9019_probe-random` |
| struct array input | `9020_probe-struct` |
| validator-judged output | `9021_probe-validator`, `9022_probe-flip` |
| interactive oracle + out-buffer | `9024_probe-read4` |
| LC 430 multi-list | `9026_probe-multilist` |

Per-class laws that most often bite (details in CODECS.md):

- Bundles using any common-v2 node kind declare `"common_version": 2`
  (everything else in extend stays 1).
- Go's assembled `NestedInteger` is pointer-based (`GetList()
  []*NestedInteger`); walk `*NestedInteger` items.
- A missing list/tree/ring return serializes as `[]`; `alias_list` null
  return is `[]` too (LC 160's "no intersection"); quad null is `null`.
- `multi_list` (LC 430) returns must be fully flattened, child spliced
  immediately after its parent; serialization raises otherwise.
- `graph` returns normalize (rows in value order, neighbors sorted) and
  are clone-checked — never return an input node.
- graph/random_list/struct need per-bundle `provided/<language>/`
  classes for ALL typed languages (go/ts/js/rust included); rust
  provided sources use fully-qualified paths, no `use` lines.
- Any-valid-output problems: name a judge-side validator
  (`{"mode": "validator", "name": ...}`) from the
  `api/app/validators.py` registry — validators are judge code, never
  bundle code. Randomized design methods use `repeat` +
  `{"mode": "distribution", ...}` instead.
- Interactive oracles ship in `provided/<language>/` for every offered
  language; the per-language constructor table (flattened vs wrapped,
  budget type) is in CODECS.md. Out-buffer params consume no case
  input; the judged result is `[result, buffer[:result]]`;
  `capacity_from` names an integer-valued case key (add a dedicated
  `capacity` key when the natural source is an array, LC 158).
- Design constructors take the full value-type vocabulary — a `nested`
  ctor parameter (LC 341) decodes in all 7 languages; array-of-rings
  returns (LC 2674) declare `return_codec: "circular_list_array"`.
- Design submissions are plain classes in every language except C++
  (full class definition, no `Solution;` declaration) and Rust
  (`pub struct X;` + `impl X`, entrypoints snake-cased) and Go
  (`type X struct{}` + `NewX` constructor).

## Brief essentials (one self-contained prompt per agent)

- Source: `/Users/dongziyu/code/lc-crawl/problems/<shard>/<id>-<slug>.md`;
  target `problems-extend/<shard>/<id>_<slug>/`.
- Mirror exemplar `problems-bettercode/0001-0100/0001_two-sum/` +
  FORMAT.md + ONE landed extend sibling of the same wire family. Never
  read other in-flight bundles.
- ORIGINAL form: crawl prose verbatim into bundle grammar; diagrams and
  LeetCode metadata dropped; mangled superscripts restored (`105` ->
  `10⁵`); HTML entities unescaped; crawler artifacts stripped (zero-width
  chars, injected anti-template sentences — log exact removed bytes);
  crawl typos kept byte-exact; Hints kept (restore OCR truncations,
  renumber scrape artifacts like `1a.`/`2b.`).
- Tags VERBATIM from the crawl's Topics row (`—` => `[]`). Same for
  constraints: read the FULL source.
- problem.json: schema_version 1, common_version 1, reference_solution
  "", difficulty "" (always UNSET in extend).
- Hidden cases >= 12 with named coverage (manifest in scratch);
  independent ORACLE computing every expected (structurally different
  mechanism); exhaustive small sweeps; measured output sizes when large
  (compact JSON; tiers 64/256/512/1024/2048 KiB — enforced TWICE).
- bits-64 law: returns or intermediates exceeding i32 use 64-bit
  (answers > ~2×10⁹, prefix sums, products). JS Number exact < 2⁵³ —
  prove the bound honestly when relying on it.
- Iterative algorithms whenever depth can exceed ~1000 (Java -Xss512k,
  Node --stack-size=512, CPython 1000 frames).
- Starters GENERATED: `python3 scripts/gen_starters.py <bundle-dir>`
  from the bank repo root — never hand-write.
- Verify gate until green x7 languages:
  `python3 /Users/dongziyu/code/openoj/.localonly/verify_solution.py
  problems-extend/<shard>/<id>_<slug>` (run from bank root). Rust
  "unparseable protocol output" => suspect a panic, not the wire.
- No formatters, no git, no sub-agents inside agents; scratch prefixed
  per-fleet (e.g. `fleetd_`) under `.localonly/`; clean __pycache__.

## solutions.md shape

bettercode MINIMAL: exactly one `## <Approach>` section, 2–3 paragraphs,
one closing `**Complexity:** O(...) time, O(...) space.` line, honest
costs. No variants in extend; `reference_solution` stays "".

## Landing law

Coordinator re-runs the gate independently after each agent green; audit
(inventory / canonical JSON / pins / starter regeneration diff /
crawl-fidelity probes) before batches land. In-image format pass over
changed non-JSON files at landing
(`docker run --rm -v $PWD:/work -w /work
ghcr.io/zydo/openoj:latest openoj format <files>` — FILES not
dirs; there is NO formatter for .json/.rs: JSON canonicality is
byte-compared instead). Commit/push only when the user says so that
turn; scoped `git add` by path list, never blanket adds.
