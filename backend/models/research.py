"""
Research and Faculty Qualification Models
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Enum, DECIMAL, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
import enum


class PublicationType(str, enum.Enum):
    prj_article = "prj_article"  # Peer-reviewed journal article
    peer_reviewed_other = "peer_reviewed_other"  # Additional peer/editorial reviewed
    other_ic = "other_ic"  # All other intellectual contributions


class PortfolioCategory(str, enum.Enum):
    basic_discovery = "basic_discovery"  # Basic or Discovery
    applied_integration = "applied_integration"  # Applied or Integration
    teaching_learning = "teaching_learning"  # Teaching and Learning


# Configurable tables

class Degree(Base):
    __tablename__ = "degrees"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    created_at = Column(DateTime, server_default=func.now())


class Discipline(Base):
    __tablename__ = "disciplines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    shorthand = Column(String(20), nullable=False, unique=True)
    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    user_disciplines = relationship("UserDiscipline", back_populates="discipline")


class ProfessionalResponsibility(Base):
    __tablename__ = "professional_responsibilities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    shorthand = Column(String(20), nullable=False, unique=True)
    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    user_responsibilities = relationship("UserResponsibility", back_populates="responsibility")


# User-linked tables

class UserDiscipline(Base):
    __tablename__ = "user_disciplines"

    user_id = Column(Integer, ForeignKey("users.uuid", ondelete="CASCADE"), primary_key=True)
    discipline_id = Column(Integer, ForeignKey("disciplines.id", ondelete="CASCADE"), primary_key=True)
    percentage = Column(DECIMAL(5, 2), nullable=False)

    # Relationships
    user = relationship("User", back_populates="disciplines")
    discipline = relationship("Discipline", back_populates="user_disciplines")


class UserResponsibility(Base):
    __tablename__ = "user_responsibilities"

    user_id = Column(Integer, ForeignKey("users.uuid", ondelete="CASCADE"), primary_key=True)
    responsibility_id = Column(Integer, ForeignKey("professional_responsibilities.id", ondelete="CASCADE"), primary_key=True)

    # Relationships
    user = relationship("User", back_populates="responsibilities")
    responsibility = relationship("ProfessionalResponsibility", back_populates="user_responsibilities")


class UserTeachingProductivity(Base):
    __tablename__ = "user_teaching_productivity"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.uuid", ondelete="CASCADE"), nullable=False)
    academic_year = Column(String(9), nullable=False)  # e.g., "2024-2025"
    credits = Column(DECIMAL(6, 2), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="teaching_productivity")


# Intellectual Contributions

class IntellectualContribution(Base):
    __tablename__ = "intellectual_contributions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nva_id = Column(String(255), nullable=False, unique=True)
    title = Column(Text, nullable=False)
    year = Column(Integer)
    publication_type = Column(Enum(PublicationType), default=PublicationType.other_ic)
    portfolio_category = Column(Enum(PortfolioCategory), default=None)
    nva_data = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    user_contributions = relationship("UserIntellectualContribution", back_populates="contribution", cascade="all, delete-orphan")


class UserIntellectualContribution(Base):
    __tablename__ = "user_intellectual_contributions"

    user_id = Column(Integer, ForeignKey("users.uuid", ondelete="CASCADE"), primary_key=True)
    ic_id = Column(Integer, ForeignKey("intellectual_contributions.id", ondelete="CASCADE"), primary_key=True)
    publication_type = Column(Enum(PublicationType), default=None)  # User's own classification
    portfolio_category = Column(Enum(PortfolioCategory), default=None)  # User's own classification
    societal_impact = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="intellectual_contributions")
    contribution = relationship("IntellectualContribution", back_populates="user_contributions")


# Professional Activities (for PA/IP tracking)

class ProfessionalActivity(Base):
    __tablename__ = "professional_activities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.uuid", ondelete="CASCADE"), nullable=False)
    year = Column(Integer, nullable=False)
    activity_type = Column(String(100), nullable=False)
    description = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="professional_activities")


# Exemptions for qualification requirements

class ExemptionType(Base):
    __tablename__ = "exemption_types"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text)
    # What this exemption affects
    reduces_ic_requirement = Column(Boolean, default=False)
    reduces_prj_requirement = Column(Boolean, default=False)
    reduces_activity_requirement = Column(Boolean, default=False)
    grants_full_exemption = Column(Boolean, default=False)  # e.g., new PhD within X years
    # How much to reduce (if applicable)
    ic_reduction = Column(Integer, default=0)
    prj_reduction = Column(Integer, default=0)
    activity_reduction = Column(Integer, default=0)
    # For time-based exemptions (e.g., years after degree)
    years_after_degree = Column(Integer, default=None)
    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    user_exemptions = relationship("UserExemption", back_populates="exemption_type", cascade="all, delete-orphan")


class UserExemption(Base):
    __tablename__ = "user_exemptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.uuid", ondelete="CASCADE"), nullable=False)
    exemption_type_id = Column(Integer, ForeignKey("exemption_types.id", ondelete="CASCADE"), nullable=False)
    year_from = Column(Integer, nullable=False)  # Start year of exemption
    year_to = Column(Integer, default=None)  # End year (NULL = ongoing)
    notes = Column(Text)
    approved_by = Column(Integer, ForeignKey("users.uuid", ondelete="SET NULL"), default=None)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", foreign_keys=[user_id], back_populates="exemptions")
    exemption_type = relationship("ExemptionType", back_populates="user_exemptions")
    approver = relationship("User", foreign_keys=[approved_by])
