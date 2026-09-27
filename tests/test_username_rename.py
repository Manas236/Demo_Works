"""
Owner-only username rename, with an audit trail (27 September 2026).

On 26 September 2026 every production login was renamed from a personal name
to a role address - `accounts@`, `hr@`, `sales@`, `purchase@` - with a one-off
script on the server, because the application could not do it. This is that job
put in the UI.

The rules under test:

* the field is on `/users/edit/<id>` and is **Owner only** - a Director is not
  offered it and a Director's forged POST carrying one is refused, not merely
  ignored;
* an Owner may rename anybody **including themselves**, and stays signed in;
* a new username is a company address, lower case, unique case-insensitively
  across **all** users, deactivated ones included;
* a name that appears in anybody **else's** history cannot be taken, because
  documents and logs carry old usernames as plain strings and handing one on
  would silently re-attribute them - but a user may take back their own;
* the rename moves the **username and nothing else**: id, password hash, roles
  and photo are untouched, and login stays case-insensitive;
* every live username lookup keeps resolving, and every historical snapshot of
  a username is left exactly as it was.

Every refusal is paired with a control on the same route that must succeed.
"""

import pytest

import auth  # noqa: E402
from store import STORE  # noqa: E402

DOMAIN = auth.COMPANY_DOMAIN
PASSWORD = "rename-test-password"


# -- People ------------------------------------------------------------------

def _user(name, role_ids, display=None):
    existing = auth.find_user(name)
    if existing:
        del STORE["users"][existing["id"]]
    return auth.create_user(name, display or name.title(), PASSWORD, role_ids,
                            created_by="rename-test")


def _as(client, user):
    with client.session_transaction() as s:
        s[auth.SESSION_KEY] = user["id"]


def _drop(*users):
    for u in users:
        STORE["users"].pop(u["id"], None)


@pytest.fixture()
def owner(client):
    auth.ensure_builtin_roles()
    o = _user("rn-owner", ["role-owner"], "Rename Owner")
    _as(client, o)
    yield o
    _drop(o)


@pytest.fixture()
def director(client):
    auth.ensure_builtin_roles()
    d = _user("rn-director", ["role-director"], "Rename Director")
    assert not auth.is_owner(d) and auth.ADMIN_PERM in auth.permissions_of(d)
    yield d
    _drop(d)


@pytest.fixture()
def staff(client):
    auth.ensure_builtin_roles()
    s = _user("rn-staff", ["role-accountant"], "Priya Shah")
    yield s
    _drop(s)


def _save(client, user, **over):
    """The ordinary /users/edit save, with every field the form really posts."""
    form = {"username": user.get("username"),
            "display_name": user.get("display_name"),
            "role_ids": list(user.get("role_ids") or [])}
    form.update(over)
    return client.post(f"/users/edit/{user['id']}", data=form)


# == 1. The happy path =======================================================

def test_an_owner_renames_another_user(client, owner, staff):
    r = _save(client, staff, username=f"accounts{DOMAIN}")
    assert r.status_code in (302, 303), r.data[:400]
    assert staff["username"] == f"accounts{DOMAIN}"


def test_the_rename_is_stamped_with_who_did_it_and_when(client, owner, staff):
    _save(client, staff, username=f"accounts{DOMAIN}")
    trail = staff[auth.USERNAME_HISTORY]
    assert len(trail) == 1
    entry = trail[0]
    assert entry["from"] == "rn-staff"
    assert entry["to"] == f"accounts{DOMAIN}"
    assert entry["by"] == owner["id"]
    assert entry["by_username"] == "rn-owner"
    # `_now()` is auth.py's one clock, so the stamp is exactly the shape
    # `created_at` on this same record carries - IST on the production box,
    # which is what the whole application already records.
    assert entry["at"] == auth._now()
    assert len(entry["at"]) == len(staff["created_at"]) == len("2026-09-27 13:40")


