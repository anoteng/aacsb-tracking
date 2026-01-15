from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class StudyProgramme(Base):
    __tablename__ = "study_programme"

    id = Column(Integer, primary_key=True, autoincrement=True)
    programme_code = Column(String(64), nullable=False)
    name_no = Column(String(128), nullable=False)
    name_eng = Column(String(128))
    studienivå = Column(Integer)

    # Relationships
    courses = relationship("ProgrammeCourse", back_populates="programme")
    learning_goals = relationship("LearningGoal", back_populates="programme")
    user_roles = relationship("UserProgrammeRole", back_populates="programme")


class Course(Base):
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    course_code = Column(String(12), nullable=False)
    course_version = Column(String(8), nullable=False)
    name_no = Column(String(128))
    name_eng = Column(String(128))
    last_update = Column(DateTime, server_default=func.now())
    update_by = Column(Integer, ForeignKey("users.uuid"))
    active_from = Column(Integer)
    active_to = Column(Integer)
    ects = Column(Numeric(4, 1), nullable=False)

    # Relationships
    programmes = relationship("ProgrammeCourse", back_populates="course")
    coordinators = relationship("CourseCoordinator", back_populates="course")
    goal_mappings = relationship("GoalCourseMatrix", back_populates="course")
    assessments = relationship("Assessment", back_populates="course")


class ProgrammeCourse(Base):
    __tablename__ = "programme_course"

    course_id = Column(Integer, ForeignKey("courses.id"), primary_key=True)
    programme_id = Column(Integer, ForeignKey("study_programme.id"), primary_key=True)
    track_id = Column(Integer, primary_key=True)
    elective_type = Column(Integer)
    year = Column(Integer)
    semester = Column(Integer)
    valid_from = Column(Integer)
    valid_to = Column(Integer)

    # Relationships
    course = relationship("Course", back_populates="programmes")
    programme = relationship("StudyProgramme", back_populates="courses")


class CourseCoordinator(Base):
    __tablename__ = "course_coordinators"

    id = Column(Integer, primary_key=True, autoincrement=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.uuid"), nullable=False)
    assigned_at = Column(DateTime, server_default=func.now())
    assigned_by = Column(Integer, ForeignKey("users.uuid"))

    # Relationships
    course = relationship("Course", back_populates="coordinators")
    user = relationship("User", foreign_keys=[user_id])
