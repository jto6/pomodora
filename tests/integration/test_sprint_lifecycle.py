"""
Integration tests for complete sprint lifecycle.
Tests the full workflow: create sprint → start timer → complete → save to database.
"""

import pytest
import time
from datetime import datetime, timedelta
from unittest.mock import Mock

from timer.pomodoro import PomodoroTimer, TimerState
from tracking.models import Sprint, Project, TaskCategory
from helpers.database_helpers import DatabaseTestUtils


@pytest.mark.integration
@pytest.mark.database
class TestSprintLifecycle:
    """Test complete sprint lifecycle integration"""
    
    def test_complete_sprint_creation_to_database(self, isolated_db, sample_project, sample_category):
        """Test creating and completing a sprint from start to finish"""
        # Create timer
        timer = PomodoroTimer(sprint_duration=1, break_duration=1)  # 1 minute for test
        
        # Create sprint record
        sprint = DatabaseTestUtils.create_test_sprint(
            isolated_db,
            sample_project.id,
            sample_category.id,
            "Integration Test Sprint",
            completed=False
        )
        
        # Start timer
        timer.start_sprint()
        assert timer.get_state() == TimerState.RUNNING
        assert sprint.completed is False
        
        # Simulate sprint completion
        timer.stop()
        sprint_end_time = datetime.now()
        
        # Update sprint as completed
        session = isolated_db.get_session()
        try:
            session.merge(sprint)  # Refresh sprint object
            sprint.end_time = sprint_end_time
            sprint.duration_minutes = 1
            sprint.completed = True
            session.commit()
            
            # Verify sprint was completed
            completed_sprint = session.query(Sprint).filter_by(id=sprint.id).first()
            assert completed_sprint.completed is True
            assert completed_sprint.end_time is not None
            assert completed_sprint.duration_minutes == 1
        finally:
            session.close()
    
    def test_sprint_interruption_workflow(self, isolated_db, sample_project, sample_category):
        """Test sprint interruption and database update"""
        timer = PomodoroTimer(sprint_duration=1, break_duration=1)
        
        # Create and start sprint
        sprint = DatabaseTestUtils.create_test_sprint(
            isolated_db,
            sample_project.id,
            sample_category.id,
            "Interrupted Sprint Test"
        )
        
        timer.start_sprint()
        assert timer.get_state() == TimerState.RUNNING
        
        # Interrupt sprint (simulate user stopping early)
        timer.stop()
        interrupt_time = datetime.now()
        
        # Update database to reflect interruption
        session = isolated_db.get_session()
        try:
            session.merge(sprint)
            sprint.end_time = interrupt_time
            sprint.duration_minutes = 0  # No actual work time
            sprint.interrupted = True
            sprint.completed = False
            session.commit()
            
            # Verify interruption was recorded
            interrupted_sprint = session.query(Sprint).filter_by(id=sprint.id).first()
            assert interrupted_sprint.interrupted is True
            assert interrupted_sprint.completed is False
            assert interrupted_sprint.end_time is not None
        finally:
            session.close()
    
    def test_sprint_with_callbacks_integration(self, isolated_db, sample_project, sample_category):
        """Test sprint lifecycle with timer callbacks"""
        timer = PomodoroTimer(sprint_duration=1, break_duration=1)
        callback_events = []
        
        # Set up callbacks to track events
        def on_sprint_complete():
            callback_events.append("sprint_complete")
        
        def on_break_complete():
            callback_events.append("break_complete")
        
        def on_state_change(state):
            callback_events.append(f"state_change:{state.value}")
        
        timer.on_sprint_complete = on_sprint_complete
        timer.on_break_complete = on_break_complete
        timer.on_state_change = on_state_change
        
        # Create sprint
        sprint = DatabaseTestUtils.create_test_sprint(
            isolated_db,
            sample_project.id,
            sample_category.id,
            "Callback Integration Test"
        )
        
        # Run through sprint lifecycle
        timer.start_sprint()
        assert "state_change:running" in callback_events
        
        # Simulate completion (in real app, this would be timer-driven)
        timer.stop()  # Stop to complete sprint
        
        # Verify callbacks were triggered
        assert "sprint_complete" in callback_events
        
        timer.stop()
        assert "state_change:stopped" in callback_events
    
    def test_multiple_sprints_sequence(self, isolated_db, sample_project, sample_category):
        """Test completing multiple sprints in sequence"""
        timer = PomodoroTimer(sprint_duration=1, break_duration=1)
        completed_sprints = []
        
        # Create and complete 3 sprints
        for i in range(3):
            # Create sprint
            sprint = DatabaseTestUtils.create_test_sprint(
                isolated_db,
                sample_project.id,
                sample_category.id,
                f"Sequential Sprint {i+1}"
            )
            
            # Start and complete sprint
            timer.start_sprint()
            assert timer.get_state() == TimerState.RUNNING
            
            # Simulate completion
            timer.stop()
            completion_time = datetime.now()
            
            # Update database
            session = isolated_db.get_session()
            try:
                session.merge(sprint)
                sprint.end_time = completion_time
                sprint.duration_minutes = 1
                sprint.completed = True
                session.commit()
                completed_sprints.append(sprint.id)
            finally:
                session.close()
        
        # Verify all sprints were completed
        session = isolated_db.get_session()
        try:
            all_sprints = session.query(Sprint).filter(Sprint.id.in_(completed_sprints)).all()
            assert len(all_sprints) == 3
            for sprint in all_sprints:
                assert sprint.completed is True
                assert sprint.duration_minutes == 1
        finally:
            session.close()
    
    def test_sprint_data_consistency(self, isolated_db, sample_project, sample_category):
        """Test data consistency between timer and database"""
        timer = PomodoroTimer(sprint_duration=25, break_duration=5)
        
        # Create sprint with specific planned duration
        planned_duration = 25
        sprint = DatabaseTestUtils.create_test_sprint(
            isolated_db,
            sample_project.id,
            sample_category.id,
            "Consistency Test Sprint"
        )
        
        session = isolated_db.get_session()
        try:
            session.merge(sprint)
            sprint.planned_duration = planned_duration
            session.commit()
            
            # Verify timer and database have consistent durations
            assert timer.sprint_duration == planned_duration * 60  # Timer in seconds
            assert sprint.planned_duration == planned_duration  # Database in minutes
            
            # Start timer
            timer.start_sprint()
            start_time = datetime.now()
            
            # Update sprint start time to match
            sprint.start_time = start_time
            session.commit()
            
            # Verify consistency
            assert timer.get_state() == TimerState.RUNNING
            assert sprint.start_time is not None
            
            # Complete sprint
            timer.stop()
            end_time = datetime.now()
            actual_duration = int((end_time - start_time).total_seconds() / 60)
            
            sprint.end_time = end_time
            sprint.duration_minutes = actual_duration
            sprint.completed = True
            session.commit()
            
            # Verify final consistency
            assert sprint.completed is True
            assert sprint.duration_minutes is not None
            assert sprint.end_time > sprint.start_time
        finally:
            session.close()


