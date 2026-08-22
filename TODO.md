# TODO — discussed, not started

Items here are design decisions we have agreed to discuss or build later.
Nothing on this page is in progress; when work starts, move it to the task
list and delete it here.

## User accounts — identity and admin surface (multi-user phase 2)

Attempt records (verdicts, submitted code, time-cost vs the reference),
per-problem progress — never tried / attempted / solved, solved meaning
any one language passed — the guest session lifecycle (cleared on
idle-expiry), and the web-UI status marks (landing list, problem drawer,
problem view; guests included) are done and live. Remaining:

- **Better password and user identity management** (subject to design
  discussion) — the current scrypt-with-salt scheme and fixed-name admin
  bootstrap are a baseline, not the destination.
- Admin management surface (listing/deleting accounts, resetting
  passwords) once the accounts UI grows beyond the gate.

## Multi-arch runner image

`ghcr.io/zydo/openoj` is published amd64-only (CI builds on
amd64 runners). Add `linux/arm64` via QEMU (`platforms:` +
`docker/setup-qemu-action`) when arm consumers appear; roughly doubles
build time. Deliberately deferred 2026-08-22: one arch only for now.
