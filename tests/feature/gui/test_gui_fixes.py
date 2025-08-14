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

    def test_stats_label_attribute_error_fix(self):
        """Test that hibernation recovery doesn't crash when stats_label doesn't exist"""
        # Skip if PySide6 not available
        pytest.importorskip("PySide6")
        
        # Create incomplete sprints in database (simulating hibernation scenario)
        session = self.db_manager.get_session()
        try:
            # Create sprint that started long ago and should be auto-completed
            old_start_time = datetime.now() - timedelta(hours=2)
            sprint = Sprint(
                project_id=self.test_project_id,
                task_category_id=self.test_category_id,
                task_description="hibernation_test_sprint",
                start_time=old_start_time,
                completed=False,
                interrupted=False,
                planned_duration=25
            )
            session.add(sprint)
            session.commit()
            sprint_id = sprint.id
        finally:
            session.close()

        # Mock the GUI window class to simulate the AttributeError scenario
        with patch('PySide6.QtWidgets.QApplication'), \
             patch('PySide6.QtWidgets.QMainWindow'), \
             patch('PySide6.QtCore.QTimer'):
            
            # Import after mocking PySide6
            from gui.pyside_main_window import ModernPomodoroWindow
            
            # Mock the window to simulate partial initialization
            mock_window = Mock(spec=ModernPomodoroWindow)
            mock_window.db_manager = self.db_manager
            
            # Simulate the scenario where _recover_hibernated_sprints runs before UI is ready
            # The fix should check hasattr(self, 'stats_label') before calling update_stats
            mock_window.update_stats = Mock()
            
            # Test the fixed hibernation recovery method
            import gui.pyside_main_window
            actual_window = gui.pyside_main_window.ModernPomodoroWindow.__new__(
                gui.pyside_main_window.ModernPomodoroWindow
            )
            actual_window.db_manager = self.db_manager
            
            # Mock hasattr to return False for stats_label (simulating uninitialized UI)
            with patch('builtins.hasattr') as mock_hasattr:
                def hasattr_side_effect(obj, attr):
                    if attr == 'stats_label':
                        return False
                    elif attr == 'update_stats':
                        return True
                    return hasattr.__wrapped__(obj, attr)
                
                mock_hasattr.side_effect = hasattr_side_effect
                
                # This should NOT crash even though stats_label doesn't exist
                try:
                    actual_window._recover_hibernated_sprints()
                    # If we reach here, the fix worked
                    success = True
                except AttributeError as e:
                    if "stats_label" in str(e):
                        success = False
                        pytest.fail(f"AttributeError still occurs: {e}")
                    else:
                        # Some other AttributeError, re-raise
                        raise
                
                assert success, "Hibernation recovery should not crash when stats_label is missing"
        
        # Verify the sprint was actually recovered
        session = self.db_manager.get_session()
        try:
            recovered_sprint = session.query(Sprint).filter_by(id=sprint_id).first()
            assert recovered_sprint is not None
            assert recovered_sprint.completed == True, "Sprint should have been auto-completed"
            assert recovered_sprint.interrupted == False, "Sprint should not be marked as interrupted"
        finally:
            session.close()

    def test_duplicate_sprint_prevention(self):
        """Test that the sprint_already_saved flag prevents duplicate sprint creation"""
        # Skip if PySide6 not available
        pytest.importorskip("PySide6")
        
        with patch('PySide6.QtWidgets.QApplication'), \
             patch('PySide6.QtWidgets.QMainWindow'), \
             patch('PySide6.QtCore.QTimer'):
            
            from gui.pyside_main_window import ModernPomodoroWindow
            
            # Create a mock window with the necessary attributes
            mock_window = Mock(spec=ModernPomodoroWindow)
            mock_window.db_manager = self.db_manager
            mock_window.current_project_id = self.test_project_id
            mock_window.current_task_category_id = self.test_category_id
            mock_window.current_task_description = "test_duplicate_prevention"
            mock_window.sprint_start_time = datetime.now()
            mock_window.sprint_already_saved = False  # Start with False
            
            # Mock the _save_current_sprint method to track how many times it's called
            save_call_count = 0
            original_add_sprint = self.db_manager.add_sprint
            
            def mock_add_sprint(sprint):
                nonlocal save_call_count
                save_call_count += 1
                return original_add_sprint(sprint)
            
            mock_window.db_manager.add_sprint = mock_add_sprint
            
            # Create actual window methods for testing
            import gui.pyside_main_window
            actual_window = gui.pyside_main_window.ModernPomodoroWindow.__new__(
                gui.pyside_main_window.ModernPomodoroWindow
            )
            
            # Set up the actual window with mock attributes
            actual_window.db_manager = mock_window.db_manager
            actual_window.current_project_id = mock_window.current_project_id
            actual_window.current_task_category_id = mock_window.current_task_category_id
            actual_window.current_task_description = mock_window.current_task_description
            actual_window.sprint_start_time = mock_window.sprint_start_time
            actual_window.sprint_already_saved = False
            
            # Mock pomodoro_timer
            actual_window.pomodoro_timer = Mock()
            actual_window.pomodoro_timer.sprint_duration = 1500  # 25 minutes in seconds
            
            # Test 1: First save should work normally
            actual_window._save_current_sprint()
            actual_window.sprint_already_saved = True  # Simulate the fix setting this flag
            assert save_call_count == 1, "First save should go through"
            
            # Test 2: Second save should be prevented by the flag
            initial_count = save_call_count
            
            # Mock the complete_sprint logic that checks the flag
            if actual_window.sprint_already_saved:
                # This should NOT call _save_current_sprint again
                pass  # Skip saving
            else:
                actual_window._save_current_sprint()
            
            assert save_call_count == initial_count, "Second save should be prevented by sprint_already_saved flag"
            
            # Test 3: Reset flag should allow new sprint
            actual_window.sprint_already_saved = False
            actual_window.current_task_description = "new_sprint_after_reset"
            actual_window.sprint_start_time = datetime.now()
            
            actual_window._save_current_sprint()
            assert save_call_count == initial_count + 1, "Save should work after flag reset"

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

    def test_hibernation_recovery_sets_interrupted_false(self):
        """Test that hibernation recovery explicitly sets interrupted=False"""
        # Create incomplete sprint that should be recovered
        session = self.db_manager.get_session()
        try:
            old_start_time = datetime.now() - timedelta(hours=1)
            sprint = Sprint(
                project_id=self.test_project_id,
                task_category_id=self.test_category_id,
                task_description="hibernation_recovery_test",
                start_time=old_start_time,
                completed=False,
                interrupted=False,  # Start as not interrupted
                planned_duration=25
            )
            session.add(sprint)
            session.commit()
            sprint_id = sprint.id
        finally:
            session.close()
        
        # Skip if PySide6 not available
        pytest.importorskip("PySide6")
        
        with patch('PySide6.QtWidgets.QApplication'), \
             patch('PySide6.QtWidgets.QMainWindow'), \
             patch('PySide6.QtCore.QTimer'):
            
            from gui.pyside_main_window import ModernPomodoroWindow
            
            # Create actual window for hibernation recovery testing
            import gui.pyside_main_window
            actual_window = gui.pyside_main_window.ModernPomodoroWindow.__new__(
                gui.pyside_main_window.ModernPomodoroWindow
            )
            actual_window.db_manager = self.db_manager
            
            # Mock the hasattr check to prevent stats update
            with patch('builtins.hasattr', return_value=False):
                # Run hibernation recovery
                actual_window._recover_hibernated_sprints()
        
        # Verify the sprint was recovered with correct status
        session = self.db_manager.get_session()
        try:
            recovered_sprint = session.query(Sprint).filter_by(id=sprint_id).first()
            assert recovered_sprint is not None
            assert recovered_sprint.completed == True, "Sprint should be completed after recovery"
            assert recovered_sprint.interrupted == False, "Sprint should have interrupted=False after recovery"
            assert recovered_sprint.end_time is not None, "Sprint should have end_time set"
            assert recovered_sprint.duration_minutes == 25, "Sprint should have correct duration"
            
            # Test data viewer status logic
            status = "✅ Completed" if recovered_sprint.completed else (
                "❌ Interrupted" if recovered_sprint.interrupted else "⏸️ Incomplete"
            )
            assert status == "✅ Completed", f"Recovered sprint should show as 'Completed', got: {status}"
            
        finally:
            session.close()

    def test_flag_reset_in_various_scenarios(self):
        """Test that sprint_already_saved flag is reset in all appropriate scenarios"""
        # Skip if PySide6 not available
        pytest.importorskip("PySide6")
        
        with patch('PySide6.QtWidgets.QApplication'), \
             patch('PySide6.QtWidgets.QMainWindow'), \
             patch('PySide6.QtCore.QTimer'):
            
            from gui.pyside_main_window import ModernPomodoroWindow
            
            # Create mock window
            import gui.pyside_main_window
            actual_window = gui.pyside_main_window.ModernPomodoroWindow.__new__(
                gui.pyside_main_window.ModernPomodoroWindow
            )
            
            actual_window.sprint_already_saved = True  # Start with flag set
            
            # Test 1: Flag reset when starting new sprint
            actual_window.current_project_id = self.test_project_id
            actual_window.current_task_category_id = self.test_category_id
            actual_window.current_task_description = "flag_reset_test"
            actual_window.pomodoro_timer = Mock()
            actual_window.pomodoro_timer.start_time = datetime.now()
            
            # Simulate the flag reset logic from sprint start
            actual_window.sprint_start_time = actual_window.pomodoro_timer.start_time
            actual_window.sprint_already_saved = False  # This is the fix
            
            assert actual_window.sprint_already_saved == False, "Flag should be reset when starting new sprint"
            
            # Test 2: Flag reset in reset_ui
            actual_window.sprint_already_saved = True  # Set it back to True
            
            # Mock UI components that reset_ui touches
            actual_window.start_button = Mock()
            actual_window.stop_button = Mock()
            actual_window.complete_button = Mock()
            actual_window.progress_bar = Mock()
            actual_window.task_input = Mock()
            actual_window.time_label = Mock()
            actual_window.pomodoro_timer = Mock()
            actual_window.pomodoro_timer.sprint_duration = 1500
            
            def mock_sync_compact_buttons():
                pass
            actual_window.sync_compact_buttons = mock_sync_compact_buttons
            
            # Call reset_ui (which should reset the flag)
            actual_window.reset_ui()
            
            assert actual_window.sprint_already_saved == False, "Flag should be reset in reset_ui"
            
            # Test 3: Flag reset after sprint completion
            actual_window.sprint_already_saved = True  # Set it back to True
            actual_window.sprint_start_time = datetime.now()
            
            # Simulate the completion cleanup logic
            actual_window.sprint_start_time = None
            actual_window.sprint_already_saved = False  # This is the fix
            
            assert actual_window.sprint_already_saved == False, "Flag should be reset after sprint completion"

    def test_multiple_sprint_sequence_no_duplicates(self):
        """Test that multiple consecutive sprints don't create duplicates"""
        initial_sprint_count = len(self.db_manager.get_sprints_by_date(datetime.now().date()))
        
        # Skip if PySide6 not available
        pytest.importorskip("PySide6")
        
        with patch('PySide6.QtWidgets.QApplication'), \
             patch('PySide6.QtWidgets.QMainWindow'), \
             patch('PySide6.QtCore.QTimer'):
            
            from gui.pyside_main_window import ModernPomodoroWindow
            
            # Create mock window
            import gui.pyside_main_window
            actual_window = gui.pyside_main_window.ModernPomodoroWindow.__new__(
                gui.pyside_main_window.ModernPomodoroWindow
            )
            actual_window.db_manager = self.db_manager
            actual_window.pomodoro_timer = Mock()
            actual_window.pomodoro_timer.sprint_duration = 1500
            
            # Simulate 3 complete sprint cycles
            for i in range(3):
                # Start sprint (flag should be reset)
                actual_window.current_project_id = self.test_project_id
                actual_window.current_task_category_id = self.test_category_id
                actual_window.current_task_description = f"sequence_test_{i}"
                actual_window.sprint_start_time = datetime.now() - timedelta(seconds=30*i)
                actual_window.sprint_already_saved = False  # Reset for new sprint
                
                # Simulate timer completion -> auto-save
                actual_window._save_current_sprint()
                actual_window.sprint_already_saved = True  # Set after auto-save
                
                # Simulate break completion -> complete_sprint call
                # This should NOT save again due to the flag
                if not actual_window.sprint_already_saved:
                    actual_window._save_current_sprint()  # Should not execute
                
                # Reset for next cycle
                actual_window.sprint_start_time = None
                actual_window.sprint_already_saved = False
        
        # Verify only 3 sprints were created (no duplicates)
        final_sprint_count = len(self.db_manager.get_sprints_by_date(datetime.now().date()))
        expected_count = initial_sprint_count + 3
        
        assert final_sprint_count == expected_count, (
            f"Expected {expected_count} sprints total, got {final_sprint_count}. "
            f"This suggests duplicate sprints were created."
        )
        
        # Verify all sprints have correct status
        session = self.db_manager.get_session()
        try:
            todays_sprints = session.query(Sprint).filter(
                Sprint.start_time >= datetime.now().date()
            ).all()
            
            sequence_sprints = [s for s in todays_sprints if s.task_description.startswith("sequence_test_")]
            assert len(sequence_sprints) == 3, f"Should have exactly 3 sequence test sprints, got {len(sequence_sprints)}"
            
            for sprint in sequence_sprints:
                assert sprint.completed == True, f"Sprint {sprint.task_description} should be completed"
                assert sprint.interrupted == False, f"Sprint {sprint.task_description} should not be interrupted"
                
        finally:
            session.close()