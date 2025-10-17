from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, TypeDecorator, types
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()

class ISODateTime(TypeDecorator):
    """Custom DateTime type that ensures consistent ISO format storage in SQLite.

    Stores datetimes as ISO 8601 strings with 'T' separator to ensure consistency
    across platforms (Linux vs macOS). Handles legacy formats on read.
    """
    impl = types.String(48)  # Store as string (ISO format: YYYY-MM-DDTHH:MM:SS.ffffff)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Convert Python datetime to ISO format string for storage"""
        if value is not None:
            if isinstance(value, datetime):
                # Always store in ISO format with 'T' separator
                return value.isoformat()
            elif isinstance(value, str):
                # Already a string - normalize it
                return value.replace(' ', 'T') if ' ' in value else value
        return value

    def process_result_value(self, value, dialect):
        """Convert stored ISO string back to Python datetime"""
        if value is not None:
            if isinstance(value, str):
                try:
                    # Handle both formats: with 'T' and with space (legacy)
                    value_normalized = value.replace(' ', 'T') if ' ' in value else value
                    return datetime.fromisoformat(value_normalized)
                except (ValueError, AttributeError):
                    # Fallback for unexpected formats
                    return None
            elif isinstance(value, datetime):
                # Already a datetime object
                return value
        return value

class TaskCategory(Base):
    __tablename__ = 'task_categories'

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    color = Column(String(7), default='#3498db')  # Hex color code
    active = Column(Boolean, default=True)
    created_at = Column(ISODateTime, default=datetime.utcnow)

    # Relationship to sprints
    sprints = relationship("Sprint", back_populates="task_category")

class Project(Base):
    __tablename__ = 'projects'

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    color = Column(String(7), default='#3498db')  # Hex color code
    active = Column(Boolean, default=True)
    created_at = Column(ISODateTime, default=datetime.utcnow)

    # Relationship to sprints
    sprints = relationship("Sprint", back_populates="project")

class Sprint(Base):
    __tablename__ = 'sprints'

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey('projects.id'), nullable=False)
    task_category_id = Column(Integer, ForeignKey('task_categories.id'), nullable=False)
    task_description = Column(Text, nullable=False)
    start_time = Column(ISODateTime, nullable=False)  # When the sprint actually started
    end_time = Column(ISODateTime)  # When the sprint ended (if completed)
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