import unittest
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from tracking.models import DatabaseManager, Project, Sprint, Settings
from timer.pomodoro import PomodoroTimer, TimerState

class TestBasicFunctionality(unittest.TestCase):
    def setUp(self):
        """Set up test database"""
        self.db_manager = DatabaseManager(":memory:")  # In-memory database for testing
        self.db_manager.initialize_default_projects()
        self.db_manager.initialize_default_settings()
    
    def test_database_initialization(self):
        """Test database initialization"""
        session = self.db_manager.get_session()
        try:
            # Test projects were created
            projects = session.query(Project).all()
            self.assertGreater(len(projects), 0)
            
            # Test settings were created
            sprint_duration = Settings.get_setting(session, "sprint_duration", 0)
            self.assertEqual(sprint_duration, 25)
        finally:
            session.close()
    
    def test_project_creation(self):
        """Test project creation"""
        session = self.db_manager.get_session()
        try:
            project = Project(name="Test Project", color="#ff0000")
            session.add(project)
            session.commit()
            
            retrieved = session.query(Project).filter(Project.name == "Test Project").first()
            self.assertIsNotNone(retrieved)
            self.assertEqual(retrieved.color, "#ff0000")
        finally:
            session.close()
    
    def test_sprint_creation(self):
        """Test sprint creation"""
        from datetime import datetime
        
        session = self.db_manager.get_session()
        try:
            sprint = Sprint(
                project_name="Test Project",
                task_description="Test task",
                start_time=datetime.now(),
                planned_duration=25
            )
            session.add(sprint)
            session.commit()
            
            retrieved = session.query(Sprint).filter(Sprint.project_name == "Test Project").first()
            self.assertIsNotNone(retrieved)
            self.assertEqual(retrieved.task_description, "Test task")
        finally:
            session.close()
    
    def test_pomodoro_timer(self):
        """Test pomodoro timer basic functionality"""
        timer = PomodoroTimer(sprint_duration=1, break_duration=1)  # 1 minute for testing
        
        # Initial state should be stopped
        self.assertEqual(timer.get_state(), TimerState.STOPPED)
        self.assertEqual(timer.get_time_remaining(), 0)
        
        # Test timer duration setting
        timer.set_durations(2, 1)
        self.assertEqual(timer.sprint_duration, 120)  # 2 minutes in seconds
        self.assertEqual(timer.break_duration, 60)    # 1 minute in seconds

if __name__ == '__main__':
    unittest.main()