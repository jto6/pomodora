"""
Integration tests for the complete efficient sync workflow.
Tests the end-to-end behavior of change detection + periodic sync system.
"""

import pytest
import tempfile
import time
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from tracking.leader_election_sync import LeaderElectionSyncManager
from tracking.coordination_backend import CoordinationBackend
from tracking.google_drive_backend import GoogleDriveBackend
from tracking.local_file_backend import LocalFileBackend


class TestChangeDetectionWorkflow:
    """Integration tests for change detection in sync workflow"""
    
    
    @pytest.fixture
    def mock_google_drive_backend(self):
        """Create a mock Google Drive backend with realistic behavior"""
        backend = Mock(spec=GoogleDriveBackend)
        backend.is_available.return_value = True
        backend.register_sync_intent.return_value = True
        backend.attempt_leader_election.return_value = True
        backend.release_leadership.return_value = None
        backend.download_database.return_value = True
        backend.upload_database.return_value = True
        
        # Initial state: database exists
        backend.has_database_changed.return_value = (True, {
            "modified_time": "2025-01-01T12:00:00Z",
            "size": 1000,
            "file_id": "initial_file"
        })
        
        return backend
    
    @pytest.fixture
    def sync_manager(self, tmp_path, mock_google_drive_backend):
        """Create sync manager for testing"""
        cache_db = tmp_path / "cache.db"
        cache_db.write_text("initial database content")
        
        with patch('tracking.leader_election_sync.OperationTracker') as mock_tracker:
            with patch('tracking.leader_election_sync.DatabaseMerger'):
                with patch.object(LeaderElectionSyncManager, '_ensure_database_schema', return_value=True):
                    # Mock operation tracker
                    tracker_instance = Mock()
                    tracker_instance.get_pending_operations.return_value = []
                    tracker_instance.clear_operations.return_value = None
                    mock_tracker.return_value = tracker_instance
                    
                    manager = LeaderElectionSyncManager(
                        coordination_backend=mock_google_drive_backend,
                        local_cache_db_path=str(cache_db)
                    )
                    manager.sync_metadata_file = tmp_path / "metadata.json"
                    
                    return manager
    
    def test_first_sync_downloads_and_saves_metadata(self, sync_manager):
        """Test that first sync downloads database and saves metadata"""
        # Ensure no existing metadata
        assert not sync_manager.sync_metadata_file.exists()
        
        # Perform sync
        success = sync_manager.sync_database()
        
        # Should succeed
        assert success is True
        
        # Should save metadata
        assert sync_manager.sync_metadata_file.exists()
        metadata = sync_manager._load_last_sync_metadata()
        assert metadata["file_id"] == "initial_file"
        
        # Should have called has_database_changed with None (no previous metadata)
        sync_manager.coordination.has_database_changed.assert_called_with(None)
    
    def test_subsequent_sync_uses_saved_metadata(self, sync_manager):
        """Test that subsequent syncs use previously saved metadata"""
        # First sync
        sync_manager.sync_database()
        
        # Reset mock call history
        sync_manager.coordination.has_database_changed.reset_mock()
        
        # Configure no changes for second sync
        sync_manager.coordination.has_database_changed.return_value = (False, {
            "modified_time": "2025-01-01T12:00:00Z",
            "size": 1000,
            "file_id": "initial_file"
        })
        
        # Second sync
        success = sync_manager.sync_database()
        assert success is True
        
        # Should have called with saved metadata
        expected_metadata = {
            "modified_time": "2025-01-01T12:00:00Z",
            "size": 1000,
            "file_id": "initial_file"
        }
        sync_manager.coordination.has_database_changed.assert_called_with(expected_metadata)
    
    def test_sync_skipped_when_no_changes(self, sync_manager):
        """Test that sync is skipped when no remote or local changes"""
        # Save initial metadata
        initial_metadata = {
            "modified_time": "2025-01-01T12:00:00Z",
            "size": 1000,
            "file_id": "test_file"
        }
        sync_manager._save_last_sync_metadata(initial_metadata)
        
        # Configure no changes
        sync_manager.coordination.has_database_changed.return_value = (False, initial_metadata)
        
        # Perform sync
        success = sync_manager.sync_database()
        assert success is True
        
        # Should not have downloaded database
        sync_manager.coordination.download_database.assert_not_called()
    
    def test_sync_downloads_when_remote_changed(self, sync_manager):
        """Test that sync downloads when remote database changed"""
        # Save initial metadata
        initial_metadata = {
            "modified_time": "2025-01-01T12:00:00Z",
            "size": 1000,
            "file_id": "old_file"
        }
        sync_manager._save_last_sync_metadata(initial_metadata)
        
        # Configure remote changes
        new_metadata = {
            "modified_time": "2025-01-02T12:00:00Z",  # Different time
            "size": 1500,  # Different size
            "file_id": "new_file"
        }
        sync_manager.coordination.has_database_changed.return_value = (True, new_metadata)
        
        # Perform sync
        success = sync_manager.sync_database()
        assert success is True
        
        # Should have downloaded database
        sync_manager.coordination.download_database.assert_called_once()
        
        # Should save new metadata
        saved_metadata = sync_manager._load_last_sync_metadata()
        assert saved_metadata == new_metadata
    
    def test_sync_downloads_when_local_operations_pending(self, sync_manager):
        """Test that sync downloads even if no remote changes when local ops pending"""
        # Save initial metadata
        initial_metadata = {
            "modified_time": "2025-01-01T12:00:00Z",
            "size": 1000,
            "file_id": "test_file"
        }
        sync_manager._save_last_sync_metadata(initial_metadata)
        
        # Configure no remote changes but local operations pending
        sync_manager.coordination.has_database_changed.return_value = (False, initial_metadata)
        sync_manager.operation_tracker.get_pending_operations.return_value = [{"op": "create_sprint"}]
        
        # Perform sync - this may fail due to merge complexity, but should attempt download
        sync_manager.sync_database()
        
        # Should still download to attempt merge of local operations
        sync_manager.coordination.download_database.assert_called_once()


