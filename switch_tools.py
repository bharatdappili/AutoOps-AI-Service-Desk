#!/usr/bin/env python3
"""External integration helpers for the AutoOps Switch agents.

Reads connection settings from .env.switch next to this file.

Usage:
    python3 switch_tools.py sql "SELECT * FROM users LIMIT 5;"
    python3 switch_tools.py jenkins-test
    python3 switch_tools.py jenkins-user-exists <username>
    python3 switch_tools.py jenkins-create-user <username> <email> [full_name]
    python3 switch_tools.py approver-check "<authenticated sender name>"

Every command prints JSON on one line and exits non-zero on failure.
"""

import base64
import json
import os
import secrets
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(HERE, ".env.switch")
APPROVERS_FILE = os.path.join(HERE, "approvers.json")


def load_env() -> dict:
    values = {}
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE) as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip()
    return values


ENV = load_env()

PG = {
    "host": ENV.get("PG_HOST", "localhost"),
    "port": int(ENV.get("PG_PORT", "5432")),
    "user": ENV.get("PG_USER", "omniroute"),
    "password": ENV.get("PG_PASSWORD", ""),
    "dbname": ENV.get("PG_DB", "omniroute"),
}

JENKINS = {
    "base_url": ENV.get("JENKINS_URL", "http://localhost:8080/jenkins").rstrip("/"),
    "username": ENV.get("JENKINS_USER", "admin"),
    "password": ENV.get("JENKINS_PASSWORD", ""),
}

SECRET_DIR = os.path.expanduser("~/.omniroute/secrets")


def out(payload) -> None:
    print(json.dumps(payload, default=str))


def _load_approvers() -> dict:
    if not os.path.exists(APPROVERS_FILE):
        return {}
    try:
        with open(APPROVERS_FILE) as handle:
            data = json.load(handle)
    except Exception:  # noqa: BLE001
        return {}
    approvers = data.get("approvers", {})
    return approvers if isinstance(approvers, dict) else {}


def cmd_approver_check(sender: str) -> int:
    """Resolve an authenticated sender name to an authorized approver.

    The sender name must come from the messaging platform's own metadata for
    the message (the name Switch reports as the sender), never from text the
    sender typed. An unmapped name is not authorized.
    """
    sender = sender.strip().strip("@")
    if not sender:
        out({"authorized": False, "reason": "empty sender name"})
        return 1

    approvers = _load_approvers()
    entry = approvers.get(sender)
    if not isinstance(entry, dict) or not entry.get("db_username"):
        out(
            {
                "authorized": False,
                "sender": sender,
                "reason": "sender is not mapped to a Postgres approver in approvers.json",
            }
        )
        return 1

    db_username = entry["db_username"]
    try:
        import psycopg2
        import psycopg2.extras

        conn = psycopg2.connect(**PG)
        conn.autocommit = True
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, username, name, email, role, status FROM users WHERE username = %s",
                (db_username,),
            )
            row = cur.fetchone()
        conn.close()
    except Exception as exc:  # noqa: BLE001
        out({"authorized": False, "sender": sender, "reason": f"lookup failed: {exc}"})
        return 1

    if not row:
        out(
            {
                "authorized": False,
                "sender": sender,
                "reason": f"mapped Postgres user '{db_username}' does not exist",
            }
        )
        return 1
    if row["role"] not in ("manager", "admin"):
        out(
            {
                "authorized": False,
                "sender": sender,
                "db_username": row["username"],
                "reason": f"role '{row['role']}' may not approve",
            }
        )
        return 1
    if row["status"] != "active":
        out(
            {
                "authorized": False,
                "sender": sender,
                "db_username": row["username"],
                "reason": f"account status '{row['status']}'",
            }
        )
        return 1

    out(
        {
            "authorized": True,
            "sender": sender,
            "db_username": row["username"],
            "db_user_id": row["id"],
            "role": row["role"],
            "name": row["name"],
        }
    )
    return 0


