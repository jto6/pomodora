"""
Tests for database change detection functionality.
Ensures change detection works correctly for both Google Drive and local file backends.
"""

import pytest
import json
import tempfile
import os
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from tracking.coordination_backend import CoordinationBackend
from tracking.google_drive_backend import GoogleDriveBackend
from tracking.local_file_backend import LocalFileBackend


class TestChangeDetectionInterface:
    """Test the abstract change detection interface"""
    
    def test_change_detection_method_exists(self):
        """Verify the abstract method exists in the interface"""
        # Check that the method is defined in the abstract base class
        assert hasattr(CoordinationBackend, 'has_database_changed')
        assert callable(getattr(CoordinationBackend, 'has_database_changed'))


class TestGoogleDriveChangeDetection:
    """Test change detection for Google Drive backend"""
    
    @pytest.fixture
    def mock_drive_backend(self):
        """Create a mock Google Drive backend for testing"""
        with patch('tracking.google_drive_backend.GoogleDriveSync'):
            backend = GoogleDriveBackend(
                credentials_path="/fake/credentials.json",
                folder_name="TestFolder"
            )
            backend.folder_id = "test_folder_id"
            return backend
    
    def test_no_remote_database_detected_as_changed(self, mock_drive_backend):
        """Test that missing remote database is detected as changed"""
        # Mock no database files found
        mock_drive_backend.drive_sync.list_files.return_value = []
        
        has_changed, metadata = mock_drive_backend.has_database_changed()
        
        assert has_changed is True
        assert metadata is None
    
    def test_no_previous_metadata_detected_as_changed(self, mock_drive_backend):
        """Test that lack of previous metadata triggers download"""
        # Mock database file exists
        mock_file = {
            'id': 'test_file_id',
            'modifiedTime': '2025-01-01T12:00:00Z',
            'size': '1000'
        }
        mock_drive_backend.drive_sync.list_files.return_value = [mock_file]
        
        has_changed, metadata = mock_drive_backend.has_database_changed(None)
        
        assert has_changed is True
        assert metadata == {
            "modified_time": "2025-01-01T12:00:00Z",
            "size": 1000,
            "file_id": "test_file_id"
        }
    
    def test_unchanged_database_detected_correctly(self, mock_drive_backend):
        """Test that unchanged database is correctly identified"""
        # Mock database file with same metadata
        mock_file = {
            'id': 'test_file_id',
            'modifiedTime': '2025-01-01T12:00:00Z',
            'size': '1000'
        }
        mock_drive_backend.drive_sync.list_files.return_value = [mock_file]
        
        last_metadata = {
            "modified_time": "2025-01-01T12:00:00Z",
            "size": 1000,
            "file_id": "test_file_id"
        }
        
        has_changed, metadata = mock_drive_backend.has_database_changed(last_metadata)
        
        assert has_changed is False
        assert metadata == {
            "modified_time": "2025-01-01T12:00:00Z",
            "size": 1000,
            "file_id": "test_file_id"
        }
    
    def test_modified_time_change_detected(self, mock_drive_backend):
        """Test that modification time changes are detected"""
        # Mock database file with different modification time
        mock_file = {
            'id': 'test_file_id',
            'modifiedTime': '2025-01-02T12:00:00Z',  # Different time
            'size': '1000'
        }
        mock_drive_backend.drive_sync.list_files.return_value = [mock_file]
        
        last_metadata = {
            "modified_time": "2025-01-01T12:00:00Z",  # Original time
            "size": 1000,
            "file_id": "test_file_id"
        }
        
        has_changed, metadata = mock_drive_backend.has_database_changed(last_metadata)
        
        assert has_changed is True
        assert metadata["modified_time"] == "2025-01-02T12:00:00Z"
    
    def test_size_change_detected(self, mock_drive_backend):
        """Test that file size changes are detected"""
        # Mock database file with different size
        mock_file = {
            'id': 'test_file_id',
            'modifiedTime': '2025-01-01T12:00:00Z',
            'size': '2000'  # Different size
        }
        mock_drive_backend.drive_sync.list_files.return_value = [mock_file]
        
        last_metadata = {
            "modified_time": "2025-01-01T12:00:00Z",
            "size": 1000,  # Original size
            "file_id": "test_file_id"
        }
        
        has_changed, metadata = mock_drive_backend.has_database_changed(last_metadata)
        
        assert has_changed is True
        assert metadata["size"] == 2000
    
    def test_multiple_files_uses_most_recent(self, mock_drive_backend):
        """Test that most recent file is selected when multiple exist"""
        # Mock multiple database files
        mock_files = [
            {
                'id': 'old_file_id',
                'modifiedTime': '2025-01-01T12:00:00Z',
                'size': '1000'
            },
            {
                'id': 'new_file_id', 
                'modifiedTime': '2025-01-02T12:00:00Z',
                'size': '1500'
            }
        ]
        mock_drive_backend.drive_sync.list_files.return_value = mock_files
        
        has_changed, metadata = mock_drive_backend.has_database_changed()
        
        assert has_changed is True
        assert metadata["file_id"] == "new_file_id"  # Most recent
        assert metadata["modified_time"] == "2025-01-02T12:00:00Z"
    
    def test_api_error_triggers_conservative_download(self, mock_drive_backend):
        """Test that API errors trigger conservative download"""
        # Mock API error
        mock_drive_backend.drive_sync.list_files.side_effect = Exception("API Error")
        
        has_changed, metadata = mock_drive_backend.has_database_changed()
        
        assert has_changed is True  # Conservative approach
        assert metadata is None


