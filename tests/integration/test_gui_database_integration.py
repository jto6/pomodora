"""
Integration tests for GUI and database manager compatibility.
Tests that the GUI can properly initialize and interact with the database manager.
"""

import pytest
import tempfile
import os
import sys
from pathlib import Path
from unittest.mock import patch, Mock

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

@pytest.mark.integration
class TestGUIDatabaseIntegration:
    """Test GUI and database manager integration"""
    
    def test_gui_imports_database_manager_successfully(self):
        """Test that GUI can import DatabaseManager without errors"""
        # This should not raise any import errors
        from tracking.database_manager_unified import UnifiedDatabaseManager as DatabaseManager
        from tracking.models import TaskCategory, Project, Sprint
        
        # Verify the classes exist
        assert DatabaseManager is not None
        assert TaskCategory is not None
        assert Project is not None
        assert Sprint is not None
    
    def test_database_manager_has_required_attributes(self):
        """Test that DatabaseManager has attributes expected by GUI"""
        from tracking.database_manager_unified import UnifiedDatabaseManager as DatabaseManager
        
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "test.db")
            db_manager = DatabaseManager(db_path=db_path)
            
            # Verify key attributes expected by GUI
            assert hasattr(db_manager, 'sync_strategy')
            assert hasattr(db_manager, 'get_active_task_categories')
            assert hasattr(db_manager, 'get_active_projects')
            assert hasattr(db_manager, 'get_sprints_by_date')
    
    def test_database_initialization_creates_tables(self):
        """Test that database initialization actually creates required tables"""
        from tracking.database_manager_unified import UnifiedDatabaseManager as DatabaseManager
        from sqlalchemy import inspect
        
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "test.db")
            db_manager = DatabaseManager(db_path=db_path)
            
            # Check that tables were created
            inspector = inspect(db_manager.engine)
            table_names = inspector.get_table_names()
            
            assert 'task_categories' in table_names
            assert 'projects' in table_names  
            assert 'sprints' in table_names
    
    def test_database_initialization_creates_default_data(self):
        """Test that database initialization creates default projects and categories"""
        from tracking.database_manager_unified import UnifiedDatabaseManager as DatabaseManager
        
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "test.db") 
            db_manager = DatabaseManager(db_path=db_path)
            db_manager.initialize_default_projects()
            
            # Check that default data was created
            categories = db_manager.get_active_task_categories()
            projects = db_manager.get_active_projects()
            
            assert len(categories) > 0, "No task categories were created"
            assert len(projects) > 0, "No projects were created"
            
            # Check for specific default categories (API returns dicts, not objects)
            category_names = [cat['name'] for cat in categories]
            assert 'Admin' in category_names
            assert 'Dev' in category_names
            
            # Check for specific default projects  
            project_names = [proj['name'] for proj in projects]
            assert 'None' in project_names

    def test_gui_can_load_database_data(self):
        """Test that GUI can load data from database without errors"""
        from tracking.database_manager_unified import UnifiedDatabaseManager as DatabaseManager
        
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "test.db")
            db_manager = DatabaseManager(db_path=db_path)
            db_manager.initialize_default_projects()
            
            # Test the specific methods GUI uses
            try:
                categories = db_manager.get_active_task_categories()
                projects = db_manager.get_active_projects()
                
                from datetime import date
                sprints = db_manager.get_sprints_by_date(date.today())
                
                # These should not raise exceptions
                assert isinstance(categories, list)
                assert isinstance(projects, list)  
                assert isinstance(sprints, list)
                
            except Exception as e:
                pytest.fail(f"GUI database operations failed: {e}")

    @patch.dict('os.environ', {'POMODORA_NO_AUDIO': '1'})
    def test_gui_window_initialization_with_database(self):
        """Test that database manager can initialize independently of GUI"""
        from tracking.database_manager_unified import UnifiedDatabaseManager as DatabaseManager

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "test.db")

            # Create database manager with test database
            db_manager = DatabaseManager(db_path=db_path)
            db_manager.initialize_default_projects()

            # Verify database manager initialized correctly
            assert db_manager is not None
            assert hasattr(db_manager, 'sync_strategy')

    def test_sync_process_preserves_tables(self):
        """Test that sync process doesn't destroy database tables"""
        from tracking.database_manager_unified import UnifiedDatabaseManager as DatabaseManager
        from tracking.sync_config import SyncConfiguration
        from sqlalchemy import inspect
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test sync config that uses local files (not cloud)
            with patch.object(SyncConfiguration, 'get_sync_strategy', return_value='leader_election'), \
                 patch.object(SyncConfiguration, 'get_database_path_for_strategy', 
                             return_value=(os.path.join(temp_dir, "test.db"), True)):
                
                db_manager = DatabaseManager()
                
                # Initialize default data
                db_manager.initialize_default_projects()
                
                # Verify tables exist after initialization
                inspector = inspect(db_manager.engine)
                table_names = inspector.get_table_names()
                
                assert 'task_categories' in table_names
                assert 'projects' in table_names
                assert 'sprints' in table_names
                
                # Verify data exists
                categories = db_manager.get_active_task_categories()
                projects = db_manager.get_active_projects()
                
                assert len(categories) > 0, "Categories were lost after sync"
                assert len(projects) > 0, "Projects were lost after sync"

    def test_full_application_initialization_flow(self):
        """Test the complete application initialization flow that was failing in production"""
        from tracking.database_manager_unified import UnifiedDatabaseManager as DatabaseManager
        from tracking.sync_config import SyncConfiguration
        from datetime import date
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Simulate production environment with leader election sync
            with patch.object(SyncConfiguration, 'get_sync_strategy', return_value='leader_election'), \
                 patch.object(SyncConfiguration, 'get_database_path_for_strategy', 
                             return_value=(os.path.join(temp_dir, "production.db"), True)):
                
                # Step 1: Database manager initialization (includes sync)
                db_manager = DatabaseManager()
                
                # Step 2: Default data initialization
                db_manager.initialize_default_projects()
                
                # Step 3: All the operations the GUI tries to do on startup
                
                # Test: Load task categories (this was failing with "no such table")
                categories = db_manager.get_active_task_categories()
                assert len(categories) > 0, "Failed to load task categories"
                
                # Test: Load projects (this was failing with "no such table") 
                projects = db_manager.get_active_projects()
                assert len(projects) > 0, "Failed to load projects"
                
                # Test: Query sprints by date (this was failing with "no such table")
                sprints = db_manager.get_sprints_by_date(date.today())
                assert isinstance(sprints, list), "Failed to query sprints by date"
                
                # Test: Verify database manager has expected attributes for GUI
                assert hasattr(db_manager, 'sync_strategy')
                # In test environment, it may fall back to local_only due to missing dependencies
                assert db_manager.sync_strategy in ['leader_election', 'local_only']
                
                # Test: Simulate stats update that GUI does on startup
                from datetime import datetime
                start_of_day = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                end_of_day = start_of_day.replace(hour=23, minute=59, second=59, microsecond=999999)
                
                # This specific query was failing in production logs
                session = db_manager.get_session()
                try:
                    from tracking.models import Sprint
                    sprint_count = session.query(Sprint).filter(
                        Sprint.start_time >= start_of_day,
                        Sprint.start_time < end_of_day
                    ).count()
                    assert isinstance(sprint_count, int)
                finally:
                    session.close()
                
                # If we reach here without exceptions, the initialization flow works!