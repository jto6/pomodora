"""
Lightweight DatabaseManager for unit tests.
Provides basic database functionality without GUI dependencies or sync features.
"""

import os
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text, ForeignKey, event
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from datetime import datetime

# Create our own Base to avoid importing the one from models.py with GUI dependencies
Base = declarative_base()

# Define model classes directly to avoid GUI dependencies
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


class UnitTestDatabaseManager:
    """
    Lightweight database manager for unit tests.
    Provides only basic functionality needed for testing without any sync or GUI dependencies.
    """
    
    def __init__(self, db_path=":memory:"):
        """Initialize test database manager with in-memory database by default"""
        self.db_path = db_path
        
        # Create SQLite engine with foreign key constraints enabled
        if db_path == ":memory:":
            self.engine = create_engine('sqlite:///:memory:', echo=False, connect_args={"check_same_thread": False})
        else:
            self.engine = create_engine(f'sqlite:///{db_path}', echo=False, connect_args={"check_same_thread": False})
        
        # Enable foreign key constraints for SQLite
        @event.listens_for(self.engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
        
        # Create all tables
        Base.metadata.create_all(self.engine)
        
        # Create session factory
        self.Session = sessionmaker(bind=self.engine)
        self.session = None
    
    def get_session(self):
        """Get a database session"""
        return self.Session()
    
    def initialize_default_projects(self):
        """Initialize default projects and categories for testing"""
        session = self.get_session()
        try:
            # Only create defaults if database is completely empty
            if session.query(Project).count() == 0 and session.query(TaskCategory).count() == 0:
                # Default categories
                default_categories = [
                    {"name": "Admin", "color": "#3498db"},
                    {"name": "Comm", "color": "#2ecc71"},
                    {"name": "Strategy", "color": "#f39c12"},
                    {"name": "Research", "color": "#9b59b6"},
                    {"name": "SelfDev", "color": "#e74c3c"},
                    {"name": "Dev", "color": "#1abc9c"}
                ]
                
                for cat_data in default_categories:
                    category = TaskCategory(name=cat_data["name"], color=cat_data["color"])
                    session.add(category)
                
                # Default projects - only "None" as default
                default_projects = [
                    {"name": "None", "color": "#3498db"}
                ]
                
                for proj_data in default_projects:
                    project = Project(name=proj_data["name"], color=proj_data["color"])
                    session.add(project)
                
                session.commit()
        finally:
            session.close()