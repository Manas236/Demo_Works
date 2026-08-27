"""
tools/set_password.py — break-glass: set the password on an account that exists.

The recovery path for ABOUT.md §7 gap 21. The failure it answers is specific:
the last Owner forgets their password. `auth._would_strand_install()` guarantees
an **active Owner exists**; it cannot guarantee anybody can **sign in** as one.
There is no e-mail reset (CLIENT_CHANGES-2.md B3 puts it out of scope), no
console and no `flask shell` in this deployment, so before this file the
documented recovery was editing `password_hash` in MySQL by hand — which is not
a recovery path, it is an invitation to write a bad hash into a live install.

    python tools/set_password.py --username manas --password "<a real one>"

**It sets passwords. It does not create users.** A username that does not exist
is refused rather than created: a typo would otherwise mint a second account
silently, and minting accounts is `/setup`'s job and `tools/seed_users.py`'s
job, both of which this deliberately does not duplicate.

**The password policy is imported, not restated.** `_reject_password()` comes
from `tools/seed_users.py`, so the placeholder list and the minimum length are
one rule with one home. A second copy here would drift, and the copy that drifts
low is the one that gets used in an emergency.

**The hashing is imported from `auth`**, which is where `/login` gets it too, so
this cannot mint a hash `check_password_hash()` will not accept. The write is
verified before it is saved: if the new password does not verify against the new
hash, nothing is persisted and the tool exits non-zero.

**It never prints the hash.** It prints the username, the account's state and
what changed — enough to know it worked, nothing that is worth stealing out of a
terminal scrollback.

⚠ It writes to the database the app is actually using, read from the same
  `.env`. Take a backup first — `python tools/backup_db.py --label pre-reset`.
"""

import argparse
import os
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import auth  # noqa: E402
import db as _db  # noqa: E402
from store import STORE  # noqa: E402
from tools.seed_users import _reject_password  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--username", required=True,
                    help="an EXISTING login name. Matched case-insensitively, "
                         "exactly as /login matches it.")
    ap.add_argument("--password", default="",
                    help="or set SAMRUDDHI_NEW_PASSWORD. No default, and "
                         "placeholders are refused.")
    args = ap.parse_args(argv)

    live = _db.init()
    if live:
        loaded = _db.load_into(STORE)
        print(f"  {_db.status()} - {loaded} record(s) loaded")
    else:
        # Same refusal as the seed script, for the same reason: the operator
        # would be told the password was changed and find it unchanged.
        print(f"  ERROR: {_db.status()}")
        print("  Refusing to set a password in memory that will not be saved. "
              "Check .env / MySQL and re-run.")
        return 2

    # Order matters: identify the account first, because `_reject_password()`
    # refuses a password equal to the username and needs the real spelling.
    user = auth.find_user(args.username)
    if user is None:
        print(f"  ERROR: no user {args.username!r} in "
              f"{_db.CONFIG['name']}@{_db.CONFIG['host']}.")
        known = sorted(u.get("username") or "" for u in auth.users().values())
        print(f"  known accounts: {', '.join(known) if known else '(none - run /setup or tools/seed_users.py)'}")
        print("  This tool sets passwords; it does not create users.")
        return 2

    password = args.password or os.getenv("SAMRUDDHI_NEW_PASSWORD", "")
    if not (password or "").strip():
        # The one case answered here rather than by the imported policy: its
        # wording names SAMRUDDHI_SEED_PASSWORD, which is the seed script's
        # variable and not this one. Sending an operator to the wrong
        # environment variable mid-lockout is exactly the wrong moment for it.
        print("  ERROR: No password supplied. Pass --password or set "
              "SAMRUDDHI_NEW_PASSWORD. There is deliberately no default.")
        return 2
    refusal = _reject_password(password, user["username"])
    if refusal:
        print(f"  ERROR: {refusal}")
        return 2

    new_hash = auth.generate_password_hash(password)
    # Verified before it is written, with the same function `/login` calls.
    # A hash this cannot read back is a hash that locks the account harder than
    # the forgotten password did.
    if not auth.check_password_hash(new_hash, password):
        print("  ERROR: the new hash does not verify. Nothing was changed.")
        return 3

    user["password_hash"] = new_hash
    _db.sync(STORE)

    print(f"  password set for {user['username']} (id {user['id']})")
    print(f"    display name : {user['display_name']}")
    print(f"    roles        : {auth._role_names(user)}")
    print(f"    active       : {user['active']}")
    print(f"    Owner tier   : {auth.is_owner(user)}")
    print(f"    database     : {_db.CONFIG['name']}@{_db.CONFIG['host']}:{_db.CONFIG['port']}")
    if not user.get("active"):
        # Setting a password on a deactivated account is legitimate — it is half
        # of reinstating somebody — but on its own it does not produce a login,
        # and finding that out at the sign-in page wastes the emergency.
        print("    !! This account is DEACTIVATED and still cannot sign in. "
              "An Owner must reactivate it at /users.")
    print("  The hash is not printed. Change this password at /account once you are in.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
