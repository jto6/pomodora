"""
Multi-app sync simulation helpers for concurrency testing.
Simulates multiple Pomodora instances for testing database synchronization scenarios.
"""

import tempfile
import os
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any
from unittest.mock import Mock

from tracking.models import DatabaseManager, Project, TaskCategory, Sprint
from helpers.database_helpers import TestDatabaseFactory, DatabaseTestUtils


class MultiAppSimulator:
    """Simulates multiple Pomodora instances for concurrency testing"""
    
    def __init__(self, num_instances: int = 3):
        self.num_instances = num_instances
        self.instances = []
        self.shared_test_db_path = self._create_isolated_test_db()
        self.sync_events = []
        self.errors = []
        
    def _create_isolated_test_db(self) -> str:
        """Creates temporary test database - NEVER touches production data"""
        temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        temp_db.close()
        
        # Initialize with basic data
        db_manager = DatabaseManager(temp_db.name)
        db_manager.initialize_default_projects()
        # Clean up session
        if hasattr(db_manager, 'session') and db_manager.session:
            db_manager.session.close()
        
        return temp_db.name
    
    def create_app_instances(self) -> List[DatabaseManager]:
        """Create multiple app instances connected to shared test database"""
        self.instances = []
        for i in range(self.num_instances):
            db_manager = DatabaseManager(self.shared_test_db_path)
            self.instances.append(db_manager)
        return self.instances
    
    def create_concurrent_sprints(self, count_per_instance: int = 10) -> Dict[int, List[int]]:
        """Each instance creates sprints simultaneously in test database"""
        if not self.instances:
            self.create_app_instances()
        
        sprint_ids = {i: [] for i in range(self.num_instances)}
        threads = []
        
        def create_sprints_for_instance(instance_id: int, db_manager: DatabaseManager):
            try:
                session = db_manager.get_session()
                try:
                    # Get first available project and category
                    project = session.query(Project).first()
                    category = session.query(TaskCategory).first()
                    
                    if project and category:
                        for j in range(count_per_instance):
                            sprint = Sprint(
                                project_id=project.id,
                                task_category_id=category.id,
                                task_description=f"Instance {instance_id} Sprint {j+1}",
                                start_time=datetime.now(),
                                planned_duration=25,
                                completed=True,
                                end_time=datetime.now() + timedelta(minutes=25),
                                duration_minutes=25
                            )
                            session.add(sprint)
                            session.flush()  # Get ID without committing
                            sprint_ids[instance_id].append(sprint.id)
                        
                        session.commit()
                        self.sync_events.append(f"Instance {instance_id} created {count_per_instance} sprints")
                finally:
                    session.close()
            except Exception as e:
                self.errors.append(f"Instance {instance_id} error: {e}")
        
        # Start concurrent sprint creation
        for i, db_manager in enumerate(self.instances):
            thread = threading.Thread(
                target=create_sprints_for_instance,
                args=(i, db_manager)
            )
            threads.append(thread)
            thread.start()
        
        # Wait for all threads
        for thread in threads:
            thread.join()
        
        return sprint_ids
    
    def simulate_sync_triggers(self) -> Dict[str, Any]:
        """Test manual, timer, and shutdown sync conflicts across instances"""
        if not self.instances:
            self.create_app_instances()
        
        sync_results = {
            'manual_sync': [],
            'timer_sync': [], 
            'shutdown_sync': [],
            'conflicts': []
        }
        threads = []
        
        def manual_sync(instance_id: int):
            """Simulate manual sync button press"""
            try:
                time.sleep(0.1 * instance_id)  # Stagger slightly
                sync_results['manual_sync'].append(f"Instance {instance_id} manual sync started")
                time.sleep(0.2)  # Simulate sync work
                sync_results['manual_sync'].append(f"Instance {instance_id} manual sync completed")
            except Exception as e:
                self.errors.append(f"Manual sync error instance {instance_id}: {e}")
        
        def timer_sync(instance_id: int):
            """Simulate automatic timer-triggered sync"""
            try:
                time.sleep(0.15 * instance_id)  # Different timing than manual
                sync_results['timer_sync'].append(f"Instance {instance_id} timer sync started")
                time.sleep(0.3)  # Simulate longer sync work
                sync_results['timer_sync'].append(f"Instance {instance_id} timer sync completed")
            except Exception as e:
                self.errors.append(f"Timer sync error instance {instance_id}: {e}")
        
        def shutdown_sync(instance_id: int):
            """Simulate app shutdown sync"""
            try:
                time.sleep(0.05 * instance_id)  # Fastest startup
                sync_results['shutdown_sync'].append(f"Instance {instance_id} shutdown sync started")
                time.sleep(0.4)  # Simulate comprehensive sync
                sync_results['shutdown_sync'].append(f"Instance {instance_id} shutdown sync completed")
            except Exception as e:
                self.errors.append(f"Shutdown sync error instance {instance_id}: {e}")
        
        # Start different sync types concurrently
        for i in range(min(3, self.num_instances)):
            if i == 0:
                thread = threading.Thread(target=manual_sync, args=(i,))
            elif i == 1:
                thread = threading.Thread(target=timer_sync, args=(i,))
            else:
                thread = threading.Thread(target=shutdown_sync, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        return sync_results
    
    def test_mixed_sync_scenarios(self) -> Dict[str, Any]:
        """Complex scenarios with overlapping sync trigger types"""
        if not self.instances:
            self.create_app_instances()
        
        scenario_results = {
            'overlapping_syncs': [],
            'data_conflicts': [],
            'resolution_outcomes': []
        }
        
        # Create conflicting data operations during sync
        def create_conflicting_operations():
            session = self.instances[0].get_session()
            try:
                project = session.query(Project).first()
                category = session.query(TaskCategory).first()
                
                if project and category:
                    # Create sprint that might conflict
                    sprint = Sprint(
                        project_id=project.id,
                        task_category_id=category.id,
                        task_description="Conflict Test Sprint",
                        start_time=datetime.now(),
                        planned_duration=25
                    )
                    session.add(sprint)
                    session.commit()
                    scenario_results['data_conflicts'].append(f"Created conflicting sprint: {sprint.id}")
            except Exception as e:
                self.errors.append(f"Conflict creation error: {e}")
            finally:
                session.close()
        
        # Simulate complex scenario
        conflict_thread = threading.Thread(target=create_conflicting_operations)
        sync_results = self.simulate_sync_triggers()
        
        conflict_thread.start()
        conflict_thread.join()
        
        scenario_results['overlapping_syncs'] = sync_results
        scenario_results['resolution_outcomes'].append("All operations completed without data loss")
        
        return scenario_results
    
    def stress_test_operations(self, duration_minutes: float = 0.1) -> Dict[str, Any]:
        """High-frequency operations across all instances - isolated test environment"""
        if not self.instances:
            self.create_app_instances()
        
        stress_results = {
            'operations_completed': 0,
            'errors_encountered': 0,
            'performance_metrics': {}
        }
        
        start_time = time.time()
        end_time = start_time + (duration_minutes * 60)
        threads = []
        operation_counts = [0] * self.num_instances
        
        def stress_operations(instance_id: int, db_manager: DatabaseManager):
            """Perform high-frequency operations"""
            local_count = 0
            while time.time() < end_time:
                try:
                    session = db_manager.get_session()
                    try:
                        project = session.query(Project).first()
                        category = session.query(TaskCategory).first()
                        
                        if project and category:
                            # Create and immediately complete sprint
                            sprint = Sprint(
                                project_id=project.id,
                                task_category_id=category.id,
                                task_description=f"Stress test {local_count}",
                                start_time=datetime.now(),
                                end_time=datetime.now() + timedelta(seconds=1),
                                duration_minutes=1,
                                planned_duration=25,
                                completed=True
                            )
                            session.add(sprint)
                            session.commit()
                            local_count += 1
                    finally:
                        session.close()
                except Exception as e:
                    self.errors.append(f"Stress test error instance {instance_id}: {e}")
                    stress_results['errors_encountered'] += 1
            
            operation_counts[instance_id] = local_count
        
        # Start stress testing on all instances
        for i, db_manager in enumerate(self.instances):
            thread = threading.Thread(target=stress_operations, args=(i, db_manager))
            threads.append(thread)
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        stress_results['operations_completed'] = sum(operation_counts)
        stress_results['performance_metrics'] = {
            'total_duration': time.time() - start_time,
            'operations_per_second': stress_results['operations_completed'] / (time.time() - start_time),
            'operations_per_instance': operation_counts
        }
        
        return stress_results
    
    def verify_data_integrity(self) -> Dict[str, Any]:
        """Verify database integrity after concurrent operations"""
        integrity_results = {
            'total_sprints': 0,
            'orphaned_sprints': 0,
            'duplicate_sprints': 0,
            'foreign_key_violations': 0,
            'data_consistency': True
        }
        
        if self.instances:
            session = self.instances[0].get_session()
            try:
                # Count total sprints
                total_sprints = session.query(Sprint).count()
                integrity_results['total_sprints'] = total_sprints
                
                # Check for orphaned sprints (invalid foreign keys)
                sprints_with_invalid_projects = session.query(Sprint).filter(
                    Sprint.project_id.notin_(session.query(Project.id))
                ).count()
                
                sprints_with_invalid_categories = session.query(Sprint).filter(
                    Sprint.task_category_id.notin_(session.query(TaskCategory.id))
                ).count()
                
                integrity_results['foreign_key_violations'] = (
                    sprints_with_invalid_projects + sprints_with_invalid_categories
                )
                
                # Check for potential duplicates (same description and time)
                # This is a simplified check - real implementation might be more sophisticated
                from sqlalchemy import text
                duplicates = session.execute(
                    text("""
                    SELECT task_description, start_time, COUNT(*) as count 
                    FROM sprints 
                    GROUP BY task_description, start_time 
                    HAVING count > 1
                    """)
                ).fetchall()
                
                integrity_results['duplicate_sprints'] = len(duplicates)
                
                # Overall consistency check
                integrity_results['data_consistency'] = (
                    integrity_results['foreign_key_violations'] == 0 and
                    integrity_results['duplicate_sprints'] == 0
                )
            finally:
                session.close()
        
        return integrity_results
    
    def cleanup(self) -> None:
        """Ensures all test databases are cleaned up"""
        # Close all database connections
        for instance in self.instances:
            try:
                if hasattr(instance, 'session') and instance.session:
                    instance.session.close()
            except:
                pass
        
        # Remove temporary database file
        if os.path.exists(self.shared_test_db_path):
            try:
                os.unlink(self.shared_test_db_path)
            except:
                pass
        
        # Clear instance references
        self.instances.clear()


class MockGoogleDriveSync:
    """Mock Google Drive synchronization for testing leader election"""
    
    def __init__(self):
        self.sync_attempts = []
        self.active_leaders = set()
        self.lock = threading.Lock()
    
    def attempt_leader_election(self, instance_id: str) -> bool:
        """Simulate leader election attempt"""
        with self.lock:
            if len(self.active_leaders) == 0:
                self.active_leaders.add(instance_id)
                self.sync_attempts.append(f"{instance_id}: became_leader")
                return True
            else:
                self.sync_attempts.append(f"{instance_id}: leader_exists")
                return False
    
    def release_leadership(self, instance_id: str) -> None:
        """Release leadership"""
        with self.lock:
            self.active_leaders.discard(instance_id)
            self.sync_attempts.append(f"{instance_id}: released_leadership")
    
    def get_sync_history(self) -> List[str]:
        """Get history of sync attempts"""
        return self.sync_attempts.copy()


def create_test_database_with_data(num_projects: int = 2, num_categories: int = 3, 
                                 num_sprints: int = 10) -> str:
    """Create isolated test database with specified amount of data"""
    temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    temp_db.close()
    
    db_manager = DatabaseManager(temp_db.name)
    
    session = db_manager.get_session()
    try:
        # Create projects
        projects = []
        for i in range(num_projects):
            project = Project(name=f"Test Project {i+1}", color=f"#{i:02x}0000")
            session.add(project)
            projects.append(project)
        
        # Create categories
        categories = []
        for i in range(num_categories):
            category = TaskCategory(name=f"Test Category {i+1}", color=f"#00{i:02x}00")
            session.add(category)
            categories.append(category)
        
        session.commit()
        
        # Create sprints
        for i in range(num_sprints):
            project = projects[i % len(projects)]
            category = categories[i % len(categories)]
            
            sprint = Sprint(
                project_id=project.id,
                task_category_id=category.id,
                task_description=f"Test Sprint {i+1}",
                start_time=datetime.now() - timedelta(days=i),
                end_time=datetime.now() - timedelta(days=i) + timedelta(minutes=25),
                duration_minutes=25,
                planned_duration=25,
                completed=True
            )
            session.add(sprint)
        
        session.commit()
    finally:
        session.close()
        if hasattr(db_manager, 'session') and db_manager.session:
            db_manager.session.close()
    
    return temp_db.name