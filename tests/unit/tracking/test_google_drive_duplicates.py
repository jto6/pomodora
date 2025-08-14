"""
Unit tests for Google Drive duplicate database file handling.
Tests that the system properly selects the most recent file and cleans up duplicates.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / 'src'))

from tracking.google_drive_backend import GoogleDriveBackend


@pytest.mark.unit
@pytest.mark.tracking
class TestGoogleDriveDuplicateHandling:
    """Test Google Drive duplicate database file handling"""

    def test_download_database_selects_most_recent_when_duplicates_exist(self):
        """Test that download_database selects the most recent file when duplicates exist"""
        # Mock Google Drive files with different modification times
        mock_files = [
            {
                'id': 'old_file_id',
                'name': 'pomodora.db',
                'modifiedTime': '2025-01-14T09:00:00.000Z'  # Older file
            },
            {
                'id': 'recent_file_id', 
                'name': 'pomodora.db',
                'modifiedTime': '2025-01-14T11:00:00.000Z'  # Most recent file
            },
            {
                'id': 'middle_file_id',
                'name': 'pomodora.db', 
                'modifiedTime': '2025-01-14T10:00:00.000Z'  # Middle file
            }
        ]
        
        # Create mock backend
        backend = GoogleDriveBackend(
            credentials_path="/fake/path",
            folder_name="test_folder"
        )
        
        # Mock the drive_sync object
        backend.drive_sync = Mock()
        backend.drive_sync.list_files_by_name.return_value = mock_files
        backend.drive_sync.download_file.return_value = True
        backend.drive_sync.service = Mock()
        
        # Mock Path operations
        with patch('tracking.google_drive_backend.Path') as mock_path:
            mock_local_path = Mock()
            mock_local_path.parent.mkdir = Mock()
            mock_local_path.exists.return_value = True
            mock_local_path.stat.return_value.st_size = 1024
            mock_path.return_value = mock_local_path
            
            # Mock print functions
            with patch('tracking.google_drive_backend.error_print') as mock_error_print, \
                 patch('tracking.google_drive_backend.info_print') as mock_info_print:
                
                # Call download_database
                result = backend.download_database("/fake/cache/path")
                
                # Verify it succeeded
                assert result == True
                
                # Verify it detected duplicates
                mock_error_print.assert_called_with("⚠️  Found 3 duplicate database files on Google Drive!")
                
                # Verify it selected the most recent file (recent_file_id)
                backend.drive_sync.download_file.assert_called_once_with('recent_file_id', str(mock_local_path))
                
                # Verify it logged selection of most recent file
                selection_calls = [call for call in mock_info_print.call_args_list 
                                 if 'Selected most recent database' in str(call)]
                assert len(selection_calls) == 1
                assert 'recent_file_id' in str(selection_calls[0])
                
                # Verify it attempted to delete duplicates
                assert backend.drive_sync.service.files().delete.call_count == 2
                delete_calls = backend.drive_sync.service.files().delete.call_args_list
                deleted_ids = [call[1]['fileId'] for call in delete_calls]
                assert 'old_file_id' in deleted_ids
                assert 'middle_file_id' in deleted_ids
                assert 'recent_file_id' not in deleted_ids  # Should not delete the selected file

    def test_download_database_handles_single_file_normally(self):
        """Test that download_database works normally when only one file exists"""
        # Mock single Google Drive file
        mock_files = [
            {
                'id': 'single_file_id',
                'name': 'pomodora.db',
                'modifiedTime': '2025-01-14T10:00:00.000Z'
            }
        ]
        
        # Create mock backend
        backend = GoogleDriveBackend(
            credentials_path="/fake/path",
            folder_name="test_folder"
        )
        
        # Mock the drive_sync object
        backend.drive_sync = Mock()
        backend.drive_sync.list_files_by_name.return_value = mock_files
        backend.drive_sync.download_file.return_value = True
        
        # Mock Path operations
        with patch('tracking.google_drive_backend.Path') as mock_path:
            mock_local_path = Mock()
            mock_local_path.parent.mkdir = Mock()
            mock_local_path.exists.return_value = True
            mock_local_path.stat.return_value.st_size = 1024
            mock_path.return_value = mock_local_path
            
            # Mock print functions
            with patch('tracking.google_drive_backend.error_print') as mock_error_print, \
                 patch('tracking.google_drive_backend.info_print') as mock_info_print:
                
                # Call download_database
                result = backend.download_database("/fake/cache/path")
                
                # Verify it succeeded
                assert result == True
                
                # Verify it did NOT report duplicates
                mock_error_print.assert_not_called()
                
                # Verify it downloaded the single file
                backend.drive_sync.download_file.assert_called_once_with('single_file_id', str(mock_local_path))
                
                # Verify no deletion attempts (since there's only one file)
                # In single file case, deletion code is never reached

    def test_download_database_handles_no_files(self):
        """Test that download_database handles the case when no files exist"""
        # Create mock backend
        backend = GoogleDriveBackend(
            credentials_path="/fake/path",
            folder_name="test_folder"
        )
        
        # Mock the drive_sync object
        backend.drive_sync = Mock()
        backend.drive_sync.list_files_by_name.return_value = []  # No files
        
        # Mock print functions
        with patch('tracking.google_drive_backend.debug_print') as mock_debug_print:
            
            # Call download_database
            result = backend.download_database("/fake/cache/path")
            
            # Verify it succeeded (not an error for first sync)
            assert result == True
            
            # Verify it logged no database found
            mock_debug_print.assert_called_with("No database found on Google Drive - nothing to download")
            
            # Verify no download attempt
            backend.drive_sync.download_file.assert_not_called()

    def test_duplicate_cleanup_handles_deletion_errors(self):
        """Test that duplicate cleanup gracefully handles deletion errors"""
        # Mock Google Drive files with duplicates
        mock_files = [
            {
                'id': 'good_file_id',
                'name': 'pomodora.db',
                'modifiedTime': '2025-01-14T11:00:00.000Z'  # Most recent
            },
            {
                'id': 'bad_file_id',
                'name': 'pomodora.db',
                'modifiedTime': '2025-01-14T10:00:00.000Z'  # Should be deleted
            }
        ]
        
        # Create mock backend
        backend = GoogleDriveBackend(
            credentials_path="/fake/path",
            folder_name="test_folder"
        )
        
        # Mock the drive_sync object
        backend.drive_sync = Mock()
        backend.drive_sync.list_files_by_name.return_value = mock_files
        backend.drive_sync.download_file.return_value = True
        backend.drive_sync.service = Mock()
        
        # Mock deletion to raise an exception
        backend.drive_sync.service.files().delete().execute.side_effect = Exception("Deletion failed")
        
        # Mock Path operations
        with patch('tracking.google_drive_backend.Path') as mock_path:
            mock_local_path = Mock()
            mock_local_path.parent.mkdir = Mock()
            mock_local_path.exists.return_value = True
            mock_local_path.stat.return_value.st_size = 1024
            mock_path.return_value = mock_local_path
            
            # Mock print functions
            with patch('tracking.google_drive_backend.error_print') as mock_error_print, \
                 patch('tracking.google_drive_backend.info_print') as mock_info_print:
                
                # Call download_database
                result = backend.download_database("/fake/cache/path")
                
                # Verify it still succeeded despite deletion error
                assert result == True
                
                # Verify it attempted deletion (fileId call)
                delete_calls = backend.drive_sync.service.files().delete.call_args_list
                assert len([call for call in delete_calls if 'fileId' in str(call)]) == 1
                
                # Verify it logged the deletion error
                deletion_error_calls = [call for call in mock_error_print.call_args_list 
                                      if 'Failed to delete duplicate file' in str(call)]
                assert len(deletion_error_calls) == 1
                assert 'bad_file_id' in str(deletion_error_calls[0])
                
                # Verify it still downloaded the correct file
                backend.drive_sync.download_file.assert_called_once_with('good_file_id', str(mock_local_path))

    def test_get_coordination_status_reports_duplicate_count(self):
        """Test that get_coordination_status reports duplicate database count"""
        # Mock Google Drive files with duplicates
        mock_files = [
            {
                'id': 'file1_id',
                'name': 'pomodora.db',
                'modifiedTime': '2025-01-14T11:00:00.000Z',
                'size': '1024'
            },
            {
                'id': 'file2_id',
                'name': 'pomodora.db',
                'modifiedTime': '2025-01-14T10:00:00.000Z',
                'size': '2048'
            }
        ]
        
        # Create mock backend
        backend = GoogleDriveBackend(
            credentials_path="/fake/path",
            folder_name="test_folder"
        )
        
        # Mock the drive_sync object
        backend.drive_sync = Mock()
        backend.drive_sync.service = Mock()  # Authenticated
        backend.drive_sync.list_files_by_pattern.return_value = []  # No leader files
        backend.drive_sync.list_files_by_name.return_value = mock_files
        
        # Call get_coordination_status
        status = backend.get_coordination_status()
        
        # Verify status reports duplicates
        assert status['duplicate_db_count'] == 2
        assert status['remote_db']['exists'] == True
        assert status['remote_db']['file_id'] == 'file1_id'  # Most recent file
        assert status['remote_db']['size_bytes'] == 1024
        assert status['remote_db']['modified_at'] == '2025-01-14T11:00:00.000Z'

    def test_get_coordination_status_no_duplicate_count_for_single_file(self):
        """Test that get_coordination_status doesn't report duplicate count for single file"""
        # Mock single Google Drive file
        mock_files = [
            {
                'id': 'single_file_id',
                'name': 'pomodora.db',
                'modifiedTime': '2025-01-14T10:00:00.000Z',
                'size': '1024'
            }
        ]
        
        # Create mock backend
        backend = GoogleDriveBackend(
            credentials_path="/fake/path",
            folder_name="test_folder"
        )
        
        # Mock the drive_sync object
        backend.drive_sync = Mock()
        backend.drive_sync.service = Mock()  # Authenticated
        backend.drive_sync.list_files_by_pattern.return_value = []  # No leader files
        backend.drive_sync.list_files_by_name.return_value = mock_files
        
        # Call get_coordination_status
        status = backend.get_coordination_status()
        
        # Verify status does NOT report duplicate count
        assert 'duplicate_db_count' not in status
        assert status['remote_db']['exists'] == True
        assert status['remote_db']['file_id'] == 'single_file_id'

    def test_file_selection_with_missing_modified_time(self):
        """Test that file selection works even when some files have missing modifiedTime"""
        # Mock Google Drive files with missing/empty modification times
        mock_files = [
            {
                'id': 'no_time_file_id',
                'name': 'pomodora.db'
                # No modifiedTime field
            },
            {
                'id': 'good_file_id',
                'name': 'pomodora.db',
                'modifiedTime': '2025-01-14T11:00:00.000Z'
            },
            {
                'id': 'empty_time_file_id',
                'name': 'pomodora.db',
                'modifiedTime': ''  # Empty modifiedTime
            }
        ]
        
        # Create mock backend
        backend = GoogleDriveBackend(
            credentials_path="/fake/path",
            folder_name="test_folder"
        )
        
        # Mock the drive_sync object
        backend.drive_sync = Mock()
        backend.drive_sync.list_files_by_name.return_value = mock_files
        backend.drive_sync.download_file.return_value = True
        backend.drive_sync.service = Mock()
        
        # Mock Path operations
        with patch('tracking.google_drive_backend.Path') as mock_path:
            mock_local_path = Mock()
            mock_local_path.parent.mkdir = Mock()
            mock_local_path.exists.return_value = True
            mock_local_path.stat.return_value.st_size = 1024
            mock_path.return_value = mock_local_path
            
            # Mock print functions
            with patch('tracking.google_drive_backend.error_print'), \
                 patch('tracking.google_drive_backend.info_print'):
                
                # Call download_database
                result = backend.download_database("/fake/cache/path")
                
                # Verify it succeeded
                assert result == True
                
                # Verify it selected the file with the valid modifiedTime (good_file_id)
                backend.drive_sync.download_file.assert_called_once_with('good_file_id', str(mock_local_path))
                
                # Verify it attempted to delete the other two files
                assert backend.drive_sync.service.files().delete.call_count == 2

    def test_duplicate_detection_logging_format(self):
        """Test that duplicate detection logs detailed information about each file"""
        # Mock Google Drive files with duplicates
        mock_files = [
            {
                'id': 'file_a_id',
                'name': 'pomodora.db',
                'modifiedTime': '2025-01-14T09:00:00.000Z'
            },
            {
                'id': 'file_b_id', 
                'name': 'pomodora.db',
                'modifiedTime': '2025-01-14T11:00:00.000Z'
            }
        ]
        
        # Create mock backend
        backend = GoogleDriveBackend(
            credentials_path="/fake/path",
            folder_name="test_folder"
        )
        
        # Mock the drive_sync object
        backend.drive_sync = Mock()
        backend.drive_sync.list_files_by_name.return_value = mock_files
        backend.drive_sync.download_file.return_value = True
        backend.drive_sync.service = Mock()
        
        # Mock Path operations
        with patch('tracking.google_drive_backend.Path') as mock_path:
            mock_local_path = Mock()
            mock_local_path.parent.mkdir = Mock()
            mock_local_path.exists.return_value = True
            mock_local_path.stat.return_value.st_size = 1024
            mock_path.return_value = mock_local_path
            
            # Mock print functions
            with patch('tracking.google_drive_backend.error_print') as mock_error_print, \
                 patch('tracking.google_drive_backend.info_print') as mock_info_print:
                
                # Call download_database
                backend.download_database("/fake/cache/path")
                
                # Verify detailed logging
                info_calls = [str(call) for call in mock_info_print.call_args_list]
                
                # Should log each database file found
                database_logs = [call for call in info_calls if 'Database ' in call and 'ID=' in call]
                assert len(database_logs) == 2
                
                # Should log selection of most recent
                selection_logs = [call for call in info_calls if 'Selected most recent database' in call]
                assert len(selection_logs) == 1
                assert 'file_b_id' in selection_logs[0]  # Most recent file
                
                # Should log deletion attempts
                deletion_logs = [call for call in info_calls if 'Deleting duplicate database file' in call]
                assert len(deletion_logs) == 1
                assert 'file_a_id' in deletion_logs[0]  # Older file should be deleted