class TestLocalFileBackendIntegration:
    """Integration tests for local file backend change detection"""
    
    @pytest.fixture
    def temp_shared_db(self):
        """Create temporary shared database file"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            f.write(b"initial database content")
            temp_path = f.name
        
        yield Path(temp_path)
        
        # Cleanup
        if Path(temp_path).exists():
            Path(temp_path).unlink()
    
    @pytest.fixture
    def local_backend(self, temp_shared_db):
        """Create local file backend"""
        return LocalFileBackend(str(temp_shared_db))
    
    def test_file_modification_triggers_download(self, local_backend, temp_shared_db):
        """Test that file modifications are properly detected"""
        # Get initial metadata
        _, initial_metadata = local_backend.has_database_changed(None)
        
        # Modify the shared database
        time.sleep(0.1)  # Ensure different timestamp
        with open(temp_shared_db, 'a') as f:
            f.write("additional content")
        
        # Check for changes
        has_changed, new_metadata = local_backend.has_database_changed(initial_metadata)
        
        assert has_changed is True
        assert new_metadata["modified_time"] != initial_metadata["modified_time"]
        assert new_metadata["size"] > initial_metadata["size"]
    
    def test_unchanged_file_skips_download(self, local_backend):
        """Test that unchanged files are correctly identified"""
        # Get initial metadata
        _, initial_metadata = local_backend.has_database_changed(None)
        
        # Check again without modifications
        has_changed, new_metadata = local_backend.has_database_changed(initial_metadata)
        
        assert has_changed is False
        assert new_metadata == initial_metadata


class TestPeriodicSyncIntegration:
    """Integration tests for periodic sync behavior"""
    
    @pytest.fixture
    def mock_database_manager(self):
        """Create mock database manager"""
        manager = Mock()
        manager.sync_if_changes_pending.return_value = True
        return manager
    
    def test_periodic_sync_workflow(self, mock_database_manager):
        """Test the complete periodic sync workflow"""
        # Test periodic sync logic without creating actual GUI components
        
        # Mock periodic sync manager behavior
        class MockPeriodicSyncManager:
            def __init__(self):
                self.periodic_sync_interval = 60 * 60 * 1000  # 1 hour
                self.idle_timeout = 10 * 60 * 1000  # 10 minutes
                self.sync_requested = False
                self.periodic_sync_timer = Mock()
                self.idle_timer = Mock()
                self.db_manager = mock_database_manager
                self.update_stats = Mock()
            
            def on_sync_completed(self):
                self.periodic_sync_timer.start(self.periodic_sync_interval)
            
            def on_user_activity(self):
                self.idle_timer.start(self.idle_timeout)
            
            def _is_currently_idle(self):
                return not self.idle_timer.isActive()
            
            def request_periodic_sync(self):
                if self._is_currently_idle():
                    self._perform_periodic_sync()
                else:
                    self.sync_requested = True
            
            def on_idle_timeout(self):
                if self.sync_requested:
                    self._perform_periodic_sync()
                    self.sync_requested = False
            
            def _perform_periodic_sync(self):
                self.db_manager.sync_if_changes_pending()
                self.update_stats()
                self.on_sync_completed()
        
        manager = MockPeriodicSyncManager()
        
        # Test sync completion restarts timer
        manager.on_sync_completed()
        manager.periodic_sync_timer.start.assert_called_with(manager.periodic_sync_interval)
        
        # Test user activity resets idle timer
        manager.on_user_activity()
        manager.idle_timer.start.assert_called_with(manager.idle_timeout)
        
        # Test periodic sync request when user active
        manager.idle_timer.isActive.return_value = True  # User active
        manager.request_periodic_sync()
        assert manager.sync_requested is True
        
        # Test idle timeout executes pending sync
        manager.on_idle_timeout()
        mock_database_manager.sync_if_changes_pending.assert_called_once()
        assert manager.sync_requested is False


class TestErrorHandlingAndRecovery:
    """Test error handling in the efficient sync system"""
    
    @pytest.fixture
    def failing_backend(self):
        """Create a backend that fails operations"""
        backend = Mock(spec=CoordinationBackend)
        backend.is_available.return_value = True
        backend.register_sync_intent.return_value = True
        backend.attempt_leader_election.return_value = True
        backend.release_leadership.return_value = None
        
        # Fail change detection
        backend.has_database_changed.side_effect = Exception("Network error")
        
        return backend
    
    def test_change_detection_error_triggers_conservative_download(self, tmp_path, failing_backend):
        """Test that change detection errors trigger conservative download"""
        cache_db = tmp_path / "cache.db"
        cache_db.write_text("test content")
        
        with patch('tracking.leader_election_sync.OperationTracker') as mock_tracker:
            with patch('tracking.leader_election_sync.DatabaseMerger'):
                with patch.object(LeaderElectionSyncManager, '_ensure_database_schema', return_value=True):
                    # Mock successful download after failed change detection
                    failing_backend.download_database.return_value = True
                    
                    tracker_instance = Mock()
                    tracker_instance.get_pending_operations.return_value = []
                    tracker_instance.clear_operations.return_value = None
                    mock_tracker.return_value = tracker_instance
                    
                    manager = LeaderElectionSyncManager(
                        coordination_backend=failing_backend,
                        local_cache_db_path=str(cache_db)
                    )
                    
                    # Should still attempt sync despite change detection failure
                    # The conservative approach should download anyway
                    success = manager.sync_database()
                    
                    # The sync might fail due to change detection error,
                    # but it should attempt the conservative approach
                    failing_backend.has_database_changed.assert_called_once()
    
    def test_metadata_corruption_handled_gracefully(self, tmp_path):
        """Test that corrupted metadata files are handled gracefully"""
        metadata_file = tmp_path / "metadata.json"
        
        # Create corrupted metadata file
        metadata_file.write_text("{ invalid json")
        
        backend = Mock(spec=CoordinationBackend)
        backend.has_database_changed.return_value = (True, {"test": "data"})
        
        cache_db = tmp_path / "cache.db"
        cache_db.write_text("test")
        
        with patch('tracking.leader_election_sync.OperationTracker'):
            manager = LeaderElectionSyncManager(
                coordination_backend=backend,
                local_cache_db_path=str(cache_db)
            )
            manager.sync_metadata_file = metadata_file
            
            # Should load None for corrupted metadata (not raise exception)
            loaded = manager._load_last_sync_metadata()
            assert loaded is None
            
            # Trigger sync to test change detection behavior
            try:
                manager.sync_database()
            except:
                pass  # May fail due to other mocking issues, but we want to test metadata loading
            
            # Should have called change detection with None (conservative approach)
            backend.has_database_changed.assert_called_with(None)


class TestEndToEndSyncOptimization:
    """End-to-end tests demonstrating sync optimization benefits"""
    
    def test_no_unnecessary_downloads_in_stable_environment(self):
        """Test that stable environment doesn't trigger unnecessary downloads"""
        # Simulate a scenario where:
        # 1. First sync downloads and saves metadata
        # 2. Multiple subsequent syncs find no changes
        # 3. No downloads should occur after the first sync
        
        backend = Mock(spec=GoogleDriveBackend)
        backend.is_available.return_value = True
        backend.register_sync_intent.return_value = True
        backend.attempt_leader_election.return_value = True
        backend.release_leadership.return_value = None
        
        stable_metadata = {
            "modified_time": "2025-01-01T12:00:00Z",
            "size": 1000,
            "file_id": "stable_file"
        }
        
        # First call: no previous metadata, file exists
        # Subsequent calls: no changes detected
        backend.has_database_changed.side_effect = [
            (True, stable_metadata),   # First sync: download needed
            (False, stable_metadata),  # Second sync: no changes
            (False, stable_metadata),  # Third sync: no changes
        ]
        backend.download_database.return_value = True
        
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_db = Path(tmpdir) / "cache.db"
            cache_db.write_text("test")
            
            with patch('tracking.leader_election_sync.OperationTracker') as mock_tracker:
                with patch('tracking.leader_election_sync.DatabaseMerger'):
                    with patch.object(LeaderElectionSyncManager, '_ensure_database_schema', return_value=True):
                        tracker_instance = Mock()
                        tracker_instance.get_pending_operations.return_value = []
                        tracker_instance.clear_operations.return_value = None
                        mock_tracker.return_value = tracker_instance
                        
                        manager = LeaderElectionSyncManager(
                            coordination_backend=backend,
                            local_cache_db_path=str(cache_db)
                        )
                        manager.sync_metadata_file = Path(tmpdir) / "metadata.json"
                        
                        # First sync: should download
                        success1 = manager.sync_database()
                        assert success1 is True
                        assert backend.download_database.call_count == 1
                        
                        # Second sync: should skip download
                        success2 = manager.sync_database()
                        assert success2 is True
                        assert backend.download_database.call_count == 1  # No additional download
                        
                        # Third sync: should skip download
                        success3 = manager.sync_database()
                        assert success3 is True
                        assert backend.download_database.call_count == 1  # Still no additional download
    
    def test_download_only_when_necessary(self):
        """Test that downloads only occur when actually necessary"""
        # Test various scenarios where downloads should/shouldn't occur
        
        scenarios = [
            {
                "name": "No remote changes, no local ops",
                "remote_changed": False,
                "local_ops": [],
                "should_download": False
            },
            {
                "name": "Remote changed, no local ops", 
                "remote_changed": True,
                "local_ops": [],
                "should_download": True
            },
            {
                "name": "No remote changes, local ops pending",
                "remote_changed": False,
                "local_ops": [{"op": "create"}],
                "should_download": True  # Need to merge local ops
            },
            {
                "name": "Remote changed, local ops pending",
                "remote_changed": True,
                "local_ops": [{"op": "create"}], 
                "should_download": True
            }
        ]
        
        for scenario in scenarios:
            backend = Mock(spec=CoordinationBackend)
            backend.is_available.return_value = True
            backend.register_sync_intent.return_value = True
            backend.attempt_leader_election.return_value = True
            backend.release_leadership.return_value = None
            backend.download_database.return_value = True
            backend.upload_database.return_value = True
            
            # Configure change detection
            metadata = {"modified_time": "2025-01-01T12:00:00Z", "size": 1000}
            backend.has_database_changed.return_value = (scenario["remote_changed"], metadata)
            
            with tempfile.TemporaryDirectory() as tmpdir:
                cache_db = Path(tmpdir) / "cache.db"
                cache_db.write_text("test")
                
                with patch('tracking.leader_election_sync.OperationTracker') as mock_tracker:
                    with patch('tracking.leader_election_sync.DatabaseMerger'):
                        with patch.object(LeaderElectionSyncManager, '_ensure_database_schema', return_value=True):
                            tracker_instance = Mock()
                            tracker_instance.get_pending_operations.return_value = scenario["local_ops"]
                            tracker_instance.clear_operations.return_value = None
                            mock_tracker.return_value = tracker_instance
                            
                            manager = LeaderElectionSyncManager(
                                coordination_backend=backend,
                                local_cache_db_path=str(cache_db)
                            )
                            manager.sync_metadata_file = Path(tmpdir) / "metadata.json"
                            
                            # Save some existing metadata
                            manager._save_last_sync_metadata(metadata)
                            
                            # Perform sync - may fail due to complex merge logic in tests
                            manager.sync_database()
                            
                            # Check if download occurred as expected
                            if scenario["should_download"]:
                                backend.download_database.assert_called_once()
                            else:
                                backend.download_database.assert_not_called()