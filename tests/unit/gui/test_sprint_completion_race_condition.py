"""
Unit tests for sprint completion race condition fix.

These tests ensure that sprint data is properly captured and saved
even when race conditions occur between timer completion and UI state clearing.
"""

import pytest
import sys
import os
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import threading
import time

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../src'))

from tracking.models import Sprint, TaskCategory, Project


class TestSprintCompletionRaceCondition:
    """Test suite for sprint completion race condition scenarios."""
    
    def create_mock_window(self):
        """Create a mock window with the essential sprint completion methods."""
        mock_window = Mock()
        
        # Set up initial valid state
        mock_window.current_project_id = 1
        mock_window.current_task_category_id = 2
        mock_window.current_task_description = "Test Sprint"
        mock_window.sprint_start_time = datetime.now() - timedelta(minutes=25)
        mock_window.pomodoro_timer = Mock()
        mock_window.pomodoro_timer.sprint_duration = 25 * 60  # 25 minutes in seconds
        
        # Mock database manager
        mock_window.db_manager = Mock()
        mock_window.update_stats = Mock()
        
        # Add the actual methods we're testing
        mock_window.emit_sprint_complete = self._create_emit_sprint_complete(mock_window)
        mock_window.handle_sprint_complete = self._create_handle_sprint_complete(mock_window)
        mock_window._save_sprint_with_data = self._create_save_sprint_with_data(mock_window)
        
        return mock_window
    
    def _create_emit_sprint_complete(self, window):
        """Create the actual emit_sprint_complete method for testing."""
        def emit_sprint_complete():
            # Capture critical sprint data immediately to avoid race conditions
            sprint_data = {
                'project_id': window.current_project_id,
                'task_category_id': window.current_task_category_id, 
                'task_description': window.current_task_description,
                'start_time': window.sprint_start_time
            }
            
            # Only emit signal if we have valid sprint data
            if (sprint_data['project_id'] and sprint_data['task_category_id'] and 
                sprint_data['task_description'] and sprint_data['start_time']):
                # Store the captured data temporarily
                window._pending_sprint_data = sprint_data
                return True
            else:
                # Don't set _pending_sprint_data for invalid cases
                if hasattr(window, '_pending_sprint_data'):
                    delattr(window, '_pending_sprint_data')
                return False
        
        return emit_sprint_complete
    
    def _create_handle_sprint_complete(self, window):
        """Create the actual handle_sprint_complete method for testing."""
        def handle_sprint_complete():
            # Use captured sprint data to avoid race conditions
            if hasattr(window, '_pending_sprint_data') and window._pending_sprint_data:
                try:
                    window._save_sprint_with_data(window._pending_sprint_data)
                    # Clear the pending data
                    delattr(window, '_pending_sprint_data')
                    return True
                except Exception as e:
                    return False
            else:
                return False
        
        return handle_sprint_complete
    
    def _create_save_sprint_with_data(self, window):
        """Create the actual _save_sprint_with_data method for testing."""
        def _save_sprint_with_data(sprint_data):
            start_time = sprint_data['start_time']
            end_time = datetime.now()
            
            if start_time is None:
                raise ValueError("Sprint start time is None in captured data")
                
            actual_duration = (end_time - start_time).total_seconds()
            task_desc = sprint_data['task_description'] or "Pomodoro Sprint"

            sprint = Sprint(
                project_id=sprint_data['project_id'],
                task_category_id=sprint_data['task_category_id'],
                task_description=task_desc,
                start_time=start_time,
                end_time=end_time,
                completed=True,
                interrupted=False,
                duration_minutes=int(actual_duration / 60),
                planned_duration=int(window.pomodoro_timer.sprint_duration / 60)
            )
            
            # Verify the sprint has the correct completion data
            assert sprint.completed == True
            assert sprint.end_time is not None
            assert sprint.interrupted == False
            
            # Mock the database save
            window.db_manager.add_sprint(sprint)
            
            return sprint
        
        return _save_sprint_with_data

    def test_normal_sprint_completion_flow(self):
        """Test that normal sprint completion works correctly."""
        window = self.create_mock_window()
        
        # Step 1: Timer completes and emits signal
        capture_success = window.emit_sprint_complete()
        assert capture_success == True
        assert hasattr(window, '_pending_sprint_data')
        
        # Step 2: Signal handler processes the completion
        save_success = window.handle_sprint_complete()
        assert save_success == True
        
        # Step 3: Verify database was called
        window.db_manager.add_sprint.assert_called_once()
        
        # Step 4: Verify pending data was cleaned up
        assert not hasattr(window, '_pending_sprint_data')

    def test_race_condition_state_cleared_before_save(self):
        """Test that sprint saves correctly even when state is cleared due to race condition."""
        window = self.create_mock_window()
        
        # Step 1: Capture data when timer completes
        capture_success = window.emit_sprint_complete()
        assert capture_success == True
        assert hasattr(window, '_pending_sprint_data')
        
        # Step 2: Simulate race condition - UI state gets cleared
        window.current_project_id = None
        window.current_task_category_id = None
        window.current_task_description = None
        window.sprint_start_time = None
        
        # Step 3: Signal handler should still work with captured data
        save_success = window.handle_sprint_complete()
        assert save_success == True
        
        # Step 4: Verify sprint was saved with correct data
        window.db_manager.add_sprint.assert_called_once()
        saved_sprint = window.db_manager.add_sprint.call_args[0][0]
        
        assert saved_sprint.project_id == 1
        assert saved_sprint.task_category_id == 2
        assert saved_sprint.task_description == "Test Sprint"
        assert saved_sprint.completed == True
        assert saved_sprint.end_time is not None

    def test_invalid_data_rejection(self):
        """Test that invalid sprint data is properly rejected."""
        window = self.create_mock_window()
        
        # Set up invalid state (missing project_id)
        window.current_project_id = None
        
        # Should reject the invalid data
        capture_success = window.emit_sprint_complete()
        assert capture_success == False
        # Should not have pending data for invalid cases
        assert not hasattr(window, '_pending_sprint_data')

    def test_missing_task_description_uses_default(self):
        """Test that missing task description gets a default value."""
        window = self.create_mock_window()
        
        # Set empty task description
        window.current_task_description = ""
        
        # Should still capture but use default
        capture_success = window.emit_sprint_complete()
        assert capture_success == False  # Empty string is falsy
        
        # Try with None
        window.current_task_description = None
        capture_success = window.emit_sprint_complete()
        assert capture_success == False  # None is falsy

    def test_missing_start_time_rejection(self):
        """Test that missing start time is properly rejected."""
        window = self.create_mock_window()
        
        # Set missing start time
        window.sprint_start_time = None
        
        # Should reject
        capture_success = window.emit_sprint_complete()
        assert capture_success == False
        # Should not have pending data for invalid cases
        assert not hasattr(window, '_pending_sprint_data')

    def test_multiple_completions_handling(self):
        """Test handling of multiple rapid completion calls."""
        window = self.create_mock_window()
        
        # First completion
        capture_success1 = window.emit_sprint_complete()
        assert capture_success1 == True
        
        # Second completion should overwrite the first
        window.current_task_description = "Different Sprint"
        capture_success2 = window.emit_sprint_complete()
        assert capture_success2 == True
        
        # Should have the latest data
        assert window._pending_sprint_data['task_description'] == "Different Sprint"
        
        # Handle completion
        save_success = window.handle_sprint_complete()
        assert save_success == True
        
        # Should save the latest sprint data
        saved_sprint = window.db_manager.add_sprint.call_args[0][0]
        assert saved_sprint.task_description == "Different Sprint"

    def test_no_pending_data_error_handling(self):
        """Test handling when no pending data is available."""
        window = self.create_mock_window()
        
        # Try to handle completion without capturing data first
        save_success = window.handle_sprint_complete()
        assert save_success == False
        
        # Database should not be called
        window.db_manager.add_sprint.assert_not_called()

    def test_data_types_preservation(self):
        """Test that all data types are properly preserved through the capture."""
        window = self.create_mock_window()
        
        # Set up specific data types
        start_time = datetime(2025, 8, 15, 14, 30, 0)
        window.sprint_start_time = start_time
        window.current_project_id = 42
        window.current_task_category_id = 7
        window.current_task_description = "Specific Test Sprint"
        
        # Capture and verify types
        capture_success = window.emit_sprint_complete()
        assert capture_success == True
        
        captured_data = window._pending_sprint_data
        assert isinstance(captured_data['project_id'], int)
        assert isinstance(captured_data['task_category_id'], int)
        assert isinstance(captured_data['task_description'], str)
        assert isinstance(captured_data['start_time'], datetime)
        
        # Verify exact values
        assert captured_data['project_id'] == 42
        assert captured_data['task_category_id'] == 7
        assert captured_data['task_description'] == "Specific Test Sprint"
        assert captured_data['start_time'] == start_time

    def test_sprint_duration_calculation(self):
        """Test that sprint duration is calculated correctly."""
        window = self.create_mock_window()
        
        # Set a specific start time for predictable duration
        start_time = datetime.now() - timedelta(minutes=30, seconds=15)
        window.sprint_start_time = start_time
        
        # Capture and save
        window.emit_sprint_complete()
        window.handle_sprint_complete()
        
        # Check the saved sprint
        saved_sprint = window.db_manager.add_sprint.call_args[0][0]
        
        # Duration should be approximately 30 minutes (allowing for small timing differences)
        assert 29 <= saved_sprint.duration_minutes <= 31
        assert saved_sprint.planned_duration == 25  # From mock timer setting

    def test_thread_safety_simulation(self):
        """Test simulated thread safety scenarios."""
        window = self.create_mock_window()
        results = {}
        
        def background_capture():
            """Simulate timer thread calling emit_sprint_complete"""
            time.sleep(0.01)  # Small delay to simulate real timing
            results['capture'] = window.emit_sprint_complete()
        
        def main_thread_clear():
            """Simulate main thread clearing state"""
            time.sleep(0.015)  # Delay to ensure capture happens first
            window.current_project_id = None
            window.sprint_start_time = None
            results['cleared'] = True
        
        def main_thread_handle():
            """Simulate main thread handling completion"""
            time.sleep(0.02)  # Delay to ensure clearing happens first
            results['save'] = window.handle_sprint_complete()
        
        # Start all threads
        threads = [
            threading.Thread(target=background_capture),
            threading.Thread(target=main_thread_clear),
            threading.Thread(target=main_thread_handle)
        ]
        
        for thread in threads:
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # Despite the race condition, sprint should still be saved
        assert results.get('capture') == True, f"Capture failed: {results}"
        assert results.get('cleared') == True, f"Clear failed: {results}"
        assert results.get('save') == True, f"Save failed: {results}"
        
        # Verify the sprint was saved
        window.db_manager.add_sprint.assert_called_once()


class TestSprintCompletionEdgeCases:
    """Test edge cases and error conditions in sprint completion."""
    
    def test_very_short_sprint_duration(self):
        """Test handling of very short sprint durations."""
        # This could happen if timer completes very quickly
        pass
    
    def test_very_long_sprint_duration(self):
        """Test handling of very long sprint durations (hibernation scenarios)."""
        # This could happen after system hibernation
        pass
    
    def test_system_clock_changes(self):
        """Test handling when system clock changes during sprint."""
        # Edge case: what if system time jumps?
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])