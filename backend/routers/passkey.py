import json
from datetime import datetime, timedelta

import webauthn
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import get_settings
from database import get_db
from dependencies import get_current_user
from models import User
from models.user import PasskeyCredential, WebAuthnChallenge
from services.auth import AuthService

router = APIRouter(prefix="/auth/passkey", tags=["Passkeys"])
settings = get_settings()

_ORIGIN = settings.app_url.rsplit("/", 1)[0]  # https://hh-utdanning.nmbu.no


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _store_challenge(db: Session, challenge: bytes, user_id: int | None = None) -> None:
    db.add(WebAuthnChallenge(
        challenge=challenge.hex(),
        user_id=user_id,
        expires_at=datetime.utcnow() + timedelta(minutes=5),
    ))
    db.commit()


def _pop_challenge(db: Session, challenge_hex: str) -> bytes | None:
    """Load and delete a challenge. Returns the bytes or None if expired/missing."""
    row = (
        db.query(WebAuthnChallenge)
        .filter(
            WebAuthnChallenge.challenge == challenge_hex,
            WebAuthnChallenge.expires_at > datetime.utcnow(),
        )
        .first()
    )
    if not row:
        return None
    db.delete(row)
    db.commit()
    return bytes.fromhex(challenge_hex)


# ---------------------------------------------------------------------------
# Registration (user must be logged in)
# ---------------------------------------------------------------------------

@router.post("/register/begin")
async def register_begin(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate WebAuthn registration options for the current user."""
    # Exclude already-registered credentials so the browser won't re-register them
    exclude = [
        webauthn.helpers.structs.PublicKeyCredentialDescriptor(id=pk.credential_id)
        for pk in user.passkeys
    ]

    options = webauthn.generate_registration_options(
        rp_id=settings.webauthn_rp_id,
        rp_name=settings.webauthn_rp_name,
        user_id=str(user.uuid).encode(),
        user_name=user.email,
        user_display_name=user.full_name,
        exclude_credentials=exclude,
        authenticator_selection=webauthn.helpers.structs.AuthenticatorSelectionCriteria(
            resident_key=webauthn.helpers.structs.ResidentKeyRequirement.PREFERRED,
            user_verification=webauthn.helpers.structs.UserVerificationRequirement.PREFERRED,
        ),
    )

    _store_challenge(db, options.challenge, user_id=user.uuid)

    return json.loads(webauthn.options_to_json(options))


class RegisterCompleteRequest(BaseModel):
    credential: dict
    name: str = "Passkey"


@router.post("/register/complete")
async def register_complete(
    body: RegisterCompleteRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Verify and store a newly created passkey."""
    # Find the pending challenge for this user
    row = (
        db.query(WebAuthnChallenge)
        .filter(
            WebAuthnChallenge.user_id == user.uuid,
            WebAuthnChallenge.expires_at > datetime.utcnow(),
        )
        .order_by(WebAuthnChallenge.id.desc())
        .first()
    )
    if not row:
        raise HTTPException(status_code=400, detail="No pending registration challenge")

    challenge = bytes.fromhex(row.challenge)
    db.delete(row)
    db.commit()

    try:
        verified = webauthn.verify_registration_response(
            credential=body.credential,
            expected_challenge=challenge,
            expected_rp_id=settings.webauthn_rp_id,
            expected_origin=_ORIGIN,
            require_user_verification=False,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Registration failed: {e}")

    db.add(PasskeyCredential(
        user_id=user.uuid,
        credential_id=verified.credential_id,
        public_key=verified.credential_public_key,
        sign_count=verified.sign_count,
        aaguid=str(verified.aaguid) if verified.aaguid else None,
        name=body.name[:64],
    ))
    db.commit()

    return {"message": "Passkey registered successfully"}


# ---------------------------------------------------------------------------
# Authentication (public)
# ---------------------------------------------------------------------------

@router.post("/auth/begin")
async def auth_begin(db: Session = Depends(get_db)):
    """Generate WebAuthn authentication options (discoverable credential flow)."""
    options = webauthn.generate_authentication_options(
        rp_id=settings.webauthn_rp_id,
        user_verification=webauthn.helpers.structs.UserVerificationRequirement.PREFERRED,
    )

    _store_challenge(db, options.challenge, user_id=None)

    return json.loads(webauthn.options_to_json(options))


class AuthCompleteRequest(BaseModel):
    credential: dict


@router.post("/auth/complete")
async def auth_complete(
    body: AuthCompleteRequest,
    req: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Verify a passkey assertion and create a session."""
    raw_id = body.credential.get("rawId") or body.credential.get("id")
    if not raw_id:
        raise HTTPException(status_code=400, detail="Missing credential ID")

    # Decode the base64url credential ID to find the stored credential
    try:
        cred_id_bytes = webauthn.base64url_to_bytes(raw_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid credential ID")

    stored = (
        db.query(PasskeyCredential)
        .filter(PasskeyCredential.credential_id == cred_id_bytes)
        .first()
    )
    if not stored:
        raise HTTPException(status_code=401, detail="Unknown passkey")

    # Find and consume the most recent valid challenge
    row = (
        db.query(WebAuthnChallenge)
        .filter(
            WebAuthnChallenge.user_id.is_(None),
            WebAuthnChallenge.expires_at > datetime.utcnow(),
        )
        .order_by(WebAuthnChallenge.id.desc())
        .first()
    )
    if not row:
        raise HTTPException(status_code=400, detail="No pending authentication challenge")

    challenge = bytes.fromhex(row.challenge)
    db.delete(row)
    db.commit()

    try:
        verified = webauthn.verify_authentication_response(
            credential=body.credential,
            expected_challenge=challenge,
            expected_rp_id=settings.webauthn_rp_id,
            expected_origin=_ORIGIN,
            credential_public_key=stored.public_key,
            credential_current_sign_count=stored.sign_count,
            require_user_verification=False,
        )
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {e}")

    # Update sign count and last used
    stored.sign_count = verified.new_sign_count
    stored.last_used_at = datetime.utcnow()

    user = stored.user
    if not user.active:
        raise HTTPException(status_code=403, detail="Account is deactivated")

    auth_service = AuthService(db)
    session_token = auth_service.create_session(
        user,
        ip_address=req.client.host if req.client else None,
        user_agent=req.headers.get("user-agent"),
    )

    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
    )

    return {"redirect": f"{settings.app_url}/aol"}


# ---------------------------------------------------------------------------
# Passkey management (user must be logged in)
# ---------------------------------------------------------------------------

@router.get("/list")
async def list_passkeys(user: User = Depends(get_current_user)):
    """List all passkeys registered by the current user."""
    return [
        {
            "id": pk.id,
            "name": pk.name,
            "created_at": pk.created_at.isoformat() if pk.created_at else None,
            "last_used_at": pk.last_used_at.isoformat() if pk.last_used_at else None,
        }
        for pk in user.passkeys
    ]


@router.delete("/{passkey_id}")
async def delete_passkey(
    passkey_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a passkey belonging to the current user."""
    pk = (
        db.query(PasskeyCredential)
        .filter(PasskeyCredential.id == passkey_id, PasskeyCredential.user_id == user.uuid)
        .first()
    )
    if not pk:
        raise HTTPException(status_code=404, detail="Passkey not found")

    db.delete(pk)
    db.commit()
    return {"message": "Passkey deleted"}
