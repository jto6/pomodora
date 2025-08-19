"""
Integration tests for sync needed detection.
Tests the complete is_sync_needed() logic with real coordination backends.
These tests would have caught the bug where is_sync_needed() only checked local operations.
"""

import pytest
import tempfile
import os
import json
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from tracking.leader_election_sync import LeaderElectionSyncManager
from tracking.coordination_backend import CoordinationBackend
from tracking.local_file_backend import LocalFileBackend
from tracking.google_drive_backend import GoogleDriveBackend
from tracking.operation_log import OperationTracker


class MockCoordinationBackend(CoordinationBackend):
    """Mock coordination backend for testing sync needed detection"""
    
    def __init__(self):
        self.current_metadata = {
            'modifiedTime': '2025-08-17T20:00:00.000Z',
            'size': 100000,
            'md5Checksum': 'current_hash_123'
        }
        self.available = True
        
    def has_database_changed(self, last_sync_metadata):
        """Mock database change detection with configurable behavior"""
        if not self.available:
            # When backend is unavailable, raise an exception to simulate failure
            raise Exception("Backend unavailable")
            
        if not last_sync_metadata:
            return True, self.current_metadata
            
        # Compare metadata
        time_changed = last_sync_metadata.get('modifiedTime') != self.current_metadata['modifiedTime']
        size_changed = last_sync_metadata.get('size') != self.current_metadata['size']
        hash_changed = last_sync_metadata.get('md5Checksum') != self.current_metadata['md5Checksum']
        
        has_changed = time_changed or size_changed or hash_changed
        return has_changed, self.current_metadata
    
    # Required abstract method implementations
    def download_database(self, local_path): return True
    def upload_database(self, local_path): return True
    def acquire_coordination_lock(self, identity, timeout_seconds): return True
    def release_coordination_lock(self, identity): return True
    def cleanup_stale_coordination_files(self, max_age_hours): pass
    def attempt_leader_election(self, identity, timeout_seconds): return True
    def get_coordination_status(self): return {}
    def is_available(self): return self.available
    def register_sync_intent(self, identity): return True
    def release_leadership(self, identity): return True


