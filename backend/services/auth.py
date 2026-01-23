import secrets
from datetime import datetime, timedelta
import bcrypt
from sqlalchemy.orm import Session
from models import User, AuthToken, Session as UserSession, Role, UserRole


class AuthService:
    def __init__(self, db: Session):
        self.db = db

    def get_user_by_email(self, email: str) -> User | None:
        return self.db.query(User).filter(User.email == email).first()

    def get_user_by_id(self, user_id: int) -> User | None:
        return self.db.query(User).filter(User.uuid == user_id).first()

    def get_user_by_google_id(self, google_id: str) -> User | None:
        return self.db.query(User).filter(User.google_id == google_id).first()

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )

    def hash_password(self, password: str) -> str:
        return bcrypt.hashpw(
            password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

    def set_user_password(self, user: User, password: str) -> None:
        user.password_hash = self.hash_password(password)
        self.db.commit()

    def link_google_account(self, user: User, google_id: str) -> None:
        user.google_id = google_id
        self.db.commit()

    def create_magic_link_token(self, user: User, expires_minutes: int = 15) -> str:
        token = secrets.token_urlsafe(32)
        auth_token = AuthToken(
            user_id=user.uuid,
            token=token,
            token_type="magic_link",
            expires_at=datetime.utcnow() + timedelta(minutes=expires_minutes),
        )
        self.db.add(auth_token)
        self.db.commit()
        return token

    def verify_magic_link_token(self, token: str) -> User | None:
        auth_token = (
            self.db.query(AuthToken)
            .filter(
                AuthToken.token == token,
                AuthToken.token_type == "magic_link",
                AuthToken.expires_at > datetime.utcnow(),
                AuthToken.used_at.is_(None),
            )
            .first()
        )
        if not auth_token:
            return None

        auth_token.used_at = datetime.utcnow()
        self.db.commit()
        return self.get_user_by_id(auth_token.user_id)

    def create_session(
        self, user: User, ip_address: str = None, user_agent: str = None, expires_days: int = 7
    ) -> str:
        token = secrets.token_urlsafe(32)
        session = UserSession(
            user_id=user.uuid,
            token=token,
            expires_at=datetime.utcnow() + timedelta(days=expires_days),
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.add(session)
        user.last_login = datetime.utcnow()
        self.db.commit()
        return token

    def verify_session(self, token: str) -> User | None:
        session = (
            self.db.query(UserSession)
            .filter(
                UserSession.token == token,
                UserSession.expires_at > datetime.utcnow(),
            )
            .first()
        )
        if not session:
            return None
        return self.get_user_by_id(session.user_id)

    def get_session_by_token(self, token: str) -> UserSession | None:
        """Get the session object by token."""
        return (
            self.db.query(UserSession)
            .filter(
                UserSession.token == token,
                UserSession.expires_at > datetime.utcnow(),
            )
            .first()
        )

    def start_impersonation(self, token: str, target_user_id: int) -> bool:
        """Start impersonating another user. Returns True if successful."""
        session = self.get_session_by_token(token)
        if not session:
            return False

        # Verify target user exists and is active
        target_user = self.get_user_by_id(target_user_id)
        if not target_user or not target_user.active:
            return False

        session.impersonating_user_id = target_user_id
        self.db.commit()
        return True

    def stop_impersonation(self, token: str) -> bool:
        """Stop impersonating. Returns True if successful."""
        session = self.get_session_by_token(token)
        if not session:
            return False

        session.impersonating_user_id = None
        self.db.commit()
        return True

    def get_effective_user(self, token: str) -> tuple[User | None, User | None]:
        """
        Get the effective user for a session.
        Returns (effective_user, real_user) tuple.
        If not impersonating, both are the same user.
        """
        session = self.get_session_by_token(token)
        if not session:
            return None, None

        real_user = self.get_user_by_id(session.user_id)
        if not real_user:
            return None, None

        if session.impersonating_user_id:
            effective_user = self.get_user_by_id(session.impersonating_user_id)
            if effective_user:
                return effective_user, real_user

        return real_user, real_user

    def invalidate_session(self, token: str) -> None:
        self.db.query(UserSession).filter(UserSession.token == token).delete()
        self.db.commit()

    def get_user_roles(self, user: User) -> list[str]:
        roles = []
        for user_role in user.roles:
            if user_role.expires is None or user_role.expires > datetime.utcnow():
                roles.append(user_role.role.role_name)
        return roles

    def has_role(self, user: User, role_name: str) -> bool:
        return role_name in self.get_user_roles(user)

    def is_system_admin(self, user: User) -> bool:
        return self.has_role(user, "system_admin")

    def assign_role(self, user: User, role_name: str, assigned_by: User = None) -> None:
        role = self.db.query(Role).filter(Role.role_name == role_name).first()
        if not role:
            raise ValueError(f"Role '{role_name}' not found")

        existing = (
            self.db.query(UserRole)
            .filter(UserRole.uuid == user.uuid, UserRole.role_id == role.role_id)
            .first()
        )
        if existing:
            return

        user_role = UserRole(role_id=role.role_id, uuid=user.uuid)
        self.db.add(user_role)
        self.db.commit()
