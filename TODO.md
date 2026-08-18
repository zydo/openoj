# TODO — discussed, not started

Items here are design decisions we have agreed to discuss or build later.
Nothing on this page is in progress; when work starts, move it to the task
list and delete it here.

## User accounts (multi-user phase 2)

Account creation (fresh-start admin bootstrap, regular sign-up, login,
logout) and user-scoped drafts/submissions are done and live. Remaining:

- **Better password and user identity management** (subject to design
  discussion) — the current scrypt-with-salt scheme and fixed-name admin
  bootstrap are a baseline, not the destination.
- Admin management surface (listing/deleting accounts, resetting
  passwords) once the accounts UI grows beyond the gate.

## Multi-solution bundles, beyond the first 42

The convention is fully wired (judge, check.py, Solutions tab,
fastest-variant baseline) and 42 problems carry named variants across all
seven languages. Extending it is open-ended content work: find further
problems whose approaches are genuinely distinct and comparable, and
author the variant sets.
