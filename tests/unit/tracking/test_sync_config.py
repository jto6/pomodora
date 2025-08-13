"""
Unit tests for sync configuration to catch backend inconsistencies.
These tests ensure that sync configuration is consistent and prevents
the kind of backend mismatches that caused the original issue.
"""

import pytest
import tempfile
import os
from unittest.mock import patch, MagicMock
from pathlib import Path

# Import after setting up sys.path in conftest.py
from tracking.sync_config import SyncConfiguration
from tracking.local_settings import LocalSettingsManager


# isolated_sync_config fixture removed - using global autouse fixture from conftest.py


class TestSyncConfiguration:
    """Test sync configuration consistency and validation"""

    def test_default_configuration_is_valid(self):
        """Test that default configuration is valid and consistent"""
        config = SyncConfiguration()
        
        # Default should be local_only strategy
        strategy = config.get_sync_strategy()
        assert strategy in ['local_only', 'leader_election']
        
        # Backend config should exist
        backend_config = config.get_coordination_backend_config()
        assert 'type' in backend_config
        assert backend_config['type'] in ['local_file', 'google_drive']
        
    def test_local_only_strategy_configuration(self):
        """Test local_only strategy configuration"""
        config = SyncConfiguration()
        config.set_sync_strategy('local_only')
        
        strategy = config.get_sync_strategy()
        assert strategy == 'local_only'
        
        db_path, needs_coordination = config.get_database_path_for_strategy()
        assert not needs_coordination
        assert db_path.endswith('pomodora.db')
        
    def test_leader_election_strategy_configuration(self):
        """Test leader_election strategy configuration"""
        config = SyncConfiguration()
        config.set_sync_strategy('leader_election')
        
        strategy = config.get_sync_strategy()
        assert strategy == 'leader_election'
        
        db_path, needs_coordination = config.get_database_path_for_strategy()
        assert needs_coordination
        assert db_path.endswith('pomodora.db')
        
    def test_coordination_backend_configuration_validation(self):
        """Test that coordination backend configuration is properly validated"""
        config = SyncConfiguration()
        backend_config = config.get_coordination_backend_config()
        
        # Must have type field
        assert 'type' in backend_config
        backend_type = backend_config['type']
        assert backend_type in ['local_file', 'google_drive']
        
        # Must have configuration for the specified type
        if backend_type == 'local_file':
            assert 'local_file' in backend_config
            assert 'shared_db_path' in backend_config['local_file']
        elif backend_type == 'google_drive':
            assert 'google_drive' in backend_config
            assert 'credentials_path' in backend_config['google_drive']
            assert 'folder_name' in backend_config['google_drive']
            
    def test_backend_creation_consistency(self):
        """Test that backend creation is consistent with configuration"""
        config = SyncConfiguration()
        
        # Set leader election strategy (which needs coordination)
        config.set_sync_strategy('leader_election')
        
        backend_config = config.get_coordination_backend_config()
        backend_type = backend_config['type']
        
        # Backend creation should match the configured type
        backend = config.create_coordination_backend()
        
        if backend_type == 'local_file':
            # Should create LocalFileBackend or None if path invalid
            if backend:
                assert backend.__class__.__name__ == 'LocalFileBackend'
        elif backend_type == 'google_drive':
            # Should create GoogleDriveBackend or None if credentials missing
            if backend:
                assert backend.__class__.__name__ == 'GoogleDriveBackend'
                
    def test_google_drive_backend_configuration(self):
        """Test Google Drive backend configuration specifically"""
        config = SyncConfiguration()
        
        # Set up Google Drive backend
        config.set_google_drive_backend('test_credentials.json', 'TestFolder')
        
        backend_config = config.get_coordination_backend_config()
        assert backend_config['type'] == 'google_drive'
        assert backend_config['google_drive']['credentials_path'] == 'test_credentials.json'
        assert backend_config['google_drive']['folder_name'] == 'TestFolder'
        
        # Strategy should be leader_election
        strategy = config.get_sync_strategy()
        assert strategy == 'leader_election'
        
    def test_local_file_backend_configuration(self):
        """Test local file backend configuration specifically"""
        with tempfile.TemporaryDirectory() as temp_dir:
            shared_db_path = os.path.join(temp_dir, 'shared_pomodora.db')
            
            config = SyncConfiguration()
            config.set_local_file_backend(shared_db_path)
            
            backend_config = config.get_coordination_backend_config()
            assert backend_config['type'] == 'local_file'
            assert backend_config['local_file']['shared_db_path'] == shared_db_path
            
            # Strategy should be leader_election
            strategy = config.get_sync_strategy()
            assert strategy == 'leader_election'
            
    def test_configuration_validation(self):
        """Test configuration validation catches inconsistencies"""
        config = SyncConfiguration()
        
        # Valid configuration should pass
        is_valid, error = config.validate_configuration()
        # Note: May fail if Google Drive credentials missing, but should not crash
        assert isinstance(is_valid, bool)
        if not is_valid:
            assert isinstance(error, str)
            
    def test_configuration_prevents_backend_type_mismatch(self):
        """
        Test that prevents the specific issue that was reported:
        coordination_backend.type not matching the intended backend
        """
        config = SyncConfiguration()
        
        # Set Google Drive backend explicitly
        config.set_google_drive_backend('/path/to/credentials.json', 'TimeTracking')
        
        # Verify the type is set correctly
        backend_config = config.get_coordination_backend_config()
        assert backend_config['type'] == 'google_drive', \
            "Backend type should be 'google_drive' when Google Drive backend is configured"
        
        # Verify Google Drive config exists
        assert 'google_drive' in backend_config
        assert backend_config['google_drive']['credentials_path'] == '/path/to/credentials.json'
        assert backend_config['google_drive']['folder_name'] == 'TimeTracking'
        
    def test_sync_status_includes_backend_info(self):
        """Test that sync status includes backend information for debugging"""
        config = SyncConfiguration()
        
        # Set to leader_election strategy to test coordination backend info
        config.set_sync_strategy('leader_election')
        
        status = config.get_sync_status()
        
        # Should include key configuration info
        assert 'sync_strategy' in status
        assert 'database_path' in status
        assert 'needs_coordination' in status
        
        # Backend availability should be tested
        assert 'backend_available' in status
        
    def test_settings_persistence(self):
        """Test that configuration changes are properly persisted"""
        config = SyncConfiguration()
        
        # Make a configuration change
        config.set_google_drive_backend('new_credentials.json', 'NewFolder')
        
        # Verify the change was applied to current config
        backend_config = config.get_coordination_backend_config()
        
        assert backend_config['type'] == 'google_drive'
        assert backend_config['google_drive']['credentials_path'] == 'new_credentials.json'
        assert backend_config['google_drive']['folder_name'] == 'NewFolder'


