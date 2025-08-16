"""
Tests for sync metadata persistence functionality.
Ensures that sync metadata is correctly saved and loaded for change detection.
"""

import pytest
import json
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch

from tracking.leader_election_sync import LeaderElectionSyncManager
from tracking.coordination_backend import CoordinationBackend


class TestMetadataPersistence:
    """Test metadata save/load functionality"""
    
    
    @pytest.fixture
    def mock_coordination_backend(self):
        """Create a mock coordination backend"""
        backend = Mock(spec=CoordinationBackend)
        backend.has_database_changed.return_value = (True, None)
        backend.download_database.return_value = True
        backend.upload_database.return_value = True
        backend.register_sync_intent.return_value = True
        backend.attempt_leader_election.return_value = True
        backend.release_leadership.return_value = None
        backend.is_available.return_value = True
        return backend
    
    @pytest.fixture
    def sync_manager(self, tmp_path, mock_coordination_backend):
        """Create a sync manager with temporary paths"""
        cache_db_path = tmp_path / "cache.db"
        operation_log_path = tmp_path / "operations.json"
        
        # Create empty cache database
        cache_db_path.touch()
        
        with patch('tracking.leader_election_sync.OperationTracker'):
            manager = LeaderElectionSyncManager(
                coordination_backend=mock_coordination_backend,
                local_cache_db_path=str(cache_db_path)
            )
            
            # Override the metadata file path to use temp directory
            manager.sync_metadata_file = tmp_path / "last_sync_metadata.json"
            
            return manager
    
    def test_save_metadata_creates_file(self, sync_manager):
        """Test that save_metadata creates the metadata file"""
        metadata = {
            "modified_time": "2025-01-01T12:00:00Z",
            "size": 1000,
            "file_id": "test_file"
        }
        
        # Save metadata
        sync_manager._save_last_sync_metadata(metadata)
        
        # File should exist
        assert sync_manager.sync_metadata_file.exists()
        
        # Content should match
        with open(sync_manager.sync_metadata_file, 'r') as f:
            saved_data = json.load(f)
        assert saved_data == metadata
    
    def test_save_metadata_creates_parent_directory(self, tmp_path, mock_coordination_backend):
        """Test that save_metadata creates parent directories if needed"""
        cache_db_path = tmp_path / "cache.db"
        cache_db_path.touch()
        
        with patch('tracking.leader_election_sync.OperationTracker'):
            manager = LeaderElectionSyncManager(
                coordination_backend=mock_coordination_backend,
                local_cache_db_path=str(cache_db_path)
            )
            
            # Set metadata file path in nested directory that doesn't exist
            nested_dir = tmp_path / "nested" / "deep"
            manager.sync_metadata_file = nested_dir / "metadata.json"
        
        metadata = {"test": "data"}
        
        # Save metadata (should create directories)
        manager._save_last_sync_metadata(metadata)
        
        # File and directories should exist
        assert manager.sync_metadata_file.exists()
        assert nested_dir.exists()
    
    def test_load_metadata_returns_none_if_file_missing(self, sync_manager):
        """Test that load_metadata returns None when file doesn't exist"""
        # Ensure file doesn't exist
        if sync_manager.sync_metadata_file.exists():
            sync_manager.sync_metadata_file.unlink()
        
        result = sync_manager._load_last_sync_metadata()
        assert result is None
    
    def test_load_metadata_returns_saved_data(self, sync_manager):
        """Test that load_metadata returns previously saved data"""
        metadata = {
            "modified_time": "2025-01-01T12:00:00Z",
            "size": 1000,
            "file_id": "test_file"
        }
        
        # Save then load
        sync_manager._save_last_sync_metadata(metadata)
        loaded_metadata = sync_manager._load_last_sync_metadata()
        
        assert loaded_metadata == metadata
    
    def test_save_metadata_overwrites_existing_file(self, sync_manager):
        """Test that save_metadata overwrites existing metadata"""
        old_metadata = {"old": "data"}
        new_metadata = {"new": "data"}
        
        # Save old data
        sync_manager._save_last_sync_metadata(old_metadata)
        assert sync_manager._load_last_sync_metadata() == old_metadata
        
        # Save new data
        sync_manager._save_last_sync_metadata(new_metadata)
        assert sync_manager._load_last_sync_metadata() == new_metadata
    
    def test_save_metadata_handles_complex_data_types(self, sync_manager):
        """Test that save_metadata handles various data types correctly"""
        complex_metadata = {
            "string": "test",
            "integer": 42,
            "float": 3.14,
            "boolean": True,
            "null": None,
            "list": [1, 2, 3],
            "nested_dict": {
                "inner": "value"
            }
        }
        
        # Save and load complex data
        sync_manager._save_last_sync_metadata(complex_metadata)
        loaded_metadata = sync_manager._load_last_sync_metadata()
        
        assert loaded_metadata == complex_metadata
    
    def test_load_metadata_handles_json_errors(self, sync_manager):
        """Test that load_metadata handles corrupted JSON gracefully"""
        # Create file with invalid JSON
        with open(sync_manager.sync_metadata_file, 'w') as f:
            f.write("invalid json content {")
        
        # Should return None and not raise exception
        result = sync_manager._load_last_sync_metadata()
        assert result is None
    
    def test_save_metadata_handles_write_errors(self, sync_manager):
        """Test that save_metadata handles write errors gracefully"""
        # Make parent directory read-only to simulate write error
        sync_manager.sync_metadata_file.parent.chmod(0o444)
        
        try:
            # Should not raise exception
            sync_manager._save_last_sync_metadata({"test": "data"})
            
            # Metadata should not be saved
            # (Can't test file existence since write would fail)
            
        finally:
            # Restore permissions for cleanup
            sync_manager.sync_metadata_file.parent.chmod(0o755)
    
    def test_metadata_file_path_based_on_cache_db(self, tmp_path, mock_coordination_backend):
        """Test that metadata file path is correctly derived from cache DB path"""
        cache_db_path = tmp_path / "subdir" / "cache.db"
        cache_db_path.parent.mkdir(parents=True)
        cache_db_path.touch()
        
        with patch('tracking.leader_election_sync.OperationTracker'):
            manager = LeaderElectionSyncManager(
                coordination_backend=mock_coordination_backend,
                local_cache_db_path=str(cache_db_path)
            )
        
        # Metadata file should be in same directory as cache DB
        expected_path = cache_db_path.parent / "last_sync_metadata.json"
        assert manager.sync_metadata_file == expected_path


