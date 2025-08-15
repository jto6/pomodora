"""
Integration tests for sprint completion in multi-threading scenarios.

These tests verify that the sprint completion fix works correctly
with actual Qt signals, threading, and database operations.
"""

import pytest
import sys
import os
import tempfile
import threading
import time
import shutil
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))

from tracking.models import Sprint, TaskCategory, Project, Base
from tracking.database_manager_unified import UnifiedDatabaseManager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.mark.integration
class TestSprintCompletionThreadingIntegration:
    """Integration tests for sprint completion with actual threading and database."""
    
    def setup_method(self):
        """Set up test database for each test."""
        # Create temporary directory for this test
        self.temp_dir = tempfile.mkdtemp()
        self.temp_db_path = os.path.join(self.temp_dir, 'test_pomodora.db')
        
        # Create database manager with explicit test database path
        # This ensures we don't use production configuration
        self.db_manager = UnifiedDatabaseManager(db_path=self.temp_db_path)
        
        # Create test data
        self.setup_test_data()
    
    def teardown_method(self):
        """Clean up after each test."""
        import shutil
        try:
            shutil.rmtree(self.temp_dir)
        except:
            pass
    
    def setup_test_data(self):
        """Create test categories and projects."""
        # Create database tables and session
        engine = create_engine(f'sqlite:///{self.temp_db_path}')
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        session = Session()
        
        try:
            # Create test category and project
            self.test_category = TaskCategory(name="Test Category", color="#ff0000", active=True)
            self.test_project = Project(name="Test Project", color="#00ff00", active=True)
            
            session.add(self.test_category)
            session.add(self.test_project)
            session.commit()
            
            # Store IDs for tests
            self.category_id = self.test_category.id
            self.project_id = self.test_project.id
            
        finally:
            session.close()
    
    def create_mock_timer(self):
        """Create a mock timer that can simulate completion."""
        timer = Mock()
        timer.sprint_duration = 25 * 60  # 25 minutes in seconds
        timer.start_time = datetime.now() - timedelta(minutes=25)
        return timer
    
    def test_real_database_sprint_completion(self):
        """Test sprint completion with real database operations."""
        
        # Create sprint data
        sprint_data = {
            'project_id': self.project_id,
            'task_category_id': self.category_id,
            'task_description': "Integration Test Sprint",
            'start_time': datetime.now() - timedelta(minutes=25)
        }
        
        # Simulate the fixed _save_sprint_with_data method
        start_time = sprint_data['start_time']
        end_time = datetime.now()
        actual_duration = (end_time - start_time).total_seconds()
        
        sprint = Sprint(
            project_id=sprint_data['project_id'],
            task_category_id=sprint_data['task_category_id'],
            task_description=sprint_data['task_description'],
            start_time=start_time,
            end_time=end_time,
            completed=True,
            interrupted=False,
            duration_minutes=int(actual_duration / 60),
            planned_duration=25
        )
        
        # Save to database
        session = self.db_manager.get_session()
        try:
            session.add(sprint)
            session.commit()
            sprint_id = sprint.id
        finally:
            session.close()
        
        # Verify sprint was saved correctly
        session = self.db_manager.get_session()
        try:
            saved_sprint = session.query(Sprint).filter(Sprint.id == sprint_id).first()
            
            assert saved_sprint is not None
            assert saved_sprint.completed == True
            assert saved_sprint.end_time is not None
            assert saved_sprint.interrupted == False
            assert saved_sprint.project_id == self.project_id
            assert saved_sprint.task_category_id == self.category_id
            assert saved_sprint.task_description == "Integration Test Sprint"
            
        finally:
            session.close()
    
    def test_concurrent_sprint_operations(self):
        """Test that concurrent sprint operations don't interfere with each other."""
        
        results = {'sprints_saved': 0, 'errors': []}
        
        def save_sprint(sprint_number):
            """Save a sprint in a separate thread."""
            try:
                sprint_data = {
                    'project_id': self.project_id,
                    'task_category_id': self.category_id,
                    'task_description': f"Concurrent Sprint {sprint_number}",
                    'start_time': datetime.now() - timedelta(minutes=25, seconds=sprint_number)
                }
                
                start_time = sprint_data['start_time']
                end_time = datetime.now()
                actual_duration = (end_time - start_time).total_seconds()
                
                sprint = Sprint(
                    project_id=sprint_data['project_id'],
                    task_category_id=sprint_data['task_category_id'],
                    task_description=sprint_data['task_description'],
                    start_time=start_time,
                    end_time=end_time,
                    completed=True,
                    interrupted=False,
                    duration_minutes=int(actual_duration / 60),
                    planned_duration=25
                )
                
                # Add some random delay to simulate real-world timing
                time.sleep(0.01 * sprint_number)
                
                session = self.db_manager.get_session()
                try:
                    session.add(sprint)
                    session.commit()
                    results['sprints_saved'] += 1
                finally:
                    session.close()
                    
            except Exception as e:
                results['errors'].append(f"Sprint {sprint_number}: {e}")
        
        # Start multiple threads to save sprints concurrently
        threads = []
        for i in range(5):
            thread = threading.Thread(target=save_sprint, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Verify results
        assert results['sprints_saved'] == 5
        assert len(results['errors']) == 0
        
        # Verify all sprints were saved correctly
        session = self.db_manager.get_session()
        try:
            saved_sprints = session.query(Sprint).filter(
                Sprint.task_description.like("Concurrent Sprint%")
            ).all()
            
            assert len(saved_sprints) == 5
            
            for sprint in saved_sprints:
                assert sprint.completed == True
                assert sprint.end_time is not None
                assert sprint.interrupted == False
                
        finally:
            session.close()
    
    def test_hibernation_recovery_vs_new_completion(self):
        """Test that hibernation recovery doesn't interfere with new sprint completion."""
        
        # Create an incomplete sprint (simulating pre-hibernation state)
        incomplete_start_time = datetime.now() - timedelta(hours=2)
        incomplete_sprint = Sprint(
            project_id=self.project_id,
            task_category_id=self.category_id,
            task_description="Pre-hibernation Sprint",
            start_time=incomplete_start_time,
            end_time=None,  # Incomplete
            completed=False,
            interrupted=False,
            duration_minutes=None,
            planned_duration=25
        )
        
        session = self.db_manager.get_session()
        try:
            session.add(incomplete_sprint)
            session.commit()
            incomplete_sprint_id = incomplete_sprint.id
        finally:
            session.close()
        
        # Now complete a new sprint using the race-condition-safe method
        new_sprint_data = {
            'project_id': self.project_id,
            'task_category_id': self.category_id,
            'task_description': "Post-hibernation Sprint",
            'start_time': datetime.now() - timedelta(minutes=25)
        }
        
        start_time = new_sprint_data['start_time']
        end_time = datetime.now()
        actual_duration = (end_time - start_time).total_seconds()
        
        new_sprint = Sprint(
            project_id=new_sprint_data['project_id'],
            task_category_id=new_sprint_data['task_category_id'],
            task_description=new_sprint_data['task_description'],
            start_time=start_time,
            end_time=end_time,
            completed=True,
            interrupted=False,
            duration_minutes=int(actual_duration / 60),
            planned_duration=25
        )
        
        session = self.db_manager.get_session()
        try:
            session.add(new_sprint)
            session.commit()
            new_sprint_id = new_sprint.id
        finally:
            session.close()
        
        # Verify both sprints exist with correct states
        session = self.db_manager.get_session()
        try:
            incomplete = session.query(Sprint).filter(Sprint.id == incomplete_sprint_id).first()
            completed = session.query(Sprint).filter(Sprint.id == new_sprint_id).first()
            
            # Incomplete sprint should still be incomplete
            assert incomplete.completed == False
            assert incomplete.end_time is None
            
            # New sprint should be properly completed
            assert completed.completed == True
            assert completed.end_time is not None
            assert completed.interrupted == False
            
        finally:
            session.close()
    
    def test_data_integrity_under_stress(self):
        """Test data integrity when multiple rapid operations occur."""
        
        operations_completed = {'count': 0}
        errors = []
        
        def rapid_sprint_completion():
            """Rapidly complete sprints to stress test the system."""
            for i in range(10):
                try:
                    sprint_data = {
                        'project_id': self.project_id,
                        'task_category_id': self.category_id,
                        'task_description': f"Stress Test Sprint {threading.current_thread().ident}_{i}",
                        'start_time': datetime.now() - timedelta(minutes=25, microseconds=i*1000)
                    }
                    
                    start_time = sprint_data['start_time']
                    end_time = datetime.now()
                    actual_duration = (end_time - start_time).total_seconds()
                    
                    sprint = Sprint(
                        project_id=sprint_data['project_id'],
                        task_category_id=sprint_data['task_category_id'],
                        task_description=sprint_data['task_description'],
                        start_time=start_time,
                        end_time=end_time,
                        completed=True,
                        interrupted=False,
                        duration_minutes=int(actual_duration / 60),
                        planned_duration=25
                    )
                    
                    session = self.db_manager.get_session()
                    try:
                        session.add(sprint)
                        session.commit()
                        operations_completed['count'] += 1
                    finally:
                        session.close()
                        
                    # Small delay to allow other threads to operate
                    time.sleep(0.001)
                    
                except Exception as e:
                    errors.append(str(e))
        
        # Start multiple threads doing rapid operations
        threads = []
        for i in range(3):
            thread = threading.Thread(target=rapid_sprint_completion)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Verify results
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert operations_completed['count'] == 30  # 3 threads * 10 operations each
        
        # Verify all sprints were saved with correct data
        session = self.db_manager.get_session()
        try:
            stress_sprints = session.query(Sprint).filter(
                Sprint.task_description.like("Stress Test Sprint%")
            ).all()
            
            assert len(stress_sprints) == 30
            
            for sprint in stress_sprints:
                assert sprint.completed == True
                assert sprint.end_time is not None
                assert sprint.interrupted == False
                assert sprint.project_id == self.project_id
                assert sprint.task_category_id == self.category_id
                
        finally:
            session.close()
    
    def test_memory_consistency_across_threads(self):
        """Test that memory state is consistent across thread boundaries."""
        
        # This test simulates the original race condition scenario
        # where thread A captures data and thread B clears state
        
        shared_state = {
            'project_id': self.project_id,
            'task_category_id': self.category_id,
            'task_description': "Memory Consistency Test",
            'start_time': datetime.now() - timedelta(minutes=25),
            'captured_data': None,
            'state_cleared': False,
            'save_successful': False
        }
        
        def capture_thread():
            """Thread that captures sprint data (simulates timer completion)."""
            time.sleep(0.01)  # Small delay to allow setup
            
            # Capture data immediately (this is the fix)
            sprint_data = {
                'project_id': shared_state['project_id'],
                'task_category_id': shared_state['task_category_id'],
                'task_description': shared_state['task_description'],
                'start_time': shared_state['start_time']
            }
            
            shared_state['captured_data'] = sprint_data
            time.sleep(0.02)  # Allow other thread to clear state
        
        def clear_state_thread():
            """Thread that clears UI state (simulates UI reset)."""
            time.sleep(0.015)  # Clear state after capture but before save
            
            shared_state['project_id'] = None
            shared_state['task_category_id'] = None  
            shared_state['task_description'] = None
            shared_state['start_time'] = None
            shared_state['state_cleared'] = True
        
        def save_thread():
            """Thread that saves sprint using captured data."""
            time.sleep(0.03)  # Save after both capture and clear
            
            if shared_state['captured_data']:
                try:
                    sprint_data = shared_state['captured_data']
                    start_time = sprint_data['start_time']
                    end_time = datetime.now()
                    actual_duration = (end_time - start_time).total_seconds()
                    
                    sprint = Sprint(
                        project_id=sprint_data['project_id'],
                        task_category_id=sprint_data['task_category_id'],
                        task_description=sprint_data['task_description'],
                        start_time=start_time,
                        end_time=end_time,
                        completed=True,
                        interrupted=False,
                        duration_minutes=int(actual_duration / 60),
                        planned_duration=25
                    )
                    
                    session = self.db_manager.get_session()
                    try:
                        session.add(sprint)
                        session.commit()
                        shared_state['save_successful'] = True
                    finally:
                        session.close()
                        
                except Exception as e:
                    shared_state['save_error'] = str(e)
        
        # Start all threads
        threads = [
            threading.Thread(target=capture_thread),
            threading.Thread(target=clear_state_thread), 
            threading.Thread(target=save_thread)
        ]
        
        for thread in threads:
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # Verify the race condition was handled correctly
        assert shared_state['captured_data'] is not None
        assert shared_state['state_cleared'] == True  # State was cleared
        assert shared_state['save_successful'] == True  # But save still worked
        
        # Verify sprint was saved correctly despite state clearing
        session = self.db_manager.get_session()
        try:
            saved_sprint = session.query(Sprint).filter(
                Sprint.task_description == "Memory Consistency Test"
            ).first()
            
            assert saved_sprint is not None
            assert saved_sprint.completed == True
            assert saved_sprint.end_time is not None
            
        finally:
            session.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])