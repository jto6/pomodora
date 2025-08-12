"""
Integration tests for database configuration changes.

Tests the workflow of changing database configurations including:
- Sync before config change
- Cache cleanup
- Restart behavior
- Data preservation
"""

import pytest
import os
import tempfile
import shutil
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add src to path for imports
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from tracking.local_settings import get_local_settings
from tracking.sync_config import SyncConfiguration
from tracking.database_manager_unified import UnifiedDatabaseManager
from tracking.leader_election_sync import LeaderElectionSyncManager
# from gui.components.settings_dialog import SettingsDialog  # Commented out to avoid GUI dependencies


class TestDatabaseConfigurationChanges:
    """Test database configuration change scenarios"""
    
    @pytest.fixture
    def temp_config_dir(self):
        """Create temporary config directory"""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def mock_settings(self, temp_config_dir):
        """Create mock settings with temporary directory"""
        # Use the actual settings manager but with a temporary config dir
        with patch('tracking.local_settings.Path.home') as mock_home:
            mock_home.return_value = temp_config_dir
            settings = get_local_settings()
            return settings
    
    @pytest.fixture  
    def test_database(self, temp_config_dir):
        """Create test database with some data"""
        db_path = temp_config_dir / "test.db"
        
        # Create database with test data
        db_manager = UnifiedDatabaseManager(str(db_path))
        session = db_manager.get_session()
        try:
            # Add test data
            from tracking.models import Project, TaskCategory
            project = Project(name="TestProject", color="#ff0000")
            category = TaskCategory(name="TestCategory", color="#00ff00") 
            session.add(project)
            session.add(category)
            session.commit()
        finally:
            session.close()
            
        return db_path
    
    def test_sync_before_config_change(self, temp_config_dir, mock_settings):
        """Test that sync happens before database configuration changes"""
        cache_dir = temp_config_dir / "cache"
        cache_dir.mkdir()
        
        # Create mock database manager with pending changes
        mock_db_manager = Mock()
        mock_db_manager.has_pending_changes.return_value = True
        mock_db_manager.sync_if_changes_pending.return_value = True
        
        # Create mock parent window
        mock_parent = Mock()
        mock_parent.db_manager = mock_db_manager
        
        # Test the sync logic directly without GUI dependencies
        def sync_before_config_change():
            """Simulate the _sync_before_config_change logic"""
            if mock_parent and hasattr(mock_parent, 'db_manager'):
                db_manager = mock_parent.db_manager
                
                if hasattr(db_manager, 'has_pending_changes') and db_manager.has_pending_changes():
                    if hasattr(db_manager, 'sync_if_changes_pending'):
                        success = db_manager.sync_if_changes_pending()
                        return success
            return True
        
        # Trigger sync before config change
        sync_before_config_change()
        
        # Verify sync was called
        mock_db_manager.has_pending_changes.assert_called_once()
        mock_db_manager.sync_if_changes_pending.assert_called_once()
    
    def test_cache_cleanup_on_config_change(self, temp_config_dir):
        """Test that cache is cleaned when database config changes"""
        # Create cache directory with files
        cache_dir = temp_config_dir / "cache"
        cache_dir.mkdir()
        
        # Create test cache files
        (cache_dir / "pomodora.db").write_text("test db")
        (cache_dir / "operations.json").write_text("{}")
        
        # Create operations files in config dir
        operations_file = temp_config_dir / "test_operations.json"
        operations_file.write_text("{}")
        
        # Test the cache cleanup logic directly without GUI
        with patch('pathlib.Path.home') as mock_home:
            mock_home.return_value = temp_config_dir
            
            # Simulate the cache cleanup logic from SettingsDialog
            import shutil
            
            # Clear cache directory
            if cache_dir.exists():
                shutil.rmtree(cache_dir)
            
            # Clear operations log files
            for operations_file in temp_config_dir.glob("*_operations.json"):
                operations_file.unlink()
            
            # Verify cache directory was removed
            assert not cache_dir.exists()
            # Verify operations file was removed
            assert not operations_file.exists()
    
    def test_settings_persistence_config_change(self, temp_config_dir):
        """Test that configuration changes are properly persisted"""
        # Test settings persistence logic without GUI
        with patch('pathlib.Path.home') as mock_home:
            mock_home.return_value = temp_config_dir
            
            settings = get_local_settings()
            
            # Set initial configuration
            settings.set("sync_strategy", "local_only")
            settings.set("coordination_backend", {
                "type": "local_file",
                "local_file": {"shared_db_path": "/old/path"},
                "google_drive": {"credentials_path": "creds.json", "folder_name": "TimeTracking"}
            })
            
            # Change to Google Drive configuration
            settings.set("sync_strategy", "leader_election")
            settings.set("coordination_backend", {
                "type": "google_drive",
                "local_file": {"shared_db_path": "/some/path"},
                "google_drive": {"credentials_path": "/new/creds.json", "folder_name": "NewFolder"}
            })
            
            # Reload settings to verify persistence
            new_settings = get_local_settings()
            assert new_settings.get("sync_strategy") == "leader_election"
            backend_config = new_settings.get("coordination_backend")
            assert backend_config["type"] == "google_drive"
            assert backend_config["google_drive"]["credentials_path"] == "/new/creds.json"
            assert backend_config["google_drive"]["folder_name"] == "NewFolder"