def test_the_trail_is_append_only_across_several_renames(client, owner, staff):
    _save(client, staff, username=f"accounts{DOMAIN}")
    _save(client, staff, username=f"hr{DOMAIN}")
    trail = staff[auth.USERNAME_HISTORY]
    assert [(e["from"], e["to"]) for e in trail] == [
        ("rn-staff", f"accounts{DOMAIN}"),
        (f"accounts{DOMAIN}", f"hr{DOMAIN}")]


def test_an_owner_renames_themselves_and_stays_signed_in(client, owner):
    r = _save(client, owner, username=f"owner{DOMAIN}")
    assert r.status_code in (302, 303), r.data[:400]
    assert owner["username"] == f"owner{DOMAIN}"
    # The session holds a uid, so the request after a self-rename is the same
    # person. This is the assertion the whole design rests on.
    page = client.get("/account")
    assert page.status_code == 200
    assert f"owner{DOMAIN}".encode() in page.data


def test_a_self_rename_is_recorded_under_the_name_it_was_done_with(client, owner):
    _save(client, owner, username=f"owner{DOMAIN}")
    entry = owner[auth.USERNAME_HISTORY][0]
    assert entry["by"] == owner["id"]
    assert entry["by_username"] == "rn-owner", (
        "the actor was stamped with the name they had AFTER renaming themselves")


def test_somebody_else_signed_in_under_the_old_name_carries_on(client, owner, staff):
    """
    The session is keyed by id, so this user never notices. If it were keyed by
    username they would land on /login at best and resolve to nobody at worst.
    """
    import app as app_module

    # Not a `with` block: the `client` fixture already holds one open, and
    # Flask's test client preserves the request context inside one - nesting
    # two pops the wrong context and fails on that rather than on the rename.
    theirs = app_module.app.test_client()
    _as(theirs, staff)
    assert theirs.get("/account").status_code == 200

    _save(client, staff, username=f"accounts{DOMAIN}")

    after = theirs.get("/account")
    assert after.status_code == 200, "a live session broke on a rename"
    assert f"accounts{DOMAIN}".encode() in after.data
    assert b"rn-staff" not in after.data


# == 2. The Owner gate =======================================================

def test_the_owner_is_offered_the_field(client, owner, staff):
    page = client.get(f"/users/edit/{staff['id']}").data
    assert b'name="username"' in page
    assert b"rn-staff" in page


def test_a_director_is_not_offered_the_field(client, director, staff):
    _as(client, director)
    page = client.get(f"/users/edit/{staff['id']}")
    assert page.status_code == 200, "control: the Director must reach the page"
    assert b'name="username"' not in page.data


def test_a_director_posting_a_username_is_refused(client, director, staff):
    _as(client, director)
    r = _save(client, staff, username=f"accounts{DOMAIN}")
    assert b"Only an Owner can change a username" in r.data
    assert staff["username"] == "rn-staff"
    assert auth.USERNAME_HISTORY not in staff


def test_a_directors_ordinary_save_still_works(client, director, staff):
    """The control. The gate must catch the forged field, not the whole form."""
    _as(client, director)
    r = client.post(f"/users/edit/{staff['id']}",
                    data={"display_name": "Renamed", "role_ids": ["role-hr"]})
    assert r.status_code in (302, 303)
    assert staff["display_name"] == "Renamed" and staff["role_ids"] == ["role-hr"]
    assert staff["username"] == "rn-staff"


def test_a_director_is_not_shown_the_previous_logins(client, owner, director, staff):
    _save(client, staff, username=f"accounts{DOMAIN}")
    _as(client, director)
    page = client.get(f"/users/edit/{staff['id']}").data
    assert b"Previous logins" not in page


def test_the_owner_is_shown_the_previous_logins(client, owner, staff):
    page = client.get(f"/users/edit/{staff['id']}").data
    assert b"Previous logins" not in page, "control: nothing to show yet"
    _save(client, staff, username=f"accounts{DOMAIN}")
    page = client.get(f"/users/edit/{staff['id']}").data
    assert b"Previous logins" in page
    assert b"rn-staff" in page and f"accounts{DOMAIN}".encode() in page
    assert b"Rename Owner" in page


