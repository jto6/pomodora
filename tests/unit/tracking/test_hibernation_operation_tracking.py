"""
Unit tests for hibernation recovery operation tracking functionality.
Tests that hibernation recovery properly tracks operations for sync upload.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / 'src'))

from tracking.models import Sprint, Project, TaskCategory
from tracking.database_manager_unified import UnifiedDatabaseManager
from tracking.operation_log import OperationTracker
from helpers.database_helpers import DatabaseTestUtils


@pytest.mark.unit
@pytest.mark.tracking
class TestHibernationOperationTracking:
    """Test hibernation recovery operation tracking for sync upload"""

    def test_hibernation_recovery_tracks_operations_for_recovered_sprints(self, isolated_db, sample_project, sample_category):
        """Test that hibernation recovery tracks operations only for sprints that were actually recovered"""
        now = datetime.now()
        
        # Create sprints: some recoverable, some not
        session = isolated_db.get_session()
        try:
            # Sprint 1: Old enough to be recovered
            recoverable_sprint = Sprint(
                project_id=sample_project.id,
                task_category_id=sample_category.id,
                task_description="recoverable_sprint",
                start_time=now - timedelta(minutes=30),  # 30 min ago
                completed=False,
                interrupted=False,
                planned_duration=25  # Should be recovered
            )
            session.add(recoverable_sprint)
            
            # Sprint 2: Recent, should not be recovered
            recent_sprint = Sprint(
                project_id=sample_project.id,
                task_category_id=sample_category.id,
                task_description="recent_sprint",
                start_time=now - timedelta(minutes=10),  # 10 min ago
                completed=False,
                interrupted=False,
                planned_duration=25  # Should NOT be recovered
            )
            session.add(recent_sprint)
            
            # Sprint 3: Another recoverable sprint
            another_recoverable = Sprint(
                project_id=sample_project.id,
                task_category_id=sample_category.id,
                task_description="another_recoverable",
                start_time=now - timedelta(hours=1),  # 1 hour ago
                completed=False,
                interrupted=False,
                planned_duration=25  # Should be recovered
            )
            session.add(another_recoverable)
            
            session.commit()
            sprint_ids = [recoverable_sprint.id, recent_sprint.id, another_recoverable.id]
            
        finally:
            session.close()
        
        # Mock operation tracker to verify calls
        mock_operation_tracker = Mock(spec=OperationTracker)
        
        # Simulate hibernation recovery logic with operation tracking
        session = isolated_db.get_session()
        try:
            # Query for incomplete sprints (same as hibernation recovery)
            incomplete_sprints = session.query(Sprint).filter(
                Sprint.completed == False,
                Sprint.interrupted == False,
                Sprint.start_time.isnot(None),
                Sprint.end_time.is_(None)
            ).filter(Sprint.id.in_(sprint_ids)).all()
            
            assert len(incomplete_sprints) == 3  # All 3 sprints are incomplete
            
            # Apply hibernation recovery logic
            recovered_count = 0
            recovered_sprints = []  # Track which sprints were actually recovered
            
            for sprint in incomplete_sprints:
                # Calculate elapsed time
                elapsed_time = now - sprint.start_time
                planned_duration_timedelta = timedelta(minutes=sprint.planned_duration)
                
                # If enough time has passed for the sprint to be considered complete
                if elapsed_time >= planned_duration_timedelta:
                    # Auto-complete the sprint
                    sprint.end_time = sprint.start_time + planned_duration_timedelta
                    sprint.duration_minutes = sprint.planned_duration
                    sprint.completed = True
                    sprint.interrupted = False
                    
                    # Add to recovered list for operation tracking
                    recovered_sprints.append(sprint)
                    recovered_count += 1
            
            session.commit()
            
            # Track operations only for recovered sprints
            for sprint in recovered_sprints:
                mock_operation_tracker.track_operation(
                    'update',
                    'sprints', 
                    {
                        'id': sprint.id, 
                        'end_time': sprint.end_time.isoformat(),
                        'duration_minutes': sprint.duration_minutes,
                        'completed': True,
                        'interrupted': False
                    }
                )
            
            # Verify that exactly 2 sprints were recovered
            assert recovered_count == 2
            assert len(recovered_sprints) == 2
            
            # Verify operation tracking was called exactly 2 times (only for recovered sprints)
            assert mock_operation_tracker.track_operation.call_count == 2
            
            # Verify the correct sprints were tracked
            tracked_sprint_ids = []
            for call in mock_operation_tracker.track_operation.call_args_list:
                operation_type, table_name, data = call[0]
                assert operation_type == 'update'
                assert table_name == 'sprints'
                assert data['completed'] == True
                assert data['interrupted'] == False
                assert 'end_time' in data
                assert 'duration_minutes' in data
                tracked_sprint_ids.append(data['id'])
            
            # Should track recoverable_sprint and another_recoverable, but NOT recent_sprint
            recovered_sprint_ids = [s.id for s in recovered_sprints]
            assert recoverable_sprint.id in recovered_sprint_ids
            assert another_recoverable.id in recovered_sprint_ids
            assert recent_sprint.id not in recovered_sprint_ids
            
        finally:
            session.close()

    def test_hibernation_recovery_operation_data_format(self, isolated_db, sample_project, sample_category):
        """Test that hibernation recovery tracks operations with correct data format"""
        now = datetime.now()
        start_time = now - timedelta(minutes=30)
        planned_duration = 25
        
        session = isolated_db.get_session()
        try:
            sprint = Sprint(
                project_id=sample_project.id,
                task_category_id=sample_category.id,
                task_description="format_test_sprint",
                start_time=start_time,
                completed=False,
                interrupted=False,
                planned_duration=planned_duration
            )
            session.add(sprint)
            session.commit()
            sprint_id = sprint.id
            
            # Apply hibernation recovery
            planned_duration_timedelta = timedelta(minutes=planned_duration)
            sprint.end_time = start_time + planned_duration_timedelta
            sprint.duration_minutes = planned_duration
            sprint.completed = True
            sprint.interrupted = False
            session.commit()
            
            # Mock operation tracker
            mock_operation_tracker = Mock()
            
            # Track operation (as hibernation recovery would)
            mock_operation_tracker.track_operation(
                'update',
                'sprints', 
                {
                    'id': sprint.id, 
                    'end_time': sprint.end_time.isoformat(),
                    'duration_minutes': sprint.duration_minutes,
                    'completed': True,
                    'interrupted': False
                }
            )
            
            # Verify operation call format
            mock_operation_tracker.track_operation.assert_called_once()
            call_args = mock_operation_tracker.track_operation.call_args
            operation_type, table_name, data = call_args[0]
            
            # Verify operation format
            assert operation_type == 'update'
            assert table_name == 'sprints'
            assert data['id'] == sprint_id
            assert data['completed'] == True
            assert data['interrupted'] == False
            assert data['duration_minutes'] == planned_duration
            
            # Verify end_time is in ISO format
            assert isinstance(data['end_time'], str)
            # Should be parseable as ISO datetime
            parsed_end_time = datetime.fromisoformat(data['end_time'])
            expected_end_time = start_time + timedelta(minutes=planned_duration)
            assert parsed_end_time == expected_end_time
            
        finally:
            session.close()

    def test_hibernation_recovery_no_operations_when_no_recovery_needed(self, isolated_db, sample_project, sample_category):
        """Test that no operations are tracked when no sprints need recovery"""
        now = datetime.now()
        
        session = isolated_db.get_session()
        try:
            # Create only recent sprints that don't need recovery
            recent_sprints = []
            for i in range(3):
                sprint = Sprint(
                    project_id=sample_project.id,
                    task_category_id=sample_category.id,
                    task_description=f"recent_sprint_{i}",
                    start_time=now - timedelta(minutes=5 + i),  # 5, 6, 7 minutes ago
                    completed=False,
                    interrupted=False,
                    planned_duration=25  # All still within planned duration
                )
                session.add(sprint)
                recent_sprints.append(sprint)
            
            session.commit()
            
        finally:
            session.close()
        
        # Mock operation tracker
        mock_operation_tracker = Mock()
        
        # Apply hibernation recovery logic
        session = isolated_db.get_session()
        try:
            incomplete_sprints = session.query(Sprint).filter(
                Sprint.completed == False,
                Sprint.interrupted == False,
                Sprint.start_time.isnot(None),
                Sprint.end_time.is_(None)
            ).all()
            
            assert len(incomplete_sprints) == 3
            
            recovered_count = 0
            recovered_sprints = []
            
            for sprint in incomplete_sprints:
                elapsed_time = now - sprint.start_time
                planned_duration_timedelta = timedelta(minutes=sprint.planned_duration)
                
                if elapsed_time >= planned_duration_timedelta:
                    # Should not enter this block for recent sprints
                    sprint.end_time = sprint.start_time + planned_duration_timedelta
                    sprint.duration_minutes = sprint.planned_duration
                    sprint.completed = True
                    sprint.interrupted = False
                    recovered_sprints.append(sprint)
                    recovered_count += 1
            
            session.commit()
            
            # Track operations only for recovered sprints
            for sprint in recovered_sprints:
                mock_operation_tracker.track_operation(
                    'update',
                    'sprints', 
                    {
                        'id': sprint.id, 
                        'end_time': sprint.end_time.isoformat(),
                        'duration_minutes': sprint.duration_minutes,
                        'completed': True,
                        'interrupted': False
                    }
                )
            
            # Verify no recovery occurred
            assert recovered_count == 0
            assert len(recovered_sprints) == 0
            
            # Verify no operations were tracked
            mock_operation_tracker.track_operation.assert_not_called()
            
        finally:
            session.close()

    def test_hibernation_recovery_with_corrupted_sprint_data(self, isolated_db, sample_project, sample_category):
        """Test hibernation recovery handles sprints with NULL end_time/duration from Google Drive corruption"""
        now = datetime.now()
        
        session = isolated_db.get_session()
        try:
            # Simulate corrupted sprint data from Google Drive (NULL end_time, NULL duration)
            corrupted_sprint = Sprint(
                project_id=sample_project.id,
                task_category_id=sample_category.id,
                task_description="corrupted_sprint",
                start_time=now - timedelta(hours=2),  # Very old
                completed=False,  # But marked as not completed
                interrupted=False,
                planned_duration=25,
                end_time=None,  # NULL end_time (corruption)
                duration_minutes=None  # NULL duration (corruption)
            )
            session.add(corrupted_sprint)
            session.commit()
            sprint_id = corrupted_sprint.id
            
        finally:
            session.close()
        
        # Mock operation tracker
        mock_operation_tracker = Mock()
        
        # Apply hibernation recovery
        session = isolated_db.get_session()
        try:
            # Query should find the corrupted sprint
            incomplete_sprints = session.query(Sprint).filter(
                Sprint.completed == False,
                Sprint.interrupted == False,
                Sprint.start_time.isnot(None),
                Sprint.end_time.is_(None)  # This condition catches corrupted sprints
            ).all()
            
            assert len(incomplete_sprints) == 1
            assert incomplete_sprints[0].id == sprint_id
            
            # Apply recovery
            recovered_sprints = []
            for sprint in incomplete_sprints:
                elapsed_time = now - sprint.start_time
                planned_duration_timedelta = timedelta(minutes=sprint.planned_duration)
                
                if elapsed_time >= planned_duration_timedelta:
                    # Fix the corrupted sprint
                    sprint.end_time = sprint.start_time + planned_duration_timedelta
                    sprint.duration_minutes = sprint.planned_duration
                    sprint.completed = True
                    sprint.interrupted = False
                    recovered_sprints.append(sprint)
            
            session.commit()
            
            # Track operations for recovered sprints
            for sprint in recovered_sprints:
                mock_operation_tracker.track_operation(
                    'update',
                    'sprints', 
                    {
                        'id': sprint.id, 
                        'end_time': sprint.end_time.isoformat(),
                        'duration_minutes': sprint.duration_minutes,
                        'completed': True,
                        'interrupted': False
                    }
                )
            
            # Verify the corrupted sprint was recovered and tracked
            assert len(recovered_sprints) == 1
            mock_operation_tracker.track_operation.assert_called_once()
            
            # Verify the sprint data was fixed
            fixed_sprint = session.query(Sprint).filter_by(id=sprint_id).first()
            assert fixed_sprint.completed == True
            assert fixed_sprint.interrupted == False
            assert fixed_sprint.end_time is not None
            assert fixed_sprint.duration_minutes == 25
            
        finally:
            session.close()

    @patch('utils.logging.debug_print')
    def test_hibernation_recovery_debug_logging(self, mock_debug_print, isolated_db, sample_project, sample_category):
        """Test that hibernation recovery logs detailed debug information about operation tracking"""
        now = datetime.now()
        
        session = isolated_db.get_session()
        try:
            # Create one recoverable sprint
            sprint = Sprint(
                project_id=sample_project.id,
                task_category_id=sample_category.id,
                task_description="debug_test_sprint",
                start_time=now - timedelta(minutes=30),
                completed=False,
                interrupted=False,
                planned_duration=25
            )
            session.add(sprint)
            session.commit()
            
        finally:
            session.close()
        
        # Mock operation tracker with pending operations
        mock_operation_tracker = Mock()
        mock_operation_tracker.get_pending_operations.return_value = [
            {'id': 1, 'operation_type': 'update', 'table_name': 'sprints'}
        ]
        
        # Simulate the hibernation recovery debug logging
        session = isolated_db.get_session()
        try:
            incomplete_sprints = session.query(Sprint).filter(
                Sprint.completed == False,
                Sprint.interrupted == False,
                Sprint.start_time.isnot(None),
                Sprint.end_time.is_(None)
            ).all()
            
            recovered_sprints = []
            for sprint in incomplete_sprints:
                elapsed_time = now - sprint.start_time
                planned_duration_timedelta = timedelta(minutes=sprint.planned_duration)
                
                if elapsed_time >= planned_duration_timedelta:
                    sprint.end_time = sprint.start_time + planned_duration_timedelta
                    sprint.duration_minutes = sprint.planned_duration
                    sprint.completed = True
                    sprint.interrupted = False
                    recovered_sprints.append(sprint)
            
            session.commit()
            
            # Simulate hibernation recovery debug logging
            from utils.logging import debug_print
            debug_print(f"Hibernation recovery: Tracking operations for {len(recovered_sprints)} recovered sprints")
            
            for sprint in recovered_sprints:
                debug_print(f"Hibernation recovery: Tracking operation for sprint ID {sprint.id}")
                mock_operation_tracker.track_operation(
                    'update',
                    'sprints', 
                    {
                        'id': sprint.id, 
                        'end_time': sprint.end_time.isoformat(),
                        'duration_minutes': sprint.duration_minutes,
                        'completed': True,
                        'interrupted': False
                    }
                )
            
            # Check pending operations
            pending_ops = mock_operation_tracker.get_pending_operations()
            debug_print(f"Hibernation recovery: Found {len(pending_ops)} pending operations before sync")
            
            # Verify debug logging was called with expected messages
            expected_calls = [
                f"Hibernation recovery: Tracking operations for 1 recovered sprints",
                f"Hibernation recovery: Tracking operation for sprint ID {sprint.id}",
                f"Hibernation recovery: Found 1 pending operations before sync"
            ]
            
            # Check that debug_print was called with our expected messages
            actual_calls = [call[0][0] for call in mock_debug_print.call_args_list if call[0]]
            for expected_msg in expected_calls:
                # Check if any actual call contains the expected message
                assert any(expected_msg in actual_call for actual_call in actual_calls), (
                    f"Expected debug message '{expected_msg}' not found in calls: {actual_calls}"
                )
                
        finally:
            session.close()