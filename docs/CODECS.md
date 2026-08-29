# OpenOJ data conventions

How problem data crosses the language boundary: the JSON wire format every
`cases.json` uses, the binary stream the typed executors read, the wrapper
types injected into submissions, and the special invocation protocols.
Source of truth: `runner/leetcode_types.py` (JSON codecs),
`runner/executors/typed.py` (binary encoder), and the per-language wrapper
templates in `runner/executors/`.

## JSON wire format (cases.json, API payloads)

Function-problem inputs are positional argument arrays in `invocation`
parameter order — `[[2,7,11,15], 9]` for `twoSum(nums, target)`.

Structured values ride as plain JSON:

| `value_type.kind` | JSON shape |
| --- | --- |
| `integer` (+`bits` 32/64) | number |
| `number` | float |
| `boolean`, `string` | as-is |
| `array` (+`items`) | JSON array |
| `linked_list` | array of node values (`[1,2,4]`); `[]` is the empty list |
| `binary_tree` | trimmed level-order array with `null` holes — `[3,9,20,null,null,15,7]`; trailing nulls are stripped, `[]` is the empty tree |
| `nary_tree` | LeetCode display array: children groups separated by `null`, one trailing `null` per node (`[1,null,3,2,4,null,5,6]`) |
| `next_tree` | binary-tree display array (`[1,2,3,4,5,6,7]`) — same trimmed level order as `binary_tree` |
| `quad_tree` | flat preorder of `[isLeaf,val]` pairs; a non-leaf's `val` normalizes to 0; `null` is the empty tree |
| `nested` | nested arrays of integers (`[1,[4,[6]]]`); a bare integer is an integer hold |
| `circular_list` | the ring's values read from the head (`[3,4,1]`); `[]` is the empty ring |
| `doubly_circular` | the ring's values read from the head; `[]` is the empty ring |
| `alias_list` | `{"values": [...], "splice_at": n}` — the decode splices the prefix chain onto node `n` of the aliased `linked_list` parameter |
| `multi_list` | `{"values": [...], "children": [...]}` — children align slot for slot, each entry `null` or a nested chain object |
| `graph` | adjacency rows by node index, 0-based (`[[2,4],[1,3]]`); row i lists node i's neighbors |
| `random_list` | rows `[val, randomIndex]`, null random as `null` (`[[7,null],[13,0]]`); index counts from the head |
| `struct` (+`class`, `fields`) | positional array in field order (`[1, 5, [2, 3]]`) |

Binary trees follow the LeetCode convention: children of missing nodes are
omitted, so `null` appears only between real nodes, never after the last one.
N-ary trees (python codec `nary_tree`) serialize children groups separated by
`null`, ending with a trailing `null` per LeetCode.

Return values use the same shapes: a solution returning `ListNode*` is
compared against the expected value array, a `TreeNode*` against the expected
level-order array. A `next_tree` return is the flat LC display read through
the solution-populated `next` chain — values with one `null` marker between
adjacent levels, trailing markers trimmed (`[1,null,2,3,null,4,5,6,7]`); the
level walk advances to the first child found anywhere in the level, so
non-perfect trees (LC 117) serialize correctly. Decode wires `parent` on
construction in every language (the LC 510 wire) — solutions may rely on
it; the probes never touch `parent`, so a decode-side gap passes the probe
suite silently.

## Typed binary stream (C++ / Go / Rust / JS / TS)

Managed-language submissions would pay JSON parsing per case, so the typed
executors encode each case into a compact big-endian stream that a generated
reader (`OpenOJReader`) decodes before calling the submission:

- `integer` 32 → `int32`; `integer` 64 → `int64`; `number` → IEEE `float64`
- `boolean` → one byte `0`/`1`
- `string` → `uint32` byte length + UTF-8 bytes
- `array` → `uint32` count + items back to back
- `linked_list` → presence byte (`0` = empty), then `uint32` count + values
- `binary_tree` → `uint32` slot count + per slot (`0` | (`1` + value)) — the
  same trimmed level-order shape as JSON, `null` slots encoded as bare `0`
