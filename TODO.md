# TODO — discussed, not started

Items here are design decisions we have agreed to discuss or build later.
Nothing on this page is in progress; when work starts, move it to the task
list and delete it here.

## Multi-solution bundles (42 done, more welcome)

Forty-two problems now carry named variants across all seven languages,
and the convention is fully wired (judge, check.py, Solutions tab,
fastest-variant baseline). Extending it is open-ended content work:
find further problems whose approaches are genuinely distinct and
comparable, and author the variant sets.

## User accounts (multi-user phase 2)

Account creation (fresh-start admin bootstrap, regular sign-up, login,
logout) and user-scoped drafts/submissions are DONE and live. Remaining:

- **Better password and user identity management** (subject to design
  discussion) — the current scrypt-with-salt scheme and fixed-name admin
  bootstrap are a baseline, not the destination.
- Admin management surface (listing/deleting accounts, resetting
  passwords) once the accounts UI grows beyond the gate.

## Import backlog: closed

The 53 distinct problems set aside during the original import (the "55"
in earlier notes double-counted 380 and 528) have all landed: 37 design
classes, 7 randomized problems on statistical judging, 7 hidden-API
problems on their oracles, and 2 concurrency problems on real threads.
The set stands at 836.
