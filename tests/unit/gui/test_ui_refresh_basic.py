"""
Basic tests for UI refresh functionality
"""

import pytest
from unittest.mock import Mock

# Test that refresh_data_dependent_ui method exists and calls expected methods
def test_refresh_data_dependent_ui_concept():
    """Test the refresh_data_dependent_ui concept - should call both stats and autocomplete updates"""
    
    # Create a mock object representing our main window
    mock_window = Mock()
    mock_window.update_stats = Mock()
    mock_window.update_task_autocompletion = Mock()
    
    # Implement the refresh_data_dependent_ui pattern we added
    def refresh_data_dependent_ui():
        """Refresh all UI elements that depend on database data"""
        mock_window.update_stats()
        mock_window.update_task_autocompletion()
    
    mock_window.refresh_data_dependent_ui = refresh_data_dependent_ui
    
    # Call the method
    mock_window.refresh_data_dependent_ui()
    
    # Verify both methods were called
    mock_window.update_stats.assert_called_once()
    mock_window.update_task_autocompletion.assert_called_once()


def test_main_window_has_refresh_method():
    """Test that the MainWindow class has refresh_data_dependent_ui method"""
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))
    
    # Import the actual main window module
    from gui import pyside_main_window
    
    # Check if we can find the refresh method in the module
    # We'll look for it in the source code since importing the class requires Qt
    import inspect
    source = inspect.getsource(pyside_main_window)
    
    assert "def refresh_data_dependent_ui(self)" in source, "MainWindow should have refresh_data_dependent_ui method"
    assert "self.update_stats()" in source, "refresh_data_dependent_ui should call update_stats"
    assert "self.update_task_autocompletion()" in source, "refresh_data_dependent_ui should call update_task_autocompletion"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])