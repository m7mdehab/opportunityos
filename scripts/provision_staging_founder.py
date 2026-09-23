"""Idempotently provision the protected staging Founder and bind its singleton identity.

All credential-bearing calls stay inside this process. Output intentionally contains
only sanitized status labels; provider responses and connection details are never
printed or included in raised exceptions.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any, Callable


class ProvisionFailure(Exception):
    def __init__(self, stage: str):
        super().__init__(stage)
        self.stage = stage


@dataclass(frozen=True)
class Config:
    supabase_url: str
    service_key: str
    founder_email: str
    founder_password: str
    database_url: str


def _config(env: dict[str, str] | os._Environ[str] = os.environ) -> Config:
    values = {
        "SUPABASE_URL": env.get("SUPABASE_URL", "").strip(),
        "SUPABASE_SERVICE_ROLE_KEY": env.get("SUPABASE_SERVICE_ROLE_KEY", "").strip(),
        "FOUNDER_EMAIL": env.get("FOUNDER_EMAIL", "").strip(),
        "FOUNDER_PASSWORD": env.get("FOUNDER_PASSWORD", ""),
        "CLOUD_DATABASE_URL": env.get("CLOUD_DATABASE_URL", "").strip(),
    }
    if any(not value for value in values.values()):
        raise ProvisionFailure("required_environment")
    parsed = urllib.parse.urlparse(values["SUPABASE_URL"])
    if parsed.scheme != "https" or parsed.hostname != "sunjfepvdzfknglrjwhm.supabase.co":
        raise ProvisionFailure("project_origin")
    return Config(
        supabase_url=values["SUPABASE_URL"].rstrip("/"),
        service_key=values["SUPABASE_SERVICE_ROLE_KEY"],
        founder_email=values["FOUNDER_EMAIL"],
        founder_password=values["FOUNDER_PASSWORD"],
        database_url=values["CLOUD_DATABASE_URL"],
    )


def _request_json(
    url: str,
    *,
    key: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json"}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read()
        parsed = json.loads(raw) if raw else {}
        if not isinstance(parsed, dict):
            raise ValueError("unexpected response")
        return parsed
    except Exception:
        raise ProvisionFailure("supabase_auth_request") from None


def _find_user(config: Config, request_json: Callable[..., dict[str, Any]]) -> dict[str, Any] | None:
    page = 1
    while True:
        query = urllib.parse.urlencode({"page": page, "per_page": 1000})
        result = request_json(
            f"{config.supabase_url}/auth/v1/admin/users?{query}", key=config.service_key
        )
        users = result.get("users")
        if not isinstance(users, list):
            raise ProvisionFailure("auth_user_listing")
        for user in users:
            if isinstance(user, dict) and str(user.get("email", "")).casefold() == config.founder_email.casefold():
                return user
        if len(users) < 1000:
            return None
        page += 1


def _ensure_user(config: Config, request_json: Callable[..., dict[str, Any]]) -> str:
    existing = _find_user(config, request_json)
    body = {
        "email": config.founder_email,
        "password": config.founder_password,
        "email_confirm": True,
    }
    if existing is None:
        user = request_json(
            f"{config.supabase_url}/auth/v1/admin/users",
            key=config.service_key,
            method="POST",
            payload=body,
        )
    else:
        user_id = str(existing.get("id", ""))
        try:
            uuid.UUID(user_id)
        except (ValueError, AttributeError):
            raise ProvisionFailure("auth_user_identity") from None
        user = request_json(
            f"{config.supabase_url}/auth/v1/admin/users/{user_id}",
            key=config.service_key,
            method="PUT",
            payload={"password": config.founder_password, "email_confirm": True},
        )
    user_id = str(user.get("id", ""))
    try:
        user_id = str(uuid.UUID(user_id))
    except (ValueError, AttributeError):
        raise ProvisionFailure("auth_user_identity") from None
    return user_id


def _verify_password(config: Config, request_json: Callable[..., dict[str, Any]], user_id: str) -> None:
    result = request_json(
        f"{config.supabase_url}/auth/v1/token?grant_type=password",
        key=config.service_key,
        method="POST",
        payload={"email": config.founder_email, "password": config.founder_password},
    )
    user = result.get("user")
    if not isinstance(user, dict) or str(user.get("id", "")) != user_id:
        raise ProvisionFailure("password_signin")


def _bind_identity(database_url: str, user_id: str, connect: Callable[..., Any] | None = None) -> None:
    if connect is None:
        try:
            import psycopg2
        except Exception:
            raise ProvisionFailure("database_driver") from None
        connect = psycopg2.connect
    try:
        connection = connect(database_url, connect_timeout=10, sslmode="require")
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s))",
                    ("opos-fr007-founder-identity-singleton",),
                )
                cursor.execute(
                    "SELECT supabase_user_id FROM public.founder_identity "
                    "WHERE id = %s FOR UPDATE",
                    ("singleton",),
                )
                row = cursor.fetchone()
                if row is None:
                    cursor.execute(
                        "INSERT INTO public.founder_identity "
                        "(id, supabase_user_id, created_at, updated_at) "
                        "VALUES (%s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                        ("singleton", user_id),
                    )
                elif str(row[0]) != user_id:
                    raise ProvisionFailure("identity_conflict")
            connection.commit()
        except Exception:
            connection.rollback()
            if isinstance(sys.exc_info()[1], ProvisionFailure):
                raise
            raise ProvisionFailure("identity_binding") from None
        finally:
            connection.close()
    except ProvisionFailure:
        raise
    except Exception:
        raise ProvisionFailure("database_connection") from None


def provision(
    config: Config,
    request_json: Callable[..., dict[str, Any]] = _request_json,
    connect: Callable[..., Any] | None = None,
) -> None:
    user_id = _ensure_user(config, request_json)
    _verify_password(config, request_json, user_id)
    _bind_identity(config.database_url, user_id, connect=connect)


def main() -> int:
    try:
        config = _config()
        provision(config)
    except ProvisionFailure as exc:
        print(f"FOUNDER_PROVISION=FAIL stage={exc.stage}", file=sys.stderr)
        return 1
    except Exception:
        print("FOUNDER_PROVISION=FAIL stage=unexpected", file=sys.stderr)
        return 1
    print("FOUNDER_AUTH_PASSWORD_SIGN_IN=PASS")
    print("FOUNDER_IDENTITY_SINGLETON=BOUND")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
