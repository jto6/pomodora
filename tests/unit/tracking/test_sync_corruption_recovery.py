"""
Unit tests for sync corruption recovery and duplicate database handling.
Tests that the system properly handles corrupted remote databases and prevents multiple database creation.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import tempfile
import os
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / 'src'))

from tracking.leader_election_sync import LeaderElectionSyncManager
from tracking.google_drive_backend import GoogleDriveBackend
from tracking.operation_log import OperationTracker


@pytest.mark.unit
@pytest.mark.tracking
class TestSyncCorruptionRecovery:
    """Test sync corruption recovery and duplicate database prevention"""

    def test_sync_handles_corrupted_remote_database(self):
        """Test that sync uses local database as authoritative when remote is corrupted"""
        # Mock components
        mock_coordination = Mock(spec=GoogleDriveBackend)
        mock_operation_tracker = Mock(spec=OperationTracker)
        
        # Mock the new change detection method
        mock_coordination.has_database_changed.return_value = (True, {"modified_time": "2025-01-01T12:00:00Z", "size": 1000})
        
        # Create sync manager
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as temp_file:
            local_cache_path = temp_file.name
            
        try:
            sync_manager = LeaderElectionSyncManager(
                coordination_backend=mock_coordination,
                local_cache_db_path=local_cache_path
            )
            
            # Override the operation tracker created by sync_manager
            sync_manager.operation_tracker = mock_operation_tracker
            
            # Mock successful download but corrupted database
            mock_coordination.download_database.return_value = True
            mock_operation_tracker.get_pending_operations.return_value = [
                {'id': 1, 'operation_type': 'update', 'table_name': 'sprints'}
            ]
            
            # Mock schema validation to fail (corrupted database)
            with patch.object(sync_manager, '_ensure_database_schema') as mock_schema_check:
                mock_schema_check.return_value = False  # Simulate corrupted database
                
                # Mock upload to succeed
                mock_coordination.upload_database.return_value = True
                
                # Mock status reporting
                with patch.object(sync_manager, '_report_progress'), \
                     patch.object(sync_manager, '_report_status'):
                    
                    # Call the leader sync method
                    result = sync_manager._perform_leader_sync()
                    
                    # Should succeed despite corrupted remote database
                    assert result == True
                    
                    # Should have attempted upload using local database as source
                    mock_coordination.upload_database.assert_called_once_with(str(sync_manager.local_cache_db))
                    
        finally:
            if os.path.exists(local_cache_path):
                os.unlink(local_cache_path)

    def test_upload_with_no_existing_files(self):
        """Test that upload works normally when no existing files exist"""
        # Create backend
        backend = GoogleDriveBackend(
            credentials_path="/fake/path",
            folder_name="test_folder"
        )
        
        # Mock drive_sync with no existing files
        backend.drive_sync = Mock()
        backend.drive_sync.upload_file.return_value = True
        backend.drive_sync.list_files_by_pattern.return_value = []  # No orphaned files
        
        # Mock temp file
        with tempfile.NamedTemporaryFile(suffix='.db') as temp_file:
            temp_file.write(b'test database content')
            temp_file.flush()
            
            # Call upload_database
            result = backend.upload_database(temp_file.name)
            
            # Should succeed
            assert result == True
            
            # Should have called upload_file
            backend.drive_sync.upload_file.assert_called_once_with(
                str(temp_file.name), "pomodora.db"
            )

    def test_sync_with_pending_operations_and_corruption(self):
        """Test sync behavior when there are pending operations AND remote database is corrupted"""
        # Mock components
        mock_coordination = Mock(spec=GoogleDriveBackend)
        mock_operation_tracker = Mock(spec=OperationTracker)
        
        # Mock the new change detection method
        mock_coordination.has_database_changed.return_value = (True, {"modified_time": "2025-01-01T12:00:00Z", "size": 1000})
        
        # Create sync manager
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as temp_file:
            local_cache_path = temp_file.name
            
        try:
            sync_manager = LeaderElectionSyncManager(
                coordination_backend=mock_coordination,
                local_cache_db_path=local_cache_path
            )
            
            # Override the operation tracker
            sync_manager.operation_tracker = mock_operation_tracker
            
            # Mock pending operations (hibernation recovery changes)
            pending_ops = [
                {'id': 1, 'operation_type': 'update', 'table_name': 'sprints', 'record_id': 79}
            ]
            mock_operation_tracker.get_pending_operations.return_value = pending_ops
            
            # Mock successful download but corrupted schema
            mock_coordination.download_database.return_value = True
            mock_coordination.upload_database.return_value = True
            
            with patch.object(sync_manager, '_ensure_database_schema') as mock_schema_check:
                # Simulate corrupted remote database
                mock_schema_check.return_value = False
                
                with patch.object(sync_manager, '_report_progress'), \
                     patch.object(sync_manager, '_report_status'), \
                     patch('tracking.leader_election_sync.info_print') as mock_info_print:
                    
                    # Call sync
                    result = sync_manager._perform_leader_sync()
                    
                    # Should succeed
                    assert result == True
                    
                    # Should upload local database due to both pending ops AND corruption
                    mock_coordination.upload_database.assert_called_once_with(str(sync_manager.local_cache_db))
                    
                    # Should log using local as authoritative source
                    info_calls = [str(call) for call in mock_info_print.call_args_list]
                    auth_source_logs = [call for call in info_calls if 'authoritative source' in call]
                    assert len(auth_source_logs) == 1
                    
        finally:
            if os.path.exists(local_cache_path):
                os.unlink(local_cache_path)

    def test_corruption_recovery_prevents_variable_reference_error(self):
        """Test that corruption recovery doesn't cause 'referenced before assignment' errors"""
        # Mock components
        mock_coordination = Mock(spec=GoogleDriveBackend)
        mock_operation_tracker = Mock(spec=OperationTracker)
        
        # Mock the new change detection method
        mock_coordination.has_database_changed.return_value = (True, {"modified_time": "2025-01-01T12:00:00Z", "size": 1000})
        
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as temp_file:
            local_cache_path = temp_file.name
            
        try:
            sync_manager = LeaderElectionSyncManager(
                coordination_backend=mock_coordination,
                local_cache_db_path=local_cache_path
            )
            
            # Override the operation tracker
            sync_manager.operation_tracker = mock_operation_tracker
            
            # Mock download success but schema validation failure
            mock_coordination.download_database.return_value = True
            mock_coordination.upload_database.return_value = True
            mock_operation_tracker.get_pending_operations.return_value = []
            
            with patch.object(sync_manager, '_ensure_database_schema') as mock_schema_check:
                # Simulate schema check failing on first call (corrupted remote)
                # but succeeding on second call (checking if we should upload)
                mock_schema_check.side_effect = [False, False]
                
                with patch.object(sync_manager, '_report_progress'), \
                     patch.object(sync_manager, '_report_status'):
                    
                    # This should not raise UnboundLocalError for merged_db_path
                    result = sync_manager._perform_leader_sync()
                    
                    # Should succeed without errors
                    assert result == True
                    
        finally:
            if os.path.exists(local_cache_path):
                os.unlink(local_cache_path)

    def test_orphan_cleanup_with_upload_failure(self):
        """Test that orphan cleanup still works even if main upload fails"""
        # Mock orphaned files
        orphaned_files = [
            {'id': 'orphan1', 'name': 'pomodora_sync_123.db'},
            {'id': 'orphan2', 'name': 'pomodora_sync_456.db'}
        ]
        
        # Create backend
        backend = GoogleDriveBackend(
            credentials_path="/fake/path",
            folder_name="test_folder"
        )
        
        # Mock drive_sync
        backend.drive_sync = Mock()
        backend.drive_sync.upload_file.return_value = False  # Upload fails
        backend.drive_sync.service = Mock()
        backend.drive_sync.list_files_by_pattern.return_value = orphaned_files
        
        with tempfile.NamedTemporaryFile(suffix='.db') as temp_file:
            temp_file.write(b'test database content')
            temp_file.flush()
            
            with patch('tracking.google_drive_backend.error_print') as mock_error_print:
                
                # Should fail due to upload failure
                result = backend.upload_database(temp_file.name)
                assert result == False
                
                # Should still have cleaned up orphaned files before the failed upload
                assert backend.drive_sync.service.files().delete.call_count == 2

    def test_upload_handles_exception_during_cleanup(self):
        """Test that upload handles exceptions during orphan cleanup gracefully"""
        # Mock orphaned files
        orphaned_files = [
            {'id': 'orphan1', 'name': 'pomodora_sync_123.db'}
        ]
        
        # Create backend
        backend = GoogleDriveBackend(
            credentials_path="/fake/path",
            folder_name="test_folder"
        )
        
        # Mock drive_sync
        backend.drive_sync = Mock()
        backend.drive_sync.upload_file.return_value = True
        backend.drive_sync.service = Mock()
        backend.drive_sync.list_files_by_pattern.return_value = orphaned_files
        
        # Mock deletion to raise exception
        backend.drive_sync.service.files().delete.side_effect = Exception("API error")
        
        with tempfile.NamedTemporaryFile(suffix='.db') as temp_file:
            temp_file.write(b'test database content')
            temp_file.flush()
            
            with patch('tracking.google_drive_backend.error_print') as mock_error_print:
                
                # Should still succeed despite cleanup error
                result = backend.upload_database(temp_file.name)
                assert result == True
                
                # Should have logged the cleanup error
                error_calls = [str(call) for call in mock_error_print.call_args_list]
                cleanup_errors = [call for call in error_calls if 'Failed to delete' in call]
                assert len(cleanup_errors) == 1

    def test_corruption_recovery_with_download_failure(self):
        """Test corruption recovery when download itself fails"""
        # Mock components
        mock_coordination = Mock(spec=GoogleDriveBackend)
        mock_operation_tracker = Mock(spec=OperationTracker)
        
        # Mock the new change detection method
        mock_coordination.has_database_changed.return_value = (True, {"modified_time": "2025-01-01T12:00:00Z", "size": 1000})
        
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as temp_file:
            local_cache_path = temp_file.name
            
        try:
            sync_manager = LeaderElectionSyncManager(
                coordination_backend=mock_coordination,
                local_cache_db_path=local_cache_path
            )
            
            # Override the operation tracker
            sync_manager.operation_tracker = mock_operation_tracker
            
            # Mock download failure
            mock_coordination.download_database.return_value = False
            mock_coordination.upload_database.return_value = True
            mock_operation_tracker.get_pending_operations.return_value = []
            
            with patch.object(sync_manager, '_report_progress'), \
                 patch.object(sync_manager, '_report_status'), \
                 patch('tracking.leader_election_sync.error_print') as mock_error_print:
                
                # Call sync
                result = sync_manager._perform_leader_sync()
                
                # Should fail due to download failure
                assert result == False
                
                # Should have logged download failure
                error_calls = [str(call) for call in mock_error_print.call_args_list]
                download_errors = [call for call in error_calls if 'Failed to download' in call]
                assert len(download_errors) == 1
                
        finally:
            if os.path.exists(local_cache_path):
                os.unlink(local_cache_path)