import hashlib
import secrets
import jwt
from datetime import datetime, timezone
from cryptography.fernet import Fernet
from fastapi import Header, HTTPException
from sqlalchemy import select
from packages.domain.config import settings
from packages.domain.db import transaction
from packages.domain.models import Membership, Group, Role


def digest(secret):
    return hashlib.sha256(secret.encode()).hexdigest()


def encrypt(secret):
    return Fernet(settings().secret_key.encode()).encrypt(secret.encode()).decode()


def issue_secret():
    secret = "vk_" + secrets.token_urlsafe(32)
    return secret, digest(secret)


def issue_contract_token(contract):
    now = datetime.now(timezone.utc)
    claims = {"iss": "quiblyx-contract", "aud": "quiblyx-gateway", "iat": now,
              "exp": contract.expires_at, "sub": contract.id, "tenant_id": contract.tenant_id,
              "application_id": contract.application_id, "key_id": contract.key_id,
              "version": contract.token_version, "scope": "spend:allocate"}
    cfg = settings()
    signing_key = cfg.contract_signing_key or hashlib.sha256(("quiblyx-contract:" + cfg.secret_key).encode()).hexdigest()
    return jwt.encode(claims, signing_key, algorithm="HS256")


def verify_contract_token(token):
    try:
        cfg = settings()
        signing_key = cfg.contract_signing_key or hashlib.sha256(("quiblyx-contract:" + cfg.secret_key).encode()).hexdigest()
        return jwt.decode(token, signing_key, algorithms=["HS256"],
                          audience="quiblyx-gateway", issuer="quiblyx-contract",
                          options={"require": ["exp", "iat", "sub", "tenant_id", "application_id",
                                               "key_id", "version", "scope"]})
    except jwt.PyJWTError:
        raise HTTPException(401, "invalid_spend_contract") from None


def identity(authorization: str = Header(default="")):
    token = authorization.removeprefix("Bearer ")
    cfg = settings()
    if cfg.dev_identity and cfg.dev_login_token and secrets.compare_digest(token, cfg.dev_login_token):
        return "local-owner"
    if cfg.oidc_jwks_url and cfg.oidc_issuer:
        try:
            key = jwt.PyJWKClient(cfg.oidc_jwks_url).get_signing_key_from_jwt(token)
            return jwt.decode(token, key.key, algorithms=["RS256"], audience=cfg.oidc_audience,
                              issuer=cfg.oidc_issuer, options={"require": ["exp", "sub", "iss"]})["sub"]
        except jwt.PyJWTError:
            pass
    raise HTTPException(401, "authentication_required")


PERMISSIONS = {"read", "write", "members.manage", "roles.manage", "content.read"}
TEMPLATES = {"owner": PERMISSIONS, "admin": PERMISSIONS - {"roles.manage"},
             "manager": {"read", "write"}, "member": {"read"}, "auditor": {"read"}}


def authorize(tenant, subject, write=False, scope=None, permission=None):
    with transaction(tenant) as s:
        member = s.scalar(select(Membership).where(Membership.tenant_id == tenant, Membership.subject == subject))
        if not member:
            raise HTTPException(403, "permission_denied")
        permissions = TEMPLATES.get(member.role)
        if permissions is None:
            role = s.scalar(select(Role).where(Role.tenant_id == tenant, Role.id == member.role))
            permissions = set(role.permissions) if role else set()
        needed = permission or ("write" if write else "read")
        if needed not in permissions:
            raise HTTPException(403, "permission_denied")
        if member.scope_id:
            path = ancestry(s, tenant, scope, check_pause=False) if scope else []
            if member.scope_id not in path:
                raise HTTPException(403, "permission_denied")
        return member.role


def ancestry(s, tenant, group_id, check_pause=True):
    path = []
    while group_id:
        if group_id in path or len(path) >= 64:
            raise HTTPException(409, "invalid_hierarchy")
        group = s.scalar(select(Group).where(Group.id == group_id, Group.tenant_id == tenant))
        if not group:
            raise HTTPException(404, "group_not_found")
        if check_pause and group.paused:
            raise HTTPException(403, "scope_paused")
        path.append(group.id)
        group_id = group.parent_id
    return path
