# Samruddhi Fire QMS

**Before doing anything in this repo, read [ABOUT.md](ABOUT.md) in full.**

It is the project's context anchor — architecture, per-page instructions, data
shapes, known gaps, and which files are stale. Do not infer structure from file
names or from `integration.py` / `product_view_additions.py` (both are dead
docs; ABOUT.md §8 explains why).

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
