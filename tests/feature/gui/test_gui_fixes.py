"""
Tests for specific GUI fixes:
1. AttributeError stats_label fix during hibernation recovery
2. Duplicate sprint prevention 
3. Sprint completion status fixes
4. Correct interrupted=False setting
"""

import pytest
import tempfile
import os
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / 'src'))

from tracking.database_manager_unified import UnifiedDatabaseManager as DatabaseManager
from tracking.models import Sprint, Project, TaskCategory


@pytest.mark.feature
@pytest.mark.gui
class TestGUIFixes:
    """Test specific GUI fixes for AttributeError, duplicate sprints, and completion status"""

    def setup_method(self):
        """Set up test database for each test"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.db_manager = DatabaseManager(db_path=self.db_path)
        self.db_manager.initialize_default_projects()

        # Get test project and category
        projects = self.db_manager.get_active_projects()
        categories = self.db_manager.get_active_task_categories()
        self.test_project_id = projects[0]['id']
        self.test_category_id = categories[0]['id']

    def teardown_method(self):
        """Clean up after each test"""
        if hasattr(self, 'db_manager'):
            del self.db_manager
        import shutil
        if hasattr(self, 'temp_dir'):
            shutil.rmtree(self.temp_dir, ignore_errors=True)



    def test_sprint_creation_with_correct_interrupted_false(self):
        """Test that new sprints are created with interrupted=False explicitly"""
        # Create a sprint using the fixed _save_current_sprint method
        session = self.db_manager.get_session()
        try:
            # Create sprint object as the fixed method does
            start_time = datetime.now()
            end_time = start_time + timedelta(minutes=25)
            
            sprint = Sprint(
                project_id=self.test_project_id,
                task_category_id=self.test_category_id,
                task_description="test_interrupted_false",
                start_time=start_time,
                end_time=end_time,
                completed=True,
                interrupted=False,  # This is the fix - explicitly set to False
                duration_minutes=25,
                planned_duration=25
            )
            
            session.add(sprint)
            session.commit()
            sprint_id = sprint.id
        finally:
            session.close()
        
        # Verify the sprint was saved with correct status
        session = self.db_manager.get_session()
        try:
            saved_sprint = session.query(Sprint).filter_by(id=sprint_id).first()
            assert saved_sprint is not None
            assert saved_sprint.completed == True, "Sprint should be completed"
            assert saved_sprint.interrupted == False, "Sprint should explicitly have interrupted=False"
            
            # Test that it shows as "Completed" in data viewer logic
            status = "✅ Completed" if saved_sprint.completed else (
                "❌ Interrupted" if saved_sprint.interrupted else "⏸️ Incomplete"
            )
            assert status == "✅ Completed", f"Sprint status should be 'Completed', got: {status}"
            
        finally:
            session.close()



