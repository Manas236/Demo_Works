"""
formdraft.py — an unsaved create form survives the Back button
==============================================================

31 October 2026, CLIENT_CHANGES.md §0 sixty-second block. On the call: "I
added three line items, pressed back, and had to make it all again." The
choice (Manas): the form saves itself IN THE BROWSER as you type, and when you
come back it offers "Resume your unsaved <document>?" with a Discard button. No
server records, so nothing half-made ever lands in a register.

How it works — and why it needs one line in the route
-----------------------------------------------------
Every create form here already knows how to redraw itself from a POSTED form —
that is what a refused POST does, rows and all. So the script saves the form's
fields (`FormData`, every value, in order) to `localStorage` under the page's
path, and **Resume** POSTs them back to the same route with `_resume=1`. The
route's one job is to treat that POST as a redraw and never as a save:

    if request.method == "POST" and not formdraft.is_resume(request.form):
        … the save path …

That keeps every repeater, every picked item and every typed box, because the
form's own redraw is what rebuilds them — the script never tries to rebuild a
page's rows itself.

What it does NOT do (honest limits)
-----------------------------------
* **Per browser, per device.** Started on the office PC → not resumable on a
  phone. Cleared browser data → gone.
* **Files are never saved** (a picture chosen in a file box is not text).
* The saved copy is cleared when the form is SUBMITTED for real, and by
  Discard. A refused save redraws the form with what was typed anyway, and the
  next keystroke saves it again.
* Browser storage can be unavailable (a private window, blocked site data):
  every read and write is wrapped, and the form then behaves exactly as before.

Wired into: `/purchase/create` (31 Oct 2026). The other create forms take the
same two pieces — `script(...)` in the page, `is_resume()` in the route — in
the next pass.

A LEAF: imports nothing of the app.
"""

RESUME_FIELD = "_resume"


def is_resume(form) -> bool:
    """Is this POST a Resume redraw (never a save)?"""
    return str((form or {}).get(RESUME_FIELD) or "") == "1"


def script(form_selector: str, doc_word: str, *, resumed: bool = False) -> str:
    """
    The `<script>` for one create page. `form_selector` finds the form (e.g.
    `form[action$="/purchase/create"]`); `doc_word` names it in the banner
    ("purchase order"). `resumed=True` on the redraw a Resume produced, so the
    banner is not offered again over the very draft it just restored.

    PLAIN text with SINGLE braces — it is substituted into a page as a value.
    """
    sel = form_selector.replace("\\", "\\\\").replace("'", "\\'")
    word = (doc_word.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace("'", "&#39;"))
    resumed_js = "true" if resumed else "false"
    return """<script>
(function () {
  var FORM = document.querySelector('%(sel)s');
  if (!FORM) return;
  var KEY = 'draft:' + location.pathname;
  var RESUMED = %(resumed)s;
  function store() { try { return window.localStorage; } catch (e) { return null; } }
  function read() {
    var s = store(); if (!s) return null;
    try { var v = JSON.parse(s.getItem(KEY) || 'null');
          return (v && v.fields && v.fields.length) ? v : null; } catch (e) { return null; }
  }
  function clear() { var s = store(); if (s) { try { s.removeItem(KEY); } catch (e) {} } }
  function save() {
    var s = store(); if (!s) return;
    var out = [];
    try {
      new FormData(FORM).forEach(function (v, k) {
        if (typeof v !== 'string' || k === '%(field)s') return;
        out.push([k, v]);
      });
      /* Only worth keeping once something has been typed or picked. */
      var typed = Array.prototype.some.call(FORM.querySelectorAll('input,select,textarea'),
        function (el) {
          if (!el.name || el.type === 'hidden' || el.type === 'file') return false;
          if (el.type === 'checkbox' || el.type === 'radio') return el.checked !== el.defaultChecked;
          if (el.tagName === 'SELECT') {
            for (var i = 0; i < el.options.length; i++) {
              if (el.options[i].selected !== el.options[i].defaultSelected) return true;
            }
            return false;
          }
          return el.value !== el.defaultValue;
        });
      if (!typed && !RESUMED) return;
      s.setItem(KEY, JSON.stringify({at: new Date().toISOString(), fields: out}));
    } catch (e) {}
  }
  var timer = null;
  function soon() { clearTimeout(timer); timer = setTimeout(save, 400); }
  FORM.addEventListener('input', soon);
  FORM.addEventListener('change', soon);
  FORM.addEventListener('click', function () { setTimeout(soon, 50); });
  FORM.addEventListener('submit', function () { clear(); });

  var draft = RESUMED ? null : read();
  if (!draft) return;
  var when = '';
  try { when = new Date(draft.at).toLocaleString('en-IN',
        {day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'}); } catch (e) {}
  var bar = document.createElement('div');
  bar.setAttribute('role', 'status');
  bar.style.cssText = 'margin:0 0 1rem;padding:.8rem 1rem;border:1px solid var(--border);' +
    'border-left:3px solid var(--navy);border-radius:var(--radius,8px);background:var(--surface);' +
    'display:flex;gap:.7rem;align-items:center;flex-wrap:wrap;font-size:.9rem;';
  var msg = document.createElement('span');
  msg.style.flex = '1 1 16rem';
  msg.innerHTML = 'You have an <b>unsaved %(word)s</b>' + (when ? ' from ' + when : '') +
                  '. Resume where you left off?';
  var go = document.createElement('button');
  go.type = 'button'; go.className = 'btn'; go.textContent = 'Resume';
  var no = document.createElement('button');
  no.type = 'button'; no.className = 'btn btn-ghost'; no.textContent = 'Discard';
  bar.appendChild(msg); bar.appendChild(go); bar.appendChild(no);
  FORM.parentNode.insertBefore(bar, FORM);
  no.addEventListener('click', function () { clear(); bar.remove(); });
  go.addEventListener('click', function () {
    var f = document.createElement('form');
    f.method = 'POST'; f.action = FORM.getAttribute('action') || location.pathname;
    f.style.display = 'none';
    draft.fields.forEach(function (kv) {
      var i = document.createElement('input');
      i.type = 'hidden'; i.name = kv[0]; i.value = kv[1]; f.appendChild(i);
    });
    var r = document.createElement('input');
    r.type = 'hidden'; r.name = '%(field)s'; r.value = '1'; f.appendChild(r);
    document.body.appendChild(f);
    f.submit();
  });
})();
</script>""" % {"sel": sel, "word": word, "resumed": resumed_js, "field": RESUME_FIELD}