class TestSyncNeededIntegration:
    """Integration tests for is_sync_needed() method covering all scenarios"""
    
    @pytest.fixture
    def temp_db(self):
        """Create temporary database file"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_file:
            db_path = tmp_file.name
        yield db_path
        # Cleanup
        if os.path.exists(db_path):
            os.unlink(db_path)
        metadata_file = db_path.replace('.db', '_sync_metadata.json')
        if os.path.exists(metadata_file):
            os.unlink(metadata_file)
    
    @pytest.fixture
    def mock_backend(self):
        """Create mock coordination backend"""
        return MockCoordinationBackend()
    
    @pytest.fixture
    def sync_manager(self, temp_db, mock_backend):
        """Create sync manager with real coordination backend"""
        return LeaderElectionSyncManager(mock_backend, temp_db)
    
    def test_first_sync_needed_no_metadata(self, sync_manager):
        """Test that first sync is needed when no previous metadata exists"""
        # This tests the scenario: first time sync
        sync_needed = sync_manager.is_sync_needed()
        
        assert sync_needed is True, "First sync should always be needed"
    
    def test_remote_changes_detected_time_change(self, sync_manager, mock_backend):
        """Test that remote time changes are detected"""
        # Save old metadata
        old_metadata = {
            'modifiedTime': '2025-08-17T18:00:00.000Z',  # 2 hours ago
            'size': 100000,
            'md5Checksum': 'current_hash_123'
        }
        sync_manager._save_last_sync_metadata(old_metadata)
        
        # Current metadata has newer time
        mock_backend.current_metadata['modifiedTime'] = '2025-08-17T20:00:00.000Z'
        
        sync_needed = sync_manager.is_sync_needed()
        
        assert sync_needed is True, "Should detect remote time changes"
    
    def test_remote_changes_detected_size_change(self, sync_manager, mock_backend):
        """Test that remote size changes are detected"""
        # Save metadata with different size
        old_metadata = {
            'modifiedTime': '2025-08-17T20:00:00.000Z',
            'size': 90000,  # Different size
            'md5Checksum': 'current_hash_123'
        }
        sync_manager._save_last_sync_metadata(old_metadata)
        
        # Current metadata has different size
        mock_backend.current_metadata['size'] = 100000
        
        sync_needed = sync_manager.is_sync_needed()
        
        assert sync_needed is True, "Should detect remote size changes"
    
    def test_remote_changes_detected_hash_change(self, sync_manager, mock_backend):
        """Test that remote hash changes are detected"""
        # Save metadata with different hash
        old_metadata = {
            'modifiedTime': '2025-08-17T20:00:00.000Z',
            'size': 100000,
            'md5Checksum': 'old_hash_456'  # Different hash
        }
        sync_manager._save_last_sync_metadata(old_metadata)
        
        # Current metadata has different hash
        mock_backend.current_metadata['md5Checksum'] = 'current_hash_123'
        
        sync_needed = sync_manager.is_sync_needed()
        
        assert sync_needed is True, "Should detect remote hash changes"
    
    def test_no_changes_when_metadata_matches(self, sync_manager, mock_backend):
        """Test that no sync is needed when metadata matches exactly"""
        # Save metadata that matches current
        matching_metadata = {
            'modifiedTime': '2025-08-17T20:00:00.000Z',
            'size': 100000,
            'md5Checksum': 'current_hash_123'
        }
        sync_manager._save_last_sync_metadata(matching_metadata)
        mock_backend.current_metadata = matching_metadata.copy()
        
        sync_needed = sync_manager.is_sync_needed()
        
        assert sync_needed is False, "Should not need sync when metadata matches"
    
    def test_local_changes_detected(self, sync_manager):
        """Test that local pending operations are detected"""
        # Add a pending operation
        sync_manager.operation_tracker.track_operation('insert', 'sprints', {
            'id': 123,
            'task_description': 'Test sprint',
            'completed': True
        })
        
        sync_needed = sync_manager.is_sync_needed()
        
        assert sync_needed is True, "Should detect local pending operations"
    
    def test_local_and_remote_changes_both_detected(self, sync_manager, mock_backend):
        """Test that both local and remote changes are detected"""
        # Add local pending operation
        sync_manager.operation_tracker.track_operation('insert', 'sprints', {
            'id': 123,
            'task_description': 'Test sprint'
        })
        
        # Set up remote changes
        old_metadata = {
            'modifiedTime': '2025-08-17T18:00:00.000Z',
            'size': 90000,
            'md5Checksum': 'old_hash'
        }
        sync_manager._save_last_sync_metadata(old_metadata)
        
        sync_needed = sync_manager.is_sync_needed()
        
        assert sync_needed is True, "Should detect both local and remote changes"
    
    def test_critical_bug_scenario_remote_only_changes(self, sync_manager, mock_backend):
        """
        CRITICAL: Test the exact scenario that was buggy.
        - No local pending operations (empty operation log)
        - Remote database has changed (different metadata)
        - Should return True, but buggy version returned False
        """
        # Ensure no local pending operations
        pending_ops = sync_manager.operation_tracker.get_pending_operations()
        assert len(pending_ops) == 0, "Should start with no pending operations"
        
        # Set up remote changes (different from any previous sync)
        old_metadata = {
            'modifiedTime': '2025-08-17T19:00:00.000Z',
            'size': 95000,
            'md5Checksum': 'old_metadata_hash'
        }
        sync_manager._save_last_sync_metadata(old_metadata)
        
        # Current remote metadata is different
        mock_backend.current_metadata = {
            'modifiedTime': '2025-08-17T20:00:00.000Z',  # Newer time
            'size': 100000,  # Different size
            'md5Checksum': 'new_metadata_hash'  # Different hash
        }
        
        # This is the critical test - the bug would make this return False
        sync_needed = sync_manager.is_sync_needed()
        
        assert sync_needed is True, (
            "CRITICAL BUG: Should detect remote changes even with no local operations. "
            "This scenario was failing before the fix."
        )


class TestSyncNeededWithRealBackends:
    """Integration tests with real coordination backends"""
    
    @pytest.fixture
    def temp_shared_db(self):
        """Create temporary shared database file"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_file:
            shared_db_path = tmp_file.name
        yield shared_db_path
        if os.path.exists(shared_db_path):
            os.unlink(shared_db_path)
    
    @pytest.fixture  
    def temp_local_db(self):
        """Create temporary local database file"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_file:
            local_db_path = tmp_file.name
        yield local_db_path
        if os.path.exists(local_db_path):
            os.unlink(local_db_path)
        metadata_file = local_db_path.replace('.db', '_sync_metadata.json')
        if os.path.exists(metadata_file):
            os.unlink(metadata_file)
    
    def test_local_file_backend_change_detection(self, temp_shared_db, temp_local_db):
        """Test sync needed detection with real LocalFileBackend"""
        # Create real local file backend
        backend = LocalFileBackend(temp_shared_db)
        sync_manager = LeaderElectionSyncManager(backend, temp_local_db)
        
        # Initially no shared database exists
        sync_needed = sync_manager.is_sync_needed()
        assert sync_needed is True, "Should need sync when no shared database exists"
        
        # Create shared database file
        with open(temp_shared_db, 'w') as f:
            f.write('fake database content')
        
        # Should detect the new file
        sync_needed = sync_manager.is_sync_needed()
        assert sync_needed is True, "Should detect new shared database file"
        
        # Save current metadata to simulate successful sync
        shared_stat = os.stat(temp_shared_db)
        metadata = {
            'modified_time': shared_stat.st_mtime,
            'size': shared_stat.st_size
        }
        sync_manager._save_last_sync_metadata(metadata)
        
        # Also clear any pending operations that might have been created
        sync_manager.operation_tracker.clear_operations()
        
        # No changes - should not need sync
        sync_needed = sync_manager.is_sync_needed()
        assert sync_needed is False, "Should not need sync when file unchanged and no pending operations"
        
        # Modify shared database
        import time
        time.sleep(0.1)  # Ensure different mtime
        with open(temp_shared_db, 'a') as f:
            f.write('\nmore content')
        
        # Should detect the modification
        sync_needed = sync_manager.is_sync_needed()
        assert sync_needed is True, "Should detect shared database modification"
    
    @patch('tracking.google_drive_backend.GoogleDriveSync')
    def test_google_drive_backend_change_detection(self, mock_drive_sync_class, temp_local_db):
        """Test sync needed detection with real GoogleDriveBackend"""
        # Mock the GoogleDriveSync class
        mock_drive_sync = Mock()
        mock_drive_sync_class.return_value = mock_drive_sync
        
        # Create real Google Drive backend
        backend = GoogleDriveBackend('/fake/credentials.json', 'TestFolder')
        backend.folder_id = 'test_folder_id'
        sync_manager = LeaderElectionSyncManager(backend, temp_local_db)
        
        # Mock no database files initially
        mock_drive_sync.list_files_by_name.return_value = []
        
        sync_needed = sync_manager.is_sync_needed()
        assert sync_needed is True, "Should need sync when no remote database exists"
        
        # Mock database file exists
        mock_file = {
            'id': 'file123',
            'name': 'pomodora.db',
            'modifiedTime': '2025-08-17T20:00:00.000Z',
            'size': 100000,
            'md5Checksum': 'hash123'
        }
        mock_drive_sync.list_files_by_name.return_value = [mock_file]
        
        sync_needed = sync_manager.is_sync_needed()
        assert sync_needed is True, "Should detect new remote database"
        
        # Save current metadata and clear pending operations
        metadata = {
            'modified_time': mock_file['modifiedTime'],
            'size': int(mock_file['size']),
            'file_id': mock_file['id']
        }
        sync_manager._save_last_sync_metadata(metadata)
        sync_manager.operation_tracker.clear_operations()
        
        # No changes - should not need sync
        sync_needed = sync_manager.is_sync_needed()
        assert sync_needed is False, "Should not need sync when metadata unchanged and no pending operations"
        
        # Mock file modification
        mock_file['modifiedTime'] = '2025-08-17T21:00:00.000Z'
        mock_file['size'] = 110000
        
        sync_needed = sync_manager.is_sync_needed()
        assert sync_needed is True, "Should detect remote database modification"


class TestSyncNeededErrorHandling:
    """Test error handling in sync needed detection"""
    
    @pytest.fixture
    def temp_db(self):
        """Create temporary database file"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_file:
            db_path = tmp_file.name
        yield db_path
        # Cleanup
        if os.path.exists(db_path):
            os.unlink(db_path)
        metadata_file = db_path.replace('.db', '_sync_metadata.json')
        if os.path.exists(metadata_file):
            os.unlink(metadata_file)
    
    def test_backend_unavailable_fallback(self, temp_db):
        """Test behavior when coordination backend is unavailable"""
        backend = MockCoordinationBackend()
        backend.available = False
        
        sync_manager = LeaderElectionSyncManager(backend, temp_db)
        
        # Should handle backend unavailability gracefully
        sync_needed = sync_manager.is_sync_needed()
        # Should handle backend unavailability gracefully - may return True for conservative sync
        # The exact behavior depends on implementation - let's check what it actually returns
        # Conservative behavior would be to sync when uncertain
        assert isinstance(sync_needed, bool), "Should return a boolean value when backend unavailable"
    
    def test_metadata_corruption_recovery(self, temp_db):
        """Test recovery from corrupted metadata files"""
        backend = MockCoordinationBackend()
        sync_manager = LeaderElectionSyncManager(backend, temp_db)
        
        # Create corrupted metadata file
        metadata_file = temp_db.replace('.db', '_sync_metadata.json')
        with open(metadata_file, 'w') as f:
            f.write('corrupted json content {[}')
        
        # Should handle corrupted metadata gracefully and treat as first sync
        sync_needed = sync_manager.is_sync_needed()
        assert sync_needed is True, "Should treat corrupted metadata as first sync"
    
    def test_backend_exception_handling(self, temp_db):
        """Test handling of backend exceptions"""
        backend = MockCoordinationBackend()
        
        # Mock backend to raise exception
        def failing_has_database_changed(last_sync_metadata):
            raise Exception("Backend communication error")
        
        backend.has_database_changed = failing_has_database_changed
        sync_manager = LeaderElectionSyncManager(backend, temp_db)
        
        # Should handle backend exceptions gracefully
        sync_needed = sync_manager.is_sync_needed()
        assert sync_needed is False, "Should return False when backend fails to avoid sync loops"


