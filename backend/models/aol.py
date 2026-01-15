from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Numeric, Date, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
import enum


class RubricType(str, enum.Enum):
    holistic = "holistic"
    analytic = "analytic"


class LearningMethod(Base):
    __tablename__ = "learning_methods"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(10), unique=True, nullable=False)
    name_eng = Column(String(64), nullable=False)
    name_no = Column(String(64))
    description = Column(Text)
    sort_order = Column(Integer, default=0)


class AssessmentMethod(Base):
    __tablename__ = "assessment_methods"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(10), unique=True, nullable=False)
    name_eng = Column(String(64), nullable=False)
    name_no = Column(String(64))
    description = Column(Text)
    sort_order = Column(Integer, default=0)


class Technology(Base):
    __tablename__ = "technologies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(10), unique=True, nullable=False)
    name_eng = Column(String(64), nullable=False)
    name_no = Column(String(64))
    description = Column(Text)


class ProgrammeCourseMetadata(Base):
    __tablename__ = "programme_course_metadata"

    id = Column(Integer, primary_key=True, autoincrement=True)
    programme_id = Column(Integer, ForeignKey("study_programme.id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    sdgs = Column(String(255))  # Comma-separated SDG numbers
    notes = Column(Text)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by = Column(Integer, ForeignKey("users.uuid"))


class CourseLearningMethod(Base):
    __tablename__ = "course_learning_methods"

    id = Column(Integer, primary_key=True, autoincrement=True)
    programme_id = Column(Integer, ForeignKey("study_programme.id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    method_id = Column(Integer, ForeignKey("learning_methods.id"), nullable=False)

    method = relationship("LearningMethod")


class CourseAssessmentMethod(Base):
    __tablename__ = "course_assessment_methods"

    id = Column(Integer, primary_key=True, autoincrement=True)
    programme_id = Column(Integer, ForeignKey("study_programme.id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    method_id = Column(Integer, ForeignKey("assessment_methods.id"), nullable=False)

    method = relationship("AssessmentMethod")


class CourseTechnology(Base):
    __tablename__ = "course_technologies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    programme_id = Column(Integer, ForeignKey("study_programme.id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    technology_id = Column(Integer, ForeignKey("technologies.id"), nullable=False)

    technology = relationship("Technology")


class GoalCategory(Base):
    __tablename__ = "goal_categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name_no = Column(String(64), nullable=False)
    name_eng = Column(String(64))
    enabled = Column(Boolean, default=True)

    # Relationships
    goals = relationship("LearningGoal", back_populates="category")


class LearningGoal(Base):
    __tablename__ = "learning_goals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    goal_eng = Column(Text)
    goal_no = Column(Text)
    valid_from = Column(DateTime, server_default=func.now())
    valid_to = Column(DateTime)
    goal_category = Column(Integer, ForeignKey("goal_categories.id"), nullable=False)
    programme_id = Column(Integer, ForeignKey("study_programme.id"), nullable=False)
    is_measured = Column(Boolean, default=False)
    target_percentage = Column(Numeric(5, 2), default=80.00)

    # Relationships
    category = relationship("GoalCategory", back_populates="goals")
    programme = relationship("StudyProgramme", back_populates="learning_goals")
    course_mappings = relationship("GoalCourseMatrix", back_populates="goal")
    staff_assignments = relationship("GoalStaffAssignment", back_populates="goal")
    rubrics = relationship("Rubric", back_populates="goal")


class GoalCourseMatrix(Base):
    __tablename__ = "goal_course_matrix"

    id = Column(Integer, primary_key=True, autoincrement=True)
    goal_id = Column(Integer, ForeignKey("learning_goals.id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    # Legacy columns (kept for backwards compatibility)
    introduced = Column(Boolean, default=False)
    practiced = Column(Boolean, default=False)
    reinforced = Column(Boolean, default=False)
    # New columns
    learning_level = Column(Integer, default=0)  # 0=None, 1=Introduced, 2=Developing, 3=Mastery
    is_assessed = Column(Boolean, default=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by = Column(Integer, ForeignKey("users.uuid"))

    # Relationships
    goal = relationship("LearningGoal", back_populates="course_mappings")
    course = relationship("Course", back_populates="goal_mappings")


class GoalStaffAssignment(Base):
    __tablename__ = "goal_staff_assignments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    goal_id = Column(Integer, ForeignKey("learning_goals.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.uuid"), nullable=False)
    assigned_at = Column(DateTime, server_default=func.now())
    assigned_by = Column(Integer, ForeignKey("users.uuid"))

    # Relationships
    goal = relationship("LearningGoal", back_populates="staff_assignments")
    user = relationship("User", back_populates="goal_assignments", foreign_keys=[user_id])


class Rubric(Base):
    __tablename__ = "rubrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    goal_id = Column(Integer, ForeignKey("learning_goals.id"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    rubric_type = Column(Enum(RubricType), default=RubricType.analytic)
    created_at = Column(DateTime, server_default=func.now())
    created_by = Column(Integer, ForeignKey("users.uuid"))
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    active = Column(Boolean, default=True)

    # Relationships
    goal = relationship("LearningGoal", back_populates="rubrics")
    traits = relationship("RubricTrait", back_populates="rubric", cascade="all, delete-orphan")
    assessments = relationship("Assessment", back_populates="rubric")


class RubricTrait(Base):
    __tablename__ = "rubric_traits"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rubric_id = Column(Integer, ForeignKey("rubrics.id"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    sort_order = Column(Integer, default=0)
    level_does_not_meet = Column(Text)
    level_meets = Column(Text)
    level_exceeds = Column(Text)

    # Relationships
    rubric = relationship("Rubric", back_populates="traits")
    results = relationship("AssessmentResult", back_populates="trait")


class Assessment(Base):
    __tablename__ = "assessments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rubric_id = Column(Integer, ForeignKey("rubrics.id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    academic_year_id = Column(Integer, ForeignKey("acad_year.id"), nullable=False)
    semester_id = Column(Integer, ForeignKey("semester.id"))
    assessment_date = Column(Date)
    total_students = Column(Integer, default=0)
    notes = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    created_by = Column(Integer, ForeignKey("users.uuid"))

    # Relationships
    rubric = relationship("Rubric", back_populates="assessments")
    course = relationship("Course", back_populates="assessments")
    results = relationship("AssessmentResult", back_populates="assessment", cascade="all, delete-orphan")


class AssessmentResult(Base):
    __tablename__ = "assessment_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    assessment_id = Column(Integer, ForeignKey("assessments.id"), nullable=False)
    trait_id = Column(Integer, ForeignKey("rubric_traits.id"), nullable=False)
    count_does_not_meet = Column(Integer, default=0)
    count_meets = Column(Integer, default=0)
    count_exceeds = Column(Integer, default=0)

    # Relationships
    assessment = relationship("Assessment", back_populates="results")
    trait = relationship("RubricTrait", back_populates="results")

    @property
    def total_students(self):
        return self.count_does_not_meet + self.count_meets + self.count_exceeds

    @property
    def meets_or_exceeds_percentage(self):
        total = self.total_students
        if total == 0:
            return 0
        return ((self.count_meets + self.count_exceeds) / total) * 100
