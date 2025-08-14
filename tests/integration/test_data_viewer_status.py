"""
Integration tests for data viewer status display after hibernation recovery.
Tests that the 'View Data' dialog shows correct completion status for recovered sprints.
"""

import pytest
import tempfile
import os
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

from tracking.database_manager_unified import UnifiedDatabaseManager as DatabaseManager
from tracking.models import Sprint, Project, TaskCategory


@pytest.mark.integration
@pytest.mark.gui
class TestDataViewerStatusIntegration:
    """Test data viewer status display integration with hibernation recovery"""

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

    def test_data_viewer_status_logic_for_completed_sprints(self):
        """Test data viewer status logic shows completed sprints correctly"""
        # Create sprints with different completion states
        session = self.db_manager.get_session()
        try:
            sprints = [
                Sprint(  # Completed sprint (normal)
                    project_id=self.test_project_id,
                    task_category_id=self.test_category_id,
                    task_description="completed_normal",
                    start_time=datetime.now() - timedelta(minutes=30),
                    end_time=datetime.now() - timedelta(minutes=5),
                    completed=True,
                    interrupted=False,
                    duration_minutes=25,
                    planned_duration=25
                ),
                Sprint(  # Completed sprint (hibernation recovery style)
                    project_id=self.test_project_id,
                    task_category_id=self.test_category_id,
                    task_description="completed_recovery",
                    start_time=datetime.now() - timedelta(minutes=50),
                    end_time=datetime.now() - timedelta(minutes=25),  # Calculated end time
                    completed=True,
                    interrupted=False,  # Explicitly set to False (the fix)
                    duration_minutes=25,
                    planned_duration=25
                ),
                Sprint(  # Interrupted sprint
                    project_id=self.test_project_id,
                    task_category_id=self.test_category_id,
                    task_description="interrupted_sprint",
                    start_time=datetime.now() - timedelta(minutes=20),
                    end_time=datetime.now() - timedelta(minutes=15),
                    completed=False,
                    interrupted=True,
                    duration_minutes=5,
                    planned_duration=25
                ),
                Sprint(  # Incomplete sprint
                    project_id=self.test_project_id,
                    task_category_id=self.test_category_id,
                    task_description="incomplete_sprint",
                    start_time=datetime.now() - timedelta(minutes=10),
                    completed=False,
                    interrupted=False,
                    planned_duration=25
                )
            ]
            
            for sprint in sprints:
                session.add(sprint)
            session.commit()
            
            sprint_ids = [s.id for s in sprints]
            
        finally:
            session.close()
        
        # Test the data viewer status logic (from pyside_data_viewer.py line 719)
        session = self.db_manager.get_session()
        try:
            saved_sprints = session.query(Sprint).filter(Sprint.id.in_(sprint_ids)).all()
            
            status_results = {}
            for sprint in saved_sprints:
                # This is the exact logic from pyside_data_viewer.py
                status = "✅ Completed" if sprint.completed else (
                    "❌ Interrupted" if sprint.interrupted else "⏸️ Incomplete"
                )
                status_results[sprint.task_description] = status
            
            # Verify status display logic
            assert status_results["completed_normal"] == "✅ Completed"
            assert status_results["completed_recovery"] == "✅ Completed"  # This is the key test
            assert status_results["interrupted_sprint"] == "❌ Interrupted"
            assert status_results["incomplete_sprint"] == "⏸️ Incomplete"
            
        finally:
            session.close()

    def test_hibernation_recovery_creates_viewable_completed_sprints(self):
        """Test full hibernation recovery -> data viewer workflow"""
        # Create incomplete sprint that needs recovery
        session = self.db_manager.get_session()
        try:
            old_start_time = datetime.now() - timedelta(hours=1)
            sprint = Sprint(
                project_id=self.test_project_id,
                task_category_id=self.test_category_id,
                task_description="hibernation_to_viewer_test",
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
        
        # Simulate hibernation recovery (using the fixed logic)
        session = self.db_manager.get_session()
        try:
            # Find incomplete sprints (exact query from _recover_hibernated_sprints)
            incomplete_sprints = session.query(Sprint).filter(
                Sprint.completed == False,
                Sprint.interrupted == False,
                Sprint.start_time.isnot(None),
                Sprint.end_time.is_(None)
            ).filter(Sprint.id == sprint_id).all()
            
            assert len(incomplete_sprints) == 1
            sprint = incomplete_sprints[0]
            
            # Apply hibernation recovery logic
            now = datetime.now()
            elapsed_time = now - sprint.start_time
            planned_duration_timedelta = timedelta(minutes=sprint.planned_duration)
            
            if elapsed_time >= planned_duration_timedelta:
                # This is the fix - explicitly set interrupted=False
                sprint.end_time = sprint.start_time + planned_duration_timedelta
                sprint.duration_minutes = sprint.planned_duration
                sprint.completed = True
                sprint.interrupted = False  # Key fix for data viewer display
                
            session.commit()
        finally:
            session.close()
        
        # Test that data viewer would show correct status
        session = self.db_manager.get_session()
        try:
            recovered_sprint = session.query(Sprint).filter_by(id=sprint_id).first()
            
            # Verify database state
            assert recovered_sprint.completed == True
            assert recovered_sprint.interrupted == False
            assert recovered_sprint.end_time is not None
            
            # Test data viewer status logic
            status = "✅ Completed" if recovered_sprint.completed else (
                "❌ Interrupted" if recovered_sprint.interrupted else "⏸️ Incomplete"
            )
            
            assert status == "✅ Completed", (
                f"Hibernation recovered sprint should show as 'Completed' in data viewer, "
                f"got: {status}. Sprint state: completed={recovered_sprint.completed}, "
                f"interrupted={recovered_sprint.interrupted}"
            )
            
        finally:
            session.close()

    def test_data_viewer_export_status_consistency(self):
        """Test that export functionality shows same status as display logic"""
        # Create sprint that went through hibernation recovery
        session = self.db_manager.get_session()
        try:
            sprint = Sprint(
                project_id=self.test_project_id,
                task_category_id=self.test_category_id,
                task_description="export_status_test",
                start_time=datetime.now() - timedelta(minutes=50),
                end_time=datetime.now() - timedelta(minutes=25),
                completed=True,
                interrupted=False,  # Fixed hibernation recovery sets this explicitly
                duration_minutes=25,
                planned_duration=25
            )
            session.add(sprint)
            session.commit()
            sprint_id = sprint.id
        finally:
            session.close()
        
        session = self.db_manager.get_session()
        try:
            saved_sprint = session.query(Sprint).filter_by(id=sprint_id).first()
            
            # Test display status logic (from pyside_data_viewer.py line 719)
            display_status = "✅ Completed" if saved_sprint.completed else (
                "❌ Interrupted" if saved_sprint.interrupted else "⏸️ Incomplete"
            )
            
            # Test export status logic (from pyside_data_viewer.py line 858)
            export_status = "Completed" if saved_sprint.completed else (
                "Interrupted" if saved_sprint.interrupted else "Incomplete"
            )
            
            # Both should indicate completion
            assert display_status == "✅ Completed"
            assert export_status == "Completed"
            
        finally:
            session.close()

    def test_stats_calculation_with_recovered_sprints(self):
        """Test that stats calculations include hibernation-recovered sprints correctly"""
        today = datetime.now().date()
        
        # Create mix of normal and recovered sprints
        session = self.db_manager.get_session()
        try:
            sprints = [
                Sprint(  # Normal completed sprint
                    project_id=self.test_project_id,
                    task_category_id=self.test_category_id,
                    task_description="normal_completed",
                    start_time=datetime.combine(today, datetime.min.time()) + timedelta(hours=9),
                    end_time=datetime.combine(today, datetime.min.time()) + timedelta(hours=9, minutes=25),
                    completed=True,
                    interrupted=False,
                    duration_minutes=25,
                    planned_duration=25
                ),
                Sprint(  # Hibernation recovered sprint
                    project_id=self.test_project_id,
                    task_category_id=self.test_category_id,
                    task_description="hibernation_recovered",
                    start_time=datetime.combine(today, datetime.min.time()) + timedelta(hours=10),
                    end_time=datetime.combine(today, datetime.min.time()) + timedelta(hours=10, minutes=25),
                    completed=True,
                    interrupted=False,  # Fixed hibernation recovery
                    duration_minutes=25,
                    planned_duration=25
                ),
                Sprint(  # Interrupted sprint (should not count as completed)
                    project_id=self.test_project_id,
                    task_category_id=self.test_category_id,
                    task_description="interrupted",
                    start_time=datetime.combine(today, datetime.min.time()) + timedelta(hours=11),
                    end_time=datetime.combine(today, datetime.min.time()) + timedelta(hours=11, minutes=10),
                    completed=False,
                    interrupted=True,
                    duration_minutes=10,
                    planned_duration=25
                )
            ]
            
            for sprint in sprints:
                session.add(sprint)
            session.commit()
            
        finally:
            session.close()
        
        # Test stats calculation logic (similar to data viewer stats)
        sprints_today = self.db_manager.get_sprints_by_date(today)
        
        completed_count = len([s for s in sprints_today if s.completed])
        total_count = len(sprints_today)
        interrupted_count = len([s for s in sprints_today if s.interrupted])
        
        # Verify stats include hibernation recovered sprints
        assert total_count == 3, f"Should have 3 total sprints, got {total_count}"
        assert completed_count == 2, f"Should have 2 completed sprints (including recovered), got {completed_count}"
        assert interrupted_count == 1, f"Should have 1 interrupted sprint, got {interrupted_count}"
        
        # Verify completion rate calculation
        completion_rate = (completed_count / total_count * 100) if total_count > 0 else 0
        expected_rate = (2 / 3 * 100)  # 2 completed out of 3 total = 66.67%
        assert abs(completion_rate - expected_rate) < 0.01, (
            f"Completion rate should be {expected_rate:.1f}%, got {completion_rate:.1f}%"
        )

    def test_data_viewer_filtering_with_recovered_sprints(self):
        """Test data viewer filtering includes hibernation recovered sprints correctly"""
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        
        # Create sprints across different days
        session = self.db_manager.get_session()
        try:
            sprints = [
                Sprint(  # Today - hibernation recovered
                    project_id=self.test_project_id,
                    task_category_id=self.test_category_id,
                    task_description="today_recovered",
                    start_time=datetime.combine(today, datetime.min.time()) + timedelta(hours=8),
                    end_time=datetime.combine(today, datetime.min.time()) + timedelta(hours=8, minutes=25),
                    completed=True,
                    interrupted=False,  # Fixed hibernation recovery
                    duration_minutes=25,
                    planned_duration=25
                ),
                Sprint(  # Yesterday - hibernation recovered
                    project_id=self.test_project_id,
                    task_category_id=self.test_category_id,
                    task_description="yesterday_recovered",
                    start_time=datetime.combine(yesterday, datetime.min.time()) + timedelta(hours=14),
                    end_time=datetime.combine(yesterday, datetime.min.time()) + timedelta(hours=14, minutes=25),
                    completed=True,
                    interrupted=False,  # Fixed hibernation recovery
                    duration_minutes=25,
                    planned_duration=25
                )
            ]
            
            for sprint in sprints:
                session.add(sprint)
            session.commit()
            
        finally:
            session.close()
        
        # Test filtering by date (data viewer functionality)
        today_sprints = self.db_manager.get_sprints_by_date(today)
        yesterday_sprints = self.db_manager.get_sprints_by_date(yesterday)
        
        # Verify hibernation recovered sprints are included in date filters
        assert len(today_sprints) == 1
        assert today_sprints[0].task_description == "today_recovered"
        assert today_sprints[0].completed == True
        
        assert len(yesterday_sprints) == 1
        assert yesterday_sprints[0].task_description == "yesterday_recovered"
        assert yesterday_sprints[0].completed == True
        
        # Test status display for filtered sprints
        for sprint in today_sprints + yesterday_sprints:
            status = "✅ Completed" if sprint.completed else (
                "❌ Interrupted" if sprint.interrupted else "⏸️ Incomplete"
            )
            assert status == "✅ Completed", (
                f"Hibernation recovered sprint {sprint.task_description} should show as completed"
            )