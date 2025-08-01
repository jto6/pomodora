from PySide6.QtWidgets import QCompleter, QListView
from PySide6.QtCore import Qt, QStringListModel, QObject
from PySide6.QtGui import QShortcut, QKeySequence
from utils.logging import debug_print, error_print


class TaskAutocompleteManager(QObject):
    """Manages task description auto-completion functionality"""

    def __init__(self, parent=None, db_manager=None):
        super().__init__(parent)
        self.parent_window = parent
        self.db_manager = db_manager
        self.task_completer = None
        self.task_completer_model = None
        self.ctrl_n_shortcut = None
        self.ctrl_p_shortcut = None

    def setup_task_autocomplete(self, task_input):
        """Setup auto-completion for task descriptions"""
        try:
            if not self.db_manager:
                error_print("No database manager available for auto-completion")
                return

            # Get unique task descriptions from database
            task_descriptions = self.db_manager.get_unique_task_descriptions()

            # Create string list model for completer
            self.task_completer_model = QStringListModel(task_descriptions)

            # Create and configure completer
            self.task_completer = QCompleter(self.task_completer_model)
            self.task_completer.setCaseSensitivity(Qt.CaseInsensitive)
            self.task_completer.setFilterMode(Qt.MatchContains)
            self.task_completer.setCompletionMode(QCompleter.PopupCompletion)

            # Apply theme styling to completer popup
            self.apply_completer_theme()

            # Set completer on the task input field
            task_input.setCompleter(self.task_completer)

            # Setup keyboard shortcuts for completion navigation
            self.setup_completion_shortcuts(task_input)

            debug_print(f"Auto-completion setup with {len(task_descriptions)} task descriptions")

        except Exception as e:
            error_print(f"Failed to setup task auto-completion: {e}")

    def refresh_task_autocomplete(self):
        """Refresh the auto-completion list with latest task descriptions"""
        try:
            if not self.db_manager or not self.task_completer_model:
                return

            task_descriptions = self.db_manager.get_unique_task_descriptions()
            self.task_completer_model.setStringList(task_descriptions)
            debug_print(f"Auto-completion refreshed with {len(task_descriptions)} task descriptions")
        except Exception as e:
            error_print(f"Failed to refresh task auto-completion: {e}")

    def apply_completer_theme(self, is_dark=None):
        """Apply theme styling to the completer popup"""
        if not self.task_completer:
            return

        # Determine if we should use dark theme
        if is_dark is None:
            is_dark = (hasattr(self.parent_window, 'theme_mode') and
                      (self.parent_window.theme_mode == "dark" or
                       (self.parent_window.theme_mode == "system" and
                        hasattr(self.parent_window, 'detect_system_dark_theme') and
                        self.parent_window.detect_system_dark_theme("completer"))))

        if is_dark:
            # Dark theme style for completer popup
            completer_style = """
            QListView {
                background-color: #2b2b2b;
                color: #ffffff;
                border: 1px solid #555555;
                selection-background-color: #3e5186;
                selection-color: #ffffff;
                alternate-background-color: #353535;
                outline: none;
            }
            QListView::item {
                padding: 8px;
                border-bottom: 1px solid #404040;
            }
            QListView::item:hover {
                background-color: #404040;
            }
            QListView::item:selected {
                background-color: #3e5186;
                color: #ffffff;
            }
            """
        else:
            # Light theme style for completer popup
            completer_style = """
            QListView {
                background-color: #ffffff;
                color: #000000;
                border: 1px solid #cccccc;
                selection-background-color: #0078d4;
                selection-color: #ffffff;
                alternate-background-color: #f5f5f5;
                outline: none;
            }
            QListView::item {
                padding: 8px;
                border-bottom: 1px solid #eeeeee;
            }
            QListView::item:hover {
                background-color: #e5e5e5;
            }
            QListView::item:selected {
                background-color: #0078d4;
                color: #ffffff;
            }
            """

        # Apply style to completer popup
        popup = self.task_completer.popup()
        popup.setStyleSheet(completer_style)

        debug_print(f"Applied {'dark' if is_dark else 'light'} theme to completer popup")

    def setup_completion_shortcuts(self, task_input):
        """Setup keyboard shortcuts for completion navigation"""
        if not self.task_completer:
            return

        # Ctrl+N to move down in completion list (like vim/emacs)
        self.ctrl_n_shortcut = QShortcut(QKeySequence("Ctrl+N"), task_input)
        self.ctrl_n_shortcut.activated.connect(self.move_completer_down)

        # Ctrl+P to move up in completion list (like vim/emacs)
        self.ctrl_p_shortcut = QShortcut(QKeySequence("Ctrl+P"), task_input)
        self.ctrl_p_shortcut.activated.connect(self.move_completer_up)

        debug_print("Setup Ctrl+N/Ctrl+P shortcuts for completion navigation")

    def move_completer_down(self):
        """Move down in the completion popup (Ctrl+N)"""
        if not self.task_completer or not self.task_completer.popup().isVisible():
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
        if not self.task_completer or not self.task_completer.popup().isVisible():
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