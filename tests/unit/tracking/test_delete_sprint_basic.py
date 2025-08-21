"""
Basic tests for delete_sprint functionality
"""

import pytest
import tempfile
import os

# Add src to path for imports
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from tracking.database_manager_unified import UnifiedDatabaseManager
from tracking.sync_config import SyncConfiguration


class TestDeleteSprintBasic:
    """Test basic delete_sprint functionality exists and works"""
    
    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database file"""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        yield path
        if os.path.exists(path):
            os.unlink(path)
    
    @pytest.fixture
    def db_manager(self, temp_db_path):
        """Create a database manager"""
        sync_config = SyncConfiguration()
        sync_config._strategy = "local_only"
        
        db_manager = UnifiedDatabaseManager(db_path=temp_db_path, sync_config=sync_config)
        return db_manager
    
    def test_delete_sprint_method_exists(self, db_manager):
        """Test that delete_sprint method exists on UnifiedDatabaseManager"""
        assert hasattr(db_manager, 'delete_sprint'), "delete_sprint method should exist"
        assert callable(getattr(db_manager, 'delete_sprint')), "delete_sprint should be callable"
    
    def test_delete_nonexistent_sprint_returns_false(self, db_manager):
        """Test deleting a sprint that doesn't exist returns False"""
        success, message = db_manager.delete_sprint(99999)
        
        assert success is False, "Deleting nonexistent sprint should return False"
        assert "not found" in message.lower(), "Error message should mention sprint not found"
    
    def test_delete_sprint_method_signature(self, db_manager):
        """Test that delete_sprint method has the correct signature"""
        import inspect
        
        # Get the method signature
        sig = inspect.signature(db_manager.delete_sprint)
        params = list(sig.parameters.keys())
        
        # Should have sprint_id parameter
        assert 'sprint_id' in params, "delete_sprint should have sprint_id parameter"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])