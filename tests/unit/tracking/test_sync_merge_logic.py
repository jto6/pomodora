"""
Unit tests for sync merge logic.

Tests the specific bug where downloaded database was ignored
when there were no local changes.
"""

import pytest
import os
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock

# Add src to path for imports
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from tracking.leader_election_sync import LeaderElectionSyncManager


class TestSyncMergeLogic:
    """Test the database merge logic in sync operations"""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files"""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def mock_backend(self):
        """Create mock coordination backend"""
        backend = Mock()
        backend.instance_id = "test_instance_12345"
        return backend
    
    @pytest.fixture
    def sync_manager(self, temp_dir, mock_backend):
        """Create sync manager with test setup"""
        local_cache_path = temp_dir / "cache.db"
        sync_manager = LeaderElectionSyncManager(mock_backend, str(local_cache_path))
        
        # Mock operation tracker
        mock_tracker = Mock()
        sync_manager.operation_tracker = mock_tracker
        
        return sync_manager
    
    def test_no_downloaded_database_uses_local(self, sync_manager, temp_dir):
        """Test behavior when no downloaded database exists"""
        local_db = temp_dir / "local.db"
        local_db.write_text("local_data")
        sync_manager.local_cache_db = local_db
        
        nonexistent_path = str(temp_dir / "nonexistent.db")
        
        result = sync_manager._merge_databases(nonexistent_path)
        
        assert result == str(local_db)
    
    def test_no_local_database_uses_downloaded(self, sync_manager, temp_dir):
        """Test behavior when no local database exists"""
        nonexistent_local = temp_dir / "nonexistent_local.db"
        sync_manager.local_cache_db = nonexistent_local
        
        downloaded_db = temp_dir / "downloaded.db" 
        downloaded_db.write_text("downloaded_data")
        
        result = sync_manager._merge_databases(str(downloaded_db))
        
        assert result == str(downloaded_db)
    
    def test_no_local_changes_prefers_downloaded(self, sync_manager, temp_dir):
        """
        Test the core bug fix: when both databases exist but no local changes,
        should prefer downloaded database over local.
        
        This is the critical test that would have caught the original bug.
        """
        # Create both databases
        local_db = temp_dir / "local.db"
        local_db.write_text("local_empty_or_defaults")
        sync_manager.local_cache_db = local_db
        
        downloaded_db = temp_dir / "downloaded.db"
        downloaded_db.write_text("downloaded_real_data_from_google_drive")
        
        # Mock no pending operations (no local changes)
        sync_manager.operation_tracker.get_pending_operations.return_value = []
        
        result = sync_manager._merge_databases(str(downloaded_db))
        
        # CRITICAL: Should return downloaded database, not local
        # This test would have failed before the fix
        assert result == str(downloaded_db), (
            "When no local changes exist, downloaded database should be preferred "
            "over local database to use authoritative remote data"
        )
    
    def test_local_changes_trigger_merge(self, sync_manager, temp_dir):
        """Test that local changes trigger proper merge operation"""
        # Create both databases
        local_db = temp_dir / "local.db"
        local_db.write_text("local_with_changes")
        sync_manager.local_cache_db = local_db
        
        downloaded_db = temp_dir / "downloaded.db"
        downloaded_db.write_text("downloaded_data")
        
        # Mock pending operations (local changes exist)
        pending_ops = [
            {"operation": "insert", "table": "sprints", "data": {"id": 1}},
            {"operation": "update", "table": "projects", "data": {"id": 2}}
        ]
        sync_manager.operation_tracker.get_pending_operations.return_value = pending_ops
        
        # Mock the DatabaseMerger
        from unittest.mock import patch
        with patch('tracking.leader_election_sync.DatabaseMerger') as mock_merger_class:
            mock_merger = Mock()
            merged_path = str(temp_dir / "merged_result.db")
            mock_merger.merge_operations.return_value = merged_path
            mock_merger_class.return_value = mock_merger
            
            result = sync_manager._merge_databases(str(downloaded_db))
            
            # Should use DatabaseMerger when local changes exist
            mock_merger_class.assert_called_once_with(
                str(local_db),           # local_db_path
                str(downloaded_db),      # remote_db_path (downloaded temp file)
                sync_manager.operation_tracker  # operation tracker
            )
            
            # Should call merge_operations with correct parameters
            mock_merger.merge_operations.assert_called_once_with(
                str(downloaded_db),  # Apply operations to downloaded database
                pending_ops          # The pending operations
            )
            
            # Should return merged database path
            assert result == merged_path
    
    def test_merge_error_handling(self, sync_manager, temp_dir):
        """Test that merge handles errors gracefully"""
        local_db = temp_dir / "local.db" 
        local_db.write_text("local_data")
        sync_manager.local_cache_db = local_db
        
        downloaded_db = temp_dir / "downloaded.db"
        downloaded_db.write_text("downloaded_data")
        
        # Mock operation tracker to raise exception
        sync_manager.operation_tracker.get_pending_operations.side_effect = Exception("Test error")
        
        result = sync_manager._merge_databases(str(downloaded_db))
        
        # Should return None on error
        assert result is None


class TestGoogleDriveSyncScenario:
    """
    Test the specific scenario that was failing:
    Switching to Google Drive mode with existing data.
    """
    
    def test_google_drive_switch_scenario(self):
        """
        Test the exact scenario that was failing:
        1. User switches to Google Drive mode
        2. Cache is cleared (local database is empty/defaults)  
        3. Google Drive database is downloaded (contains real data)
        4. Merge should use downloaded database, not empty local
        """
        import tempfile
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Simulate cache being cleared - local database has only defaults
            local_cache = temp_path / "cache.db"
            local_cache.write_text("empty_database_with_defaults")
            
            # Simulate Google Drive download - contains real user data
            downloaded_db = temp_path / "google_drive_download.db"
            downloaded_db.write_text("real_user_data_from_google_drive")
            
            # Create sync manager
            mock_backend = Mock()
            mock_backend.instance_id = "test_google_drive_switch"
            
            sync_manager = LeaderElectionSyncManager(mock_backend, str(local_cache))
            
            # Mock no pending operations (fresh cache after clear)
            mock_tracker = Mock()
            mock_tracker.get_pending_operations.return_value = []
            sync_manager.operation_tracker = mock_tracker
            
            # This is the critical test - should prefer downloaded data
            result = sync_manager._merge_databases(str(downloaded_db))
            
            # MUST use downloaded database to get the real Google Drive data
            assert result == str(downloaded_db), (
                "Google Drive sync must use downloaded database when switching modes "
                "to preserve user's real data from Google Drive"
            )
            
            # Verify the fix is working
            assert "google_drive_download.db" in result
            assert "cache.db" not in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])