class TestMetadataIntegrationWithSync:
    """Test metadata persistence integration with sync operations"""
    
    @pytest.fixture
    def mock_backend_with_metadata(self):
        """Create a mock backend that returns metadata"""
        backend = Mock(spec=CoordinationBackend)
        backend.is_available.return_value = True
        backend.register_sync_intent.return_value = True
        backend.attempt_leader_election.return_value = True
        backend.release_leadership.return_value = None
        backend.download_database.return_value = True
        backend.upload_database.return_value = True
        
        # Mock change detection with metadata
        backend.has_database_changed.return_value = (True, {
            "modified_time": "2025-01-01T12:00:00Z",
            "size": 1000,
            "file_id": "test_file"
        })
        
        return backend
    
    @pytest.fixture
    def sync_manager_with_temp_db(self, tmp_path, mock_backend_with_metadata):
        """Create sync manager with temporary database"""
        cache_db_path = tmp_path / "cache.db"
        
        # Create a simple database file
        cache_db_path.write_text("dummy database content")
        
        with patch('tracking.leader_election_sync.OperationTracker') as mock_tracker:
            with patch('tracking.leader_election_sync.DatabaseMerger'):
                with patch.object(LeaderElectionSyncManager, '_ensure_database_schema', return_value=True):
                    # Mock operation tracker
                    mock_tracker_instance = Mock()
                    mock_tracker_instance.get_pending_operations.return_value = []
                    mock_tracker_instance.clear_operations.return_value = None
                    mock_tracker.return_value = mock_tracker_instance
                    
                    manager = LeaderElectionSyncManager(
                        coordination_backend=mock_backend_with_metadata,
                        local_cache_db_path=str(cache_db_path)
                    )
                    manager.sync_metadata_file = tmp_path / "metadata.json"
                    
                    return manager
    
    def test_sync_saves_metadata_on_success(self, sync_manager_with_temp_db):
        """Test that successful sync saves current metadata"""
        # Ensure no existing metadata
        if sync_manager_with_temp_db.sync_metadata_file.exists():
            sync_manager_with_temp_db.sync_metadata_file.unlink()
        
        # Perform sync
        success = sync_manager_with_temp_db.sync_database()
        
        # Sync should succeed and save metadata
        assert success is True
        assert sync_manager_with_temp_db.sync_metadata_file.exists()
        
        # Check saved metadata
        saved_metadata = sync_manager_with_temp_db._load_last_sync_metadata()
        assert saved_metadata is not None
        assert "modified_time" in saved_metadata
        assert saved_metadata["modified_time"] == "2025-01-01T12:00:00Z"
    
    def test_sync_uses_existing_metadata_for_change_detection(self, sync_manager_with_temp_db):
        """Test that sync uses existing metadata for change detection"""
        # Save some initial metadata
        initial_metadata = {
            "modified_time": "2024-12-31T12:00:00Z",
            "size": 500,
            "file_id": "old_file"
        }
        sync_manager_with_temp_db._save_last_sync_metadata(initial_metadata)
        
        # Perform sync
        sync_manager_with_temp_db.sync_database()
        
        # Backend should have been called with the initial metadata
        sync_manager_with_temp_db.coordination.has_database_changed.assert_called_with(initial_metadata)
    
    def test_metadata_persists_across_sync_manager_instances(self, tmp_path, mock_backend_with_metadata):
        """Test that metadata persists across different sync manager instances"""
        cache_db_path = tmp_path / "cache.db"
        cache_db_path.write_text("dummy content")
        
        metadata_to_save = {
            "modified_time": "2025-01-01T12:00:00Z",
            "size": 1000
        }
        
        # Create first sync manager and save metadata
        with patch('tracking.leader_election_sync.OperationTracker'):
            manager1 = LeaderElectionSyncManager(
                coordination_backend=mock_backend_with_metadata,
                local_cache_db_path=str(cache_db_path)
            )
            manager1.sync_metadata_file = tmp_path / "metadata.json"
            manager1._save_last_sync_metadata(metadata_to_save)
        
        # Create second sync manager (simulating app restart)
        with patch('tracking.leader_election_sync.OperationTracker'):
            manager2 = LeaderElectionSyncManager(
                coordination_backend=mock_backend_with_metadata,
                local_cache_db_path=str(cache_db_path)
            )
            manager2.sync_metadata_file = tmp_path / "metadata.json"
            
            # Should load the previously saved metadata
            loaded_metadata = manager2._load_last_sync_metadata()
            assert loaded_metadata == metadata_to_save
    
    def test_no_metadata_saved_on_sync_failure(self, sync_manager_with_temp_db):
        """Test that metadata is not saved when sync fails"""
        # Make sync fail
        sync_manager_with_temp_db.coordination.download_database.return_value = False
        
        # Ensure no existing metadata
        if sync_manager_with_temp_db.sync_metadata_file.exists():
            sync_manager_with_temp_db.sync_metadata_file.unlink()
        
        # Attempt sync
        success = sync_manager_with_temp_db.sync_database()
        
        # Sync should fail and not save metadata
        assert success is False
        assert not sync_manager_with_temp_db.sync_metadata_file.exists()