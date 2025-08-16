"""
Tests for sprint field preservation during add_sprint operations.
These tests verify that all Sprint object fields are preserved when saving to database.
"""

import pytest
import tempfile
import os
from datetime import datetime, timedelta
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / 'src'))

from tracking.database_manager_unified import UnifiedDatabaseManager
from tracking.models import Sprint
from utils.logging import set_verbose_level


@pytest.mark.unit
@pytest.mark.database
class TestSprintFieldPreservation:
    """Test that all Sprint fields are preserved during database operations"""

    def setup_method(self):
        """Set up test database for each test"""
        set_verbose_level(0)  # Quiet logging for tests
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.db_manager = UnifiedDatabaseManager(db_path=self.db_path)
        self.db_manager.initialize_default_projects()

        # Get test project and category
        projects = self.db_manager.get_active_projects()
        categories = self.db_manager.get_active_task_categories()
        self.test_project_id = projects[0]['id']
        self.test_category_id = categories[0]['id']

    def teardown_method(self):
        """Clean up after each test"""
        try:
            if hasattr(self, 'db_manager'):
                self.db_manager.close()
            if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
                import shutil
                shutil.rmtree(self.temp_dir)
        except:
            pass

    def test_completed_sprint_fields_preserved(self):
        """Test that completed sprint with end_time is saved correctly"""
        start_time = datetime.now() - timedelta(minutes=25)
        end_time = datetime.now()
        
        # Create completed sprint with all fields set
        sprint = Sprint(
            project_id=self.test_project_id,
            task_category_id=self.test_category_id,
            task_description="Completed Sprint Test",
            start_time=start_time,
            end_time=end_time,
            completed=True,
            interrupted=False,
            duration_minutes=25,
            planned_duration=25
        )
        
        # Verify fields before save
        assert sprint.end_time == end_time
        assert sprint.completed == True
        assert sprint.interrupted == False
        assert sprint.duration_minutes == 25
        
        # Save sprint
        saved_sprint = self.db_manager.add_sprint(sprint)
        assert saved_sprint is not None
        
        # Verify fields are preserved after save
        assert saved_sprint.end_time == end_time, f"end_time not preserved: expected {end_time}, got {saved_sprint.end_time}"
        assert saved_sprint.completed == True, f"completed not preserved: expected True, got {saved_sprint.completed}"
        assert saved_sprint.interrupted == False, f"interrupted not preserved: expected False, got {saved_sprint.interrupted}"
        assert saved_sprint.duration_minutes == 25, f"duration_minutes not preserved: expected 25, got {saved_sprint.duration_minutes}"
        
        # Verify by querying database directly
        session = self.db_manager.get_session()
        try:
            db_sprint = session.query(Sprint).filter_by(id=saved_sprint.id).first()
            assert db_sprint is not None
            assert db_sprint.end_time == end_time, "end_time not saved to database"
            assert db_sprint.completed == True, "completed not saved to database"
            assert db_sprint.interrupted == False, "interrupted not saved to database"
            assert db_sprint.duration_minutes == 25, "duration_minutes not saved to database"
        finally:
            session.close()

    def test_interrupted_sprint_fields_preserved(self):
        """Test that interrupted sprint fields are saved correctly"""
        start_time = datetime.now() - timedelta(minutes=10)
        end_time = datetime.now()
        
        # Create interrupted sprint
        sprint = Sprint(
            project_id=self.test_project_id,
            task_category_id=self.test_category_id,
            task_description="Interrupted Sprint Test",
            start_time=start_time,
            end_time=end_time,
            completed=False,
            interrupted=True,
            duration_minutes=10,
            planned_duration=25
        )
        
        # Save and verify
        saved_sprint = self.db_manager.add_sprint(sprint)
        assert saved_sprint is not None
        
        assert saved_sprint.end_time == end_time
        assert saved_sprint.completed == False
        assert saved_sprint.interrupted == True
        assert saved_sprint.duration_minutes == 10

    def test_incomplete_sprint_fields_preserved(self):
        """Test that incomplete sprint fields (no end_time) are saved correctly"""
        start_time = datetime.now() - timedelta(minutes=5)
        
        # Create incomplete sprint (no end_time)
        sprint = Sprint(
            project_id=self.test_project_id,
            task_category_id=self.test_category_id,
            task_description="Incomplete Sprint Test",
            start_time=start_time,
            end_time=None,  # No end time
            completed=False,
            interrupted=False,
            duration_minutes=None,  # No duration yet
            planned_duration=25
        )
        
        # Save and verify
        saved_sprint = self.db_manager.add_sprint(sprint)
        assert saved_sprint is not None
        
        assert saved_sprint.end_time is None
        assert saved_sprint.completed == False
        assert saved_sprint.interrupted == False
        assert saved_sprint.duration_minutes is None

    def test_all_sprint_fields_roundtrip(self):
        """Test that ALL sprint fields survive the save/load roundtrip"""
        start_time = datetime.now() - timedelta(minutes=30)
        end_time = datetime.now() - timedelta(minutes=5)
        
        # Create sprint with all possible field combinations
        original_sprint = Sprint(
            project_id=self.test_project_id,
            task_category_id=self.test_category_id,
            task_description="Complete Field Test Sprint",
            start_time=start_time,
            end_time=end_time,
            completed=True,
            interrupted=False,
            duration_minutes=25,
            planned_duration=25
        )
        
        # Capture original values
        original_values = {
            'project_id': original_sprint.project_id,
            'task_category_id': original_sprint.task_category_id,
            'task_description': original_sprint.task_description,
            'start_time': original_sprint.start_time,
            'end_time': original_sprint.end_time,
            'completed': original_sprint.completed,
            'interrupted': original_sprint.interrupted,
            'duration_minutes': original_sprint.duration_minutes,
            'planned_duration': original_sprint.planned_duration
        }
        
        # Save to database
        saved_sprint = self.db_manager.add_sprint(original_sprint)
        assert saved_sprint is not None
        
        # Verify ALL fields are preserved
        for field_name, original_value in original_values.items():
            saved_value = getattr(saved_sprint, field_name)
            assert saved_value == original_value, (
                f"Field '{field_name}' not preserved: "
                f"original={original_value}, saved={saved_value}"
            )
        
        # Double-check by reloading from database
        session = self.db_manager.get_session()
        try:
            reloaded_sprint = session.query(Sprint).filter_by(id=saved_sprint.id).first()
            assert reloaded_sprint is not None
            
            for field_name, original_value in original_values.items():
                reloaded_value = getattr(reloaded_sprint, field_name)
                assert reloaded_value == original_value, (
                    f"Field '{field_name}' not persisted to database: "
                    f"original={original_value}, reloaded={reloaded_value}"
                )
        finally:
            session.close()

    def test_hibernation_recovery_pattern_preserved(self):
        """Test the specific pattern used by hibernation recovery is preserved"""
        # This tests the exact pattern that was failing before the fix
        start_time = datetime.now() - timedelta(hours=1)
        calculated_end_time = start_time + timedelta(minutes=25)
        
        # Create sprint exactly as hibernation recovery does
        recovery_sprint = Sprint(
            project_id=self.test_project_id,
            task_category_id=self.test_category_id,
            task_description="Hibernation Recovery Pattern",
            start_time=start_time,
            end_time=calculated_end_time,  # Calculated end time
            completed=True,                 # Mark as completed
            interrupted=False,              # Explicitly set to False
            duration_minutes=25,            # Planned duration achieved
            planned_duration=25
        )
        
        # Save and verify the exact hibernation recovery pattern
        saved_sprint = self.db_manager.add_sprint(recovery_sprint)
        assert saved_sprint is not None
        
        # These assertions would have failed before the fix
        assert saved_sprint.end_time == calculated_end_time, "Hibernation recovery end_time lost"
        assert saved_sprint.completed == True, "Hibernation recovery completed status lost"
        assert saved_sprint.interrupted == False, "Hibernation recovery interrupted status lost"
        assert saved_sprint.duration_minutes == 25, "Hibernation recovery duration lost"
        
        # Verify this sprint would NOT be picked up by hibernation recovery query
        session = self.db_manager.get_session()
        try:
            incomplete_sprints = session.query(Sprint).filter(
                Sprint.completed == False,
                Sprint.interrupted == False,
                Sprint.start_time.isnot(None),
                Sprint.end_time.is_(None)
            ).filter(Sprint.id == saved_sprint.id).all()
            
            # This sprint should NOT match the hibernation recovery query
            assert len(incomplete_sprints) == 0, (
                "Hibernation recovery sprint should not match incomplete sprint query"
            )
        finally:
            session.close()

    def test_gui_sprint_completion_pattern_preserved(self):
        """Test the exact pattern used by GUI sprint completion"""
        # This simulates the exact Sprint object created by _save_current_sprint()
        # and _save_sprint_with_data() methods in the GUI
        
        start_time = datetime.now() - timedelta(minutes=25)
        end_time = datetime.now()
        actual_duration_seconds = (end_time - start_time).total_seconds()
        
        # Create sprint exactly as GUI does
        gui_sprint = Sprint(
            project_id=self.test_project_id,
            task_category_id=self.test_category_id,
            task_description="GUI Sprint Completion",
            start_time=start_time,
            end_time=end_time,                                    # Set by GUI
            completed=True,                                       # Always True for completed sprints
            interrupted=False,                                    # Always False for completed sprints
            duration_minutes=int(actual_duration_seconds / 60),   # Calculated by GUI
            planned_duration=25                                   # From settings
        )
        
        # Save using the same method the GUI uses
        saved_sprint = self.db_manager.add_sprint(gui_sprint)
        assert saved_sprint is not None
        
        # Verify GUI-created sprint fields are preserved
        assert saved_sprint.end_time == end_time, "GUI end_time lost during save"
        assert saved_sprint.completed == True, "GUI completed status lost during save"  
        assert saved_sprint.interrupted == False, "GUI interrupted status lost during save"
        assert saved_sprint.duration_minutes == int(actual_duration_seconds / 60), "GUI duration lost during save"
        
        # Verify this would appear correctly in data viewer
        status = "✅ Completed" if saved_sprint.completed else (
            "❌ Interrupted" if saved_sprint.interrupted else "⏸️ Incomplete"
        )
        assert status == "✅ Completed", "GUI sprint should show as completed in data viewer"
        
        # Verify duration calculation for data viewer  
        if saved_sprint.duration_minutes:
            duration_text = f"{saved_sprint.duration_minutes}m"
        else:
            duration_text = "N/A"
        assert duration_text != "N/A", "GUI sprint should have valid duration in data viewer"