def test_the_previous_logins_list_follows_a_later_rename_of_the_actor(
        client, owner, staff):
    """
    Who did it is resolved from the stored id at RENDER time -
    `address.editor_label()`'s rule. A name resolved at write time restates
    itself the next time that person is renamed.
    """
    _save(client, staff, username=f"accounts{DOMAIN}")
    owner["display_name"] = "Renamed Owner"
    page = client.get(f"/users/edit/{staff['id']}").data
    assert b"Renamed Owner" in page


# == 3. Format ===============================================================

@pytest.mark.parametrize("bad", [
    "accounts@gmail.com",
    "accounts@samruddhifire.in",
    "accounts@samruddhifirepvtltd.com",
    "accounts",
    DOMAIN,
    f"acc ounts{DOMAIN}",
    f"acc+ounts{DOMAIN}",
    f"acc/ounts{DOMAIN}",
    f"acc$ounts{DOMAIN}",
    f"accounts{DOMAIN}.evil.com",
])
def test_a_username_outside_the_company_domain_is_refused(client, owner, staff, bad):
    r = _save(client, staff, username=bad)
    assert r.status_code == 200, "it saved"
    assert staff["username"] == "rn-staff"
    assert auth.USERNAME_HISTORY not in staff


@pytest.mark.parametrize("good", [
    f"accounts{DOMAIN}", f"hr{DOMAIN}", f"sales{DOMAIN}", f"purchase{DOMAIN}",
    f"a.b{DOMAIN}", f"a-b{DOMAIN}", f"a_b{DOMAIN}", f"site01{DOMAIN}",
])
def test_a_company_address_is_accepted(client, owner, staff, good):
    """The control, and the reason the refusals above are not a tautology."""
    r = _save(client, staff, username=good)
    assert r.status_code in (302, 303), r.data[:400]
    assert staff["username"] == good


def test_the_stored_username_is_lowercased_and_stripped(client, owner, staff):
    _save(client, staff, username=f"  ACCOUNTS{DOMAIN.upper()}  ")
    assert staff["username"] == f"accounts{DOMAIN}"
    assert staff[auth.USERNAME_HISTORY][0]["to"] == f"accounts{DOMAIN}"


def test_a_blank_username_is_refused(client, owner, staff):
    """The box is pre-filled, so blank is an emptied field and not "leave it"."""
    r = _save(client, staff, username="   ")
    assert b"A username is required." in r.data
    assert staff["username"] == "rn-staff"


# == 4. Uniqueness ===========================================================

def test_a_case_insensitive_duplicate_is_refused(client, owner, staff):
    other = _user(f"accounts{DOMAIN}", ["role-hr"], "Accounts Desk")
    try:
        r = _save(client, staff, username=f"ACCOUNTS{DOMAIN}")
        assert b"already the login of" in r.data
        assert b"Accounts Desk" in r.data
        assert staff["username"] == "rn-staff"
    finally:
        _drop(other)


def test_a_deactivated_users_login_is_still_taken(client, owner, staff):
    """
    Users are deactivated, never deleted, and can be reactivated. Handing their
    login on would give somebody else their history the moment they came back.
    """
    other = _user(f"hr{DOMAIN}", ["role-hr"], "Gone Away")
    other["active"] = False
    try:
        r = _save(client, staff, username=f"hr{DOMAIN}")
        assert b"already the login of" in r.data
        assert b"a deactivated account" in r.data
        assert staff["username"] == "rn-staff"
    finally:
        _drop(other)


def test_the_unchanged_value_is_a_silent_no_op(client, owner, staff):
    r = _save(client, staff, username="rn-staff")
    assert r.status_code in (302, 303), r.data[:400]
    assert staff["username"] == "rn-staff"
    assert auth.USERNAME_HISTORY not in staff, "an unchanged value wrote history"


