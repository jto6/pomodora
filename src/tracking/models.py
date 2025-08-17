from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()

class TaskCategory(Base):
    __tablename__ = 'task_categories'

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    color = Column(String(7), default='#3498db')  # Hex color code
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship to sprints
    sprints = relationship("Sprint", back_populates="task_category")

class Project(Base):
    __tablename__ = 'projects'

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    color = Column(String(7), default='#3498db')  # Hex color code
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship to sprints
    sprints = relationship("Sprint", back_populates="project")

class Sprint(Base):
    __tablename__ = 'sprints'

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey('projects.id'), nullable=False)
    task_category_id = Column(Integer, ForeignKey('task_categories.id'), nullable=False)
    task_description = Column(Text, nullable=False)
    start_time = Column(DateTime, nullable=False)  # When the sprint actually started
    end_time = Column(DateTime)  # When the sprint ended (if completed)
    duration_minutes = Column(Integer)  # Actual duration in minutes
    planned_duration = Column(Integer, default=25)  # Planned duration
    completed = Column(Boolean, default=False)
    interrupted = Column(Boolean, default=False)

    # Relationships to access project and task category objects
    project = relationship("Project", back_populates="sprints")
    task_category = relationship("TaskCategory", back_populates="sprints")

    # Compatibility properties for backward compatibility with old code
    @property
    def project_name(self):
        """Get project name via relationship for backward compatibility"""
        return self.project.name if self.project else None

    @property
    def task_category_name(self):
        """Get task category name via relationship for backward compatibility"""
        return self.task_category.name if self.task_category else None