- `nary_tree`, `next_tree` → binary-tree slots exactly like `binary_tree`
  (children groups decoded per the display rules of each kind)
- `quad_tree` → per node: presence byte, then `isLeaf` byte + `val` byte,
  then (inner nodes only) the four subtrees preorder
- `nested` → tag `1` + `int32` (integer hold) or tag `2` + `uint32` count +
  encoded children (list hold)
- `circular_list`, `doubly_circular` → `uint32` count + values (rings decode
  closed — see the invariants below)
- `alias_list` → presence byte, `uint32` count + prefix values, then the
  `uint32` splice index
- `multi_list` → per chain: `uint32` count, then per node the value, a
  child flag byte, and the flagged child's own chain
- `graph` → `uint32` node count, then per node `uint32` degree + 0-based
  neighbor indices
- `random_list` → `uint32` count, then per node value + `uint32` random
  index (`0xFFFFFFFF` = null)
- `struct` → field values in declaration order

The reader rejects trailing bytes (`finished()`), truncation, and — for the
JS/TS family — 64-bit inputs beyond the safe-integer range. Results flow back
as the JSON wire shapes above; the JS/TS wrappers serialize integer doubles
beyond 2^53 as exact decimal digits (see `openojSerialize` in the wrapper
templates).

## Return-serialization invariants (every language identically)

- A missing list/tree/ring return (`nullptr`, `null`, `None`) serializes as
  `[]`. The one exception is `quad_tree`, where a missing tree serializes as
  `null` (an empty preorder would be indistinguishable from garbage).
- `circular_list` / `doubly_circular` inputs decode **closed** (tail wired to
  head) — solutions always see a genuine ring. Return serialization walks the
  ring and raises "not closed" / "not properly linked" when the solution
  breaks the invariant, so an unclosed ring can never pass as `[]`.
- `multi_list` returns must be fully flattened: every `prev` back-link set
  and no `child` left anywhere; otherwise serialization raises. The LC 430
  order is: a child chain splices in immediately after its parent node.
- `graph` returns normalize: rows emit in node-value order, each row's
  neighbors sorted — adjacency order is irrelevant on LC 133. The judge also
  clone-checks: the returned graph must not alias any input node (python/java
  identity sets; the typed wrappers collect input pointers alongside).
