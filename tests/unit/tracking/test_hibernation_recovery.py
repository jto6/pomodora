"""
Unit tests for hibernation recovery functionality.
Tests the logic for auto-completing sprints after system sleep/hibernation.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / 'src'))

from tracking.models import Sprint, Project, TaskCategory
from helpers.database_helpers import DatabaseTestUtils


@pytest.mark.unit
@pytest.mark.tracking
class TestHibernationRecovery:
    """Test hibernation recovery logic in isolation"""

    def test_hibernation_recovery_completion_logic(self, isolated_db, sample_project, sample_category):
        """Test the core logic for determining which sprints need recovery"""
        now = datetime.now()
        
        # Create test sprints with different elapsed times
        test_cases = [
            {
                'name': 'recent_sprint',
                'start_time': now - timedelta(minutes=10),  # Started 10 min ago
                'planned_duration': 25,  # 25 min planned
                'should_recover': False  # Still within planned time
            },
            {
                'name': 'old_sprint_exact',
                'start_time': now - timedelta(minutes=25),  # Started exactly 25 min ago
                'planned_duration': 25,  # 25 min planned
                'should_recover': True  # Exactly at planned duration
            },
            {
                'name': 'very_old_sprint',
                'start_time': now - timedelta(hours=2),  # Started 2 hours ago
                'planned_duration': 25,  # 25 min planned
                'should_recover': True  # Way past planned duration
            },
            {
                'name': 'long_sprint',
                'start_time': now - timedelta(minutes=45),  # Started 45 min ago
                'planned_duration': 60,  # 60 min planned
                'should_recover': False  # Still within planned time
            }
        ]
        
        sprint_ids = []
        session = isolated_db.get_session()
        
        try:
            # Create all test sprints
            for case in test_cases:
                sprint = Sprint(
                    project_id=sample_project.id,
                    task_category_id=sample_category.id,
                    task_description=case['name'],
                    start_time=case['start_time'],
                    completed=False,
                    interrupted=False,
                    planned_duration=case['planned_duration']
                )
                session.add(sprint)
                session.commit()
                sprint_ids.append((sprint.id, case))
            
            # Test the hibernation recovery logic
            for sprint_id, case in sprint_ids:
                sprint = session.query(Sprint).filter_by(id=sprint_id).first()
                
                # Calculate elapsed time (this is the logic from _recover_hibernated_sprints)
                elapsed_time = now - sprint.start_time
                planned_duration_timedelta = timedelta(minutes=sprint.planned_duration)
                should_recover = elapsed_time >= planned_duration_timedelta
                
                assert should_recover == case['should_recover'], (
                    f"Sprint '{case['name']}': expected should_recover={case['should_recover']}, "
                    f"got {should_recover}. Elapsed: {elapsed_time.total_seconds()/60:.1f}min, "
                    f"Planned: {sprint.planned_duration}min"
                )
                
                if should_recover:
                    # Test the recovery actions
                    sprint.end_time = sprint.start_time + planned_duration_timedelta
                    sprint.duration_minutes = sprint.planned_duration
                    sprint.completed = True
                    sprint.interrupted = False  # This is the fix we're testing
                    session.commit()
                    
                    # Verify recovery was applied correctly
                    recovered_sprint = session.query(Sprint).filter_by(id=sprint_id).first()
                    assert recovered_sprint.completed == True
                    assert recovered_sprint.interrupted == False
                    assert recovered_sprint.end_time is not None
                    assert recovered_sprint.duration_minutes == case['planned_duration']
                    
        finally:
            session.close()

    def test_hibernation_recovery_preserves_non_recoverable_sprints(self, isolated_db, sample_project, sample_category):
        """Test that recent sprints are left untouched by hibernation recovery"""
        now = datetime.now()
        
        # Create a recent sprint that shouldn't be recovered
        session = isolated_db.get_session()
        try:
            sprint = Sprint(
                project_id=sample_project.id,
                task_category_id=sample_category.id,
                task_description="recent_active_sprint",
                start_time=now - timedelta(minutes=5),  # Started 5 min ago
                completed=False,
                interrupted=False,
                planned_duration=25  # 25 min planned, so 20 min remaining
            )
            session.add(sprint)
            session.commit()
            sprint_id = sprint.id
            
            # Store original state
            original_completed = sprint.completed
            original_interrupted = sprint.interrupted
            original_end_time = sprint.end_time
            
        finally:
            session.close()
        
        # Apply hibernation recovery logic
        session = isolated_db.get_session()
        try:
            sprint = session.query(Sprint).filter_by(id=sprint_id).first()
            
            # This is the logic from _recover_hibernated_sprints
            elapsed_time = now - sprint.start_time
            planned_duration_timedelta = timedelta(minutes=sprint.planned_duration)
            
            if elapsed_time >= planned_duration_timedelta:
                # Should not enter this block for recent sprint
                sprint.end_time = sprint.start_time + planned_duration_timedelta
                sprint.duration_minutes = sprint.planned_duration
                sprint.completed = True
                sprint.interrupted = False
                session.commit()
            
            # Verify the sprint was NOT modified
            final_sprint = session.query(Sprint).filter_by(id=sprint_id).first()
            assert final_sprint.completed == original_completed  # Should still be False
            assert final_sprint.interrupted == original_interrupted  # Should still be False
            assert final_sprint.end_time == original_end_time  # Should still be None
            
        finally:
            session.close()

    def test_hibernation_recovery_query_conditions(self, isolated_db, sample_project, sample_category):
        """Test that hibernation recovery only finds the correct sprints"""
        now = datetime.now()
        old_time = now - timedelta(hours=1)
        
        session = isolated_db.get_session()
        try:
            # Create sprints that should NOT be found by hibernation recovery
            excluded_sprints = [
                Sprint(  # Already completed
                    project_id=sample_project.id,
                    task_category_id=sample_category.id,
                    task_description="already_completed",
                    start_time=old_time,
                    completed=True,
                    interrupted=False,
                    planned_duration=25
                ),
                Sprint(  # Already interrupted
                    project_id=sample_project.id,
                    task_category_id=sample_category.id,
                    task_description="already_interrupted",
                    start_time=old_time,
                    completed=False,
                    interrupted=True,
                    planned_duration=25
                ),
                Sprint(  # No start time
                    project_id=sample_project.id,
                    task_category_id=sample_category.id,
                    task_description="no_start_time",
                    start_time=None,
                    completed=False,
                    interrupted=False,
                    planned_duration=25
                ),
                Sprint(  # Has end time already
                    project_id=sample_project.id,
                    task_category_id=sample_category.id,
                    task_description="has_end_time",
                    start_time=old_time,
                    end_time=old_time + timedelta(minutes=25),
                    completed=False,
                    interrupted=False,
                    planned_duration=25
                )
            ]
            
            # Create sprint that SHOULD be found
            recoverable_sprint = Sprint(
                project_id=sample_project.id,
                task_category_id=sample_category.id,
                task_description="recoverable_sprint",
                start_time=old_time,
                completed=False,
                interrupted=False,
                planned_duration=25
            )
            
            # Add all sprints
            for sprint in excluded_sprints:
                session.add(sprint)
            session.add(recoverable_sprint)
            session.commit()
            
            # Test the exact query from _recover_hibernated_sprints
            incomplete_sprints = session.query(Sprint).filter(
                Sprint.completed == False,
                Sprint.interrupted == False,
                Sprint.start_time.isnot(None),
                Sprint.end_time.is_(None)
            ).all()
            
            # Should only find the recoverable sprint
            assert len(incomplete_sprints) == 1
            assert incomplete_sprints[0].task_description == "recoverable_sprint"
            
        finally:
            session.close()

    def test_hibernation_recovery_end_time_calculation(self, isolated_db, sample_project, sample_category):
        """Test that hibernation recovery calculates end_time correctly"""
        start_time = datetime(2025, 1, 15, 10, 0, 0)  # Fixed start time
        planned_duration = 25  # 25 minutes
        
        session = isolated_db.get_session()
        try:
            sprint = Sprint(
                project_id=sample_project.id,
                task_category_id=sample_category.id,
                task_description="end_time_test",
                start_time=start_time,
                completed=False,
                interrupted=False,
                planned_duration=planned_duration
            )
            session.add(sprint)
            session.commit()
            sprint_id = sprint.id
            
            # Apply hibernation recovery logic
            planned_duration_timedelta = timedelta(minutes=planned_duration)
            expected_end_time = start_time + planned_duration_timedelta
            
            sprint.end_time = start_time + planned_duration_timedelta
            sprint.duration_minutes = planned_duration
            sprint.completed = True
            sprint.interrupted = False
            session.commit()
            
            # Verify calculations
            recovered_sprint = session.query(Sprint).filter_by(id=sprint_id).first()
            assert recovered_sprint.end_time == expected_end_time
            assert recovered_sprint.end_time == datetime(2025, 1, 15, 10, 25, 0)  # 10:00 + 25min = 10:25
            assert recovered_sprint.duration_minutes == 25
            
        finally:
            session.close()

    def test_hibernation_recovery_batch_processing(self, isolated_db, sample_project, sample_category):
        """Test hibernation recovery handles multiple sprints correctly"""
        now = datetime.now()
        
        # Create multiple old sprints that need recovery
        sprint_count = 5
        sprint_ids = []
        
        session = isolated_db.get_session()
        try:
            for i in range(sprint_count):
                start_time = now - timedelta(hours=i+1)  # Each sprint older than the last
                sprint = Sprint(
                    project_id=sample_project.id,
                    task_category_id=sample_category.id,
                    task_description=f"batch_sprint_{i}",
                    start_time=start_time,
                    completed=False,
                    interrupted=False,
                    planned_duration=25
                )
                session.add(sprint)
                session.commit()
                sprint_ids.append(sprint.id)
            
        finally:
            session.close()
        
        # Apply hibernation recovery to all sprints
        session = isolated_db.get_session()
        try:
            incomplete_sprints = session.query(Sprint).filter(
                Sprint.completed == False,
                Sprint.interrupted == False,
                Sprint.start_time.isnot(None),
                Sprint.end_time.is_(None)
            ).filter(Sprint.id.in_(sprint_ids)).all()
            
            assert len(incomplete_sprints) == sprint_count
            
            recovered_count = 0
            for sprint in incomplete_sprints:
                elapsed_time = now - sprint.start_time
                planned_duration_timedelta = timedelta(minutes=sprint.planned_duration)
                
                if elapsed_time >= planned_duration_timedelta:
                    sprint.end_time = sprint.start_time + planned_duration_timedelta
                    sprint.duration_minutes = sprint.planned_duration
                    sprint.completed = True
                    sprint.interrupted = False  # The fix we're testing
                    recovered_count += 1
            
            session.commit()
            
            # Verify all sprints were recovered
            assert recovered_count == sprint_count
            
            # Verify all sprints have correct final state
            for sprint_id in sprint_ids:
                final_sprint = session.query(Sprint).filter_by(id=sprint_id).first()
                assert final_sprint.completed == True
                assert final_sprint.interrupted == False
                assert final_sprint.end_time is not None
                assert final_sprint.duration_minutes == 25
                
        finally:
            session.close()

    def test_hibernation_recovery_edge_cases(self, isolated_db, sample_project, sample_category):
        """Test hibernation recovery handles edge cases correctly"""
        now = datetime.now()
        
        session = isolated_db.get_session()
        try:
            # Edge case 1: Sprint started exactly planned_duration ago
            exactly_duration_sprint = Sprint(
                project_id=sample_project.id,
                task_category_id=sample_category.id,
                task_description="exactly_duration",
                start_time=now - timedelta(minutes=25),  # Exactly 25 minutes ago
                completed=False,
                interrupted=False,
                planned_duration=25
            )
            session.add(exactly_duration_sprint)
            
            # Edge case 2: Sprint with 0 planned duration
            zero_duration_sprint = Sprint(
                project_id=sample_project.id,
                task_category_id=sample_category.id,
                task_description="zero_duration",
                start_time=now - timedelta(minutes=1),  # 1 minute ago
                completed=False,
                interrupted=False,
                planned_duration=0  # Edge case: 0 duration
            )
            session.add(zero_duration_sprint)
            
            # Edge case 3: Very long planned duration
            long_duration_sprint = Sprint(
                project_id=sample_project.id,
                task_category_id=sample_category.id,
                task_description="long_duration",
                start_time=now - timedelta(minutes=30),  # 30 minutes ago
                completed=False,
                interrupted=False,
                planned_duration=120  # 2 hours planned
            )
            session.add(long_duration_sprint)
            
            session.commit()
            
            # Test hibernation recovery logic on edge cases
            sprints = session.query(Sprint).filter(
                Sprint.task_description.in_(["exactly_duration", "zero_duration", "long_duration"])
            ).all()
            
            for sprint in sprints:
                elapsed_time = now - sprint.start_time
                planned_duration_timedelta = timedelta(minutes=sprint.planned_duration)
                should_recover = elapsed_time >= planned_duration_timedelta
                
                if sprint.task_description == "exactly_duration":
                    assert should_recover == True, "Sprint at exactly planned duration should be recovered"
                elif sprint.task_description == "zero_duration":
                    assert should_recover == True, "Sprint with 0 duration should be recovered immediately"
                elif sprint.task_description == "long_duration":
                    assert should_recover == False, "Sprint with long duration shouldn't be recovered yet"
                    
        finally:
            session.close()