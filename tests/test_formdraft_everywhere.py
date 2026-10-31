"""
Resume after Back on every create form — CLIENT_CHANGES.md §0 sixty-fourth
block, Part 4 (31 Oct 2026). `/purchase/create` had it first; these nineteen
gained it in this pass, by the same two pieces (`formdraft.script()` in the
page, `formdraft.is_resume()` in the route).

For each: the page carries the script; a Resume POST REDRAWS (200, the
script again with `RESUMED = true`), saves nothing in any collection, and
spends no number (the settings record — series floors, the challan counter,
the document-number ledger — is byte-identical afterwards).
"""

import copy
import json
import re
from html.parser import HTMLParser

import pytest
from werkzeug.datastructures import MultiDict

import formdraft as FD
from store import STORE
from tests.test_entity_fallbacks import populated  # noqa: F401 — the fixture

MARK = "var KEY = 'draft:' + location.pathname;"

# (label, id key in populated["ids"] or None, url template, a field to post)
FORMS = [
    ("BOQ",               None, "/boq/create", {}),
    ("delivery challan",  "/boq/view/<id>", "/dc/create?boq={id}", {}),
    ("measurement sheet", "/boq/view/<id>", "/measurement/create?boq={id}", {}),
    ("product inquiry",   "/boq/view/<id>", "/po/create?boq={id}", {}),
    ("RA bill",           "/boq/view/<id>", "/ra/create?boq={id}&leg=supply", {}),
    ("RA set",            "/boq/view/<id>", "/raboth/create?boq={id}", {}),
    ("PI from quotation", "/proforma/from/<qid>", "/proforma/from/{id}", {}),
    ("PI from BOQ",       "/proforma/from-boq/<boq_id>", "/proforma/from-boq/{id}", {}),
    ("TI from PI",        "/invoice/from/<pid>", "/invoice/from/{id}", {}),
    ("TI from BOQ",       "/invoice/from-boq/<boq_id>", "/invoice/from-boq/{id}", {}),
    ("PO from BOQ",       "/purchase/from-boq/<boq_id>", "/purchase/from-boq/{id}", {}),
    ("PO from inquiry",   "/purchase/from-draft/<draft_id>", "/purchase/from-draft/{id}", {}),
    ("work order",        None, "/wo/create", {}),
    ("receipt",           "/ra/view/<id>", "/receipt/new?ra={id}", {}),
    ("charge",            None, "/charge/new", {}),
    ("employee",          None, "/employee/new", {}),
    ("address",           None, "/address/add", {}),
    ("specification",     None, "/spec/add", {}),
    ("project",           None, "/projects/create", {}),
]


def _url(populated, key, tmpl):
    if key is None:
        return tmpl
    return tmpl.format(id=populated["ids"][key])


class _Fields(HTMLParser):
    """What `new FormData(form)` would carry: the defaults of every named field."""

    def __init__(self):
        super().__init__()
        self.out, self._sel, self._ta, self._opt_first = [], None, None, None
        self._in_form = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form" and (a.get("method") or "").upper() == "POST" and not self.out:
            self._in_form = True
        if not self._in_form:
            return
        name = a.get("name")
        if tag == "input" and name:
            kind = (a.get("type") or "text").lower()
            if kind in ("checkbox", "radio"):
                if "checked" in a:
                    self.out.append((name, a.get("value") or "on"))
            elif kind not in ("file", "submit", "button"):
                self.out.append((name, a.get("value") or ""))
        elif tag == "select" and name:
            self._sel, self._opt_first = name, None
        elif tag == "option" and self._sel:
            if self._opt_first is None:
                self._opt_first = a.get("value") or ""
            if "selected" in a:
                self.out.append((self._sel, a.get("value") or ""))
                self._sel = None
        elif tag == "textarea" and name:
            self._ta = [name, ""]

    def handle_endtag(self, tag):
        if tag == "select" and self._sel:
            self.out.append((self._sel, self._opt_first or ""))
            self._sel = None
        elif tag == "textarea" and self._ta:
            self.out.append(tuple(self._ta))
            self._ta = None
        elif tag == "form" and self._in_form:
            self._in_form = False

    def handle_data(self, data):
        if self._ta:
            self._ta[1] += data


def _defaults(html):
    p = _Fields()
    p.feed(html)
    return p.out


def _norm(html):
    return re.sub(r"var RESUMED = (true|false);", "", html)


def _snapshot():
    sizes = {k: len(v) for k, v in STORE.items() if isinstance(v, dict)}
    return sizes, json.dumps(STORE.get("settings") or {}, sort_keys=True, default=str)


def test_there_are_nineteen():
    assert len(FORMS) == 19


@pytest.mark.parametrize("label,key,tmpl,extra", FORMS, ids=[f[0] for f in FORMS])
def test_the_form_carries_the_script(client, populated, label, key, tmpl, extra):
    r = client.get(_url(populated, key, tmpl))
    assert r.status_code == 200, label
    html = r.get_data(as_text=True)
    assert MARK in html, label
    assert "var RESUMED = false;" in html, label


@pytest.mark.parametrize("label,key,tmpl,extra", FORMS, ids=[f[0] for f in FORMS])
def test_resume_redraws_and_saves_nothing(client, populated, label, key, tmpl, extra):
    """
    The payload is the form's own defaults — what the browser's FormData
    would save. ⚠ The CONTROL is the same POST without `_resume`: it must
    either save (a redirect) or draw a refusal, so a route whose guard is
    missing renders the control's page for the Resume too and fails here.
    """
    url = _url(populated, key, tmpl)
    fields = _defaults(client.get(url).get_data(as_text=True))
    before = copy.deepcopy(_snapshot())
    r = client.post(url, data=MultiDict(fields + [(FD.RESUME_FIELD, "1")]))
    assert r.status_code == 200, f"{label}: a Resume must redraw, got {r.status_code}"
    html = r.get_data(as_text=True)
    assert "var RESUMED = true;" in html, label
    assert _snapshot() == before, f"{label}: a Resume saved something or spent a number"
    control = client.post(url, data=MultiDict(fields))
    if control.status_code == 200:
        assert _norm(control.get_data(as_text=True)) != _norm(html), (
            f"{label}: the Resume drew exactly what an ordinary POST draws — "
            f"its guard is not being consulted")
