# ADAPT — an independently written problem bank

OpenOJ's 838 bundles were built by reading LeetCode problems. The
statements, examples, and API names in them are LeetCode's; the judging
data, reference solutions, guides, and figures are ours. This document
designs the program that turns that set into **problems inspired by
LeetCode** — the same computational task, the same technique, the same
difficulty, written independently.

Nothing here has been executed. Adapted bundles land in
`openoj-problems/problems-adapt/`; the live `problems/` tree keeps
serving until the whole set passes and we choose to cut over.

## The rule the whole design serves

Treat each source problem as a way to identify a functional
specification, then write everything else from that specification. Never
paraphrase. Per problem:

1. Read the source bundle.
2. Write down the abstract spec — inputs, output, conditions,
   guarantees, intended technique, intended complexity.
3. Close the source.
4. Write the new problem from the spec alone.

A rewrite that reads like the original with words swapped has failed,
even if every word differs.

## Decisions

1. **Cutover.** The adapted set eventually replaces `problems/` and the
   LeetCode-derived tree is archived. Until then the original stays the
   default; both trees coexist.
2. **Numbering.** Our own ids, 1…838, assigned by us. The source number
   survives only in the mapping file.
3. **Figures.** Two phases. Adaptation updates a figure's *data* to the
   new example where a text edit suffices, and drops the figure when the
   drawing's geometry encodes the old data. A later selective pass
   redraws the ones that genuinely help — the same standard as the
   earlier illustration round.
4. **Variant ids** (`dijkstra`, `kadane`, `union_find`) stay as they
   are: algorithm names, not LeetCode's wording.
5. **Compatibility is a requirement, not just a check.** A correct
   solution to the original problem must pass the adapted problem after
   renaming its entry point (and, for class-based problems, its class
   and method names) and nothing else. Same task, same data shapes, same
   judged semantics.
6. **Mapping.** Every adapted problem records where it came from, in a
   file that outlives the archived tree.

### What decision 5 costs, and why it is the right trade

The original brief allowed re-picking constraints so the bounds "enforce
the intended complexity". Decision 5 forbids that: moving a bound
changes the input domain, and then an original solution may legitimately
fail (a widened value range can require 64-bit accumulation the original
port never needed). So:

**Constraints keep their numeric domain exactly; only their presentation
is rewritten.** This costs nothing legally — bounds are functional
facts, not creative expression — and it buys a mechanical proof that the
rewrite preserved the problem.

The same reasoning fixes the test data:

- **Hidden cases stay byte-identical.** They are ours already, and
  keeping them is what makes decision 5 provable.
- **Public cases change**, because they mirror the examples and the
  examples must be new. Their expected values come from the same
  reference solution, so an original solution still passes them.

## What we hold, and what each artifact needs

| Artifact | Provenance | Action |
| --- | --- | --- |
| `statement.md` description, examples | Derived from LeetCode prose | **Rewrite from the spec.** New title, new statement, newly constructed examples |
| `statement.md` constraints | Functional facts | Same numbers, new presentation (decision 5) |
| `statement.md` hints | Ours, written against their framing | Rewrite from the algorithmic insight |
| `problem.json` `title`, `slug`, `invocation.method`, `class_name`, `entrypoints`, parameter names | LeetCode's public API | **Rename**, consistently in every language |
| `problem.json` `id` | LeetCode's number | Our own sequential id; source id lives in the mapping |
| `problem.json` `difficulty`, `tags`, `limits`, `comparison`, codecs | Ours | Keep |
| `cases.json` **hidden** | Ours | **Unchanged** |
| `cases.json` **public** | Mirror the examples | Regenerate with the new examples |
| `solution.*` | Ours | Keep the algorithm; rename the API; update comments naming old terminology |
| `starter.*` | Generated from `problem.json` | Regenerate via `gen_starters.py`; never hand-edit |
| `solutions.md` | Ours | Keep the exposition; update names and any worked example using the old data |
| `figures/example-*.svg` | Ours, but they draw the old examples | Update the labels, or drop (see below) |
| `figures/solution-*.svg` | Ours, illustrate the algorithm | Keep unless the drawing walks through an old example |

### Figures: pick examples that fit the picture

313 bundles carry figures, and in them the example data sits in SVG text
nodes — `>2<`, `>4<` — so changing a linked list's values is a text
edit, not a redraw. Geometry is the exception: histogram bar heights,
tree shapes, and grid contents encode the data structurally.

That gives a cheap rule for constructing examples:

> When a bundle has a figure, prefer a new example that **preserves the
> drawn structure** — same list length, same tree shape, same grid
> dimensions — and changes only the values. The figure then needs a
> label edit and nothing more.

Where that is not possible without making the example contrived, drop
the figure and let phase two decide whether to redraw it. Never ship a
new statement beside a figure showing the old data.

## Naming

### Titles and slugs

Short, descriptive, algorithm-oriented, searchable. Rename unless the
name is an unavoidable generic term (*Binary Search*). Never rename
merely to differ.

```
Two Sum            → Pair Sum                pair-sum
Valid Parentheses  → Balanced Brackets       balanced-brackets
Maximum Subarray   → Largest Subarray Sum    largest-subarray-sum
Number of Islands  → Count Grid Islands      count-grid-islands
```

Directories become `<our id>_<new slug>`, keeping check.py's
`<zero-padded id>_<slug>` rule. All 838 slugs must be unique among
themselves — checked mechanically.

**Sibling problems keep their kinship.** The 48 alternates are near-twins
of a prime (Single Number I/II/III; Best Time to Buy and Sell Stock
I–IV). Their new titles must stay recognizably related and mutually
distinguishable, decided together rather than one at a time.

### Methods, classes, parameters

The public API follows the new title, in every language including the Go
/ Rust / TypeScript entrypoints:

```
twoSum → pairSum      (go pairSum, rust pair_sum, typescript pairSum)
numIslands → countGridIslands
```

The 48 design classes and 2 concurrency classes carry LeetCode names too
(`LRUCache`, `Trie`, `MedianFinder`, `H2O`) and get renamed with the
problem.

Parameters: rename when it improves consistency; keep conventional
identifiers (`nums`, `target`, `root`, `head`, `grid`, `s`, `k`, `n`).
Clarity beats superficial difference. A renamed parameter changes in the
statement, skeleton, annotations, examples, judge invocation, fixtures,
and reference implementation — no stale identifier anywhere.

### Oracles — open question

The nine interactive problems name their oracle after LeetCode's hidden
API (`GridMaster`, `Master`, `MountainArray`, `BinaryMatrix`,
`ArrayReader`, `Robot`, `Sea`, `InfiniteStream`). These names live in
the **harness**, not the bundle, so renaming them means:

- new names in `runner/interactive_oracles.py`,
  `runner/java/InteractiveOracles.java`, both dispatch tables, and
  `gen_starters.py`;
- old names kept as **aliases** while both trees coexist, dropped at
  cutover — the order matters, or the coexistence period breaks one
  tree;
- decision 5 stretched slightly for these nine: a pasted original
  solution needs its oracle *type* renamed as well as its method.

Nine problems, real harness work. **Recommendation: rename them** — they
are as much LeetCode's API surface as the method names — but this is
worth an explicit yes/no before the interactive batch starts.

### SQL

The four SQL bundles carry LeetCode's table names, column names, and
sample rows. All three are rewritten, with `solution.sql` and the schema
fixtures moving together.

## Statement style

```
Given <input>, return <output>.
<guarantee or restriction>.
```

Then examples, then constraints. No invented scenarios — no inventory
systems, banks, robots, or kingdoms unless the computation genuinely is
one. A reader should grasp the task as fast as they would a good
interview question.

## Examples

Newly constructed, never permuted. `[2,7,11,15], target 9` becoming
`[7,2,15,11], target 9` is not a new example. Two or three per problem,
covering meaningfully different shapes, each small enough to follow by
eye — and, where a figure exists, structure-preserving per the rule
above.

## Guides and hints

Reconstruct from the algorithm, in our existing shape: `## <Approach>`,
insight, algorithm, `**Complexity:**`. Multi-solution bundles keep one
section per variant, and the heading must still resolve to the variant
(the matcher pairs them by token containment). Hints follow the
reasoning path, not the answer.

## Layout

```
openoj-problems/
  problems/                # live, untouched during the program
  problems-adapt/
    MAPPING.md             # human-readable, generated from the ledger
    0001_pair-sum/ ...
  .adapt/
    ledger.json            # source id+slug ↔ our id+slug, old/new API names
    report/<slug>.md
```

`MAPPING.md` reads:

```
| ours | source | old API → new API |
| 0001_pair-sum | 0001_two-sum | twoSum → pairSum |
```

The ledger is the only place old identifiers survive, and it is what
makes the submissions migration possible at cutover: submissions are
keyed by slug, so replacing the tree requires rewriting those keys
through this map, or history breaks.

## Verification gates

1. **`scripts/check.py`** — bundle shape, naming, public/example
   correspondence, variant parity, formatter cleanliness.
2. **`verify_solution.py`** — every solution, variant, and language,
   N/N.
3. **Sandboxed judge** — submit through the running API. The authoring
   harness applies no limits; this is what caught the concurrency
   failures. Mandatory for design, interactive, concurrent and SQL.
4. **Compatibility (decision 5)** — take the *original* bundle's
   reference solution, rename only its entry point (plus class name
   where applicable), run it against the *adapted* bundle's cases in
   every language. All must pass. This is the mechanical proof that the
   rewrite preserved the problem.
5. **Stale-identifier scan** — old title, slug, method, class, oracle,
   parameter names, and old example values, across `statement.md`,
   `solutions.md`, `solution.*`, and `figures/*.svg`. Zero hits. The
   guides matter here: several walk through the original example data.
6. **Prose-overlap scan** — 7-word shingles, normalized, against the
   source statement. Above a small threshold means paraphrase rather
   than rewrite, and the problem goes back. Ordinary technical phrasing
   sits below it naturally.

## Working order

**Phase 0 — pilot (10 problems).** One or two from each invocation kind:
a plain function problem with a figure, one without, a design class, an
interactive one, a concurrency one, a SQL one, and a multi-solution
bundle. Review the output together and settle what "good" reads like
before committing to 828 more. Nothing about this program is worth
scaling before that conversation.

**Phase 1 — the bulk**, batched by invocation kind so harness work lands
before the problems that need it:

1. 775 function problems — no judge changes.
2. 4 SQL — schema rewrite.
3. 48 design — class renames.
4. 9 interactive — after the oracle-alias work.
5. 2 concurrency — class and method renames, sandbox verification.

**Phase 2 — figures.** Selective redraws for the ones dropped in
phase 1, judged by whether the picture genuinely helps.

**Phase 3 — cutover.** Swap the trees, migrate submission slugs through
the ledger, archive the original, drop the oracle aliases.

Within a batch, one problem at a time to completion. Per-problem report:

```markdown
## <source id> — <old title>
- New id / title / slug:
- Old → new API:
- Core algorithm / difficulty:
- Statement rewritten from spec: yes
- Examples newly constructed: yes   (structure-preserving: yes/no/n-a)
- Constraints: domain unchanged, presentation rewritten
- Skeletons regenerated: <languages>
- Figures: labels updated / dropped / none
- Gates: check ✓ verify ✓ sandbox ✓ compatibility ✓ stale ✓ overlap ✓
```