- `alias_list` returns serialize the aliased segment from the returned node;
  a null return serializes as `[]` (LC 160's "no intersection").
- An array-of-rings return (LC 2674's split) declares `return_codec:
  "circular_list_array"` with `return_type` an array of `circular_list`;
  each element serializes through the ring walk, in every language.

## Wrapper types and the provided-class contract

The problem set's `common/` library (`common/VERSION.json`, version 2)
declares `ListNode`, `TreeNode`, `Node` (n-ary), `QuadNode`,
`NestedInteger`, `NodeWithNext` (`val/left/right/next/parent`), and
`MultiListNode` (`val/prev/next/child`) — assembled into every submission
by the judge: executed into the python module namespace, compiled in the
same java package, concatenated into the typed languages' translation
units. Generated starters reference the names bare; solutions never
define them; the editor never shows the implementations.

Graph (LC 133) and random list (LC 138) nodes are deliberately NOT in
`common/`: every bundle that needs them names its own class in the
manifest and ships the sources in `provided/<language>/`:

    "value_type": {"kind": "graph", "items": {"kind": "integer", "bits": 32},
                   "class": "GraphNode"}

- `class` (optional, identifier) is honored for `graph` and `random_list`
  only. Every typed renderer re-decorates around the provided name
  (`GraphNode*` in C++, `*GraphNode` in Go, `GraphNode | null` in TS,
  `Option<Rc<RefCell<GraphNode>>>` in Rust); legacy manifests without
  `class` fall back to `Node`.
- Java resolves the node type reflectively from the solution's declared
  parameter type; the python harness decodes into the classes its
  namespace carries.
- Same contract on the return side: return_codec `graph`/`random_list`
  serialize through the provided class's `neighbors` / `next`+`random`
  fields.

`struct` fields name their own provided class the same way: the struct's
`class` must exist in `provided/` (constructed positionally from the
decoded field values in every language — a C++ struct needs a matching
positional constructor). Declared field order is the positional order in
every language; Go's reader builds the composite literal positionally, so
the provided struct's field order must match the manifest exactly.

Provided Rust sources share one module with `common.rs` and the wrapper,
so they use fully-qualified paths (`std::rc::Rc<...>`) and carry no `use`
lines; the submission's own `solution.rs` MAY import. The assembled Go
`NestedInteger` is pointer-based (`GetList() []*NestedInteger`, `Add`/
`SetInteger` on pointer receivers) — Go solutions walk `*NestedInteger`
items, mirroring LeetCode's own Go template.

## Design problems (`type: "design"`)

Cases carry LeetCode-style sequences instead of positional arguments:

```json
{"input": {"actions": ["NumArray","update","sumRange"],
            "params": [[[1,3,5]], [1,2], [0,2]]},
 "expected": [null, null, 9]}
```

`params[0]` goes to the class constructor; each later `actions[i]` names a
method invoked with `params[i]`. The recorded output starts with `null` (the
constructor returns nothing); methods without a declared `return_type`
contribute `null` slots. Offered in all seven languages. Constructor
parameters take the full `value_type` vocabulary — a `nested` constructor
parameter (LC 341) decodes into the language's NestedInteger in every
offered language.

### Statistical judging of randomized methods

A method whose LeetCode contract is "pick uniformly at random" cannot be
compared against a single expected value, so an action may instead be
`{"call": "getRandom", "repeat": 2000}`. The harness invokes the method
that many times and reports a frequency table keyed by the canonical JSON
of each returned value (`json.dumps(value, sort_keys=True,
separators=(",", ":"))` in Python; `Json.stringify` in Java). The matching
expected slot carries the distribution:

```json
{"mode": "distribution", "repeat": 2000, "tolerance": 0.12,
 "probabilities": {"1": 0.5, "2": 0.5}}
```

The judge requires the observed total to equal `repeat`, every observed
value to be a declared key, and each bucket to land inside the wider of
`tolerance × expected` and 3.5 binomial standard deviations — a band that
a correct sampler effectively never leaves while a biased one still
fails. Buckets whose expected count falls below 10 merge into a single
tail bucket. Exact and statistical slots mix freely in one case, so
`insert`/`remove` stay exactly judged alongside a sampled `getRandom`.
Case authors should size `repeat` so each bucket expects a few hundred
draws or more.

## Interactive problems (`type: "interactive"`)

The oracle ships **with the problem** in `provided/` (all seven languages),
hidden from the editor. The judge assembles it with the submission and
constructs it from the case's hidden state per `invocation.provided.oracle`:

    "provided": {"oracle": {"class": "SequenceReader",
                            "construct": ["arr"], "auxiliary": ["target"]}}

- `construct`: case keys passed to the constructor, in order; the query
  budget (`invocation.query_limit`, default 1 000 000) is appended last
- `auxiliary`: case keys passed to the solution method after the oracle,
  converted to the method's own parameter types
- a void method is judged by the oracle's `verdict()` final state

Out-buffer parameters: an interactive method may declare

    {"name": "buf", "codec": "json",
     "value_type": {"kind": "array", "items": {"kind": "string"}},
     "out_buffer": {"capacity_from": "n"}}

The harness allocates the buffer (length taken from the named case key)
and passes it in its declared position; an out-buffer parameter consumes
no case input — the LC 157/158 read4 wire. `capacity_from` must name an
integer-valued case key: when the natural source is an array (158's
queries), add a dedicated integer `capacity` key and point at it. The
judged result becomes
`[result, buffer[:result]]` (the written prefix), so the case's expected
value carries both.

Offered in all seven languages. Authoring a new interactive problem
touches only its own bundle — no judge changes. The wrapper constructs
the oracle class the bundle ships, and the constructor signature is
per-language (the budget parameter carries `query_limit`):

| Language | Construction (one `construct` key shown) | Budget type |
| --- | --- | --- |
| Python 3 | `File(content, budget)` — construct values flattened | `int` |
| Java | `new File(content, budget)` — flattened | `long` |
| C++ | `File(openoj_value_0, …, budget)` — one `OjValue` per construct key | `long long` |
| Go | `NewFile([]any{content…}, budget)` — construct values wrapped in one slice | `int64` |
| TypeScript / JavaScript | `new File([content…], budget)` — wrapped in one array | `number` |
| Rust | `File::new(&[OjValue…], budget)` — wrapped in one slice | `i64` |

C++ and Rust see generic `OjValue`s (decode with the language's helpers in
the wrapper prelude); every other language receives decoded values. A void
method is judged by the oracle's final `verdict()` state (the bundle ships
that method under the language's own casing — `Verdict()` in Go).

## Concurrency problems (`type: "concurrent"`)

LeetCode's concurrency problems hand the same object to several threads
at once. The case carries a schedule, one entry per thread:

```json
{"constructor": [3],
 "threads": [{"call": "hydrogen", "emits": "H"},
              {"call": "hydrogen", "emits": "H"},
              {"call": "oxygen", "emits": "O"}]}
```

Each entry becomes one real thread. `emits` marks the LeetCode shape
where the method receives a release callback: the harness passes a
callback that appends that token to a shared log, so the log is the
interleaving the submission actually produced. `records: true` instead
appends the call's return value when it completes. Everything else runs
for its side effects only.

The callback parameter itself is a `value_type`, with four shapes:

- `{"kind": "callback"}` — plain release callback; records the `emits`
  token of the thread that received it
- `{"kind": "callback", "event": [...]}` — composes the log entry from
  the method's own arguments: `"#0"` inserts argument 0, any other
  string verbatim (LC 1279's `carArrived(3, 1, 0, turnGreen, crossCar)`)
- `{"kind": "callback", "value": true}` — records the VALUE the solution
  passes to the callback rather than a fixed token (LC 1195's
  `printNumber(value)`) — the fizzbuzz wire
- `{"kind": "callback", "record": false}` — silent; runs the callback
  for the solution's synchronization only and records nothing

Java materializes the callback with `java.lang.reflect.Proxy`
implementing whatever interface the solution's method declares, so a
bundle may ship its own single-method interface (e.g.
`interface PrintNumber { void accept(int value); }`) — no fixed
harness-side functional type.

The invocation declares the class the way a design problem does —
`class_name`, `constructor.parameters`, `methods` — with one extra
parameter kind: `{"kind": "callback"}` is the release callback the judge
supplies, rendered as `Callable[[], None]` in the Python starter and
`Runnable` in Java. Every Java method of a concurrent class is generated
with `throws InterruptedException`, since any of them may block.

`limits.threads` tells the sandbox how many threads the schedule
spawns — threads count against the runtime process cap, which would
otherwise stop the schedule short. A schedule that deadlocks never
returns, so the case's ordinary time limit is the deadlock detector.

Because a correct concurrent program has many valid interleavings, these
cases are judged by invariant rather than by one expected order:
`multiset` comparison where only the collection of results matters, or
`{"mode": "grouped", "size": 3, "counts": {"H": 2, "O": 1}}`, which
requires every consecutive group of that size to hold exactly those
tokens. Offered in Python 3 and Java only.

## SQL judging (`type: "sql"`)

The submission file is one SELECT whose row set is the answer; each case
seeds an in-memory sqlite with `invocation.sql.schema` then the case's
setup statements. Flags on `invocation.sql`:

- `"headers": true` — the result carries column names:
  `{"columns": [...], "rows": [...]}` (expected compares both — the LC
  2884-2886 rename family). Without the flag the result is bare rows.
- `"dynamic_columns": true` — the submission may run several statements.
  Statement 1 is a discovery SELECT returning exactly one row/one column
  (a text column list); its output substitutes raw into every
  `__COLUMNS__` placeholder (default; `separator`/`placeholder` flags
  customize the split and the marker) of the remaining statements, of
  which the last is the answer SELECT (the LC 2252/2253/2889 pivot
  family). The default marker is deliberately a bare word: the pinned
  SQL formatter rewrites `%`-wrapped markers (`%COLUMNS%` becomes
  `% COLUMNS %`) but leaves name tokens byte-exact, so submissions
  survive the in-image format pass. ATTACH is denied on this path.
  Requires `comparison: "exact"` discovery hygiene — malformed
  discovery raises a runtime error, never a wrong answer.

Multi-statement submissions without `dynamic_columns` are rejected up
front. Expected rows compare through the invocation's ordinary
comparison mode (`set`/`multiset`/`exact`).

## Validator judging (`{"mode": "validator", ...}`)

When a problem accepts many correct answers, the expected slot can name a
judge-side checker instead of one value:

    {"mode": "validator", "name": "flip_permutation"}

The registry lives in `api/app/validators.py`; unknown names raise at
load, so a typo'd bundle fails loudly. Every validator receives the
submission's output, the case input, and optional `params`, and answers
one question — is THIS output a correct answer to THIS input:

- `fizzbuzz` — the recorded value-callback stream is exactly the fizzbuzz
  sequence for `params.n` (LC 1195)
- `knight_tour` — a full n×n tour: every cell once, every step a legal
  knight move (LC 2664-ish tour contracts)
- `last_marked_nodes` — for every node i the answer names a node at
  maximum distance from i, the crawl's "choose any one answer"
  (input `[edges]`, LC 3313)
- `grid_layout`, `grid_paths`, `grid_k_paths`, `grid_k_paths_free` —
  grid-construction families; `params.impossible: true` (or a derived
  impossibility) accepts an explicitly declared impossible answer
- `rearrange_pair_order` — output is a permutation of the input string
  in which every `y` precedes every `x` (input `[s, x, y]`, LC 3992)
- `disc_points` — a point set inside the disc requirements, judged with
  a reproducible seeded sampler, not randomness
- `flip_permutation` — the recorded flip stream is a permutation of all
  m·n cells since the last reset (LC 519)

Design-problem validator slots (`flip_permutation`, `fizzbuzz`) apply to
the recorded action outputs, not a single return.

## Solution files (`solution*.<ext>`)

A bundle carries either a single canonical `solution.<ext>` per language, or
named variants `solution_<variant>.<ext>` (e.g. `solution_dfs.py`,
`solution_bfs.py`) for problems with multiple equivalent approaches. Rules
(enforced by openoj-problems' check.py):

- every language the problem offers has at least one solution file;
- the variant set is identical across languages — `dfs` in Python means
  `dfs` in Java too, with equivalent behavior;
- `problem.json`'s `reference_solution` designates the ONE reference whose
  runtime is the time-cost baseline (the canonical `solution.<ext>` when
  it is `""`, else that named variant) — it is the optimal-last approach,
  and the judge runs exactly it alongside the submission.

## Comparison modes (`invocation.comparison`)

- `exact` (default) — structural equality
- `sorted` — order-insensitive top level (any valid order passes)
- `multiset` — duplicates matter, order does not
- `set` — neither order nor duplicates matter
- `close` — per-scalar tolerance for floats: 1e-9 relative and absolute,
  recursively through nested arrays/objects; structure must still match.
  `{"mode": "close", "tolerance": …}` customizes the tolerance in the
  problem source.

Two modes live in the expected value rather than the invocation, so a
single case can mix them with exactly-judged slots:

- `{"mode": "any_of", "values": [...]}` — any listed answer passes. Used
  where LeetCode itself accepts several results, e.g. `getMaxKey` when two
  keys share the extreme count.
- `{"mode": "distribution", ...}` — statistical judging of a randomized
  method (see "Statistical judging of randomized methods" above).
- `{"mode": "validator", "name": ...}` — a judge-side checker decides
  (see "Validator judging" above).