def test_resubmitting_the_new_value_writes_no_second_entry(client, owner, staff):
    _save(client, staff, username=f"accounts{DOMAIN}")
    _save(client, staff, username=f"ACCOUNTS{DOMAIN}")
    assert len(staff[auth.USERNAME_HISTORY]) == 1


# == 5. The history reservation ==============================================

def test_a_name_from_somebody_elses_history_is_refused(client, owner, staff):
    other = _user("rn-other", ["role-hr"], "Vikram Rao")
    try:
        _save(client, other, username=f"sales{DOMAIN}")
        _save(client, other, username=f"purchase{DOMAIN}")
        # `sales@` is free - nobody holds it - and it must still be refused.
        assert auth.find_user(f"sales{DOMAIN}") is None
        r = _save(client, staff, username=f"sales{DOMAIN}")
        assert b"was previously used by" in r.data
        assert b"Vikram Rao" in r.data
        assert staff["username"] == "rn-staff"
    finally:
        _drop(other)


def test_the_far_end_of_an_entry_is_reserved_too(client, owner, staff):
    other = _user("rn-other", ["role-hr"], "Vikram Rao")
    try:
        _save(client, other, username=f"sales{DOMAIN}")
        # `sales@` is this person's CURRENT name, so uniqueness catches it; the
        # `to` end of the entry is what catches it once they move on again.
        _save(client, other, username=f"purchase{DOMAIN}")
        trail = other[auth.USERNAME_HISTORY]
        assert trail[0]["to"] == f"sales{DOMAIN}"
        assert auth.username_history_holder(f"sales{DOMAIN}") is other
    finally:
        _drop(other)


def test_a_user_may_take_back_their_own_old_name(client, owner, staff):
    _save(client, staff, username=f"accounts{DOMAIN}")
    r = _save(client, staff, username=f"hr{DOMAIN}")
    assert r.status_code in (302, 303)
    r = _save(client, staff, username=f"accounts{DOMAIN}")
    assert r.status_code in (302, 303), r.data[:400]
    assert staff["username"] == f"accounts{DOMAIN}"
    assert len(staff[auth.USERNAME_HISTORY]) == 3


def test_a_new_account_cannot_be_minted_on_a_reserved_name(client, owner, staff):
    """
    The reservation binds `/users/create` as hard as it binds the rename. Left
    off here it would be bypassable in one click: refuse the rename, then mint
    the name from scratch and re-attribute the same records.
    """
    _save(client, staff, username=f"accounts{DOMAIN}")
    with pytest.raises(ValueError) as exc:
        auth.create_user(f"rn-staff", "Impostor", PASSWORD, ["role-hr"])
    assert "previously used by" in str(exc.value)


def test_the_format_rule_does_NOT_bind_a_new_account(client, owner):
    """
    Deliberate, and the reason it is written down: `/setup`, the two CLI tools
    and every grandfathered login mint names that are not company addresses.
    The rule binds what a name may be renamed TO.
    """
    fresh = auth.create_user("rn-plain-name", "Plain", PASSWORD, ["role-hr"])
    try:
        assert fresh["username"] == "rn-plain-name"
    finally:
        _drop(fresh)


# == 6. Nothing but the username moves =======================================

def test_the_password_and_roles_are_unchanged_by_a_rename(client, owner, staff):
    before = (staff["id"], staff["password_hash"], list(staff["role_ids"]),
              staff["active"], staff["created_at"], staff["created_by"])
    _save(client, staff, username=f"accounts{DOMAIN}")
    assert (staff["id"], staff["password_hash"], list(staff["role_ids"]),
            staff["active"], staff["created_at"], staff["created_by"]) == before


def test_a_photo_survives_a_rename(client, owner, staff):
    import photo

    staff["photo"] = photo.PREFIX + "QUJD"
    _save(client, staff, username=f"accounts{DOMAIN}")
    assert staff["photo"] == photo.PREFIX + "QUJD"


