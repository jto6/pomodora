"""
Database testing helpers and utilities.
Provides common database operations for testing scenarios.
"""

import tempfile
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional

from .test_database_manager import UnitTestDatabaseManager as DatabaseManager, Project, TaskCategory, Sprint


class TestDatabaseFactory:
    """Factory for creating test databases with various data scenarios"""
    
    @staticmethod
    def create_empty_db() -> DatabaseManager:
        """Create empty in-memory database with tables but no data"""
        # Tables are created automatically in __init__
        db_manager = DatabaseManager(":memory:")
        return db_manager
    
    @staticmethod
    def create_basic_db() -> DatabaseManager:
        """Create database with default projects and categories"""
        db_manager = TestDatabaseFactory.create_empty_db()
        db_manager.initialize_default_projects()
        return db_manager
    
    @staticmethod
    def create_populated_db(num_sprints: int = 10) -> DatabaseManager:
        """Create database with sample data including sprints"""
        db_manager = TestDatabaseFactory.create_basic_db()
        
        session = db_manager.get_session()
        try:
            # Get first project and category for sample data
            project = session.query(Project).first()
            category = session.query(TaskCategory).first()
            
            if project and category:
                # Create sample sprints
                for i in range(num_sprints):
                    start_time = datetime.now() - timedelta(days=i, hours=i)
                    sprint = Sprint(
                        project_id=project.id,
                        task_category_id=category.id,
                        task_description=f"Test task {i+1}",
                        start_time=start_time,
                        end_time=start_time + timedelta(minutes=25),
                        duration_minutes=25,
                        planned_duration=25,
                        completed=True
                    )
                    session.add(sprint)
                
                session.commit()
        finally:
            session.close()
            
        return db_manager
    
    @staticmethod
    def create_file_db(num_sprints: int = 0) -> tuple[DatabaseManager, str]:
        """Create temporary file database, returns (db_manager, file_path)"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_db:
            db_path = tmp_db.name
            
        db_manager = DatabaseManager(db_path)
        db_manager.initialize_default_projects()
        
        if num_sprints > 0:
            session = db_manager.get_session()
            try:
                project = session.query(Project).first()
                category = session.query(TaskCategory).first()
                
                if project and category:
                    for i in range(num_sprints):
                        start_time = datetime.now() - timedelta(days=i)
                        sprint = Sprint(
                            project_id=project.id,
                            task_category_id=category.id,
                            task_description=f"File test task {i+1}",
                            start_time=start_time,
                            end_time=start_time + timedelta(minutes=25),
                            duration_minutes=25,
                            planned_duration=25,
                            completed=True
                        )
                        session.add(sprint)
                    session.commit()
            finally:
                session.close()
        
        return db_manager, db_path


class DatabaseTestUtils:
    """Utility methods for database testing operations"""
    
    @staticmethod
    def count_records(db_manager: DatabaseManager, model_class) -> int:
        """Count records of a specific model type"""
        session = db_manager.get_session()
        try:
            return session.query(model_class).count()
        finally:
            session.close()
    
    @staticmethod
    def get_all_records(db_manager: DatabaseManager, model_class) -> List:
        """Get all records of a specific model type"""
        session = db_manager.get_session()
        try:
            return session.query(model_class).all()
        finally:
            session.close()
    
    @staticmethod
    def create_test_project(db_manager: DatabaseManager, name: str = "Test Project", 
                           color: str = "#ff0000") -> Project:
        """Create a test project or return existing one with same name"""
        session = db_manager.get_session()
        try:
            # Check if project already exists
            existing_project = session.query(Project).filter(Project.name == name).first()
            if existing_project:
                return existing_project
                
            project = Project(name=name, color=color)
            session.add(project)
            session.commit()
            session.refresh(project)
            return project
        finally:
            session.close()
    
    @staticmethod
    def create_test_category(db_manager: DatabaseManager, name: str = "Test Category",
                            color: str = "#00ff00") -> TaskCategory:
        """Create a test task category or return existing one with same name"""
        session = db_manager.get_session()
        try:
            # Check if category already exists
            existing_category = session.query(TaskCategory).filter(TaskCategory.name == name).first()
            if existing_category:
                return existing_category
                
            category = TaskCategory(name=name, color=color)
            session.add(category)
            session.commit()
            session.refresh(category)
            return category
        finally:
            session.close()
    
    @staticmethod
    def create_test_sprint(db_manager: DatabaseManager, project_id: int, 
                          category_id: int, description: str = "Test Sprint",
                          completed: bool = False) -> Sprint:
        """Create a test sprint"""
        session = db_manager.get_session()
        try:
            sprint = Sprint(
                project_id=project_id,
                task_category_id=category_id,
                task_description=description,
                start_time=datetime.now(),
                planned_duration=25,
                completed=completed
            )
            if completed:
                sprint.end_time = sprint.start_time + timedelta(minutes=25)
                sprint.duration_minutes = 25
                
            session.add(sprint)
            session.commit()
            session.refresh(sprint)
            return sprint
        finally:
            session.close()
    
    @staticmethod
    def verify_database_integrity(db_manager: DatabaseManager) -> bool:
        """Verify database foreign key constraints and data integrity"""
        session = db_manager.get_session()
        try:
            # Check that all sprints have valid project and category references
            sprints = session.query(Sprint).all()
            for sprint in sprints:
                if not sprint.project or not sprint.task_category:
                    return False
            
            # Check that all projects and categories are properly formed
            projects = session.query(Project).all()
            for project in projects:
                if not project.name or not project.color:
                    return False
                    
            categories = session.query(TaskCategory).all()
            for category in categories:
                if not category.name or not category.color:
                    return False
                    
            return True
        finally:
            session.close()
    
    @staticmethod
    def cleanup_file_db(db_path: str) -> None:
        """Clean up temporary database file"""
        if os.path.exists(db_path):
            os.unlink(db_path)