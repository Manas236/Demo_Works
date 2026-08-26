"""
tools/seed_users.py — create the builtin roles and the first administrator.

The scriptable half of the bootstrap; `GET /setup` is the same job in a
browser. Both exist because a seed script can be run on a fresh install by
somebody who has not started the app yet, and a setup page can be used by
somebody who will never open a terminal.

    python tools/seed_users.py --password "<a real one>"
    python tools/seed_users.py --username yogesh --roles director

The password comes from `--password` or `SAMRUDDHI_SEED_PASSWORD`. **There is
no default and there never will be** — a seeded default password is a published
one, and this account holds `admin.roles`, which is the right to grant itself
anything. `_reject_password()` refuses the obvious placeholders for the same
reason.

**Idempotent.** Roles are seeded by fixed slug and an existing one is left
alone; a username that already exists is reported and not touched. Running it
twice changes nothing, which is what makes it safe to put in a deploy step.

⚠ It writes to the database the app is actually using, read from the same
  `.env`. Take a backup first — `python tools/backup_db.py --label pre-seed`.
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

# Refused outright, however long. Every one of these has been somebody's
# production administrator password.
PLACEHOLDERS = {
    "password", "password1", "passw0rd", "admin", "admin123", "administrator",
    "changeme", "change-me", "changeit", "secret", "letmein", "welcome",
    "qwerty", "12345678", "123456789", "1234567890", "test", "testing",
    "demo", "default", "samruddhi", "samruddhifire", "fire123", "seed",
    "qms-demo-secret-2024",
}

MIN_LENGTH = 8


def _reject_password(password: str, username: str) -> str:
    """"" when the password may be used, else the reason it may not."""
    if not (password or "").strip():
        return ("No password supplied. Pass --password or set "
                "SAMRUDDHI_SEED_PASSWORD. There is deliberately no default.")
    if password != password.strip():
        return "The password has leading or trailing whitespace; that is almost always a paste error."
    if len(password) < MIN_LENGTH:
        return f"The password must be at least {MIN_LENGTH} characters."
    if password.lower() in PLACEHOLDERS:
        return (f"{password!r} is a placeholder password and is refused. This "
                f"account can grant itself every permission in the system.")
    if password.lower() == (username or "").lower():
        return "The password must not be the username."
    return ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--username", default="owner",
                    help="login name for the first administrator (default: owner)")
    ap.add_argument("--display-name", default="",
                    help="full name shown in the app (default: the username)")
    ap.add_argument("--password", default="",
                    help="or set SAMRUDDHI_SEED_PASSWORD. No default.")
    ap.add_argument("--roles", default="owner,director",
                    help="comma-separated builtin role slugs (default: owner,director). "
                         "An Owner is required to edit role definitions at all.")
    ap.add_argument("--roles-only", action="store_true",
                    help="seed the builtin roles and create no user")
    args = ap.parse_args(argv)

    live = _db.init()
    if live:
        loaded = _db.load_into(STORE)
        print(f"  {_db.status()} - {loaded} record(s) loaded")
    else:
        # Refuse rather than seed into a dict that dies with the process: the
        # operator would be told the account exists and find it gone.
        print(f"  ERROR: {_db.status()}")
        print("  Refusing to seed into memory that will not be saved. "
              "Check .env / MySQL and re-run.")
        return 2

    made = auth.ensure_builtin_roles()
    print(f"  roles: {made} created, {len(auth.roles())} total")
    for role in sorted(auth.roles().values(), key=lambda r: r["name"]):
        owner = "  [Owner tier]" if auth.OWNER_PERM in role["permissions"] else ""
        print(f"    {role['id']:<22} {role['name']:<18} "
              f"{len(role['permissions']):>3} permissions{owner}")

    if args.roles_only:
        _db.sync(STORE)
        print("  --roles-only: no user created.")
        return 0

    existing = auth.find_user(args.username)
    if existing is not None:
        # Idempotent, and deliberately not an update: silently resetting the
        # administrator's password on a re-run is how a deploy step locks
        # somebody out of their own install.
        print(f"  user {args.username!r} already exists (id {existing['id']}) - "
              f"left untouched.")
        _db.sync(STORE)
        return 0

    password = args.password or os.getenv("SAMRUDDHI_SEED_PASSWORD", "")
    refusal = _reject_password(password, args.username)
    if refusal:
        print(f"  ERROR: {refusal}")
        return 2

    slugs = [s.strip() for s in args.roles.split(",") if s.strip()]
    unknown = [s for s in slugs if f"role-{s}" not in auth.roles()]
    if unknown:
        print(f"  ERROR: unknown role slug(s): {', '.join(unknown)}")
        print(f"  known: {', '.join(sorted(auth.BUILTIN_ROLES))}")
        return 2

    user = auth.create_user(
        args.username, args.display_name, password,
        [f"role-{s}" for s in slugs], created_by="tools/seed_users.py")

    _db.sync(STORE)
    print(f"  user created: {user['username']} (id {user['id']})")
    print(f"    display name : {user['display_name']}")
    print(f"    roles        : {', '.join(auth.roles()[r]['name'] for r in user['role_ids'])}")
    print(f"    permissions  : {len(auth.permissions_of(user))}")
    print(f"    Owner tier   : {auth.is_owner(user)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
