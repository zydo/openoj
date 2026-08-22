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

## Multi-solution bundles, beyond the first 76

Fully wired and 76 problems carry named variants (waves 2 and 3; 2026-08-21). Open-ended content
work: find further problems whose approaches are genuinely distinct and
comparable, and author the variant sets.

## Multi-arch runner image

`ghcr.io/zydo/openoj-runner` is published amd64-only (CI builds on
amd64 runners). Add `linux/arm64` via QEMU (`platforms:` +
`docker/setup-qemu-action`) when arm consumers appear; roughly doubles
build time. Deliberately deferred 2026-08-22: one arch only for now.