def test_a_refused_rename_leaves_the_rest_of_the_save_unapplied(client, owner, staff):
    """
    Validated with the other guards and applied with the other writes. Half a
    save is worse than none, and the half that moves is what somebody signs in
    with.
    """
    before = (staff["display_name"], list(staff["role_ids"]))
    r = _save(client, staff, username="nope@example.com",
              display_name="Should Not Land", role_ids=["role-hr"])
    assert r.status_code == 200
    assert staff["username"] == "rn-staff"
    assert (staff["display_name"], list(staff["role_ids"])) == before


def test_a_rename_refused_by_another_guard_does_not_land(client, owner):
    """
    The other direction: the rename is valid, the role change is not. The last
    active Owner cannot be edited out of the tier, and the username must not
    move on a save that was refused.
    """
    for other in list(STORE["users"].values()):
        if other["id"] != owner["id"] and auth.is_owner(other):
            other["active"] = False
    r = _save(client, owner, username=f"owner{DOMAIN}", role_ids=["role-hr"])
    assert r.status_code == 200, r.data[:200]
    assert owner["username"] == "rn-owner"
    assert auth.USERNAME_HISTORY not in owner


# == 7. Logging in ===========================================================

def test_login_works_under_the_new_name_and_fails_under_the_old(anon_client):
    auth.ensure_builtin_roles()
    o = _user("rn-owner", ["role-owner"], "Rename Owner")
    s = _user("rn-staff", ["role-accountant"], "Priya Shah")
    try:
        assert auth.rename_user(s, f"accounts{DOMAIN}", o) == ""

        r = anon_client.post("/login", data={"username": "rn-staff",
                                             "password": PASSWORD})
        assert b"do not match" in r.data, "the old name still signs in"

        r = anon_client.post("/login", data={"username": f"accounts{DOMAIN}",
                                             "password": PASSWORD},
                             follow_redirects=False)
        assert r.status_code in (302, 303), r.data[:400]

        # Case-insensitive, exactly as before the rename.
        anon_client.get("/logout")
        r = anon_client.post("/login", data={"username": f"ACCOUNTS{DOMAIN}",
                                             "password": PASSWORD})
        assert r.status_code in (302, 303)
    finally:
        _drop(o, s)


def test_a_grandfathered_username_still_signs_in_untouched(anon_client):
    """`manas` and `recovery` are not addresses and are never asked to be."""
    auth.ensure_builtin_roles()
    m = _user("manas", ["role-owner"], "Manas Gawde")
    try:
        assert auth.username_format_error("manas") != "", (
            "control: `manas` would be refused as a NEW name")
        r = anon_client.post("/login", data={"username": "manas",
                                             "password": PASSWORD})
        assert r.status_code in (302, 303), r.data[:400]
        assert m["username"] == "manas"
        assert auth.USERNAME_HISTORY not in m
    finally:
        _drop(m)


# == 8. Every live lookup, and every historical snapshot =====================

def test_every_live_username_lookup_resolves_under_the_new_name(client, owner, staff):
    """
    The four places a username is LOOKED UP, all of which scan the live
    collection: `/login` and `create_user()`'s duplicate check through
    `find_user()`, and `tools/seed_users.py` and `tools/set_password.py`
    through the same function.
    """
    _save(client, staff, username=f"accounts{DOMAIN}")

    assert auth.find_user(f"accounts{DOMAIN}") is staff
    assert auth.find_user(f"ACCOUNTS{DOMAIN}") is staff
    assert auth.find_user("rn-staff") is None

    # `create_user()`'s duplicate check now refuses the NEW name.
    with pytest.raises(ValueError) as exc:
        auth.create_user(f"accounts{DOMAIN}", "Impostor", PASSWORD, [])
    assert "already taken" in str(exc.value)

    # The two CLI tools resolve through the same function and nothing else, so
    # they follow the rename without being touched. Read as source rather than
    # imported: both parse argv at import-adjacent module scope.
    import pathlib
    root = pathlib.Path(auth.__file__).resolve().parent
    for name in ("seed_users.py", "set_password.py"):
        src = (root / "tools" / name).read_text(encoding="utf-8")
        assert "auth.find_user(" in src, f"{name} looks a user up some other way"
        assert 'STORE["users"]' not in src, f"{name} reaches past find_user()"