@pytest.mark.integration
@pytest.mark.database
class TestSprintProjectCategoryIntegration:
    """Test sprint integration with projects and categories"""
    
    def test_sprint_project_category_relationships(self, isolated_db):
        """Test sprint relationships with projects and categories"""
        # Create project and category
        project = DatabaseTestUtils.create_test_project(isolated_db, "Integration Project")
        category = DatabaseTestUtils.create_test_category(isolated_db, "Integration Category")
        
        # Create sprint linking them
        sprint = DatabaseTestUtils.create_test_sprint(
            isolated_db,
            project.id,
            category.id,
            "Relationship Test Sprint"
        )
        
        # Verify relationships work
        session = isolated_db.get_session()
        try:
            retrieved_sprint = session.query(Sprint).filter_by(id=sprint.id).first()
            assert retrieved_sprint.project.name == "Integration Project"
            assert retrieved_sprint.task_category.name == "Integration Category"
            
            # Verify reverse relationships
            retrieved_project = session.query(Project).filter_by(id=project.id).first()
            assert len(retrieved_project.sprints) == 1
            assert retrieved_project.sprints[0].task_description == "Relationship Test Sprint"
            
            retrieved_category = session.query(TaskCategory).filter_by(id=category.id).first()
            assert len(retrieved_category.sprints) == 1
            assert retrieved_category.sprints[0].task_description == "Relationship Test Sprint"
        finally:
            session.close()
    
    def test_sprint_invalid_project_category(self, isolated_db):
        """Test error handling for invalid project/category IDs"""
        session = isolated_db.get_session()
        try:
            # Try to create sprint with non-existent project and category
            sprint = Sprint(
                project_id=9999,  # Non-existent
                task_category_id=9999,  # Non-existent
                task_description="Invalid FK Test",
                start_time=datetime.now(),
                planned_duration=25
            )
            session.add(sprint)
            
            # Should raise foreign key constraint error
            with pytest.raises(Exception):
                session.commit()
        finally:
            session.rollback()
            session.close()
    
    def test_sprint_project_category_updates(self, isolated_db):
        """Test updating sprint project/category associations"""
        # Create initial project and category
        project1 = DatabaseTestUtils.create_test_project(isolated_db, "Initial Project")
        category1 = DatabaseTestUtils.create_test_category(isolated_db, "Initial Category")
        
        # Create second project and category
        project2 = DatabaseTestUtils.create_test_project(isolated_db, "Updated Project")
        category2 = DatabaseTestUtils.create_test_category(isolated_db, "Updated Category")
        
        # Create sprint with initial associations
        sprint = DatabaseTestUtils.create_test_sprint(
            isolated_db,
            project1.id,
            category1.id,
            "Update Test Sprint"
        )
        
        # Update sprint associations
        session = isolated_db.get_session()
        try:
            session.merge(sprint)
            sprint.project_id = project2.id
            sprint.task_category_id = category2.id
            session.commit()
            
            # Verify updates
            updated_sprint = session.query(Sprint).filter_by(id=sprint.id).first()
            assert updated_sprint.project.name == "Updated Project"
            assert updated_sprint.task_category.name == "Updated Category"
        finally:
            session.close()


