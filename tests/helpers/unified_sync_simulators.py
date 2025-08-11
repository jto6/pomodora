"""
Unified sync simulators for testing both LocalFile and GoogleDrive coordination backends.
Uses the same leader election logic to test concurrency scenarios with different backends.
"""

import tempfile
import os
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
from unittest.mock import Mock

from tracking.database_manager_unified import UnifiedDatabaseManager
from tracking.sync_config import SyncConfiguration
from tracking.models import Project, TaskCategory, Sprint


class UnifiedSyncSimulator:
    """
    Simulates multiple app instances using unified leader election sync.
    Can test both LocalFile and GoogleDrive coordination backends.
    """
    
    def __init__(self, backend_type: str = "local_file", num_instances: int = 3):
        self.backend_type = backend_type
        self.num_instances = num_instances
        self.instances = []
        self.sync_events = []
        self.errors = []
        
        # Create test environment based on backend type
        if backend_type == "local_file":
            self._setup_local_file_test()
        elif backend_type == "google_drive":
            self._setup_google_drive_test()
        else:
            raise ValueError(f"Unknown backend type: {backend_type}")
    
    def _setup_local_file_test(self) -> None:
        """Set up local file backend test environment"""
        # Create temporary shared directory
        self.test_dir = Path(tempfile.mkdtemp(prefix="pomodora_test_"))
        self.shared_db_path = self.test_dir / "shared_pomodora.db"
        
        # Create sync configurations for each instance
        self.sync_configs = []
        for i in range(self.num_instances):
            config = SyncConfiguration()
            config.set_local_file_backend(str(self.shared_db_path))
            # Each instance has its own local cache
            cache_path = self.test_dir / f"cache_{i}" / "pomodora.db" 
            config.settings.set('local_cache_db_path', str(cache_path))
            self.sync_configs.append(config)
        
        print(f"LocalFile test setup:")
        print(f"  Shared DB: {self.shared_db_path}")
        print(f"  Test dir: {self.test_dir}")
    
    def _setup_google_drive_test(self) -> None:
        """Set up Google Drive backend test environment with mocks"""
        # Create temporary directory for local caches
        self.test_dir = Path(tempfile.mkdtemp(prefix="pomodora_gdrive_test_"))
        
        # Create mock Google Drive backend for testing
        self.mock_drive_files = {}  # Simulate Google Drive files
        self.mock_coordination_files = {}  # Simulate coordination files
        self.coordination_lock = threading.Lock()
        
        # Create sync configurations for each instance
        self.sync_configs = []
        for i in range(self.num_instances):
            config = SyncConfiguration()
            # Use mock credentials (won't actually connect to Google Drive)
            config.set_google_drive_backend("mock_credentials.json", "TestFolder")
            # Each instance has its own local cache
            cache_path = self.test_dir / f"cache_{i}" / "pomodora.db"
            config.settings.set('local_cache_db_path', str(cache_path))
            self.sync_configs.append(config)
        
        print(f"GoogleDrive test setup (mocked):")
        print(f"  Test dir: {self.test_dir}")
        print(f"  Mock folder: TestFolder")
    
    def create_app_instances(self) -> List[UnifiedDatabaseManager]:
        """Create multiple app instances with unified database managers"""
        self.instances = []
        
        for i, sync_config in enumerate(self.sync_configs):
            try:
                # For testing, we need to mock Google Drive if that's the backend
                if self.backend_type == "google_drive":
                    # Replace with mock backend
                    mock_backend = self._create_mock_google_drive_backend(i)
                    
                    # Create database manager with mock backend
                    db_manager = UnifiedDatabaseManager(sync_config=sync_config)
                    if db_manager.coordination_backend:
                        # Replace with our mock
                        db_manager.coordination_backend = mock_backend
                        # Update sync manager with mock backend
                        from tracking.leader_election_sync import LeaderElectionSyncManager
                        db_manager.sync_manager = LeaderElectionSyncManager(
                            mock_backend, str(db_manager.db_path)
                        )
                else:
                    # Local file backend works as-is
                    db_manager = UnifiedDatabaseManager(sync_config=sync_config)
                
                self.instances.append(db_manager)
                
            except Exception as e:
                self.errors.append(f"Failed to create instance {i}: {e}")
        
        print(f"Created {len(self.instances)} app instances")
        return self.instances
    
    def _create_mock_google_drive_backend(self, instance_id: int) -> 'MockGoogleDriveBackend':
        """Create mock Google Drive backend for testing"""
        return MockGoogleDriveBackend(
            instance_id, 
            self.mock_drive_files, 
            self.mock_coordination_files,
            self.coordination_lock
        )
    
    def create_concurrent_sprints(self, count_per_instance: int = 10) -> Dict[int, List[int]]:
        """Each instance creates sprints simultaneously using unified database managers"""
        if not self.instances:
            self.create_app_instances()
        
        sprint_ids = {i: [] for i in range(self.num_instances)}
        threads = []
        
        def create_sprints_for_instance(instance_id: int, db_manager: UnifiedDatabaseManager):
            try:
                session = db_manager.get_session()
                try:
                    # Get first available project and category
                    project = session.query(Project).first()
                    category = session.query(TaskCategory).first()
                    
                    if project and category:
                        for j in range(count_per_instance):
                            # Use unified database manager method
                            sprint = db_manager.add_sprint(
                                project.id,
                                category.id,
                                f"Instance {instance_id} Sprint {j+1}",
                                datetime.now(),
                                25
                            )
                            
                            if sprint:
                                sprint_ids[instance_id].append(sprint.id)
                        
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
        """Test manual, timer, and shutdown sync using unified sync managers"""
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
                
                # Use unified database manager sync
                success = self.instances[instance_id].trigger_manual_sync()
                
                status = "completed" if success else "failed"
                sync_results['manual_sync'].append(f"Instance {instance_id} manual sync {status}")
            except Exception as e:
                self.errors.append(f"Manual sync error instance {instance_id}: {e}")
        
        def timer_sync(instance_id: int):
            """Simulate automatic timer-triggered sync"""
            try:
                time.sleep(0.15 * instance_id)  # Different timing than manual
                sync_results['timer_sync'].append(f"Instance {instance_id} timer sync started")
                
                # Use unified database manager sync
                success = self.instances[instance_id].trigger_auto_sync()
                
                status = "completed" if success else "failed"
                sync_results['timer_sync'].append(f"Instance {instance_id} timer sync {status}")
            except Exception as e:
                self.errors.append(f"Timer sync error instance {instance_id}: {e}")
        
        def shutdown_sync(instance_id: int):
            """Simulate app shutdown sync"""
            try:
                time.sleep(0.05 * instance_id)  # Fastest startup
                sync_results['shutdown_sync'].append(f"Instance {instance_id} shutdown sync started")
                
                # Use unified database manager sync
                success = self.instances[instance_id].trigger_shutdown_sync()
                
                status = "completed" if success else "failed"
                sync_results['shutdown_sync'].append(f"Instance {instance_id} shutdown sync {status}")
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
    
    def verify_data_integrity(self) -> Dict[str, Any]:
        """Verify database integrity after concurrent operations"""
        integrity_results = {
            'total_sprints': 0,
            'orphaned_sprints': 0,
            'duplicate_sprints': 0,
            'foreign_key_violations': 0,
            'data_consistency': True,
            'backend_type': self.backend_type
        }
        
        if self.instances:
            db_manager = self.instances[0]
            session = db_manager.get_session()
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
                from sqlalchemy import text, func
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
    
    def get_sync_status(self) -> Dict[str, Any]:
        """Get sync status from all instances"""
        status = {
            'backend_type': self.backend_type,
            'num_instances': len(self.instances),
            'instances': []
        }
        
        for i, instance in enumerate(self.instances):
            try:
                instance_status = instance.get_sync_status()
                instance_status['instance_id'] = i
                status['instances'].append(instance_status)
            except Exception as e:
                status['instances'].append({
                    'instance_id': i,
                    'error': str(e)
                })
        
        return status
    
    def cleanup(self) -> None:
        """Clean up test environment"""
        # Close all database connections
        for instance in self.instances:
            try:
                if hasattr(instance, 'engine') and instance.engine:
                    instance.engine.dispose()
            except:
                pass
        
        # Remove test directory
        if hasattr(self, 'test_dir') and self.test_dir.exists():
            import shutil
            try:
                shutil.rmtree(self.test_dir)
            except:
                pass
        
        # Clear instance references
        self.instances.clear()


