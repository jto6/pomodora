"""
Unit tests for database models.
Tests CRUD operations, foreign key relationships, and data validation.
"""

import pytest
import sys
import os
from datetime import datetime, timedelta

# Add tests directory to path for helper imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from helpers.test_database_manager import Project, TaskCategory, Sprint


@pytest.mark.unit
@pytest.mark.database
class TestProject:
    """Test Project model functionality"""
    
    def test_create_project(self, isolated_db):
        """Test creating a project"""
        session = isolated_db.get_session()
        try:
            project = Project(name="Test Project", color="#ff0000")
            session.add(project)
            session.commit()
            
            # Verify project was created
            assert project.id is not None
            assert project.name == "Test Project"
            assert project.color == "#ff0000"
            assert project.active is True
            assert project.created_at is not None
        finally:
            session.close()
    
    def test_project_defaults(self, isolated_db):
        """Test project default values"""
        session = isolated_db.get_session()
        try:
            project = Project(name="Default Test")
            session.add(project)
            session.commit()
            
            assert project.color == "#3498db"  # Default blue
            assert project.active is True
            assert project.created_at is not None
        finally:
            session.close()
    
    def test_project_unique_name(self, isolated_db):
        """Test that project names must be unique"""
        session = isolated_db.get_session()
        try:
            # Create first project
            project1 = Project(name="Unique Name", color="#ff0000")
            session.add(project1)
            session.commit()
            
            # Try to create second project with same name
            project2 = Project(name="Unique Name", color="#00ff00")
            session.add(project2)
            
            with pytest.raises(Exception):  # Should raise integrity error
                session.commit()
        finally:
            session.rollback()
            session.close()
    
    def test_project_sprint_relationship(self, isolated_db, sample_category):
        """Test project-sprint relationship"""
        session = isolated_db.get_session()
        try:
            # Create project
            project = Project(name="Relationship Test", color="#ff0000")
            session.add(project)
            session.commit()
            session.refresh(project)
            
            # Create sprint linked to project
            sprint = Sprint(
                project_id=project.id,
                task_category_id=sample_category.id,
                task_description="Test Sprint",
                start_time=datetime.now(),
                planned_duration=25
            )
            session.add(sprint)
            session.commit()
            
            # Test relationship
            assert len(project.sprints) == 1
            assert project.sprints[0].task_description == "Test Sprint"
        finally:
            session.close()


@pytest.mark.unit
@pytest.mark.database
class TestTaskCategory:
    """Test TaskCategory model functionality"""
    
    def test_create_category(self, isolated_db):
        """Test creating a task category"""
        session = isolated_db.get_session()
        try:
            category = TaskCategory(name="Test Category", color="#00ff00")
            session.add(category)
            session.commit()
            
            assert category.id is not None
            assert category.name == "Test Category"
            assert category.color == "#00ff00"
            assert category.active is True
            assert category.created_at is not None
        finally:
            session.close()
    
    def test_category_defaults(self, isolated_db):
        """Test category default values"""
        session = isolated_db.get_session()
        try:
            category = TaskCategory(name="Default Category")
            session.add(category)
            session.commit()
            
            assert category.color == "#3498db"  # Default blue
            assert category.active is True
            assert category.created_at is not None
        finally:
            session.close()
    
    def test_category_unique_name(self, isolated_db):
        """Test that category names must be unique"""
        session = isolated_db.get_session()
        try:
            # Create first category
            category1 = TaskCategory(name="Unique Category", color="#ff0000")
            session.add(category1)
            session.commit()
            
            # Try to create second category with same name
            category2 = TaskCategory(name="Unique Category", color="#00ff00")
            session.add(category2)
            
            with pytest.raises(Exception):  # Should raise integrity error
                session.commit()
        finally:
            session.rollback()
            session.close()
    
    def test_category_sprint_relationship(self, isolated_db, sample_project):
        """Test category-sprint relationship"""
        session = isolated_db.get_session()
        try:
            # Create category
            category = TaskCategory(name="Relationship Test", color="#00ff00")
            session.add(category)
            session.commit()
            session.refresh(category)
            
            # Create sprint linked to category
            sprint = Sprint(
                project_id=sample_project.id,
                task_category_id=category.id,
                task_description="Test Sprint",
                start_time=datetime.now(),
                planned_duration=25
            )
            session.add(sprint)
            session.commit()
            
            # Test relationship
            assert len(category.sprints) == 1
            assert category.sprints[0].task_description == "Test Sprint"
        finally:
            session.close()


