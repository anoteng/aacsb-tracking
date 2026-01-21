from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Enum, DECIMAL
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
import enum


class FacultyCategory(str, enum.Enum):
    SA = "SA"
    PA = "PA"
    SP = "SP"
    IP = "IP"
    Other = "Other"


class User(Base):
    __tablename__ = "users"

    uuid = Column(Integer, primary_key=True, autoincrement=True)
    lastname = Column(String(64), nullable=False)
    firstname = Column(String(64), nullable=False)
    email = Column(String(64))
    password_hash = Column(String(255))
    google_id = Column(String(255))
    researcher_id = Column(String(64))  # NVA/Cristin researcher ID
    created_at = Column(DateTime, server_default=func.now())
    last_login = Column(DateTime)
    active = Column(Boolean, default=True)

    # Faculty qualification fields
    faculty_category = Column(Enum(FacultyCategory), default=None)
    is_participating = Column(Boolean, default=True)
    participating_note = Column(Text)
    highest_degree_id = Column(Integer, ForeignKey("degrees.id"), default=None)
    degree_year = Column(Integer, default=None)

    # Relationships
    roles = relationship("UserRole", back_populates="user", foreign_keys="UserRole.uuid")
    programme_roles = relationship("UserProgrammeRole", back_populates="user", foreign_keys="UserProgrammeRole.user_id")
    sessions = relationship("Session", back_populates="user", foreign_keys="Session.user_id")
    goal_assignments = relationship("GoalStaffAssignment", back_populates="user", foreign_keys="GoalStaffAssignment.user_id")
    highest_degree = relationship("Degree", foreign_keys=[highest_degree_id])
    disciplines = relationship("UserDiscipline", back_populates="user", cascade="all, delete-orphan")
    responsibilities = relationship("UserResponsibility", back_populates="user", cascade="all, delete-orphan")
    teaching_productivity = relationship("UserTeachingProductivity", back_populates="user", cascade="all, delete-orphan")
    intellectual_contributions = relationship("UserIntellectualContribution", back_populates="user", cascade="all, delete-orphan")
    professional_activities = relationship("ProfessionalActivity", back_populates="user", cascade="all, delete-orphan")
    exemptions = relationship("UserExemption", back_populates="user", foreign_keys="UserExemption.user_id", cascade="all, delete-orphan")

    @property
    def full_name(self):
        return f"{self.firstname} {self.lastname}"


class Role(Base):
    __tablename__ = "roles"

    role_id = Column(Integer, primary_key=True, autoincrement=True)
    role_name = Column(String(64))
    role_desc = Column(Text)
    root = Column(Boolean, default=False)

    # Relationships
    user_roles = relationship("UserRole", back_populates="role")


class UserRole(Base):
    __tablename__ = "user_roles"

    role_id = Column(Integer, ForeignKey("roles.role_id"), primary_key=True)
    uuid = Column(Integer, ForeignKey("users.uuid"), primary_key=True)
    last_change = Column(DateTime, server_default=func.now())
    expires = Column(DateTime)

    # Relationships
    role = relationship("Role", back_populates="user_roles")
    user = relationship("User", back_populates="roles")


class UserProgrammeRole(Base):
    __tablename__ = "user_programme_roles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.uuid"), nullable=False)
    programme_id = Column(Integer, ForeignKey("study_programme.id"), nullable=False)
    role_id = Column(Integer, ForeignKey("roles.role_id"), nullable=False)
    assigned_at = Column(DateTime, server_default=func.now())
    assigned_by = Column(Integer, ForeignKey("users.uuid"))

    # Relationships
    user = relationship("User", back_populates="programme_roles", foreign_keys=[user_id])
    programme = relationship("StudyProgramme", back_populates="user_roles")
    role = relationship("Role")


class Session(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.uuid"), nullable=False)
    token = Column(String(64), unique=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    expires_at = Column(DateTime, nullable=False)
    ip_address = Column(String(45))
    user_agent = Column(String(255))

    # Relationships
    user = relationship("User", back_populates="sessions")


class AuthToken(Base):
    __tablename__ = "auth_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.uuid"), nullable=False)
    token = Column(String(64), unique=True, nullable=False)
    token_type = Column(String(20), nullable=False)  # 'magic_link' or 'password_reset'
    created_at = Column(DateTime, server_default=func.now())
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
