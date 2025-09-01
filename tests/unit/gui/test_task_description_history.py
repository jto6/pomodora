"""
Unit tests for task description history navigation feature.

Tests the arrow key navigation functionality for task descriptions,
including history loading, adjacent duplicate removal, and navigation behavior.
"""

import pytest
import tempfile
import os
import sys
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / 'src'))

from PySide6.QtWidgets import QApplication, QLineEdit
from PySide6.QtCore import QEvent, Qt, QObject
from PySide6.QtGui import QKeyEvent

# Test imports
from tracking.database_manager_unified import UnifiedDatabaseManager as DatabaseManager
from tracking.models import Sprint, Project, TaskCategory


class MockMainWindow(QObject):
    """Mock main window class for testing history navigation in isolation"""
    
    def __init__(self, db_manager):
        super().__init__()
        self.db_manager = db_manager
        self.task_input = QLineEdit()
        
        # Initialize history navigation state
        self.task_history = []
        self.task_history_index = -1
        self.original_text = ""
        
        # Install the event filter (we'll test this separately)
        self.task_input.installEventFilter(self)
        
    def get_task_description_history(self, limit=100):
        """Get chronological task description history for navigation with adjacent duplicates removed"""
        try:
            session = self.db_manager.get_session()
            try:
                # Get recent sprints ordered by start time (most recent first)
                recent_sprints = session.query(Sprint.task_description).filter(
                    Sprint.task_description != None,
                    Sprint.task_description != ""
                ).order_by(Sprint.start_time.desc()).limit(limit).all()
                
                # Extract task descriptions and remove adjacent duplicates
                raw_history = [description for (description,) in recent_sprints if description]
                
                # Remove adjacent duplicates while preserving chronological order
                history = []
                prev_desc = None
                for desc in raw_history:
                    if desc != prev_desc:
                        history.append(desc)
                        prev_desc = desc
                
                return history
            finally:
                session.close()
        except Exception as e:
            return []

    def navigate_task_history_down(self):
        """Navigate down in task history (backwards in time - older tasks)"""
        # Load history if not already loaded or if we're starting navigation
        if self.task_history_index == -1:
            self.task_history = self.get_task_description_history()
            if not self.task_history:
                return
            self.original_text = self.task_input.text()
            self.task_history_index = 0
        else:
            # Move to next item in history (older)
            if self.task_history_index < len(self.task_history) - 1:
                self.task_history_index += 1
            else:
                # Stay at end
                return
        
        # Update the input field
        if 0 <= self.task_history_index < len(self.task_history):
            self.task_input.setText(self.task_history[self.task_history_index])

    def navigate_task_history_up(self):
        """Navigate up in task history (forwards in time - newer tasks)"""
        if self.task_history_index == -1:
            # Not in history navigation mode
            return
            
        if self.task_history_index > 0:
            # Move to previous item in history (newer)
            self.task_history_index -= 1
            self.task_input.setText(self.task_history[self.task_history_index])
        else:
            # Back to original text
            self.task_input.setText(self.original_text)
            self.task_history_index = -1

    def reset_task_history_navigation(self):
        """Reset task description history navigation state"""
        self.task_history_index = -1
        self.original_text = ""
        
    def eventFilter(self, obj, event):
        """Simplified event filter for testing"""
        if obj is self.task_input and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            
            if key == Qt.Key.Key_Down:
                self.navigate_task_history_down()
                return True
            elif key == Qt.Key.Key_Up:
                self.navigate_task_history_up()
                return True
            elif key in (Qt.Key.Key_Escape, Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.reset_task_history_navigation()
                return False
            elif event.text() and event.text().isprintable():
                self.reset_task_history_navigation()
                return False
        
        return False


class TestTaskDescriptionHistory:
    """Test suite for task description history navigation."""
    
    @pytest.fixture(autouse=True)
    def setup_method(self):
        """Set up test environment before each test"""
        # Create QApplication if it doesn't exist (needed for QLineEdit)
        if not QApplication.instance():
            self.app = QApplication([])
        
        # Create temporary database
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test.db")
        
        # Initialize database manager
        self.db_manager = DatabaseManager(db_path=self.db_path)
        
        # Create mock main window
        self.window = MockMainWindow(self.db_manager)
        
        # Create test data
        self.setup_test_data()
        
    def teardown_method(self):
        """Clean up after each test"""
        self.temp_dir.cleanup()
        
    def setup_test_data(self):
        """Create test sprints with various task descriptions"""
        session = self.db_manager.get_session()
        
        try:
            # Create test project and category
            project = Project(name="Test Project")
            session.add(project)
            session.flush()
            
            category = TaskCategory(name="Test Category")
            session.add(category)
            session.flush()
            
            # Create test sprints with task descriptions (most recent first in creation order)
            base_time = datetime.now() - timedelta(hours=5)
            
            test_sprints = [
                # Most recent (should appear first in history)
                (base_time + timedelta(hours=4, minutes=30), "Latest task description"),
                (base_time + timedelta(hours=4, minutes=20), "Duplicate task"),  # Adjacent duplicate
                (base_time + timedelta(hours=4, minutes=10), "Duplicate task"),  # Adjacent duplicate  
                (base_time + timedelta(hours=4, minutes=0), "Duplicate task"),   # Adjacent duplicate
                (base_time + timedelta(hours=3, minutes=30), "Middle task description"),
                (base_time + timedelta(hours=3, minutes=20), "Another duplicate"),  # Adjacent duplicate
                (base_time + timedelta(hours=3, minutes=10), "Another duplicate"),  # Adjacent duplicate
                (base_time + timedelta(hours=3, minutes=0), "Unique task description"),
                (base_time + timedelta(hours=2, minutes=30), "Old task description"),
                # Oldest
                (base_time + timedelta(hours=2, minutes=0), "Oldest task description"),
            ]
            
            for start_time, task_desc in test_sprints:
                sprint = Sprint(
                    project_id=project.id,
                    task_category_id=category.id,
                    task_description=task_desc,
                    start_time=start_time,
                    end_time=start_time + timedelta(minutes=25),
                    completed=True,
                    duration_minutes=25
                )
                session.add(sprint)
            
            session.commit()
            
        finally:
            session.close()

    def test_get_task_description_history_basic(self):
        """Test basic history loading functionality"""
        history = self.window.get_task_description_history()
        
        # Should have task descriptions
        assert len(history) > 0
        
        # Should be in chronological order (most recent first)
        assert history[0] == "Latest task description"
        assert history[-1] == "Oldest task description"

    def test_get_task_description_history_removes_adjacent_duplicates(self):
        """Test that adjacent duplicates are removed from history"""
        history = self.window.get_task_description_history()
        
        # Expected history without adjacent duplicates:
        # "Latest task description", "Duplicate task", "Middle task description", 
        # "Another duplicate", "Unique task description", "Old task description", "Oldest task description"
        expected_descriptions = [
            "Latest task description",
            "Duplicate task",  # Only one instance despite 3 adjacent duplicates
            "Middle task description", 
            "Another duplicate",  # Only one instance despite 2 adjacent duplicates
            "Unique task description",
            "Old task description",
            "Oldest task description"
        ]
        
        assert history == expected_descriptions
        
        # Verify we removed some duplicates
        assert len(history) == 7  # Should be 7 unique descriptions instead of 10 total

    def test_get_task_description_history_empty_database(self):
        """Test history loading with empty database"""
        # Create empty database
        temp_dir = tempfile.TemporaryDirectory()
        empty_db_path = os.path.join(temp_dir.name, "empty.db")
        empty_db_manager = DatabaseManager(db_path=empty_db_path)
        
        window = MockMainWindow(empty_db_manager)
        history = window.get_task_description_history()
        
        assert history == []
        temp_dir.cleanup()

    def test_navigate_task_history_down_basic(self):
        """Test basic down navigation through history"""
        # Start with some text in the input
        self.window.task_input.setText("Current text")
        
        # First down arrow - should load history and show first item
        self.window.navigate_task_history_down()
        
        assert self.window.task_input.text() == "Latest task description"
        assert self.window.task_history_index == 0
        assert self.window.original_text == "Current text"
        
        # Second down arrow - should show next item
        self.window.navigate_task_history_down()
        
        assert self.window.task_input.text() == "Duplicate task"
        assert self.window.task_history_index == 1

    def test_navigate_task_history_up_basic(self):
        """Test basic up navigation through history"""
        # Start navigation
        self.window.task_input.setText("Original")
        self.window.navigate_task_history_down()  # Go to first item
        self.window.navigate_task_history_down()  # Go to second item
        
        assert self.window.task_input.text() == "Duplicate task"
        assert self.window.task_history_index == 1
        
        # Up arrow - should go back to first item
        self.window.navigate_task_history_up()
        
        assert self.window.task_input.text() == "Latest task description"
        assert self.window.task_history_index == 0
        
        # Another up arrow - should restore original text
        self.window.navigate_task_history_up()
        
        assert self.window.task_input.text() == "Original"
        assert self.window.task_history_index == -1

    def test_navigate_history_bounds_checking(self):
        """Test navigation doesn't go beyond bounds"""
        history = self.window.get_task_description_history()
        history_length = len(history)
        
        # Navigate to the end
        self.window.task_input.setText("Start")
        for i in range(history_length + 2):  # Try to go beyond end
            self.window.navigate_task_history_down()
        
        # Should be at last item, not beyond
        assert self.window.task_history_index == history_length - 1
        assert self.window.task_input.text() == history[-1]
        
        # Try to go up beyond beginning
        for i in range(history_length + 2):  # Go way up
            self.window.navigate_task_history_up()
        
        # Should be back to original text
        assert self.window.task_history_index == -1
        assert self.window.task_input.text() == "Start"

    def test_reset_task_history_navigation(self):
        """Test resetting navigation state"""
        # Start navigation
        self.window.task_input.setText("Test")
        self.window.navigate_task_history_down()
        
        assert self.window.task_history_index == 0
        assert self.window.original_text == "Test"
        
        # Reset navigation
        self.window.reset_task_history_navigation()
        
        assert self.window.task_history_index == -1
        assert self.window.original_text == ""

    def test_navigate_with_empty_history(self):
        """Test navigation behavior when no history exists"""
        # Create window with empty database
        temp_dir = tempfile.TemporaryDirectory()
        empty_db_path = os.path.join(temp_dir.name, "empty.db")
        empty_db_manager = DatabaseManager(db_path=empty_db_path)
        
        window = MockMainWindow(empty_db_manager)
        window.task_input.setText("Test text")
        
        # Try to navigate down - should do nothing
        window.navigate_task_history_down()
        
        assert window.task_input.text() == "Test text"  # Unchanged
        assert window.task_history_index == -1  # Still not in navigation mode
        
        temp_dir.cleanup()

    def test_up_navigation_without_down_first(self):
        """Test up navigation when not in navigation mode"""
        self.window.task_input.setText("Test text")
        
        # Try up navigation without starting down navigation first
        self.window.navigate_task_history_up()
        
        # Should do nothing
        assert self.window.task_input.text() == "Test text"
        assert self.window.task_history_index == -1

    def test_history_limit_parameter(self):
        """Test that the limit parameter works correctly"""
        # Test with very small limit
        limited_history = self.window.get_task_description_history(limit=3)
        full_history = self.window.get_task_description_history()
        
        assert len(limited_history) <= 3
        assert len(limited_history) < len(full_history)
        
        # Should still be most recent items
        assert limited_history[0] == full_history[0]

    @patch('sys.path')  # Mock to avoid import issues in event testing
    def test_event_filter_down_key(self, mock_path):
        """Test event filter handles down arrow key"""
        # Create a mock key event for down arrow
        down_event = Mock()
        down_event.type.return_value = QEvent.Type.KeyPress
        down_event.key.return_value = Qt.Key.Key_Down
        
        self.window.task_input.setText("Original")
        
        # Mock the event filter call
        with patch.object(self.window, 'navigate_task_history_down') as mock_down:
            result = self.window.eventFilter(self.window.task_input, down_event)
            
            mock_down.assert_called_once()
            assert result is True  # Event should be consumed

    @patch('sys.path')  # Mock to avoid import issues in event testing  
    def test_event_filter_up_key(self, mock_path):
        """Test event filter handles up arrow key"""
        # Create a mock key event for up arrow
        up_event = Mock()
        up_event.type.return_value = QEvent.Type.KeyPress
        up_event.key.return_value = Qt.Key.Key_Up
        
        # Mock the event filter call
        with patch.object(self.window, 'navigate_task_history_up') as mock_up:
            result = self.window.eventFilter(self.window.task_input, up_event)
            
            mock_up.assert_called_once()
            assert result is True  # Event should be consumed

    def test_history_maintains_chronological_order(self):
        """Test that history maintains proper chronological order"""
        history = self.window.get_task_description_history()
        
        # Verify the expected order (most recent first)
        expected_order = [
            "Latest task description",      # Most recent
            "Duplicate task",               # Next (duplicates removed)
            "Middle task description",      # Middle
            "Another duplicate",            # Next (duplicates removed)
            "Unique task description",      # Older
            "Old task description",         # Older
            "Oldest task description"       # Oldest
        ]
        
        assert history == expected_order

    def test_navigation_preserves_original_text(self):
        """Test that original text is preserved during navigation"""
        original = "My original task"
        self.window.task_input.setText(original)
        
        # Navigate through some history
        self.window.navigate_task_history_down()  # First item
        self.window.navigate_task_history_down()  # Second item
        self.window.navigate_task_history_down()  # Third item
        
        # Verify we're not at original text
        assert self.window.task_input.text() != original
        
        # Navigate all the way back up
        while self.window.task_history_index != -1:
            self.window.navigate_task_history_up()
        
        # Should be back to original
        assert self.window.task_input.text() == original

    def test_adjacent_duplicates_complex_case(self):
        """Test adjacent duplicate removal with complex patterns"""
        session = self.db_manager.get_session()
        
        try:
            # Clear existing data
            session.query(Sprint).delete()
            
            # Create complex pattern with various adjacent duplicates
            project = session.query(Project).first()
            category = session.query(TaskCategory).first()
            
            base_time = datetime.now() - timedelta(hours=2)
            complex_pattern = [
                (base_time + timedelta(minutes=100), "A"),
                (base_time + timedelta(minutes=90), "A"),   # Adjacent duplicate
                (base_time + timedelta(minutes=80), "B"),
                (base_time + timedelta(minutes=70), "B"),   # Adjacent duplicate
                (base_time + timedelta(minutes=60), "B"),   # Adjacent duplicate
                (base_time + timedelta(minutes=50), "C"),
                (base_time + timedelta(minutes=40), "A"),   # Not adjacent to previous A
                (base_time + timedelta(minutes=30), "A"),   # Adjacent duplicate
                (base_time + timedelta(minutes=20), "D"),
                (base_time + timedelta(minutes=10), "D"),   # Adjacent duplicate
            ]
            
            for start_time, task_desc in complex_pattern:
                sprint = Sprint(
                    project_id=project.id,
                    task_category_id=category.id,
                    task_description=task_desc,
                    start_time=start_time,
                    end_time=start_time + timedelta(minutes=25),
                    completed=True,
                    duration_minutes=25
                )
                session.add(sprint)
            
            session.commit()
            
        finally:
            session.close()
        
        # Get history and verify adjacent duplicates are removed correctly
        history = self.window.get_task_description_history()
        
        # Expected: A, B, C, A, D (adjacent duplicates removed, non-adjacent preserved)
        expected = ["A", "B", "C", "A", "D"]
        assert history == expected