class TestLocalFileChangeDetection:
    """Test change detection for local file backend"""
    
    @pytest.fixture
    def temp_shared_db(self):
        """Create a temporary shared database file for testing"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            f.write(b"test data")
            temp_path = f.name
        
        yield Path(temp_path)
        
        # Cleanup
        if Path(temp_path).exists():
            Path(temp_path).unlink()
    
    @pytest.fixture
    def local_backend(self, temp_shared_db):
        """Create a local file backend with temporary shared database"""
        backend = LocalFileBackend(str(temp_shared_db))
        return backend
    
    def test_missing_file_detected_as_changed(self):
        """Test that missing shared file is detected as changed"""
        # Use temporary path that doesn't exist yet
        with tempfile.TemporaryDirectory() as tmpdir:
            nonexistent_db = Path(tmpdir) / "nonexistent.db"
            backend = LocalFileBackend(str(nonexistent_db))
            
            # Delete the file if it was created by constructor
            if nonexistent_db.exists():
                nonexistent_db.unlink()
            
            has_changed, metadata = backend.has_database_changed()
            
            assert has_changed is True
            assert metadata is None
    
    def test_no_previous_metadata_detected_as_changed(self, local_backend):
        """Test that lack of previous metadata triggers download"""
        has_changed, metadata = local_backend.has_database_changed(None)
        
        assert has_changed is True
        assert metadata is not None
        assert "modified_time" in metadata
        assert "size" in metadata
    
    def test_unchanged_file_detected_correctly(self, local_backend):
        """Test that unchanged file is correctly identified"""
        # Get initial metadata
        _, initial_metadata = local_backend.has_database_changed(None)
        
        # Check again with same metadata
        has_changed, metadata = local_backend.has_database_changed(initial_metadata)
        
        assert has_changed is False
        assert metadata == initial_metadata
    
    def test_file_modification_detected(self, local_backend, temp_shared_db):
        """Test that file modifications are detected"""
        # Get initial metadata
        _, initial_metadata = local_backend.has_database_changed(None)
        
        # Modify the file
        import time
        time.sleep(0.1)  # Ensure different timestamp
        with open(temp_shared_db, 'a') as f:
            f.write("additional data")
        
        # Check for changes
        has_changed, new_metadata = local_backend.has_database_changed(initial_metadata)
        
        assert has_changed is True
        assert new_metadata["modified_time"] != initial_metadata["modified_time"]
        assert new_metadata["size"] != initial_metadata["size"]
    
    def test_file_access_error_triggers_conservative_download(self, local_backend):
        """Test that file access errors trigger conservative download"""
        # Delete the file to simulate access error
        local_backend.shared_db_path.unlink()
        
        has_changed, metadata = local_backend.has_database_changed()
        
        assert has_changed is True  # Conservative approach
        assert metadata is None


class TestChangeDetectionIntegration:
    """Integration tests for change detection in sync workflow"""
    
    def test_metadata_serialization_roundtrip(self):
        """Test that metadata can be serialized and deserialized correctly"""
        # Test Google Drive metadata
        gd_metadata = {
            "modified_time": "2025-01-01T12:00:00Z",
            "size": 1000,
            "file_id": "test_file_id"
        }
        
        # Test local file metadata
        lf_metadata = {
            "modified_time": 1640995200.0,  # Unix timestamp
            "size": 1000
        }
        
        # Test JSON roundtrip
        for metadata in [gd_metadata, lf_metadata]:
            json_str = json.dumps(metadata)
            restored = json.loads(json_str)
            assert restored == metadata
    
    def test_change_detection_with_mixed_backends(self):
        """Test that change detection works consistently across backend types"""
        # This would be useful for migration scenarios
        # Test that the interface is consistent between backends
        
        gd_backend = Mock(spec=GoogleDriveBackend)
        lf_backend = Mock(spec=LocalFileBackend)
        
        # Both should have the same method signature
        assert hasattr(gd_backend, 'has_database_changed')
        assert hasattr(lf_backend, 'has_database_changed')
        
        # Mock return values should have same structure
        gd_return = (True, {"modified_time": "2025-01-01T12:00:00Z", "size": 1000})
        lf_return = (True, {"modified_time": 1640995200.0, "size": 1000})
        
        gd_backend.has_database_changed.return_value = gd_return
        lf_backend.has_database_changed.return_value = lf_return
        
        # Both should return tuple[bool, Optional[Dict]]
        gd_result = gd_backend.has_database_changed()
        lf_result = lf_backend.has_database_changed()
        
        assert isinstance(gd_result[0], bool)
        assert isinstance(lf_result[0], bool)
        assert isinstance(gd_result[1], dict) or gd_result[1] is None
        assert isinstance(lf_result[1], dict) or lf_result[1] is None