@pytest.mark.integration
class TestSprintTimerIntegration:
    """Test integration between sprint data and timer functionality"""
    
    def test_timer_duration_from_sprint_data(self, isolated_db, sample_project, sample_category):
        """Test setting timer duration based on sprint planned duration"""
        # Create sprint with custom duration
        custom_duration = 30
        sprint = DatabaseTestUtils.create_test_sprint(
            isolated_db,
            sample_project.id,
            sample_category.id,
            "Custom Duration Sprint"
        )
        
        session = isolated_db.get_session()
        try:
            session.merge(sprint)
            sprint.planned_duration = custom_duration
            session.commit()
            
            # Create timer with duration from sprint
            timer = PomodoroTimer(
                sprint_duration=sprint.planned_duration,
                break_duration=5
            )
            
            # Verify timer has correct duration
            assert timer.sprint_duration == custom_duration * 60  # Convert to seconds
            
            # Start timer and verify
            timer.start_sprint()
            assert timer.get_time_remaining() == custom_duration * 60
            timer.stop()
        finally:
            session.close()
    
    def test_sprint_timing_accuracy(self, isolated_db, sample_project, sample_category):
        """Test accuracy of sprint timing measurements"""
        timer = PomodoroTimer(sprint_duration=1, break_duration=1)  # 1 minute
        
        sprint = DatabaseTestUtils.create_test_sprint(
            isolated_db,
            sample_project.id,
            sample_category.id,
            "Timing Accuracy Test"
        )
        
        # Record precise start time
        start_time = datetime.now()
        sprint.start_time = start_time
        timer.start_sprint()
        
        # Let timer run briefly
        time.sleep(0.1)  # 100ms
        
        # Stop and measure
        timer.stop()
        end_time = datetime.now()
        
        # Calculate actual duration
        actual_duration = (end_time - start_time).total_seconds()
        
        # Update sprint
        session = isolated_db.get_session()
        try:
            session.merge(sprint)
            sprint.end_time = end_time
            sprint.duration_minutes = int(actual_duration / 60)
            sprint.completed = True
            session.commit()
            
            # Verify timing data is reasonable
            assert sprint.end_time > sprint.start_time
            assert actual_duration >= 0.1  # At least 100ms
            assert actual_duration < 60  # Less than a full minute
        finally:
            session.close()
    
    def test_break_timer_integration(self, isolated_db):
        """Test break timer functionality in sprint context"""
        timer = PomodoroTimer(sprint_duration=1, break_duration=1)
        break_events = []
        
        def on_break_complete():
            break_events.append("break_completed")
        
        timer.on_break_complete = on_break_complete
        
        # Start break phase
        timer.start_sprint()
        timer.start_break()  # Transition to break
        assert timer.get_state() == TimerState.BREAK
        
        # Complete break
        timer.stop()  # Stop break
        
        # Verify break completion was tracked
        assert "break_completed" in break_events
        
        timer.stop()
        assert timer.get_state() == TimerState.STOPPED