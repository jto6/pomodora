"""
Task input mixin for ModernPomodoroWindow.

Provides functionality for task description autocompletion, history navigation,
and field auto-population based on previous sprint context.
"""

from PySide6.QtWidgets import QCompleter
from PySide6.QtCore import Qt, QEvent, QStringListModel
from PySide6.QtGui import QShortcut, QKeySequence
from sqlalchemy import func

from tracking.models import Sprint
from utils.logging import debug_print, info_print, error_print


class TaskInputMixin:
    """Mixin providing task input and autocompletion functionality."""

    def setup_task_autocompletion(self):
        """Set up auto-completion for task descriptions based on recent sprints"""
        try:
            # Get recent unique task descriptions with context from database
            recent_descriptions, self.task_context = self.get_recent_task_descriptions_with_context()

            # Create completer with recent descriptions
            self.task_completer = QCompleter(recent_descriptions, self)
            self.task_completer.setCaseSensitivity(Qt.CaseInsensitive)
            self.task_completer.setFilterMode(Qt.MatchContains)
            self.task_completer.setMaxVisibleItems(10)

            # Connect completion selection to auto-populate fields
            self.task_completer.activated.connect(self.on_task_autocomplete_selected)
            # Also connect to highlighted signal as backup (fires on hover/navigation)
            self.task_completer.highlighted.connect(self.on_task_autocomplete_highlighted)

            # Set completer on task input
            self.task_input.setCompleter(self.task_completer)

            # Setup keyboard shortcuts for completion navigation
            self.setup_completion_shortcuts()

            debug_print(f"Set up auto-completion with {len(recent_descriptions)} recent task descriptions")
        except Exception as e:
            error_print(f"Error setting up task auto-completion: {e}")

    def on_task_autocomplete_selected(self, completion_text):
        """Handle autocomplete selection - auto-populate project and category fields"""
        try:
            info_print(f"AUTOCOMPLETE: Selection triggered for task: '{completion_text}'")

            # Defensive check: ensure GUI widgets are initialized
            # This should NEVER happen - if it does, there's an initialization order bug
            if not hasattr(self, 'project_combo') or not hasattr(self, 'task_category_combo'):
                error_print("=" * 80)
                error_print("CRITICAL: Autocomplete triggered before GUI widgets initialized!")
                error_print("This indicates an initialization order bug that needs investigation.")
                error_print("Stack trace will help identify the calling code:")
                import traceback
                error_print(traceback.format_stack())
                error_print("=" * 80)
                return

            if not hasattr(self, 'task_context') or not self.task_context:
                error_print("AUTOCOMPLETE: No task context available for autocomplete selection")
                return

            info_print(f"AUTOCOMPLETE: Available contexts: {list(self.task_context.keys())}")

            context = self.task_context.get(completion_text)
            if not context:
                error_print(f"AUTOCOMPLETE: No context found for task: '{completion_text}'")
                return

            info_print(f"AUTOCOMPLETE: Found context: {context}")

            # Find and select the project in the combo box
            project_id = context['project_id']
            info_print(f"AUTOCOMPLETE: Looking for project ID {project_id} in {self.project_combo.count()} items")

            project_found = False
            for i in range(self.project_combo.count()):
                item_data = self.project_combo.itemData(i)
                debug_print(f"  Project combo index {i}: itemData = {item_data}")
                if item_data == project_id:
                    self.project_combo.setCurrentIndex(i)
                    info_print(f"AUTOCOMPLETE: Auto-populated project ID: {project_id} at index {i}")
                    project_found = True
                    break

            if not project_found:
                error_print(f"AUTOCOMPLETE: Project ID {project_id} not found in combo box")

            # Find and select the task category in the combo box
            category_id = context['task_category_id']
            info_print(f"AUTOCOMPLETE: Looking for category ID {category_id} in {self.task_category_combo.count()} items")

            category_found = False
            for i in range(self.task_category_combo.count()):
                item_data = self.task_category_combo.itemData(i)
                debug_print(f"  Category combo index {i}: itemData = {item_data}")
                if item_data == category_id:
                    self.task_category_combo.setCurrentIndex(i)
                    info_print(f"AUTOCOMPLETE: Auto-populated task category ID: {category_id} at index {i}")
                    category_found = True
                    break

            if not category_found:
                error_print(f"AUTOCOMPLETE: Category ID {category_id} not found in combo box")

            if project_found and category_found:
                info_print(f"AUTOCOMPLETE: Successfully auto-populated fields for task '{completion_text}'")

        except Exception as e:
            error_print(f"AUTOCOMPLETE: Error handling autocomplete selection: {e}")

    def on_task_autocomplete_highlighted(self, completion_text):
        """Handle autocomplete highlighting - auto-populate fields on hover/navigation"""
        debug_print(f"AUTOCOMPLETE: Highlighted task: '{completion_text}'")
        # For now, just call the same handler - can differentiate behavior later if needed
        self.on_task_autocomplete_selected(completion_text)

    def populate_fields_from_task_context(self, task_description):
        """Helper method to populate project/category fields from task context"""
        try:
            # Defensive check: ensure GUI widgets are initialized
            # This should NEVER happen - if it does, there's an initialization order bug
            if not hasattr(self, 'project_combo') or not hasattr(self, 'task_category_combo'):
                error_print("=" * 80)
                error_print("CRITICAL: Field population triggered before GUI widgets initialized!")
                error_print(f"Task description: '{task_description}'")
                error_print("This indicates an initialization order bug that needs investigation.")
                error_print("Stack trace will help identify the calling code:")
                import traceback
                error_print(traceback.format_stack())
                error_print("=" * 80)
                return

            if not hasattr(self, 'task_context') or not self.task_context:
                debug_print("No task context available for field population")
                return

            context = self.task_context.get(task_description)
            if not context:
                debug_print(f"No context found for task: '{task_description}'")
                return

            # Find and select the project in the combo box
            project_id = context['project_id']
            for i in range(self.project_combo.count()):
                item_data = self.project_combo.itemData(i)
                if item_data == project_id:
                    self.project_combo.setCurrentIndex(i)
                    debug_print(f"HISTORY: Auto-populated project ID: {project_id}")
                    break

            # Find and select the task category in the combo box
            category_id = context['task_category_id']
            for i in range(self.task_category_combo.count()):
                item_data = self.task_category_combo.itemData(i)
                if item_data == category_id:
                    self.task_category_combo.setCurrentIndex(i)
                    debug_print(f"HISTORY: Auto-populated task category ID: {category_id}")
                    break

            info_print(f"HISTORY: Auto-populated fields for task '{task_description}'")

        except Exception as e:
            error_print(f"Error populating fields from task context: {e}")

    def get_recent_task_descriptions(self, limit=50):
        """Get recent unique task descriptions for auto-completion"""
        try:
            session = self.db_manager.get_session()
            try:
                # Get recent sprints ordered by start time, limited to prevent too many suggestions
                recent_sprints = session.query(Sprint.task_description).filter(
                    Sprint.task_description != None,
                    Sprint.task_description != ""
                ).order_by(Sprint.start_time.desc()).limit(limit * 2).all()  # Get extra to filter out duplicates

                # Extract unique descriptions, preserving order (most recent first)
                seen = set()
                unique_descriptions = []
                for (description,) in recent_sprints:
                    if description and description not in seen:
                        seen.add(description)
                        unique_descriptions.append(description)
                        if len(unique_descriptions) >= limit:
                            break

                debug_print(f"Found {len(unique_descriptions)} unique task descriptions")
                return unique_descriptions
            finally:
                session.close()
        except Exception as e:
            error_print(f"Error getting recent task descriptions: {e}")
            return []

    def get_recent_task_descriptions_with_context(self):
        """Get all unique task descriptions with their project and category context

        Returns all unique task descriptions ordered by most recent usage, with context
        for auto-populating project and category fields. No limit is applied since
        processing all sprints is fast and ensures all tasks are accessible.
        """
        try:
            session = self.db_manager.get_session()
            try:
                # Get ALL sprints with just IDs (no joins needed)
                all_sprints = session.query(
                    Sprint.task_description,
                    Sprint.project_id,
                    Sprint.task_category_id
                ).filter(
                    Sprint.task_description != None,
                    Sprint.task_description != ""
                ).order_by(Sprint.start_time.desc()).all()

                # Create context map: task_description -> {project_id, task_category_id}
                # Keep only the most recent occurrence of each task
                task_context = {}
                unique_descriptions = []

                for sprint in all_sprints:
                    description = sprint.task_description
                    if description and description not in task_context:
                        task_context[description] = {
                            'project_id': sprint.project_id,
                            'task_category_id': sprint.task_category_id
                        }
                        unique_descriptions.append(description)

                debug_print(f"Found {len(unique_descriptions)} unique task descriptions with context")
                return unique_descriptions, task_context
            finally:
                session.close()
        except Exception as e:
            error_print(f"Error getting task descriptions with context: {e}")
            return [], {}

    def update_task_autocompletion(self):
        """Update auto-completion list with latest task descriptions"""
        try:
            recent_descriptions, self.task_context = self.get_recent_task_descriptions_with_context()

            # Update the completer's model
            if hasattr(self, 'task_completer') and self.task_completer:
                model = QStringListModel(recent_descriptions)
                self.task_completer.setModel(model)
                debug_print(f"Updated auto-completion with {len(recent_descriptions)} descriptions")
        except Exception as e:
            error_print(f"Error updating task auto-completion: {e}")

    def setup_completion_shortcuts(self):
        """Setup keyboard shortcuts for completion navigation"""
        if not hasattr(self, 'task_completer') or not self.task_completer:
            return

        # Ctrl+N to move down in completion list (like vim/emacs)
        self.ctrl_n_shortcut = QShortcut(QKeySequence("Ctrl+N"), self.task_input)
        self.ctrl_n_shortcut.activated.connect(self.move_completer_down)

        # Ctrl+P to move up in completion list (like vim/emacs)
        self.ctrl_p_shortcut = QShortcut(QKeySequence("Ctrl+P"), self.task_input)
        self.ctrl_p_shortcut.activated.connect(self.move_completer_up)

        debug_print("Setup Ctrl+N/Ctrl+P shortcuts for completion navigation")

    def move_completer_down(self):
        """Move down in the completion popup (Ctrl+N)"""
        if not hasattr(self, 'task_completer') or not self.task_completer or not self.task_completer.popup().isVisible():
            return

        popup = self.task_completer.popup()
        current_index = popup.currentIndex()
        model = popup.model()

        # Move to next item, wrap to first if at end
        if current_index.row() < model.rowCount() - 1:
            next_index = model.index(current_index.row() + 1, 0)
        else:
            next_index = model.index(0, 0)

        popup.setCurrentIndex(next_index)
        popup.scrollTo(next_index)

    def move_completer_up(self):
        """Move up in the completion popup (Ctrl+P)"""
        if not hasattr(self, 'task_completer') or not self.task_completer or not self.task_completer.popup().isVisible():
            return

        popup = self.task_completer.popup()
        current_index = popup.currentIndex()
        model = popup.model()

        # Move to previous item, wrap to last if at beginning
        if current_index.row() > 0:
            prev_index = model.index(current_index.row() - 1, 0)
        else:
            prev_index = model.index(model.rowCount() - 1, 0)

        popup.setCurrentIndex(prev_index)
        popup.scrollTo(prev_index)

    def setup_task_history_navigation(self):
        """Setup task description history navigation with arrow keys"""
        # Initialize history tracking variables
        self.task_history = []
        self.task_history_index = -1  # -1 means no history position selected
        self.original_text = ""  # Store the original text when starting history navigation

        # Install event filter to capture key events
        self.task_input.installEventFilter(self)

        debug_print("Setup task description history navigation with up/down arrows")

    def get_task_description_history(self):
        """Get chronological task description history for navigation with all duplicates removed

        Returns unique task descriptions ordered by most recent usage, keeping only the first
        (most recent) occurrence of each task. This allows efficient navigation through your
        entire task history without seeing the same task multiple times.
        """
        try:
            session = self.db_manager.get_session()
            try:
                # Force fresh query - expire all cached objects
                session.expire_all()

                # Get ALL sprints ordered by start time (most recent first)
                # No limit - with typical sprint counts (hundreds to low thousands), this is fast
                # Use datetime() function to ensure proper datetime comparison in SQLite (handles format inconsistencies)
                all_sprints = session.query(Sprint.task_description, Sprint.start_time).filter(
                    Sprint.task_description != None,
                    Sprint.task_description != ""
                ).order_by(func.datetime(Sprint.start_time).desc()).all()

                # Debug: Show first 10 raw entries with timestamps
                if all_sprints:
                    debug_print(f"Raw history (first 10 with timestamps):")
                    for i, (desc, start_time) in enumerate(all_sprints[:10]):
                        debug_print(f"  [{i}] {start_time}: {desc}")

                # Remove ALL duplicates (not just adjacent), keeping only the most recent occurrence
                # Use a set to track what we've seen, preserving chronological order
                history = []
                seen = set()
                for desc, _ in all_sprints:
                    if desc and desc not in seen:
                        history.append(desc)
                        seen.add(desc)

                debug_print(f"Loaded {len(history)} unique task descriptions for history navigation (from {len(all_sprints)} total sprints)")
                # Debug: Show first 5 items in history
                if history:
                    debug_print(f"History order (first 5): {history[:5]}")
                return history
            finally:
                session.close()
        except Exception as e:
            error_print(f"Error getting task description history: {e}")
            return []

    def eventFilter(self, obj, event):
        """Event filter to handle arrow key navigation in task input field"""
        if obj is self.task_input:
            if event.type() == QEvent.Type.KeyPress:
                key = event.key()

                # Only handle arrow keys when not in completion mode
                if hasattr(self, 'task_completer') and self.task_completer and self.task_completer.popup().isVisible():
                    return super().eventFilter(obj, event)

                if key == Qt.Key.Key_Down:
                    self.navigate_task_history_down()
                    return True  # Consume the event
                elif key == Qt.Key.Key_Up:
                    self.navigate_task_history_up()
                    return True  # Consume the event
                elif key in (Qt.Key.Key_Escape, Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    # Reset history navigation on escape or enter
                    self.reset_task_history_navigation()
                    return super().eventFilter(obj, event)
                elif event.text() and event.text().isprintable():
                    # Reset history navigation when user starts typing
                    self.reset_task_history_navigation()
                    return super().eventFilter(obj, event)
            elif event.type() == QEvent.Type.FocusOut:
                # Reset history navigation when field loses focus (e.g., clicking Start button)
                self.reset_task_history_navigation()

        return super().eventFilter(obj, event)

    def navigate_task_history_down(self):
        """Navigate down in task history (backwards in time - older tasks)"""
        # Load history if not already loaded or if we're starting navigation
        if self.task_history_index == -1:
            # First time entering history navigation - start at most recent (index 0)
            self.task_history = self.get_task_description_history()
            if not self.task_history:
                return
            self.original_text = self.task_input.text()
            self.task_history_index = 0
        elif self.task_history_index < len(self.task_history) - 1:
            # Already in history navigation - move to next older item
            self.task_history_index += 1
        else:
            # Already at end, don't move further
            return

        # Update the input field with the selected history item
        selected_task = self.task_history[self.task_history_index]
        self.task_input.setText(selected_task)
        debug_print(f"History navigation: set text to '{selected_task}' (index {self.task_history_index})")
        # Auto-populate project/category fields from context
        self.populate_fields_from_task_context(selected_task)

    def navigate_task_history_up(self):
        """Navigate up in task history (forwards in time - newer tasks)"""
        if self.task_history_index == -1:
            # Not in history navigation mode
            return

        if self.task_history_index > 0:
            # Move to previous item in history (newer)
            self.task_history_index -= 1
            selected_task = self.task_history[self.task_history_index]
            self.task_input.setText(selected_task)
            debug_print(f"History navigation: set text to '{selected_task}' (index {self.task_history_index})")
            # Auto-populate project/category fields from context
            self.populate_fields_from_task_context(selected_task)
        else:
            # Back to original text
            self.task_input.setText(self.original_text)
            self.task_history_index = -1
            debug_print(f"History navigation: restored original text '{self.original_text}'")

    def reset_task_history_navigation(self):
        """Reset task description history navigation state"""
        self.task_history_index = -1
        self.original_text = ""
        debug_print("Reset task description history navigation")

    def refresh_task_history(self):
        """Refresh cached task history with latest data from database"""
        try:
            # Refresh if history system has been initialized (even if empty)
            if hasattr(self, 'task_history'):
                old_count = len(self.task_history)
                self.task_history = self.get_task_description_history()
                new_count = len(self.task_history)
                debug_print(f"Refreshed task history: {old_count} -> {new_count} items")

                # If we were in the middle of navigation, reset to avoid index errors
                if self.task_history_index >= new_count:
                    self.reset_task_history_navigation()
        except Exception as e:
            error_print(f"Error refreshing task history: {e}")