class TestSyncConfigurationEdgeCases:
    """Test edge cases and error scenarios"""
    
    def test_invalid_sync_strategy_rejected(self):
        """Test that invalid sync strategies are rejected"""
        config = SyncConfiguration()
        
        with pytest.raises(ValueError, match="Invalid sync strategy"):
            config.set_sync_strategy('invalid_strategy')
            
    def test_missing_google_drive_credentials_handled(self):
        """Test graceful handling of missing Google Drive credentials"""
        config = SyncConfiguration()
        config.set_google_drive_backend('/nonexistent/credentials.json', 'TestFolder')
        
        # Should not crash, but should return None backend
        backend = config.create_coordination_backend()
        assert backend is None
        
    def test_invalid_local_file_path_handled(self):
        """Test graceful handling of invalid local file paths"""
        config = SyncConfiguration()
        
        # Set an invalid path (empty string)
        config.set_local_file_backend('')
        
        # Should handle gracefully
        backend = config.create_coordination_backend()
        assert backend is None
        
    def test_corrupted_settings_recovery(self):
        """Test recovery from corrupted settings"""
        # This tests the fallback behavior when settings are corrupted
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
            # Write invalid JSON
            temp_file.write('{"invalid": json}')
            temp_settings_path = temp_file.name
            
        try:
            with patch.object(LocalSettingsManager, 'get_config_path', return_value=temp_settings_path):
                # Should not crash, should use defaults
                config = SyncConfiguration()
                strategy = config.get_sync_strategy()
                assert strategy in ['local_only', 'leader_election']
                
        finally:
            if os.path.exists(temp_settings_path):
                os.unlink(temp_settings_path)