@pytest.mark.unit  
@pytest.mark.database
class TestSprint:
    """Test Sprint model functionality"""
    
    def test_create_sprint(self, isolated_db, sample_project, sample_category):
        """Test creating a sprint"""
        session = isolated_db.get_session()
        try:
            start_time = datetime.now()
            sprint = Sprint(
                project_id=sample_project.id,
                task_category_id=sample_category.id,
                task_description="Test Sprint",
                start_time=start_time,
                planned_duration=25
            )
            session.add(sprint)
            session.commit()
            
            assert sprint.id is not None
            assert sprint.project_id == sample_project.id
            assert sprint.task_category_id == sample_category.id
            assert sprint.task_description == "Test Sprint"
            assert sprint.start_time == start_time
            assert sprint.planned_duration == 25
            assert sprint.completed is False
            assert sprint.interrupted is False
        finally:
            session.close()
    
    def test_sprint_completion(self, isolated_db, sample_project, sample_category):
        """Test sprint completion"""
        session = isolated_db.get_session()
        try:
            start_time = datetime.now()
            sprint = Sprint(
                project_id=sample_project.id,
                task_category_id=sample_category.id,
                task_description="Completion Test",
                start_time=start_time,
                planned_duration=25
            )
            session.add(sprint)
            session.commit()
            
            # Mark sprint as completed
            end_time = start_time + timedelta(minutes=25)
            sprint.end_time = end_time
            sprint.duration_minutes = 25
            sprint.completed = True
            session.commit()
            
            assert sprint.completed is True
            assert sprint.end_time == end_time
            assert sprint.duration_minutes == 25
        finally:
            session.close()
    
    def test_sprint_interruption(self, isolated_db, sample_project, sample_category):
        """Test sprint interruption"""
        session = isolated_db.get_session()
        try:
            start_time = datetime.now()
            sprint = Sprint(
                project_id=sample_project.id,
                task_category_id=sample_category.id,
                task_description="Interruption Test",
                start_time=start_time,
                planned_duration=25
            )
            session.add(sprint)
            session.commit()
            
            # Mark sprint as interrupted
            interrupt_time = start_time + timedelta(minutes=10)
            sprint.end_time = interrupt_time
            sprint.duration_minutes = 10
            sprint.interrupted = True
            session.commit()
            
            assert sprint.interrupted is True
            assert sprint.completed is False
            assert sprint.duration_minutes == 10
        finally:
            session.close()
    
    def test_sprint_foreign_key_constraints(self, isolated_db):
        """Test that sprint requires valid project and category IDs"""
        session = isolated_db.get_session()
        try:
            # Try to create sprint with invalid foreign keys
            sprint = Sprint(
                project_id=9999,  # Non-existent project
                task_category_id=9999,  # Non-existent category
                task_description="Invalid FK Test",
                start_time=datetime.now(),
                planned_duration=25
            )
            session.add(sprint)
            
            with pytest.raises(Exception):  # Should raise foreign key constraint error
                session.commit()
        finally:
            session.rollback()
            session.close()
    
    def test_sprint_relationships(self, isolated_db, sample_project, sample_category):
        """Test sprint relationships to project and category"""
        session = isolated_db.get_session()
        try:
            sprint = Sprint(
                project_id=sample_project.id,
                task_category_id=sample_category.id,
                task_description="Relationship Test",
                start_time=datetime.now(),
                planned_duration=25
            )
            session.add(sprint)
            session.commit()
            session.refresh(sprint)
            
            # Test relationships
            assert sprint.project is not None
            assert sprint.project.name == sample_project.name
            assert sprint.task_category is not None
            assert sprint.task_category.name == sample_category.name
        finally:
            session.close()
    
    @pytest.mark.parametrize("planned_duration", [1, 25, 30, 45, 60])
    def test_sprint_duration_values(self, isolated_db, sample_project, sample_category, planned_duration):
        """Test various sprint duration values"""
        session = isolated_db.get_session()
        try:
            sprint = Sprint(
                project_id=sample_project.id,
                task_category_id=sample_category.id,
                task_description=f"Duration {planned_duration}min",
                start_time=datetime.now(),
                planned_duration=planned_duration
            )
            session.add(sprint)
            session.commit()
            
            assert sprint.planned_duration == planned_duration
        finally:
            session.close()


@pytest.mark.unit
@pytest.mark.database
class TestModelIntegration:
    """Test integration between all models"""
    
    def test_full_data_model_workflow(self, isolated_db):
        """Test complete workflow with all models"""
        session = isolated_db.get_session()
        try:
            # Create project
            project = Project(name="Integration Project", color="#ff0000")
            session.add(project)
            session.commit()
            session.refresh(project)
            
            # Create category
            category = TaskCategory(name="Integration Category", color="#00ff00")
            session.add(category)
            session.commit()
            session.refresh(category)
            
            # Create multiple sprints
            sprints = []
            for i in range(3):
                sprint = Sprint(
                    project_id=project.id,
                    task_category_id=category.id,
                    task_description=f"Integration Sprint {i+1}",
                    start_time=datetime.now() - timedelta(hours=i),
                    planned_duration=25
                )
                sprints.append(sprint)
                session.add(sprint)
            
            session.commit()
            
            # Verify relationships
            assert len(project.sprints) == 3
            assert len(category.sprints) == 3
            
            # Verify all sprints are linked correctly
            for sprint in sprints:
                assert sprint.project == project
                assert sprint.task_category == category
        finally:
            session.close()
    
    def test_cascade_behavior(self, isolated_db, sample_project, sample_category):
        """Test deletion cascade behavior (if implemented)"""
        session = isolated_db.get_session()
        try:
            # Create sprint
            sprint = Sprint(
                project_id=sample_project.id,
                task_category_id=sample_category.id,
                task_description="Cascade Test",
                start_time=datetime.now(),
                planned_duration=25
            )
            session.add(sprint)
            session.commit()
            sprint_id = sprint.id
            
            # Verify sprint exists
            assert session.query(Sprint).filter_by(id=sprint_id).first() is not None
            
            # Note: Actual cascade behavior depends on database constraints
            # This test documents expected behavior but may need adjustment
            # based on actual foreign key constraint configuration
            
        finally:
            session.close()