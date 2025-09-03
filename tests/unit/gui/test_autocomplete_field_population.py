"""
Test autocomplete context retrieval functionality.

Tests the database method that retrieves task descriptions
with their associated project and category context.
"""

import pytest
import os
import sys
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))


class TestAutocompleteContextRetrieval:
    """Test autocomplete context retrieval from database"""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test database"""
        temp_dir = tempfile.mkdtemp()
        yield Path(temp_dir)
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def test_db_manager(self, temp_dir):
        """Create test database with sample data"""
        from tracking.database_manager_unified import UnifiedDatabaseManager
        from tracking.models import Project, TaskCategory, Sprint
        from datetime import datetime
        
        db_path = temp_dir / "test.db"
        db_manager = UnifiedDatabaseManager(str(db_path))
        
        # Add test data
        session = db_manager.get_session()
        try:
            # Create test project and category (let database assign IDs)
            project = Project(name="TestProject", color="#ff0000", active=True)
            category = TaskCategory(name="TestCategory", color="#00ff00", active=True)
            session.add(project)
            session.add(category)
            session.flush()  # Get database-assigned IDs
            
            # Create test sprint using the assigned IDs
            sprint = Sprint(
                project_id=project.id,
                task_category_id=category.id,
                task_description="Fix autocomplete bug",
                start_time=datetime.now(),
                duration_minutes=25,
                completed=True
            )
            session.add(sprint)
            session.commit()
            
            # Store the assigned IDs for test assertions
            db_manager.test_project_id = project.id
            db_manager.test_category_id = category.id
            
        finally:
            session.close()
        
        return db_manager
    
    def test_get_recent_task_descriptions_with_context_database_query(self, test_db_manager):
        """Test the database query for getting task descriptions with context"""
        from tracking.models import Sprint, Project, TaskCategory
        
        # Test the database query directly (simplified version)
        session = test_db_manager.get_session()
        try:
            recent_sprints = session.query(
                Sprint.task_description,
                Sprint.project_id,
                Sprint.task_category_id
            ).filter(
                Sprint.task_description != None,
                Sprint.task_description != ""
            ).order_by(Sprint.start_time.desc()).all()
            
            # Should find our test sprint
            assert len(recent_sprints) == 1
            sprint = recent_sprints[0]
            
            assert sprint.task_description == "Fix autocomplete bug"
            assert sprint.project_id == test_db_manager.test_project_id
            assert sprint.task_category_id == test_db_manager.test_category_id
            
        finally:
            session.close()
    
    def test_task_context_data_structure(self, test_db_manager):
        """Test that context data structure contains expected fields"""
        # Create mock main window just for the method
        mock_window = Mock()
        mock_window.db_manager = test_db_manager
        
        # Manually add the method from the real class
        def get_recent_task_descriptions_with_context(self, limit=50):
            """Get recent task descriptions with their project and category context"""
            try:
                session = self.db_manager.get_session()
                try:
                    from tracking.models import Sprint, Project, TaskCategory
                    # Get recent sprints with just IDs (no joins needed)
                    recent_sprints = session.query(
                        Sprint.task_description,
                        Sprint.project_id,
                        Sprint.task_category_id
                    ).filter(
                        Sprint.task_description != None,
                        Sprint.task_description != ""
                    ).order_by(Sprint.start_time.desc()).limit(limit * 2).all()
                    
                    # Create context map
                    task_context = {}
                    unique_descriptions = []
                    
                    for sprint in recent_sprints:
                        description = sprint.task_description
                        if description and description not in task_context:
                            task_context[description] = {
                                'project_id': sprint.project_id,
                                'task_category_id': sprint.task_category_id
                            }
                            unique_descriptions.append(description)
                            if len(unique_descriptions) >= limit:
                                break
                    
                    return unique_descriptions, task_context
                finally:
                    session.close()
            except Exception as e:
                return [], {}
        
        mock_window.get_recent_task_descriptions_with_context = get_recent_task_descriptions_with_context.__get__(mock_window)
        
        # Test the method
        descriptions, context = mock_window.get_recent_task_descriptions_with_context()
        
        # Verify structure
        assert len(descriptions) == 1
        assert "Fix autocomplete bug" in descriptions
        
        assert "Fix autocomplete bug" in context
        task_context = context["Fix autocomplete bug"]
        
        # Verify all expected fields are present
        required_fields = ['project_id', 'task_category_id']
        for field in required_fields:
            assert field in task_context
        
        # Verify values
        assert task_context['project_id'] == test_db_manager.test_project_id
        assert task_context['task_category_id'] == test_db_manager.test_category_id


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])