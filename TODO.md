# TODO — discussed, not started

Items here are design decisions we have agreed to discuss or build later.
Nothing on this page is in progress; when work starts, move it to the task
list and delete it here.

## Versioned common-harness contract

Bundles currently assume the `common/` library ambiently (both trees move
together in one repo, so this is harmless today). The open item: make the
common vocabulary a declared, versioned dependency per bundle so the
problems repo stays portable across judge versions. The trust model for
bundle-carried code — common/, provided/ — is now written down in
`docs/TRUST-BOUNDARIES.md`.

## User accounts (multi-user phase 2)

Account creation (fresh-start admin bootstrap, regular sign-up, login,
logout) and user-scoped drafts/submissions are done and live. Remaining:

- **Better password and user identity management** (subject to design
  discussion) — the current scrypt-with-salt scheme and fixed-name admin
  bootstrap are a baseline, not the destination.
- Admin management surface (listing/deleting accounts, resetting
  passwords) once the accounts UI grows beyond the gate.

## Multi-solution bundles, beyond the first 54

Fully wired and 54 problems carry named variants. Open-ended content
work: find further problems whose approaches are genuinely distinct and
comparable, and author the variant sets.

## DONE 2026-08-21: CLI services live on the runner image

`openoj format` (7 languages), `openoj gen-starters` (language-agnostic
schema in, seven starters out), and `openoj judge` (every solution in
every language through the real executors, common + provided assembly
included) are implemented in `runner/cli.py`, installed as the `openoj`
entrypoint by the runner image, and verified in-image on all four
invocation kinds. The authoring tutorial below is the remaining piece.

## (Done — see docs/AUTHORING.md and runner/cli.py) Formatting and starter generation as published CLI services of core

The runner image already carries the pinned toolchain for every language
(and `POST /format` already exposes it to the editor). Publish the image
and give it CLI entry points so any machine can pull and run:

- **format service** — `docker run ghcr.io/zydo/openoj-runner format
  <files...>` formats starters and solutions in any offered language to
  the OpenOJ standard. This replaces the fragile "authoring machine must
  install every formatter" arrangement (see the earlier
  "authoring machine cannot format what it generates" item) — the image
  is the standard, by construction identical to CI and the editor's
  Format button.
- **starter generation service** — `... gen-starters <problem.json>`
  emits every language's `starter.*` from the language-agnostic schema
  (signatures, class names, method/parameter names, invocation kind) in
  `problem.json`. The schema is the contract; the image is the only
  generator, so bundles anywhere regenerate byte-identically.
- **judging service** — `... judge <bundle-dir>` runs the authoring
  loop end-to-end: a problem creator composing a bundle (statement,
  `problem.json`, `cases.json`, starters, and their reference
  solutions) submits those solutions through the exact judging path —
  same executors, same limits, same comparison semantics as a solver's
  submission — and sees per-case pass/fail for every solution in every
  language. Most of the machinery already exists (the judge is an API;
  the worker consumes job files; the executors live in the image), so
  this is the authoring-side front door to it: local bundle in, judged
  verdict out, no authoring-machine toolchain required.

## Multi-arch runner image

`ghcr.io/zydo/openoj-runner` is published amd64-only (CI builds on
amd64 runners). Add `linux/arm64` via QEMU (`platforms:` +
`docker/setup-qemu-action`) when arm consumers appear; roughly doubles
build time. Deliberately deferred 2026-08-22: one arch only for now.
