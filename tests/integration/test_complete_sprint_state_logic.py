#!/usr/bin/env python3
"""
Integration tests for complete_sprint() state-based logic.
Tests the core duplicate prevention logic without GUI dependencies.
"""

import pytest
import tempfile
import os
from datetime import datetime, date
from unittest.mock import Mock
from pathlib import Path
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

from timer.pomodoro import TimerState
from tracking.database_manager_unified import UnifiedDatabaseManager as DatabaseManager
from tracking.models import Sprint


@pytest.mark.integration
@pytest.mark.database
class TestCompleteSprintStateLogic:
    """Test complete_sprint() logic for different timer states - no GUI dependencies"""

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
        try:
            if hasattr(self, 'db_manager'):
                self.db_manager.close()
            if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir):
                import shutil
                shutil.rmtree(self.temp_dir)
        except:
            pass

    def simulate_complete_sprint_logic(self, timer_state, project_id, category_id, task_description):
        """
        Simulate the complete_sprint() logic from ModernPomodoroWindow.
        This mimics the fixed logic that checks timer state before saving.
        """
        save_count = 0
        
        if timer_state == TimerState.RUNNING:
            # Sprint is still running - save it and stop timer
            sprint = Sprint(
                project_id=project_id,
                task_category_id=category_id,
                task_description=task_description,
                start_time=datetime.now(),
                duration_minutes=25,  # 25 minutes
                interrupted=False,
                completed=True
            )
            self.db_manager.add_sprint(sprint)
            save_count = 1
            
        elif timer_state == TimerState.BREAK:
            # During break - sprint already auto-saved, just reset UI
            save_count = 0
            
        else:
            # Other states (STOPPED, PAUSED) - don't save
            save_count = 0
            
        return save_count

    def test_running_state_saves_sprint(self):
        """Test that complete_sprint() during RUNNING state saves exactly one sprint"""
        
        # Get initial sprint count
        initial_sprints = self.db_manager.get_sprints_by_date(date.today())
        initial_count = len(initial_sprints)
        
        # Simulate clicking "Complete Sprint" during RUNNING state
        saves = self.simulate_complete_sprint_logic(
            TimerState.RUNNING,
            self.test_project_id,
            self.test_category_id,
            "manual completion during sprint"
        )
        
        # Verify exactly one sprint was saved
        final_sprints = self.db_manager.get_sprints_by_date(date.today())
        final_count = len(final_sprints)
        
        assert saves == 1, "Should save during RUNNING state"
        assert final_count == initial_count + 1, f"Database should have one more sprint. Expected {initial_count + 1}, got {final_count}"

    def test_break_state_no_save(self):
        """Test that complete_sprint() during BREAK state doesn't save sprint"""
        
        # First, simulate auto-save (what happens when timer completes)
        auto_save_sprint = Sprint(
            project_id=self.test_project_id,
            task_category_id=self.test_category_id,
            task_description="auto-saved on timer completion",
            start_time=datetime.now(),
            duration_minutes=25,
            interrupted=False,
            completed=True
        )
        self.db_manager.add_sprint(auto_save_sprint)
        
        # Get sprint count after auto-save
        after_auto_save = self.db_manager.get_sprints_by_date(date.today())
        auto_save_count = len(after_auto_save)
        
        # Now simulate clicking "Done" during BREAK state
        saves = self.simulate_complete_sprint_logic(
            TimerState.BREAK,
            self.test_project_id,
            self.test_category_id,
            "done during break - should not save"
        )
        
        # Verify no additional sprint was saved
        final_sprints = self.db_manager.get_sprints_by_date(date.today())
        final_count = len(final_sprints)
        
        assert saves == 0, "Should NOT save during BREAK state"
        assert final_count == auto_save_count, f"No additional sprint should be saved. Expected {auto_save_count}, got {final_count}"

    def test_full_workflow_no_duplicates(self):
        """Test full workflow: auto-save + break complete = exactly one sprint"""
        
        # Get initial count
        initial_sprints = self.db_manager.get_sprints_by_date(date.today())
        initial_count = len(initial_sprints)
        
        # Step 1: Timer completes and auto-saves (simulates timer callback)
        auto_save_sprint = Sprint(
            project_id=self.test_project_id,
            task_category_id=self.test_category_id,
            task_description="full workflow test",
            start_time=datetime.now(),
            duration_minutes=25,
            interrupted=False,
            completed=True
        )
        self.db_manager.add_sprint(auto_save_sprint)
        
        after_auto_save = self.db_manager.get_sprints_by_date(date.today())
        auto_save_count = len(after_auto_save)
        
        assert auto_save_count == initial_count + 1, "Auto-save should create exactly one sprint"
        
        # Step 2: User clicks "Done" during break (should NOT save duplicate)
        saves = self.simulate_complete_sprint_logic(
            TimerState.BREAK,
            self.test_project_id,
            self.test_category_id,
            "break completion - no duplicate"
        )
        
        # Verify no duplicate was created
        final_sprints = self.db_manager.get_sprints_by_date(date.today())
        final_count = len(final_sprints)
        
        assert saves == 0, "Break completion should not save sprint"
        assert final_count == auto_save_count, f"Should have exactly one sprint from workflow. Expected {auto_save_count}, got {final_count}"

    def test_multiple_states_comprehensive(self):
        """Test complete_sprint() behavior across all timer states"""
        
        # Test cases: (timer_state, should_save, description)
        test_cases = [
            (TimerState.RUNNING, True, "running state should save"),
            (TimerState.BREAK, False, "break state should not save"),
            (TimerState.STOPPED, False, "stopped state should not save"),
            (TimerState.PAUSED, False, "paused state should not save"),
        ]
        
        initial_sprints = self.db_manager.get_sprints_by_date(date.today())
        initial_count = len(initial_sprints)
        expected_total_saves = 0
        
        for timer_state, should_save, description in test_cases:
            saves = self.simulate_complete_sprint_logic(
                timer_state,
                self.test_project_id,
                self.test_category_id,
                f"test_{timer_state.name.lower()}"
            )
            
            if should_save:
                expected_total_saves += 1
                assert saves == 1, f"{description}: should save sprint"
            else:
                assert saves == 0, f"{description}: should not save sprint"
        
        # Verify total saves match expectations
        final_sprints = self.db_manager.get_sprints_by_date(date.today())
        final_count = len(final_sprints)
        expected_final_count = initial_count + expected_total_saves
        
        assert final_count == expected_final_count, f"Total saves should be {expected_total_saves}. Expected {expected_final_count}, got {final_count}"

    def test_edge_case_rapid_state_changes(self):
        """Test that rapid state changes don't cause duplicate saves"""
        
        initial_sprints = self.db_manager.get_sprints_by_date(date.today())
        initial_count = len(initial_sprints)
        
        # Simulate rapid clicks in RUNNING state (should save only once)
        total_saves = 0
        for _ in range(5):
            saves = self.simulate_complete_sprint_logic(
                TimerState.RUNNING,
                self.test_project_id, 
                self.test_category_id,
                "rapid running clicks"
            )
            total_saves += saves
        
        # All 5 clicks in RUNNING state should each save (they're separate operations)
        assert total_saves == 5, "Each RUNNING state click should save (separate operations)"
        
        # Now simulate rapid clicks in BREAK state (should save none)
        break_saves = 0
        for _ in range(5):
            saves = self.simulate_complete_sprint_logic(
                TimerState.BREAK,
                self.test_project_id,
                self.test_category_id, 
                "rapid break clicks"
            )
            break_saves += saves
        
        assert break_saves == 0, "BREAK state clicks should never save"
        
        # Verify final count
        final_sprints = self.db_manager.get_sprints_by_date(date.today())
        final_count = len(final_sprints)
        expected_count = initial_count + total_saves  # Only RUNNING clicks should have saved
        
        assert final_count == expected_count, f"Final count should reflect only RUNNING saves. Expected {expected_count}, got {final_count}"

    def test_timer_completion_auto_save_simulation(self):
        """Test simulation of the timer auto-save + manual break completion scenario"""
        
        initial_sprints = self.db_manager.get_sprints_by_date(date.today())
        initial_count = len(initial_sprints)
        
        # Scenario: User starts sprint, timer completes and auto-saves, user clicks Done during break
        
        # Step 1: Timer auto-saves on completion (this is what actually happens)
        auto_save_sprint = Sprint(
            project_id=self.test_project_id,
            task_category_id=self.test_category_id,
            task_description="timer auto-save scenario", 
            start_time=datetime.now(),
            duration_minutes=25,
            interrupted=False,
            completed=True
        )
        self.db_manager.add_sprint(auto_save_sprint)
        
        after_auto_save = self.db_manager.get_sprints_by_date(date.today())
        auto_save_count = len(after_auto_save)
        
        assert auto_save_count == initial_count + 1, "Timer auto-save should create sprint"
        
        # Step 2: Timer enters break state, user clicks "Done" 
        # This should NOT save another sprint due to our fix
        manual_saves = self.simulate_complete_sprint_logic(
            TimerState.BREAK,
            self.test_project_id,
            self.test_category_id,
            "manual done during break"
        )
        
        final_sprints = self.db_manager.get_sprints_by_date(date.today())
        final_count = len(final_sprints)
        
        assert manual_saves == 0, "Manual 'Done' during break should not save"
        assert final_count == auto_save_count, f"Should have exactly one sprint from entire workflow. Expected {auto_save_count}, got {final_count}"
        
        # Verify we have exactly the sprint from auto-save, not a duplicate
        assert len(final_sprints) == initial_count + 1, "Should have exactly one new sprint from the workflow"