# TODO — discussed, not started

Items here are design decisions we have agreed to discuss or build later.
Nothing on this page is in progress; when work starts, move it to the task
list and delete it here.

## User accounts (multi-user phase 2)

Guest sessions (phase 1) are done; the backend user layer exists but is
hidden from the UI. Remaining:

- The UI itself: a **fresh-start flow** — on first startup with no previous
  account data, show an admin sign-up page asking to set the admin password
  (the admin username is fixed: `admin`) to create the admin account with
  the highest privilege. After that, conventional username + password (no
  email), password typed twice. `admin` is a reserved username; normal
  (non-admin) accounts can also be created. A login button stays visible in
  guest mode for login or sign-up.
- Account data is persisted and **isolated**: a non-admin user never sees
  another non-admin user's data (submissions, drafts, state).
- Account state attaches to the **user, not the login session**: drafts,
  last language selection per problem, and submission history are stored
  under the user id — signing in again from any device or session restores
  all of it. Ephemeral session scoping stays guest-only. (Backend scope
  keys already implement this; surface it.)
- **Better password and user identity management** (subject to design
  discussion) — the current scrypt-with-salt scheme and fixed-name admin
  bootstrap are a baseline, not the destination.
