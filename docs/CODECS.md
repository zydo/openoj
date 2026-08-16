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

Binary trees follow the LeetCode convention: children of missing nodes are
omitted, so `null` appears only between real nodes, never after the last one.
N-ary trees (python codec `nary_tree`) serialize children groups separated by
`null`, ending with a trailing `null` per LeetCode.

Return values use the same shapes: a solution returning `ListNode*` is
compared against the expected value array, a `TreeNode*` against the expected
level-order array.

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

The reader rejects trailing bytes (`finished()`), truncation, and — for the
JS/TS family — 64-bit inputs beyond the safe-integer range. Results flow back
as the JSON wire shapes above; the JS/TS wrappers serialize integer doubles
beyond 2^53 as exact decimal digits (see `openojSerialize` in the wrapper
templates).

## Wrapper types given to submissions

Python submissions get these names in module scope (`runner/python_harness.py`):
`ListNode`, `TreeNode`, `Node` (n-ary), `NestedInteger`, `HtmlParser`,
`GridMaster`. Java solutions see the same names from the judge classpath
(`runner/java/*.java`, compiled into the image). Generated starters reference
them; solutions never define them.

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
contribute `null` slots. Offered in Python 3 and Java only.

## Interactive problems (`type: "interactive"`)

The judge constructs an oracle from the case's hidden state and passes it to
the solution method. The first oracle is `GridMaster` (hidden-grid problems):

- case input: `{"grid": [[cost]], "start": [r, c], "target": [r, c]}` where
  `0` is a blocked cell and `>= 1` is the move-in cost
- API: `canMove(direction)`, `move(direction)` (cost, or `-1` without
  moving), `isTarget()` — directions `U`/`D`/`L`/`R`; every call spends one
  query from the per-case budget (`invocation.query_limit`, default 1 000 000)

Offered in Python 3 and Java only. New oracles are added as harness classes
on both sides.

## Solution files (`solution*.<ext>`)

A bundle carries either a single canonical `solution.<ext>` per language, or
named variants `solution_<variant>.<ext>` (e.g. `solution_dfs.py`,
`solution_bfs.py`) for problems with multiple equivalent approaches. Rules
(enforced by openoj-problems' check.py):

- every language the problem offers has at least one solution file;
- the variant set is identical across languages — `dfs` in Python means
  `dfs` in Java too, with equivalent behavior;
- the judge's reference-runtime baseline for a multi-solution problem is the
  **fastest** variant's run, so users are never compared against a slow
  reference port.

## Comparison modes (`invocation.comparison`)

- `exact` (default) — structural equality
- `sorted` — order-insensitive top level (any valid order passes)
- `multiset` — duplicates matter, order does not
- `set` — neither order nor duplicates matter
- `close` — per-scalar tolerance for floats: 1e-9 relative and absolute,
  recursively through nested arrays/objects; structure must still match.
  `{"mode": "close", "tolerance": …}` customizes the tolerance in the
  problem source.