class MockGoogleDriveBackend:
    """
    Mock Google Drive backend for testing leader election without actual Google Drive.
    Implements same interface as real GoogleDriveBackend but uses in-memory storage.
    """
    
    def __init__(self, instance_id: int, shared_files: Dict[str, Any], 
                 coordination_files: Dict[str, Any], lock: threading.Lock):
        self.instance_id = instance_id
        self.shared_files = shared_files
        self.coordination_files = coordination_files
        self.lock = lock
        self.mock_instance_id = f"mock_instance_{instance_id}_{int(time.time())}"
        
    def is_available(self) -> bool:
        return True
        
    def register_sync_intent(self, operation_type: str = "sync") -> bool:
        with self.lock:
            intent_key = f"intent_{self.mock_instance_id}.json"
            self.coordination_files[intent_key] = {
                "instance_id": self.mock_instance_id,
                "operation_type": operation_type,
                "timestamp": datetime.now().isoformat()
            }
            return True
    
    def attempt_leader_election(self, timeout_seconds: int = 30) -> bool:
        start_time = time.time()
        
        while time.time() - start_time < timeout_seconds:
            with self.lock:
                # Check for existing leaders
                existing_leaders = [k for k in self.coordination_files.keys() 
                                 if k.startswith("leader_")]
                
                if not existing_leaders:
                    # Become leader
                    leader_key = f"leader_{self.mock_instance_id}.json"
                    self.coordination_files[leader_key] = {
                        "instance_id": self.mock_instance_id,
                        "elected_at": datetime.now().isoformat()
                    }
                    return True
            
            time.sleep(0.1)
        
        return False
    
    def upload_database(self, local_db_path: str, backup_info: Optional[Dict[str, Any]] = None) -> bool:
        with self.lock:
            # Simulate database upload
            try:
                with open(local_db_path, 'rb') as f:
                    db_content = f.read()
                self.shared_files["pomodora.db"] = {
                    "content": db_content,
                    "size": len(db_content),
                    "uploaded_by": self.mock_instance_id,
                    "timestamp": datetime.now().isoformat()
                }
                return True
            except Exception:
                return False
    
    def download_database(self, local_cache_path: str) -> bool:
        with self.lock:
            if "pomodora.db" not in self.shared_files:
                return True  # No remote database
            
            try:
                Path(local_cache_path).parent.mkdir(parents=True, exist_ok=True)
                with open(local_cache_path, 'wb') as f:
                    f.write(self.shared_files["pomodora.db"]["content"])
                return True
            except Exception:
                return False
    
    def release_leadership(self) -> None:
        with self.lock:
            # Remove leader and intent files
            keys_to_remove = []
            for key in self.coordination_files.keys():
                if (key.startswith(f"leader_{self.mock_instance_id}") or 
                    key.startswith(f"intent_{self.mock_instance_id}")):
                    keys_to_remove.append(key)
            
            for key in keys_to_remove:
                self.coordination_files.pop(key, None)
    
    def cleanup_stale_coordination_files(self, max_age_hours: int = 1) -> None:
        with self.lock:
            cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
            
            keys_to_remove = []
            for key, data in self.coordination_files.items():
                try:
                    file_time = datetime.fromisoformat(data["timestamp"])
                    if file_time < cutoff_time:
                        keys_to_remove.append(key)
                except:
                    keys_to_remove.append(key)  # Remove malformed entries
            
            for key in keys_to_remove:
                self.coordination_files.pop(key, None)
    
    def get_coordination_status(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "backend_type": "mock_google_drive",
                "instance_id": self.mock_instance_id,
                "coordination_files": len(self.coordination_files),
                "shared_files": len(self.shared_files),
                "is_leader": any(k.startswith(f"leader_{self.mock_instance_id}") 
                               for k in self.coordination_files.keys())
            }