def cmd_sql(query: str) -> int:
    import psycopg2
    import psycopg2.extras

    if not query.strip():
        out({"ok": False, "error": "empty query"})
        return 2
    try:
        conn = psycopg2.connect(**PG)
        conn.autocommit = True
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query)
            if cur.description:
                rows = [dict(row) for row in cur.fetchall()]
                out({"ok": True, "rows": rows, "count": len(rows)})
            else:
                out({"ok": True, "rowcount": cur.rowcount})
        conn.close()
        return 0
    except Exception as exc:  # noqa: BLE001
        out({"ok": False, "error": str(exc)})
        return 1


def _jenkins_session():
    import requests

    session = requests.Session()
    session.auth = (JENKINS["username"], JENKINS["password"])
    session.headers.update({"Content-Type": "application/json"})
    return session


def _jenkins_crumb(session) -> dict:
    """Fetch a CSRF crumb header, if this Jenkins requires one."""
    try:
        response = session.get(
            f"{JENKINS['base_url']}/crumbIssuer/api/json", timeout=10
        )
        if response.status_code == 404:
            return {}
        response.raise_for_status()
        data = response.json()
        field = data.get("crumbRequestField")
        crumb = data.get("crumb")
        if field and crumb:
            return {field: crumb}
    except Exception:  # noqa: BLE001
        return {}
    return {}


def _write_private_secret(username: str, value: str) -> str:
    os.makedirs(SECRET_DIR, mode=0o700, exist_ok=True)
    os.chmod(SECRET_DIR, 0o700)
    path = os.path.join(SECRET_DIR, f"{username}-jenkins-one-time-password.txt")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(value + "\n")
    finally:
        os.chmod(path, 0o600)
    return path


def _read_private_secret(path: str) -> str:
    with open(path) as handle:
        return handle.read().strip()


def _jenkins_script_headers(session) -> dict:
    return {
        "Content-Type": "application/x-www-form-urlencoded",
        **_jenkins_crumb(session),
    }


def cmd_jenkins_create_realm_user(
    username: str, email: str, full_name: str = ""
) -> int:
    full_name = full_name or username
    password = secrets.token_urlsafe(32)
    password_b64 = base64.b64encode(password.encode("utf-8")).decode("ascii")
    script = f"""
import hudson.model.User
import hudson.security.HudsonPrivateSecurityRealm
import jenkins.model.Jenkins
import hudson.tasks.Mailer

def realm = Jenkins.get().getSecurityRealm()
if (!(realm instanceof HudsonPrivateSecurityRealm)) {{
    error("active security realm is not HudsonPrivateSecurityRealm: " + realm.getClass().getName())
}}

def username = {json.dumps(username)}
def fullName = {json.dumps(full_name)}
def email = {json.dumps(email)}

def existing = User.getById(username, false)
if (existing != null) {{
    if (existing.getProperty(HudsonPrivateSecurityRealm.Details.class) != null) {{
        println("already-realm: " + username)
        return
    }}
    existing.delete()
}}

def password = new String({json.dumps(password_b64)}.decodeBase64(), "UTF-8")
def created = realm.createAccount(username, password)
created.setFullName(fullName)
created.addProperty(new Mailer.UserProperty(email))
created.save()
def details = created.getProperty(HudsonPrivateSecurityRealm.Details.class)
println("created-realm: " + username + " details=" + (details != null))
"""
    try:
        session = _jenkins_session()
        response = session.post(
            f"{JENKINS['base_url']}/scriptText",
            data={"script": script},
            headers=_jenkins_script_headers(session),
            timeout=30,
        )
        response.raise_for_status()
        result = response.text.strip()
        payload = {
            "ok": True,
            "username": username,
            "realm": "HudsonPrivateSecurityRealm",
            "response": result,
            "password_generated": True,
            "password_printed": False,
        }
        if result.startswith("created-realm:"):
            payload["credential_file"] = _write_private_secret(username, password)
            payload["credential_file_mode"] = "0600"
        out(payload)
        return 0
    except Exception as exc:  # noqa: BLE001
        out({"ok": False, "error": str(exc)})
        return 1


