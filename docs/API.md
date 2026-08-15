# OpenOJ REST API

The judge's full surface — the same API the web UI uses — available to
scripted callers. Every endpoint except health requires a **guest session**;
there is no other auth until accounts exist, so treat any deployment's API as
public and rate-limit at the edge if you expose it.

## Base URL

- Same origin as the web UI: `https://openoj.dongziyu.com/api/…` (always on —
  this is how the UI works).
- Optional direct endpoint without the web container in the path:
  `https://api.openoj.dongziyu.com/…`, off by default. Enable with

  ```sh
  OPENOJ_CADDY_EXTRA=./deploy/api.caddy docker compose up -d
  ```

  and point DNS for `api.openoj.dongziyu.com` at the host (Caddy provisions
  the certificate on first request). Paths below assume the same-origin form;
  strip the `/api` prefix on the direct endpoint.

## Sessions

A session is an HttpOnly cookie created on demand. It idles out after one
hour; an expired session and everything it owns (drafts, submissions) is
deleted.

```sh
# Create a session (keep the cookie jar)
curl -c jar.txt -X POST https://openoj.dongziyu.com/api/session
# {"status":"active","idle_seconds":3600}

# Check it
curl -b jar.txt https://openoj.dongziyu.com/api/session
```

Every request with a valid cookie refreshes the idle clock. A request without
one gets `401 {"detail":"No active session"}`.

## Problems

```sh
# Full list (single page — the editor needs the whole ordering)
curl -b jar.txt 'https://openoj.dongziyu.com/api/problems'

# Paginated slice for lists
curl -b jar.txt 'https://openoj.dongziyu.com/api/problems?page=2&page_size=50'
```

Response page shape: `{items, total, page, page_size, pages}`; each item is
`{id, slug, title, difficulty, tags}` (difficulty is the set's own H1–H5
scale).

```sh
# One problem with statement, hints, invocation, limits, languages,
# starters, and public cases (inputs only — expected values are hidden)
curl -b jar.txt https://openoj.dongziyu.com/api/problems/two-sum
```

`invocation` describes the judge contract: parameter names/types (`integer`
with `bits`, `number`, `string`, `boolean`, `array`, `linked_list`,
`binary_tree`), the return type, and `comparison` — `exact`, `sorted`,
`multiset`, or `close` (floats compared per-scalar within 1e-9 relative
tolerance; `{"mode":"close","tolerance":…}` customizes it in the problem
source). For `type: "design"` problems, cases carry LeetCode-style
`actions`/`params` sequences instead of a positional argument list.

## Drafts (session-scoped editor state)

```sh
curl -b jar.txt https://openoj.dongziyu.com/api/drafts/two-sum
# [{"language":"python3","code":"…","updated_at":1786790973.5}]

curl -b jar.txt -X PUT https://openoj.dongziyu.com/api/drafts/two-sum/python3 \
  -H 'content-type: application/json' -d '{"code":"class Solution:\n    …"}'
```

## Run (visible cases only)

```sh
curl -b jar.txt -X POST https://openoj.dongziyu.com/api/run \
  -H 'content-type: application/json' \
  -d '{"slug":"two-sum","language":"python3","code":"…"}'
```

Omit `cases` to run the problem's public cases. Pass `cases` (a list of
`{parameter: value}` objects) to run custom inputs; custom cases execute
without an assertion and return the actual output. Response:

```json
{
  "status": "completed",
  "passed": 3, "total": 3, "runtime_ms": 128,
  "results": [
    {"name":"Case 1","status":"completed","input":{…},"actual":[0,1]}
  ]
}
```

## Submit (full judge)

```sh
curl -b jar.txt -X POST https://openoj.dongziyu.com/api/submit \
  -H 'content-type: application/json' \
  -d '{"slug":"two-sum","language":"python3","code":"…"}'
```

Judges every hidden case. Verdict statuses: `accepted`, `wrong_answer`,
`compile_error`, `runtime_error`, `time_limit_exceeded`,
`memory_limit_exceeded`, `system_error`. The response adds
`submission_id` and `reference_runtime_ms` (the bundle's reference solution
on the same runner; the ratio is a hardware-independent speed signal).

```sh
# Session's submission history for a problem (pre-session history is shared)
curl -b jar.txt 'https://openoj.dongziyu.com/api/submissions?slug=two-sum'
curl -b jar.txt https://openoj.dongziyu.com/api/submissions/42
```

## Errors

`401` no/expired session · `400` unavailable language, malformed input, or
oversized draft · `404` unknown problem/submission · `503` judge runner
unavailable. Error bodies are `{"detail": "…"}`.

## Limits

Per-problem `limits` (`time_ms`, `memory_mb`, `output_kb`) ship in the
problem payload and are enforced inside the isolated runner; the API returns
verdict statuses rather than killing the HTTP request. Bodies over 256 KiB
are rejected at the web proxy.