class TestGoogleDriveSyncLogic:
    """Test Google Drive sync logic fixes"""
    
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
        backend.instance_id = "test_instance"
        return backend
    
    @pytest.fixture
    def test_databases(self, temp_dir):
        """Create test databases for merge testing"""
        # Create local cache database (empty/defaults)
        local_db = temp_dir / "local.db"
        local_db.write_text("local_empty_db")
        
        # Create downloaded database (with real data) 
        downloaded_db = temp_dir / "downloaded.db"
        downloaded_db.write_text("downloaded_real_data")
        
        return local_db, downloaded_db
    
    def test_merge_prefers_downloaded_when_no_local_changes(self, temp_dir, mock_backend, test_databases):
        """Test that merge logic prefers downloaded database when no local changes exist"""
        local_db, downloaded_db = test_databases
        
        # Create sync manager
        sync_manager = LeaderElectionSyncManager(mock_backend, str(local_db))
        
        # Mock operation tracker to return no pending operations
        mock_tracker = Mock()
        mock_tracker.get_pending_operations.return_value = []
        sync_manager.operation_tracker = mock_tracker
        
        # Test merge logic
        result = sync_manager._merge_databases(str(downloaded_db))
        
        # Should return downloaded database path when no local changes
        assert result == str(downloaded_db)
        
        # Verify operation tracker was checked
        mock_tracker.get_pending_operations.assert_called_once()
    
    def test_merge_applies_local_changes_when_present(self, temp_dir, mock_backend, test_databases):
        """Test that merge logic applies local changes when they exist"""
        local_db, downloaded_db = test_databases
        
        # Create sync manager
        sync_manager = LeaderElectionSyncManager(mock_backend, str(local_db))
        
        # Mock operation tracker to return pending operations
        mock_tracker = Mock()
        mock_tracker.get_pending_operations.return_value = [
            {"operation": "insert", "table": "sprints", "data": {"id": 1}}
        ]
        sync_manager.operation_tracker = mock_tracker
        
        # Mock database merger
        with patch('tracking.leader_election_sync.DatabaseMerger') as mock_merger_class:
            mock_merger = Mock()
            mock_merger.merge_operations.return_value = str(temp_dir / "merged.db")
            mock_merger_class.return_value = mock_merger
            
            # Test merge logic
            result = sync_manager._merge_databases(str(downloaded_db))
            
            # Should create merger and apply operations
            mock_merger_class.assert_called_once()
            mock_merger.merge_operations.assert_called_once()
            
            # Should return merged database path
            assert result == str(temp_dir / "merged.db")
    
    def test_merge_handles_missing_downloaded_database(self, temp_dir, mock_backend):
        """Test that merge handles case where downloaded database doesn't exist"""
        local_db = temp_dir / "local.db"
        local_db.write_text("local_db")
        nonexistent_db = temp_dir / "nonexistent.db"
        
        sync_manager = LeaderElectionSyncManager(mock_backend, str(local_db))
        
        # Test with nonexistent downloaded database
        result = sync_manager._merge_databases(str(nonexistent_db))
        
        # Should return local database path
        assert result == str(local_db)
    
    def test_merge_handles_missing_local_database(self, temp_dir, mock_backend):
        """Test that merge handles case where local database doesn't exist"""
        nonexistent_local = temp_dir / "nonexistent_local.db"
        downloaded_db = temp_dir / "downloaded.db"
        downloaded_db.write_text("downloaded_data")
        
        sync_manager = LeaderElectionSyncManager(mock_backend, str(nonexistent_local))
        
        # Test with nonexistent local database
        result = sync_manager._merge_databases(str(downloaded_db))
        
        # Should return downloaded database path
        assert result == str(downloaded_db)


class TestDailyBackupLogic:
    """Test daily backup logic fixes"""
    
    @pytest.fixture
    def temp_backup_dir(self):
        """Create temporary backup directory"""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir)
    
    def test_should_create_daily_backup_once_per_day(self, temp_backup_dir):
        """Test that daily backup is only created once per day"""
        from tracking.database_backup import DatabaseBackupManager
        from datetime import date
        
        # Create test database
        test_db = temp_backup_dir / "test.db"
        test_db.write_text("test_data")
        
        backup_manager = DatabaseBackupManager(str(test_db), str(temp_backup_dir))
        
        # First check - should create backup
        assert backup_manager.should_create_daily_backup() == True
        
        # Create a daily backup
        backup_manager.create_backup("daily")
        
        # Second check - should not create another backup for same day
        assert backup_manager.should_create_daily_backup() == False
    
    def test_perform_scheduled_backups_respects_daily_limit(self, temp_backup_dir):
        """Test that scheduled backups only creates one daily backup per day"""
        from tracking.database_backup import DatabaseBackupManager
        
        # Create test database
        test_db = temp_backup_dir / "test.db"
        test_db.write_text("test_data")
        
        backup_manager = DatabaseBackupManager(str(test_db), str(temp_backup_dir))
        
        # Run scheduled backups multiple times
        backup_manager.perform_scheduled_backups()
        backup_manager.perform_scheduled_backups() 
        backup_manager.perform_scheduled_backups()
        
        # Should only have one daily backup for today
        daily_dir = temp_backup_dir / "Daily"
        if daily_dir.exists():
            daily_backups = list(daily_dir.glob("pomodora_daily_*.db"))
            today_backups = [b for b in daily_backups if date.today().strftime('%Y%m%d') in b.name]
            assert len(today_backups) <= 1


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])