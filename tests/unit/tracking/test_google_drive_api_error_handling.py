"""
Test Google Drive API error handling to prevent data loss.

This test verifies that Google Drive API errors are properly handled
and do not result in empty databases being created.
"""

import pytest
import os
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add src to path for imports
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

# Mock Google Drive modules to avoid import errors
sys.modules['google.auth'] = Mock()
sys.modules['google.auth.transport'] = Mock()
sys.modules['google.auth.transport.requests'] = Mock()
sys.modules['google.oauth2'] = Mock()
sys.modules['google.oauth2.credentials'] = Mock()
sys.modules['google_auth_oauthlib'] = Mock()
sys.modules['google_auth_oauthlib.flow'] = Mock()
sys.modules['googleapiclient'] = Mock()
sys.modules['googleapiclient.discovery'] = Mock()
sys.modules['googleapiclient.http'] = Mock()


class TestGoogleDriveAPIErrorHandling:
    """Test Google Drive API error handling"""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory"""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir)
    
    def test_list_files_by_name_raises_on_api_error(self):
        """Test that list_files_by_name raises exception on API errors"""
        from tracking.google_drive import GoogleDriveSync
        
        # Create mock sync with authentication success
        sync = GoogleDriveSync("fake_credentials.json")
        sync.service = Mock()
        sync.folder_id = "test_folder_id"
        
        # Mock API to raise an exception
        mock_files = Mock()
        mock_files.list.return_value.execute.side_effect = Exception("HTTP 500 Internal Server Error")
        sync.service.files.return_value = mock_files
        
        # Should raise exception, not return empty list
        with pytest.raises(Exception) as exc_info:
            sync.list_files_by_name("pomodora.db")
        
        # Verify the exception message
        assert "Google Drive API error during file listing" in str(exc_info.value)
        assert "HTTP 500 Internal Server Error" in str(exc_info.value)
    
    def test_list_files_by_name_returns_empty_when_no_service(self):
        """Test that list_files_by_name returns empty list when not authenticated"""
        from tracking.google_drive import GoogleDriveSync
        
        # Create sync without authentication
        sync = GoogleDriveSync("fake_credentials.json")
        sync.service = None  # Not authenticated
        sync.folder_id = None
        
        # Should return empty list (not an error condition)
        result = sync.list_files_by_name("pomodora.db")
        assert result == []
    
    def test_download_database_fails_on_api_error(self):
        """Test that download_database fails when list_files_by_name raises exception"""
        from tracking.google_drive_backend import GoogleDriveBackend
        
        # Create mock backend
        backend = GoogleDriveBackend("fake_creds.json", "TestFolder")
        
        # Mock the drive_sync to raise exception on list_files_by_name
        mock_drive_sync = Mock()
        mock_drive_sync.list_files_by_name.side_effect = Exception("Google Drive API error during file listing: HTTP 500")
        backend.drive_sync = mock_drive_sync
        
        # Create temp file for download target
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_path = temp_file.name
        
        try:
            # Should return False (failure) when API error occurs
            result = backend.download_database(temp_path)
            assert result is False
            
            # Verify the mock was called
            mock_drive_sync.list_files_by_name.assert_called_once_with("pomodora.db")
            
        finally:
            os.unlink(temp_path)
    
    def test_download_database_succeeds_on_no_files(self):
        """Test that download_database succeeds when no files found (first sync scenario)"""
        from tracking.google_drive_backend import GoogleDriveBackend
        
        # Create mock backend
        backend = GoogleDriveBackend("fake_creds.json", "TestFolder")
        
        # Mock the drive_sync to return empty list (no files found)
        mock_drive_sync = Mock()
        mock_drive_sync.list_files_by_name.return_value = []  # No files found
        backend.drive_sync = mock_drive_sync
        
        # Create temp file for download target
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_path = temp_file.name
        
        try:
            # Should return True (success) when no files found
            result = backend.download_database(temp_path)
            assert result is True
            
            # Verify the mock was called
            mock_drive_sync.list_files_by_name.assert_called_once_with("pomodora.db")
            
        finally:
            os.unlink(temp_path)
    
    def test_download_database_downloads_existing_file(self):
        """Test that download_database successfully downloads when file exists"""
        from tracking.google_drive_backend import GoogleDriveBackend
        
        # Create mock backend
        backend = GoogleDriveBackend("fake_creds.json", "TestFolder")
        
        # Mock file data
        mock_file = {
            'id': 'test_file_id',
            'name': 'pomodora.db',
            'modifiedTime': '2023-01-01T12:00:00.000Z',
            'size': '1024'
        }
        
        # Mock the drive_sync
        mock_drive_sync = Mock()
        mock_drive_sync.list_files_by_name.return_value = [mock_file]
        mock_drive_sync.download_file.return_value = True  # Successful download
        backend.drive_sync = mock_drive_sync
        
        # Create temp file for download target
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_path = temp_file.name
        
        try:
            # Write some data to simulate successful download
            Path(temp_path).write_text("downloaded_data")
            
            # Should return True (success) when file downloaded successfully
            result = backend.download_database(temp_path)
            assert result is True
            
            # Verify the mocks were called correctly
            mock_drive_sync.list_files_by_name.assert_called_once_with("pomodora.db")
            mock_drive_sync.download_file.assert_called_once_with('test_file_id', temp_path)
            
        finally:
            os.unlink(temp_path)
    
    def test_backend_download_database_fails_on_api_error(self):
        """Test that GoogleDriveBackend.download_database fails when API errors occur"""
        from tracking.google_drive_backend import GoogleDriveBackend
        
        # Create backend
        backend = GoogleDriveBackend("fake_creds.json", "TestFolder")
        
        # Mock the drive_sync to raise API error
        mock_drive_sync = Mock()
        api_error = Exception("Google Drive API error during file listing: HTTP 500 Internal Server Error")
        mock_drive_sync.list_files_by_name.side_effect = api_error
        backend.drive_sync = mock_drive_sync
        
        # Create temp path for download
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_path = temp_file.name
        
        try:
            # Should return False when API fails - not create empty database
            result = backend.download_database(temp_path)
            assert result is False
            
            # The temp file should still be empty (no database created)
            assert os.path.getsize(temp_path) == 0
            
        finally:
            os.unlink(temp_path)


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])