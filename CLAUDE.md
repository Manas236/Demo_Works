# Samruddhi Fire QMS

**Before doing anything in this repo, read [ABOUT.md](ABOUT.md) in full.**

It is the project's context anchor — architecture, per-page instructions, data
shapes, known gaps, and which files are stale. Do not infer structure from file
names or from `integration.py` / `product_view_additions.py` (both are dead
docs; ABOUT.md §8 explains why).

Two documents are easy to miss because nothing else used to point at them.
[INTRODUCTION.md §4](INTRODUCTION.md) holds the full document map; these two are
the ones you are most likely to need and least likely to find:

- [CLIENT_CHANGES-2.md](CLIENT_CHANGES-2.md) — **Phase 3 scope** (3A / 3B / 3C)
  from the 19 August 2026 meeting. Read it before touching users, approvals,
  attachments, measurement, the merged RA or labour cost. It is a
  specification, not permission to build: the CLIENT_CHANGES.md §0 gate applies
  to it in full.
- [SOURCE_DOCUMENTS.md](SOURCE_DOCUMENTS.md) — what the client's own 18 source
  documents contain, and what that evidence does to DOMAIN.md. Read it before
  asserting how their paperwork behaves. Every finding is OPEN; none is
  actioned.

Fast facts so you don't get it wrong before reading:

- Flask app, **no `/templates` and no `/static`** — all HTML is f-strings passed
  to `render_template_string()`, all CSS is Python string constants, all images
  are inlined base64 data URIs.
- Because HTML lives in f-strings, **literal `{` and `}` in embedded CSS/JS must
  be doubled** (`{{` / `}}`). This is the most common way to break a page here.
- `store.STORE` is one shared dict mutated in place; `db.py` persists it by
  snapshotting and diffing after every request.
- Seller-side app: we issue the quotation, the customer sends us the PO.

When you change architecture, a data shape, or a route — update ABOUT.md in the
same commit.

Any pass that changes the build state of a Phase 3 item must update
[PROGRESS.md](PROGRESS.md) in the same commit, header block included.
PROGRESS.md is regenerated from code, never edited to match a plan.