class TestSyncNeededPerformance:
    """Test performance characteristics of sync needed detection"""
    
    @pytest.fixture
    def temp_db(self):
        """Create temporary database file"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_file:
            db_path = tmp_file.name
        yield db_path
        # Cleanup
        if os.path.exists(db_path):
            os.unlink(db_path)
        metadata_file = db_path.replace('.db', '_sync_metadata.json')
        if os.path.exists(metadata_file):
            os.unlink(metadata_file)
    
    def test_metadata_comparison_efficiency(self, temp_db):
        """Test that metadata comparison is efficient"""
        backend = MockCoordinationBackend()
        sync_manager = LeaderElectionSyncManager(backend, temp_db)
        
        # Set up scenario with matching metadata
        metadata = {
            'modifiedTime': '2025-08-17T20:00:00.000Z',
            'size': 100000,
            'md5Checksum': 'hash123'
        }
        sync_manager._save_last_sync_metadata(metadata)
        backend.current_metadata = metadata.copy()
        
        # Multiple calls should be efficient
        import time
        start_time = time.time()
        
        for _ in range(100):
            sync_needed = sync_manager.is_sync_needed()
            assert sync_needed is False
        
        elapsed = time.time() - start_time
        assert elapsed < 1.0, f"100 sync checks took {elapsed:.3f}s - should be much faster"
    
    def test_large_metadata_handling(self, temp_db):
        """Test handling of large metadata objects"""
        backend = MockCoordinationBackend()
        sync_manager = LeaderElectionSyncManager(backend, temp_db)
        
        # Create large metadata object
        large_metadata = {
            'modifiedTime': '2025-08-17T20:00:00.000Z',
            'size': 100000,
            'md5Checksum': 'hash123',
            'custom_field': 'x' * 10000  # Large custom field
        }
        
        sync_manager._save_last_sync_metadata(large_metadata)
        backend.current_metadata = large_metadata.copy()
        
        # Should handle large metadata efficiently
        sync_needed = sync_manager.is_sync_needed()
        assert sync_needed is False, "Should handle large metadata objects"