def test_the_session_holds_an_id_and_not_a_username():
    """
    The fact the whole design rests on, pinned. If this ever became a username
    a rename would sign somebody out - or, worse, sign in whoever took the name
    next.
    """
    assert auth.SESSION_KEY == "uid"
    src = open(auth.__file__, encoding="utf-8").read()
    assert 'session[SESSION_KEY] = user["id"]' in src


def test_historical_snapshots_of_a_username_are_not_rewritten(client, owner, staff):
    """
    A snapshot records who acted at the time and is deliberately left alone:
    `purchase.reprice_log[].by`, `approval.approvals[].user_name` and
    `rejected_by_name`. Rewriting them would be a lie about the past; the
    reservation in `username_history_holder()` is what stops the same string
    coming to mean somebody else.
    """
    po = {"id": "rn-po", "reprice_log": [{"at": "2026-09-01 10:00",
                                          "by": "Priya Shah", "lines": []}]}
    STORE.setdefault("purchases", {})["rn-po"] = po
    rec = {"approvals": [{"role": "accounts", "user_id": staff["id"],
                          "user_name": "Priya Shah", "at": "2026-09-01 10:00"}],
           "rejected_by": staff["id"], "rejected_by_name": "Priya Shah"}
    try:
        _save(client, staff, username=f"accounts{DOMAIN}")
        assert po["reprice_log"][0]["by"] == "Priya Shah"
        assert rec["approvals"][0]["user_name"] == "Priya Shah"
        assert rec["rejected_by_name"] == "Priya Shah"
        # And the uid beside each one still resolves, to the new name.
        assert auth.users()[rec["approvals"][0]["user_id"]]["username"] == \
            f"accounts{DOMAIN}"
    finally:
        STORE["purchases"].pop("rn-po", None)


def test_the_address_edit_log_follows_the_rename(client, owner, staff):
    """
    `address.editor_label()` stores a uid and resolves at render time, so it
    follows a rename by construction. This is the (2) case of the sweep:
    a live lookup that has to keep resolving.
    """
    import address as AD

    staff["display_name"] = ""
    _save(client, staff, username=f"accounts{DOMAIN}", display_name="")
    assert AD.editor_label(staff["id"]) == f"accounts{DOMAIN}"


def test_the_refusal_log_is_a_snapshot_and_not_a_lookup(client, owner, staff):
    """
    `REFUSAL_LOG` stores the username as text. It is an in-memory diagnostic
    that says so on its own page (ABOUT.md section 7 gap 23), so it is group
    (1) - and the rename writes nothing into it, because inventing a second log
    system was the one thing this was not to do.
    """
    auth.REFUSAL_LOG.clear()
    _save(client, staff, username=f"accounts{DOMAIN}")
    assert len(auth.REFUSAL_LOG) == 0


# == 9. Nothing was added to the gate ========================================

def test_no_endpoint_and_no_permission_was_added(client):
    """
    The rename is a field on a form that already exists. A new endpoint would
    have to be classified in `ROUTE_PERMISSIONS` and would move
    `docs/ACCESS_MATRIX.md`; a new permission would move every role's row.
    """
    import app as app_module

    endpoints = {r.endpoint for r in app_module.app.url_map.iter_rules()}
    assert not [e for e in endpoints if "rename" in e.lower()]
    assert not [p for p in auth.PERMISSIONS if "rename" in p.lower()]
    assert auth.ROUTE_PERMISSIONS["auth.edit_user"] == auth.ADMIN_PERM


def test_the_username_is_escaped_where_it_reaches_the_page(client, owner, staff):
    staff["username"] = '<script>alert(1)</script>'
    page = client.get(f"/users/edit/{staff['id']}").data.decode()
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page
