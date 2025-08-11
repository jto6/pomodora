"""
Basic functionality tests - Updated for current schema.
Legacy test file updated to work with modern database model and pytest infrastructure.
"""
import pytest
import sys
import os
from datetime import datetime

# Add src to path for compatibility
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from tracking.models import DatabaseManager, Project, TaskCategory, Sprint
from timer.pomodoro import PomodoroTimer, TimerState


@pytest.mark.unit
@pytest.mark.database
class TestBasicFunctionality:
    """Updated basic functionality tests using pytest"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test database - using pytest fixture pattern"""
        self.db_manager = DatabaseManager(":memory:")
        self.db_manager.initialize_default_projects()
        yield
        if hasattr(self.db_manager, 'session') and self.db_manager.session:
            self.db_manager.session.close()
    
    def test_database_initialization(self):
        """Test database initialization with current schema"""
        session = self.db_manager.get_session()
        try:
            # Test projects were created
            projects = session.query(Project).all()
            assert len(projects) > 0
            
            # Test categories were created  
            categories = session.query(TaskCategory).all()
            assert len(categories) > 0
            
            # Verify default project exists
            default_project = session.query(Project).filter_by(name="General").first()
            assert default_project is not None
        finally:
            session.close()
    
    def test_project_creation(self):
        """Test project creation with current schema"""
        session = self.db_manager.get_session()
        try:
            project = Project(name="Test Project", color="#ff0000")
            session.add(project)
            session.commit()
            
            retrieved = session.query(Project).filter(Project.name == "Test Project").first()
            assert retrieved is not None
            assert retrieved.color == "#ff0000"
            assert retrieved.active is True  # Default value
            assert retrieved.created_at is not None
        finally:
            session.close()
    
    def test_task_category_creation(self):
        """Test task category creation"""
        session = self.db_manager.get_session()
        try:
            category = TaskCategory(name="Test Category", color="#00ff00")
            session.add(category)
            session.commit()
            
            retrieved = session.query(TaskCategory).filter(TaskCategory.name == "Test Category").first()
            assert retrieved is not None
            assert retrieved.color == "#00ff00"
            assert retrieved.active is True
            assert retrieved.created_at is not None
        finally:
            session.close()
    
    def test_sprint_creation_current_schema(self):
        """Test sprint creation with current foreign key schema"""
        session = self.db_manager.get_session()
        try:
            # Get first available project and category
            project = session.query(Project).first()
            category = session.query(TaskCategory).first()
            
            assert project is not None, "No projects found in database"
            assert category is not None, "No categories found in database"
            
            # Create sprint with proper foreign keys
            sprint = Sprint(
                project_id=project.id,
                task_category_id=category.id,
                task_description="Test task",
                start_time=datetime.now(),
                planned_duration=25
            )
            session.add(sprint)
            session.commit()
            
            # Retrieve and verify
            retrieved = session.query(Sprint).filter(Sprint.task_description == "Test task").first()
            assert retrieved is not None
            assert retrieved.project_id == project.id
            assert retrieved.task_category_id == category.id
            assert retrieved.planned_duration == 25
            assert retrieved.completed is False  # Default value
            assert retrieved.interrupted is False  # Default value
        finally:
            session.close()
    
    def test_sprint_relationships(self):
        """Test sprint relationships to project and category"""
        session = self.db_manager.get_session()
        try:
            project = session.query(Project).first()
            category = session.query(TaskCategory).first()
            
            sprint = Sprint(
                project_id=project.id,
                task_category_id=category.id,
                task_description="Relationship test",
                start_time=datetime.now(),
                planned_duration=25
            )
            session.add(sprint)
            session.commit()
            session.refresh(sprint)
            
            # Test relationships work
            assert sprint.project is not None
            assert sprint.project.name == project.name
            assert sprint.task_category is not None
            assert sprint.task_category.name == category.name
            
            # Test reverse relationships
            assert len(project.sprints) >= 1
            assert len(category.sprints) >= 1
        finally:
            session.close()
    
    def test_pomodoro_timer_basic(self):
        """Test pomodoro timer basic functionality"""
        timer = PomodoroTimer(sprint_duration=1, break_duration=1)  # 1 minute for testing
        
        # Initial state should be stopped
        assert timer.get_state() == TimerState.STOPPED
        assert timer.get_time_remaining() == 0
        
        # Test timer duration setting
        timer.set_durations(2, 1)
        assert timer.sprint_duration == 120  # 2 minutes in seconds
        assert timer.break_duration == 60    # 1 minute in seconds
    
    def test_pomodoro_timer_state_transitions(self):
        """Test timer state transitions"""
        timer = PomodoroTimer(sprint_duration=1, break_duration=1)
        
        # Start sprint
        timer.start_sprint()
        assert timer.get_state() == TimerState.RUNNING
        assert timer.get_time_remaining() == 60
        
        # Pause
        timer.pause()
        assert timer.get_state() == TimerState.PAUSED
        
        # Resume  
        timer.resume()
        assert timer.get_state() == TimerState.RUNNING
        
        # Stop
        timer.stop()
        assert timer.get_state() == TimerState.STOPPED
        assert timer.get_time_remaining() == 0


# Keep unittest compatibility for backward compatibility
import unittest

class TestBasicFunctionalityUnittest(unittest.TestCase):
    """Unittest version for backward compatibility"""
    
    def setUp(self):
        """Set up test database"""
        self.db_manager = DatabaseManager(":memory:")
        self.db_manager.initialize_default_categories()  
        self.db_manager.initialize_default_projects()
    
    def tearDown(self):
        """Clean up"""
        if hasattr(self.db_manager, 'session') and self.db_manager.session:
            self.db_manager.session.close()
    
    def test_basic_timer_functionality(self):
        """Test basic timer functionality"""
        timer = PomodoroTimer(sprint_duration=1, break_duration=1)
        
        # Initial state
        self.assertEqual(timer.get_state(), TimerState.STOPPED)
        self.assertEqual(timer.get_time_remaining(), 0)
        
        # Start and stop
        timer.start_sprint()
        self.assertEqual(timer.get_state(), TimerState.RUNNING)
        timer.stop()
        self.assertEqual(timer.get_state(), TimerState.STOPPED)

if __name__ == '__main__':
    unittest.main()