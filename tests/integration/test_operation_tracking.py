"""
Integration tests for operation tracking across all CRUD operations.
Ensures that all database changes are properly tracked for sync.
"""

import pytest
import tempfile
from datetime import datetime
from pathlib import Path

from tracking.database_manager_unified import UnifiedDatabaseManager
from tracking.sync_config import SyncConfiguration


class TestOperationTracking:
    """Test operation tracking for all database operations"""
    
    @pytest.fixture
    def temp_db_manager(self):
        """Create temporary database manager with operation tracking"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_db:
            db_path = tmp_db.name
        
        try:
            # Create database manager with override path (local-only mode)
            db_manager = UnifiedDatabaseManager(db_path=db_path)
            yield db_manager
        finally:
            # Cleanup
            if Path(db_path).exists():
                Path(db_path).unlink()
    
    def test_create_project_tracks_operation(self, temp_db_manager):
        """Test that creating a project tracks the operation"""
        db_manager = temp_db_manager
        
        # Verify no pending operations initially
        pending = db_manager.operation_tracker.get_pending_operations()
        assert len(pending) == 0
        
        # Create a project
        success, message = db_manager.create_project("TestProject", "#FF0000")
        assert success, f"Project creation failed: {message}"
        
        # Verify operation was tracked
        pending = db_manager.operation_tracker.get_pending_operations()
        assert len(pending) == 1
        
        operation = pending[0]
        assert operation['operation_type'] == 'INSERT'
        assert operation['table_name'] == 'projects'
        assert 'TestProject' in operation['record_data']
        assert '#FF0000' in operation['record_data']
    
    def test_create_task_category_tracks_operation(self, temp_db_manager):
        """Test that creating a task category tracks the operation"""
        db_manager = temp_db_manager
        
        # Verify no pending operations initially
        pending = db_manager.operation_tracker.get_pending_operations()
        assert len(pending) == 0
        
        # Create a task category
        success, message = db_manager.create_task_category("TestCategory", "#00FF00")
        assert success, f"Task category creation failed: {message}"
        
        # Verify operation was tracked
        pending = db_manager.operation_tracker.get_pending_operations()
        assert len(pending) == 1
        
        operation = pending[0]
        assert operation['operation_type'] == 'INSERT'
        assert operation['table_name'] == 'task_categories'
        assert 'TestCategory' in operation['record_data']
        assert '#00FF00' in operation['record_data']
    
    def test_toggle_project_active_tracks_operation(self, temp_db_manager):
        """Test that toggling project active status tracks the operation"""
        db_manager = temp_db_manager
        
        # Create a project first
        success, message = db_manager.create_project("ToggleProject", "#0000FF")
        assert success
        
        # Get project ID
        projects = db_manager.get_all_projects()
        project = next(p for p in projects if p['name'] == 'ToggleProject')
        project_id = project['id']
        
        # Clear operations (we only care about the toggle operation)
        db_manager.operation_tracker.clear_operations()
        
        # Toggle project active status
        new_status = db_manager.toggle_project_active(project_id)
        assert new_status is not None
        
        # Verify operation was tracked
        pending = db_manager.operation_tracker.get_pending_operations()
        assert len(pending) == 1
        
        operation = pending[0]
        assert operation['operation_type'] == 'UPDATE'
        assert operation['table_name'] == 'projects'
        assert 'ToggleProject' in operation['record_data']
    
    def test_toggle_category_active_tracks_operation(self, temp_db_manager):
        """Test that toggling category active status tracks the operation"""
        db_manager = temp_db_manager
        
        # Create a category first
        success, message = db_manager.create_task_category("ToggleCategory", "#FFFF00")
        assert success
        
        # Get category ID
        categories = db_manager.get_all_task_categories()
        category = next(c for c in categories if c['name'] == 'ToggleCategory')
        category_id = category['id']
        
        # Clear operations (we only care about the toggle operation)
        db_manager.operation_tracker.clear_operations()
        
        # Toggle category active status
        new_status = db_manager.toggle_task_category_active(category_id)
        assert new_status is not None
        
        # Verify operation was tracked
        pending = db_manager.operation_tracker.get_pending_operations()
        assert len(pending) == 1
        
        operation = pending[0]
        assert operation['operation_type'] == 'UPDATE'
        assert operation['table_name'] == 'task_categories'
        assert 'ToggleCategory' in operation['record_data']
    
    def test_delete_project_tracks_operation(self, temp_db_manager):
        """Test that deleting a project tracks the operation"""
        db_manager = temp_db_manager
        
        # Create a project first
        success, message = db_manager.create_project("DeleteProject", "#FF00FF")
        assert success
        
        # Get project ID
        projects = db_manager.get_all_projects()
        project = next(p for p in projects if p['name'] == 'DeleteProject')
        project_id = project['id']
        
        # Clear operations (we only care about the delete operation)
        db_manager.operation_tracker.clear_operations()
        
        # Delete project
        success, message = db_manager.delete_project(project_id)
        assert success, f"Project deletion failed: {message}"
        
        # Verify operation was tracked
        pending = db_manager.operation_tracker.get_pending_operations()
        assert len(pending) == 1
        
        operation = pending[0]
        assert operation['operation_type'] == 'DELETE'
        assert operation['table_name'] == 'projects'
        assert 'DeleteProject' in operation['old_data']
    
    def test_delete_category_tracks_operation(self, temp_db_manager):
        """Test that deleting a task category tracks the operation"""
        db_manager = temp_db_manager
        
        # Create a category first
        success, message = db_manager.create_task_category("DeleteCategory", "#00FFFF")
        assert success
        
        # Get category ID
        categories = db_manager.get_all_task_categories()
        category = next(c for c in categories if c['name'] == 'DeleteCategory')
        category_id = category['id']
        
        # Clear operations (we only care about the delete operation)
        db_manager.operation_tracker.clear_operations()
        
        # Delete category
        success, message = db_manager.delete_task_category(category_id)
        assert success, f"Category deletion failed: {message}"
        
        # Verify operation was tracked
        pending = db_manager.operation_tracker.get_pending_operations()
        assert len(pending) == 1
        
        operation = pending[0]
        assert operation['operation_type'] == 'DELETE'
        assert operation['table_name'] == 'task_categories'
        assert 'DeleteCategory' in operation['old_data']
    
    def test_add_sprint_tracks_operation(self, temp_db_manager):
        """Test that adding a sprint tracks the operation"""
        db_manager = temp_db_manager
        
        # Get default project and category IDs
        projects = db_manager.get_active_projects()
        categories = db_manager.get_active_task_categories()
        assert len(projects) > 0, "No default projects found"
        assert len(categories) > 0, "No default categories found"
        
        project_id = projects[0]['id']
        category_id = categories[0]['id']
        
        # Clear operations
        db_manager.operation_tracker.clear_operations()
        
        # Add a sprint
        sprint = db_manager.add_sprint(
            project_id,
            category_id,
            "Test Sprint",
            datetime.now(),
            25
        )
        assert sprint is not None
        
        # Verify operation was tracked
        pending = db_manager.operation_tracker.get_pending_operations()
        assert len(pending) == 1
        
        operation = pending[0]
        assert operation['operation_type'] == 'INSERT'
        assert operation['table_name'] == 'sprints'
        assert 'Test Sprint' in operation['record_data']
    
    def test_complete_sprint_tracks_operation(self, temp_db_manager):
        """Test that completing a sprint tracks the operation"""
        db_manager = temp_db_manager
        
        # Get default project and category IDs
        projects = db_manager.get_active_projects()
        categories = db_manager.get_active_task_categories()
        project_id = projects[0]['id']
        category_id = categories[0]['id']
        
        # Add a sprint first
        sprint = db_manager.add_sprint(
            project_id,
            category_id,
            "Complete Test Sprint",
            datetime.now(),
            25
        )
        assert sprint is not None
        sprint_id = sprint.id
        
        # Clear operations (we only care about the complete operation)
        db_manager.operation_tracker.clear_operations()
        
        # Complete the sprint
        success = db_manager.complete_sprint(
            sprint_id=sprint_id,
            end_time=datetime.now(),
            duration_minutes=25
        )
        assert success
        
        # Verify operation was tracked
        pending = db_manager.operation_tracker.get_pending_operations()
        assert len(pending) == 1
        
        operation = pending[0]
        assert operation['operation_type'] == 'UPDATE'
        assert operation['table_name'] == 'sprints'
        assert str(sprint_id) in operation['record_data']
    
    def test_multiple_operations_accumulate(self, temp_db_manager):
        """Test that multiple operations accumulate correctly"""
        db_manager = temp_db_manager
        
        # Clear operations
        db_manager.operation_tracker.clear_operations()
        
        # Perform multiple operations
        success1, _ = db_manager.create_project("Multi1", "#111111")
        success2, _ = db_manager.create_project("Multi2", "#222222")
        success3, _ = db_manager.create_task_category("MultiCat", "#333333")
        
        assert all([success1, success2, success3])
        
        # Verify all operations were tracked
        pending = db_manager.operation_tracker.get_pending_operations()
        assert len(pending) == 3
        
        # Verify operation types
        operation_types = [op['operation_type'] for op in pending]
        assert all(op_type == 'INSERT' for op_type in operation_types)
        
        # Verify table names
        table_names = [op['table_name'] for op in pending]
        assert table_names.count('projects') == 2
        assert table_names.count('task_categories') == 1
    
    def test_clear_operations_empties_tracker(self, temp_db_manager):
        """Test that clearing operations empties the tracker"""
        db_manager = temp_db_manager
        
        # Add some operations
        db_manager.create_project("ClearTest", "#444444")
        
        # Verify operation exists
        pending = db_manager.operation_tracker.get_pending_operations()
        assert len(pending) > 0
        
        # Clear operations
        db_manager.operation_tracker.clear_operations()
        
        # Verify operations are cleared
        pending = db_manager.operation_tracker.get_pending_operations()
        assert len(pending) == 0


class TestOperationTrackingRegressions:
    """Regression tests to prevent operation tracking from breaking again"""
    
    def test_all_crud_methods_have_tracking(self):
        """Ensure all CRUD methods include operation tracking calls"""
        import inspect
        from tracking.database_manager_unified import UnifiedDatabaseManager
        
        # Get all methods that should track operations
        crud_methods = [
            'create_project',
            'create_task_category', 
            'toggle_project_active',
            'toggle_task_category_active',
            'delete_project',
            'delete_task_category',
            '_add_sprint_from_params',  # Check the internal method that actually does tracking
            'complete_sprint'
        ]
        
        for method_name in crud_methods:
            method = getattr(UnifiedDatabaseManager, method_name)
            source_code = inspect.getsource(method)
            
            # Verify the method contains a call to track_operation
            assert 'track_operation' in source_code, \
                f"Method {method_name} is missing track_operation() call"
            
            # Verify the method contains the right operation type
            if 'create' in method_name:
                assert "'insert'" in source_code, \
                    f"Method {method_name} should use 'insert' operation type"
            elif 'toggle' in method_name or 'complete' in method_name:
                assert "'update'" in source_code, \
                    f"Method {method_name} should use 'update' operation type"
            elif 'delete' in method_name:
                assert "'delete'" in source_code, \
                    f"Method {method_name} should use 'delete' operation type"
            elif '_add_sprint_from_params' == method_name:
                assert "'insert'" in source_code, \
                    f"Method {method_name} should use 'insert' operation type"
    
    def test_operation_tracker_has_required_methods(self):
        """Ensure OperationTracker has all required methods"""
        from tracking.operation_log import OperationTracker
        
        required_methods = [
            'track_operation',
            'get_pending_operations', 
            'clear_operations'
        ]
        
        for method_name in required_methods:
            assert hasattr(OperationTracker, method_name), \
                f"OperationTracker is missing required method: {method_name}"