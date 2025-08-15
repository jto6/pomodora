"""
Unit tests for Google Drive duplicate prevention.
Tests that upload properly prevents duplicate file creation.
"""

import pytest
from unittest.mock import Mock, patch, call
import tempfile
import time
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / 'src'))

from tracking.google_drive_backend import GoogleDriveBackend


@pytest.mark.unit
@pytest.mark.tracking
class TestDuplicatePrevention:
    """Test Google Drive duplicate prevention during upload"""

    def test_upload_cleans_orphaned_temp_files(self):
        """Test that upload cleans up orphaned temp files from failed previous uploads"""
        # Mock orphaned temp files from failed uploads
        orphaned_temp_files = [
            {'id': 'temp1', 'name': 'pomodora_sync_123456.db'},
            {'id': 'temp2', 'name': 'pomodora_sync_789012.db'}
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
        
        # Mock list_files_by_pattern to return orphaned files
        backend.drive_sync.list_files_by_pattern.return_value = orphaned_temp_files
        
        with tempfile.NamedTemporaryFile(suffix='.db') as temp_file:
            temp_file.write(b'test database content')
            temp_file.flush()
            
            with patch('tracking.google_drive_backend.error_print') as mock_error_print:
                
                # Call upload_database
                result = backend.upload_database(temp_file.name)
                
                # Should succeed
                assert result == True
                
                # Should have cleaned up orphaned temp files
                assert backend.drive_sync.service.files().delete.call_count == 2
                delete_calls = backend.drive_sync.service.files().delete.call_args_list
                deleted_ids = [call[1]['fileId'] for call in delete_calls if 'fileId' in call[1]]
                assert 'temp1' in deleted_ids
                assert 'temp2' in deleted_ids

    def test_upload_handles_no_orphaned_files(self):
        """Test that upload works normally when no orphaned files exist"""
        # Create backend
        backend = GoogleDriveBackend(
            credentials_path="/fake/path",
            folder_name="test_folder"
        )
        
        # Mock drive_sync
        backend.drive_sync = Mock()
        backend.drive_sync.upload_file.return_value = True
        backend.drive_sync.service = Mock()
        
        # Mock no orphaned files
        backend.drive_sync.list_files_by_pattern.return_value = []
        
        with tempfile.NamedTemporaryFile(suffix='.db') as temp_file:
            temp_file.write(b'test database content')
            temp_file.flush()
            
            with patch('tracking.google_drive_backend.info_print') as mock_info_print:
                
                # Call upload_database
                result = backend.upload_database(temp_file.name)
                
                # Should succeed
                assert result == True
                
                # Should have called upload with correct parameters
                backend.drive_sync.upload_file.assert_called_once_with(
                    str(temp_file.name), "pomodora.db"
                )

    def test_upload_handles_file_size_verification(self):
        """Test that upload properly logs file size information"""
        # Create backend
        backend = GoogleDriveBackend(
            credentials_path="/fake/path",
            folder_name="test_folder"
        )
        
        # Mock drive_sync
        backend.drive_sync = Mock()
        backend.drive_sync.upload_file.return_value = True
        backend.drive_sync.service = Mock()
        
        # Mock no orphaned files
        backend.drive_sync.list_files_by_pattern.return_value = []
        
        with tempfile.NamedTemporaryFile(suffix='.db') as temp_file:
            test_content = b'test database content with specific size'
            temp_file.write(test_content)
            temp_file.flush()
            
            with patch('tracking.google_drive_backend.info_print') as mock_info_print:
                
                # Call upload_database
                result = backend.upload_database(temp_file.name)
                
                # Should succeed
                assert result == True
                
                # Should have logged file size
                info_calls = [str(call) for call in mock_info_print.call_args_list]
                size_logs = [call for call in info_calls if 'bytes' in call]
                assert len(size_logs) == 1
                assert str(len(test_content)) in size_logs[0]

    def test_upload_with_missing_local_file(self):
        """Test that upload fails gracefully when local database file doesn't exist"""
        # Create backend
        backend = GoogleDriveBackend(
            credentials_path="/fake/path",
            folder_name="test_folder"
        )
        
        # Mock drive_sync
        backend.drive_sync = Mock()
        backend.drive_sync.service = Mock()
        
        fake_path = "/nonexistent/database.db"
        
        with patch('tracking.google_drive_backend.error_print') as mock_error_print:
            
            # Call upload_database with nonexistent file
            result = backend.upload_database(fake_path)
            
            # Should fail
            assert result == False
            
            # Should have logged error about missing file
            error_calls = [str(call) for call in mock_error_print.call_args_list]
            missing_file_errors = [call for call in error_calls if 'not found' in call]
            assert len(missing_file_errors) == 1

    def test_orphan_cleanup_handles_deletion_errors(self):
        """Test that orphan cleanup handles deletion errors gracefully"""
        # Mock orphaned files with one that fails to delete
        orphaned_files = [
            {'id': 'deletable_temp', 'name': 'pomodora_sync_123.db'},
            {'id': 'problematic_temp', 'name': 'pomodora_sync_456.db'}
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
        
        # Mock deletion to fail for one file
        def mock_delete_side_effect(*args, **kwargs):
            if 'fileId' in kwargs and kwargs['fileId'] == 'problematic_temp':
                raise Exception("Network error during deletion")
            return Mock()
        
        backend.drive_sync.service.files().delete.side_effect = mock_delete_side_effect
        
        with tempfile.NamedTemporaryFile(suffix='.db') as temp_file:
            temp_file.write(b'test database content')
            temp_file.flush()
            
            with patch('tracking.google_drive_backend.error_print') as mock_error_print:
                
                # Should still succeed despite deletion error
                result = backend.upload_database(temp_file.name)
                assert result == True
                
                # Should have attempted to delete both files
                assert backend.drive_sync.service.files().delete.call_count == 2
                
                # Should have logged the deletion error
                error_calls = [str(call) for call in mock_error_print.call_args_list]
                deletion_errors = [call for call in error_calls if 'Failed to delete' in call]
                assert len(deletion_errors) == 1