def cmd_jenkins_user_details(username: str) -> int:
    try:
        session = _jenkins_session()
        response = session.get(
            f"{JENKINS['base_url']}/user/{username}/api/json", timeout=10
        )
        if response.status_code == 404:
            out({"ok": True, "exists": False, "username": username})
            return 0
        response.raise_for_status()
        data = response.json()
        properties = [
            item.get("_class") for item in data.get("property", []) if item.get("_class")
        ]
        has_details = any(
            item == "hudson.security.HudsonPrivateSecurityRealm$Details"
            for item in properties
        )
        out(
            {
                "ok": True,
                "exists": True,
                "username": username,
                "full_name": data.get("fullName"),
                "has_hudson_private_security_realm_details": has_details,
                "properties": properties,
            }
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        out({"ok": False, "error": str(exc)})
        return 1


def cmd_jenkins_auth_check(username: str, password_file: str) -> int:
    try:
        import requests

        password = _read_private_secret(password_file)
        response = requests.get(
            f"{JENKINS['base_url']}/whoAmI/api/json",
            auth=(username, password),
            timeout=10,
        )
        data = {}
        try:
            data = response.json()
        except Exception:  # noqa: BLE001
            pass
        authenticated = bool(data.get("authenticated"))
        authenticated_name = data.get("name")
        out(
            {
                "ok": response.status_code == 200 and authenticated,
                "status_code": response.status_code,
                "authenticated": authenticated,
                "name": authenticated_name,
                "matches_user": authenticated_name == username,
                "password_printed": False,
            }
        )
        return 0 if response.status_code == 200 and authenticated else 1
    except Exception as exc:  # noqa: BLE001
        out({"ok": False, "error": str(exc)})
        return 1


def cmd_jenkins_test() -> int:
    try:
        session = _jenkins_session()
        response = session.get(f"{JENKINS['base_url']}/api/json", timeout=10)
        response.raise_for_status()
        info = response.json()
        out(
            {
                "ok": True,
                "url": JENKINS["base_url"],
                "user": JENKINS["username"],
                "jobs": len(info.get("jobs", [])),
            }
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        out({"ok": False, "error": str(exc)})
        return 1


def cmd_jenkins_user_exists(username: str) -> int:
    try:
        session = _jenkins_session()
        response = session.get(
            f"{JENKINS['base_url']}/user/{username}/api/json", timeout=10
        )
        if response.status_code == 404:
            out({"ok": True, "exists": False, "username": username})
            return 0
        response.raise_for_status()
        data = response.json()
        out(
            {
                "ok": True,
                "exists": True,
                "username": username,
                "full_name": data.get("fullName"),
            }
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        out({"ok": False, "error": str(exc)})
        return 1


def cmd_jenkins_create_user(username: str, email: str, full_name: str = "") -> int:
    return cmd_jenkins_create_realm_user(username, email, full_name)


def main(argv) -> int:
    if len(argv) < 2:
        out(
            {
                "ok": False,
                "error": "usage: switch_tools.py sql|jenkins-test|jenkins-user-exists|jenkins-user-details|jenkins-create-user|jenkins-create-realm-user|jenkins-auth-check|approver-check ...",
            }
        )
        return 2
    command, args = argv[1], argv[2:]
    if command == "sql":
        return cmd_sql(" ".join(args))
    if command == "jenkins-test":
        return cmd_jenkins_test()
    if command == "jenkins-user-exists":
        if not args:
            out({"ok": False, "error": "username required"})
            return 2
        return cmd_jenkins_user_exists(args[0])
    if command == "jenkins-create-user":
        if len(args) < 2:
            out({"ok": False, "error": "username and email required"})
            return 2
        return cmd_jenkins_create_user(args[0], args[1], args[2] if len(args) > 2 else "")
    if command == "jenkins-create-realm-user":
        if len(args) < 2:
            out({"ok": False, "error": "username and email required"})
            return 2
        return cmd_jenkins_create_realm_user(
            args[0], args[1], args[2] if len(args) > 2 else ""
        )
    if command == "jenkins-user-details":
        if not args:
            out({"ok": False, "error": "username required"})
            return 2
        return cmd_jenkins_user_details(args[0])
    if command == "jenkins-auth-check":
        if len(args) < 2:
            out({"ok": False, "error": "username and password_file required"})
            return 2
        return cmd_jenkins_auth_check(args[0], args[1])
    if command == "approver-check":
        if not args:
            out({"authorized": False, "reason": "authenticated sender name required"})
            return 2
        return cmd_approver_check(" ".join(args))
    out({"ok": False, "error": f"unknown command: {command}"})
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
