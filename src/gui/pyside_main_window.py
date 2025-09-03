import sys
from datetime import datetime, timedelta
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QLabel, QPushButton, QComboBox,
                               QLineEdit, QProgressBar, QFrame, QTextEdit, QMenuBar, QMenu, QCompleter)
from PySide6.QtCore import QTimer, QTime, Qt, Signal, QStringListModel, QEvent
from PySide6.QtGui import QFont, QPalette, QColor, QIcon, QAction, QPixmap, QShortcut, QKeySequence
from PySide6.QtSvg import QSvgRenderer
from timer.pomodoro import PomodoroTimer, TimerState
from tracking.database_manager_unified import UnifiedDatabaseManager as DatabaseManager
from tracking.models import TaskCategory, Project, Sprint
from audio.alarm import play_alarm_async
from utils.logging import verbose_print, error_print, info_print, debug_print, trace_print
from utils.progress_wrapper import run_with_auto_progress

# Import the new component modules
from gui.components.theme_manager import ThemeManager
from gui.components.settings_dialog import SettingsDialog
from gui.components.activity_manager import ActivityClassificationsDialog
from gui.components.system_tray import SystemTrayManager


class ModernPomodoroWindow(QMainWindow):
    """Modern, colorful PySide6 Pomodoro timer with elegant design"""

    # Qt signals for thread-safe timer callbacks
    sprint_completed = Signal()
    break_completed = Signal()

    def __init__(self):
        super().__init__()
        # Initialize database manager using unified configuration system
        # The UnifiedDatabaseManager will handle all path and sync strategy determination
        self.db_manager = DatabaseManager()
        info_print("Database initialized")
        # Default projects/categories are initialized automatically by DatabaseManager if database is empty
        info_print("Default projects and categories checked")

        # Debug: Check existing sprints on startup
        try:
            from datetime import date
            today = date.today()
            existing_sprints = self.db_manager.get_sprints_by_date(today)
            debug_print(f"App startup: Found {len(existing_sprints)} existing sprints for today")
        except Exception as e:
            error_print(f"Error checking existing sprints: {e}")

        # Hibernation recovery: auto-complete sprints that were interrupted by system sleep
        self._recover_hibernated_sprints()
        self.pomodoro_timer = PomodoroTimer()

        # Set up timer callbacks using thread-safe signals
        self.pomodoro_timer.on_sprint_complete = self.emit_sprint_complete
        self.pomodoro_timer.on_break_complete = self.emit_break_complete

        # Connect signals to slot methods (these run on main thread)
        self.sprint_completed.connect(self.handle_sprint_complete)
        self.break_completed.connect(self.handle_break_complete)

        self.qt_timer = QTimer()
        self.qt_timer.timeout.connect(self.update_display)

        # Date checking timer to refresh stats at midnight
        self.date_timer = QTimer()
        self.date_timer.timeout.connect(self.check_date_change)
        self.date_timer.start(3600000)  # Check every hour
        self.current_date = None  # Track current date for comparison

        # Periodic sync timer - sync 1 hour after last sync when idle
        self.periodic_sync_timer = QTimer()
        self.periodic_sync_timer.setSingleShot(True)  # Single-shot timer, restarts after each sync
        self.periodic_sync_timer.timeout.connect(self.request_periodic_sync)
        self.periodic_sync_interval = 60 * 60 * 1000  # 1 hour in milliseconds
        
        # Idle detection timer - waits for user inactivity before executing sync
        self.idle_timer = QTimer()
        self.idle_timer.setSingleShot(True)  # Only trigger once per idle period
        self.idle_timer.timeout.connect(self.on_idle_timeout)
        self.idle_timeout = 10 * 60 * 1000  # 10 minutes in milliseconds
        
        # Sync state
        self.sync_requested = False  # True when periodic sync is waiting for idle period

        # Sprint tracking
        self.current_project_id = None
        self.current_task_category_id = None
        self.current_task_description = None
        self.sprint_start_time = None  # Preserve start time for completion

        # Field synchronization tracking
        self._last_project_text = ""
        self._last_category_text = ""

        # UI state
        self.compact_mode = False
        self.auto_compact_mode = True  # Auto-enter compact mode on sprint start
        self.theme_mode = "light"  # light, dark, or system
        self.normal_size = (500, 680)
        self.compact_size = (300, 180)  # Increased size for better visibility

        # Initialize theme manager
        self.theme_manager = ThemeManager(self)

        # Load and set application icon
        self.app_icon = self.load_app_icon()
        if self.app_icon:
            self.setWindowIcon(self.app_icon)

        # Initialize system tray
        self.system_tray = SystemTrayManager(self)
        self.system_tray.init_system_tray()

        self.init_ui()
        self.setup_form_validation()
        self.setup_sprint_shortcuts()
        self.create_menu_bar()
        self.load_settings()  # Load settings before applying styling
        self.apply_modern_styling()
        self.load_projects()
        self.load_task_categories()
        self.reset_ui()

        # Ensure proper initial layout geometry
        self.centralWidget().updateGeometry()
        self.update()

        # App always starts in normal mode - compact mode only activated by auto-compact or manual toggle

        # Update stats on startup - call AFTER reset_ui
        debug_print("Calling update_stats() on startup")
        self.update_stats()
        debug_print(f"Stats label text after update: '{self.stats_label.text()}'")

        # Start periodic sync system
        self.start_periodic_sync_system()

    def load_app_icon(self):
        """Load the application icon from logo.svg"""
        try:
            from pathlib import Path
            logo_path = Path(__file__).parent.parent.parent / "logo.svg"
            
            if logo_path.exists():
                # Create SVG renderer and render to pixmap
                renderer = QSvgRenderer(str(logo_path))
                if renderer.isValid():
                    pixmap = QPixmap(64, 64)  # 64x64 icon size
                    pixmap.fill(Qt.transparent)  # Transparent background
                    
                    from PySide6.QtGui import QPainter
                    painter = QPainter(pixmap)
                    renderer.render(painter)
                    painter.end()
                    
                    return QIcon(pixmap)
                else:
                    error_print("SVG renderer is not valid for logo.svg")
            else:
                error_print(f"Logo file not found at: {logo_path}")
                
        except Exception as e:
            error_print(f"Error loading app icon: {e}")
            
        return None

    def mousePressEvent(self, event):
        """Handle mouse clicks - exit compact mode on any click"""
        if self.compact_mode:
            self.toggle_compact_mode()
        
        # Reset idle timer on user activity
        self.on_user_activity()
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        """Handle key presses - reset idle timer on any key activity"""
        self.on_user_activity()
        super().keyPressEvent(event)

    def closeEvent(self, event):
        """Handle application close event to prevent segfault"""
        try:
            debug_print("Starting application cleanup...")

            # Stop Qt timer first
            if hasattr(self, 'qt_timer') and self.qt_timer:
                self.qt_timer.stop()
                info_print("Qt timer stopped")

            # Stop date checking timer
            if hasattr(self, 'date_timer') and self.date_timer:
                self.date_timer.stop()
                info_print("Date timer stopped")

            # Stop periodic sync timers
            if hasattr(self, 'periodic_sync_timer') and self.periodic_sync_timer:
                self.periodic_sync_timer.stop()
                info_print("Periodic sync timer stopped")
            if hasattr(self, 'idle_timer') and self.idle_timer:
                self.idle_timer.stop()
                info_print("Idle timer stopped")

            # Stop pomodoro timer
            if hasattr(self, 'pomodoro_timer') and self.pomodoro_timer:
                self.pomodoro_timer.stop()
                info_print("Pomodoro timer stopped")

            # Close database connections properly
            if hasattr(self, 'db_manager') and self.db_manager:
                # Check for pending changes and sync before exit
                if hasattr(self.db_manager, 'has_local_changes') and hasattr(self.db_manager, 'sync_if_changes_pending'):
                    if self.db_manager.has_local_changes():
                        info_print("Syncing pending changes before exit...")
                        try:
                            # Show brief progress dialog for exit sync
                            from PySide6.QtWidgets import QProgressDialog
                            from PySide6.QtCore import Qt
                            
                            progress = QProgressDialog("Syncing database changes...", None, 0, 0, self)
                            progress.setWindowTitle("Saving Data")
                            progress.setWindowModality(Qt.WindowModal)
                            progress.setMinimumDuration(100)  # Show immediately for exit
                            progress.setCancelButton(None)  # No cancel for exit sync
                            progress.show()
                            
                            # Process events to show the dialog
                            from PySide6.QtWidgets import QApplication
                            QApplication.processEvents()
                            
                            # Perform the sync
                            success = self.db_manager.sync_if_changes_pending()
                            
                            progress.close()
                            
                            if success:
                                info_print("Exit sync completed successfully")
                            else:
                                error_print("Exit sync failed - some changes may not be saved")
                                
                        except Exception as e:
                            error_print(f"Error during exit sync: {e}")
                    else:
                        debug_print("No pending changes to sync on exit")

                info_print("Database cleanup completed")

            # Clean up any references
            self.pomodoro_timer = None
            self.db_manager = None

            info_print("Cleanup completed successfully")
            # Accept the close event
            event.accept()
        except Exception as e:
            error_print(f"Error during cleanup: {e}")
            event.accept()

    def init_ui(self):
        """Initialize the modern UI layout"""
        self.setWindowTitle("Pomodora")
        self.setFixedSize(*self.normal_size)  # Use the defined normal size

        # Central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(5)
        main_layout.setContentsMargins(25, 25, 25, 25)

        # Header with app title
        self.create_header(main_layout)

        # Timer display section with integrated progress bar
        self.create_timer_section(main_layout)

        # Project and task input
        self.create_input_section(main_layout)

        # Control buttons
        self.create_control_section(main_layout)

        # Status and stats
        self.create_status_section(main_layout)

    def create_header(self, layout):
        """Create modern header with app title"""
        header_frame = QFrame()
        header_frame.setObjectName("headerFrame")
        header_layout = QHBoxLayout(header_frame)

        # Create title with icon
        title_layout = QHBoxLayout()
        
        # Add icon if available
        if hasattr(self, 'app_icon') and self.app_icon:
            icon_label = QLabel()
            icon_pixmap = self.app_icon.pixmap(32, 32)  # 32x32 for header
            icon_label.setPixmap(icon_pixmap)
            title_layout.addWidget(icon_label)
        
        title_label = QLabel("Pomodora")
        title_label.setObjectName("titleLabel")
        title_layout.addWidget(title_label)
        
        # Center the title layout
        header_layout.addStretch()
        header_layout.addLayout(title_layout)
        header_layout.addStretch()

        layout.addWidget(header_frame)

    def create_timer_section(self, layout):
        """Create the main timer display with integrated progress bar"""
        timer_frame = QFrame()
        timer_frame.setObjectName("timerFrame")
        timer_frame.setFrameStyle(QFrame.StyledPanel)  # Ensure proper frame boundaries
        timer_layout = QVBoxLayout(timer_frame)
        timer_layout.setAlignment(Qt.AlignCenter)
        timer_layout.setSpacing(10)
        timer_layout.setContentsMargins(11, 11, 11, 11)

        # Timer display
        self.time_label = QLabel("25:00")
        self.time_label.setObjectName("timeLabel")
        self.time_label.setAlignment(Qt.AlignCenter)

        # Timer state label
        self.state_label = QLabel("Ready to Focus")
        self.state_label.setObjectName("stateLabel")
        self.state_label.setAlignment(Qt.AlignCenter)

        # Progress bar integrated into timer section
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("progressBar")
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setVisible(True)  # Ensure it's visible

        # Create compact control buttons (initially hidden)
        self.compact_controls_frame = QFrame()
        self.compact_controls_frame.setObjectName("compactControlsFrame")
        compact_controls_layout = QHBoxLayout(self.compact_controls_frame)
        compact_controls_layout.setSpacing(8)  # Smaller spacing for compact mode
        compact_controls_layout.setContentsMargins(5, 5, 5, 5)

        # Compact Start/Pause button
        self.compact_start_button = QPushButton("Start")
        self.compact_start_button.setObjectName("compactStartButton")
        self.compact_start_button.clicked.connect(self.toggle_timer)
        self.compact_start_button.setFixedSize(60, 24)  # Smaller size for compact mode

        # Compact Stop button
        self.compact_stop_button = QPushButton("Stop")
        self.compact_stop_button.setObjectName("compactStopButton")
        self.compact_stop_button.clicked.connect(self.stop_timer)
        self.compact_stop_button.setEnabled(False)
        self.compact_stop_button.setFixedSize(50, 24)  # Smaller size for compact mode

        # Compact Complete button
        self.compact_complete_button = QPushButton("Done")
        self.compact_complete_button.setObjectName("compactCompleteButton")
        self.compact_complete_button.clicked.connect(self.complete_sprint)
        self.compact_complete_button.setEnabled(False)
        self.compact_complete_button.setFixedSize(50, 24)  # Smaller size for compact mode

        compact_controls_layout.addWidget(self.compact_start_button)
        compact_controls_layout.addWidget(self.compact_stop_button)
        compact_controls_layout.addWidget(self.compact_complete_button)

        # Add to timer layout
        timer_layout.addWidget(self.time_label)
        timer_layout.addWidget(self.state_label)
        timer_layout.addWidget(self.progress_bar)
        timer_layout.addWidget(self.compact_controls_frame)

        # Hide compact controls initially (only shown in compact mode)
        self.compact_controls_frame.hide()

        layout.addWidget(timer_frame)

    def sync_compact_buttons(self):
        """Synchronize compact button states with main control buttons"""
        # In compact mode, only show controls for active sprints
        main_text = self.start_button.text()
        timer_state = self.pomodoro_timer.get_state()

        # Sync complete button text with main button
        self.compact_complete_button.setText(self.complete_button.text())

        if "Start" in main_text and timer_state == TimerState.STOPPED:
            # Hide start button in compact mode - user needs to use main interface to start new sprints
            self.compact_start_button.hide()
            self.compact_stop_button.setEnabled(False)
            self.compact_complete_button.setEnabled(False)
        elif "Start" in main_text and timer_state == TimerState.BREAK:
            # During break - show all buttons, enable start and complete, disable stop
            self.compact_start_button.show()
            self.compact_start_button.setText("Start")
            self.compact_start_button.setEnabled(True)
            self.compact_stop_button.setEnabled(False)  # No need to stop during break
            self.compact_complete_button.setEnabled(True)
        elif "Pause" in main_text:
            self.compact_start_button.show()
            self.compact_start_button.setText("Pause")
            self.compact_start_button.setEnabled(True)
            self.compact_stop_button.setEnabled(True)
            self.compact_complete_button.setEnabled(True)
        elif "Resume" in main_text:
            self.compact_start_button.show()
            self.compact_start_button.setText("Resume")
            self.compact_start_button.setEnabled(True)
            self.compact_stop_button.setEnabled(True)
            self.compact_complete_button.setEnabled(True)


    def create_input_section(self, layout):
        """Create project and task input section"""
        input_frame = QFrame()
        input_frame.setObjectName("inputFrame")
        input_frame.setFrameStyle(QFrame.StyledPanel)  # Ensure proper frame boundaries
        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(15, 15, 15, 15)
        input_layout.setSpacing(15)

        # Project selection
        project_layout = QHBoxLayout()
        project_layout.setSpacing(20)  # Add spacing between label and input
        project_label = QLabel("Project:")
        project_label.setObjectName("inputLabel")
        project_label.setFixedWidth(80)  # Fixed width for label
        self.project_combo = QComboBox()
        self.project_combo.setObjectName("projectCombo")
        self.project_combo.setFixedWidth(250)  # Narrower combo box
        self.project_combo.currentTextChanged.connect(self.on_project_changed)
        project_layout.addWidget(project_label)
        project_layout.addWidget(self.project_combo)
        project_layout.addStretch()  # Push everything to the left

        # Task Category selection
        category_layout = QHBoxLayout()
        category_layout.setSpacing(20)  # Add spacing between label and input
        category_label = QLabel("Category:")
        category_label.setObjectName("inputLabel")
        category_label.setFixedWidth(80)  # Fixed width for label
        self.task_category_combo = QComboBox()
        self.task_category_combo.setObjectName("taskCategoryCombo")
        self.task_category_combo.setFixedWidth(250)  # Narrower combo box
        self.task_category_combo.currentTextChanged.connect(self.on_category_changed)
        category_layout.addWidget(category_label)
        category_layout.addWidget(self.task_category_combo)
        category_layout.addStretch()  # Push everything to the left

        # Task input
        task_layout = QHBoxLayout()
        task_layout.setSpacing(20)  # Add spacing between label and input
        task_label = QLabel("Task:")
        task_label.setObjectName("inputLabel")
        task_label.setFixedWidth(80)  # Fixed width for label
        self.task_input = QLineEdit()
        self.task_input.setObjectName("taskInput")
        self.task_input.setPlaceholderText("What are you working on?")
        self.task_input.setFixedWidth(250)  # Narrower input box
        
        # Set up auto-completion for task descriptions
        self.setup_task_autocompletion()
        
        # Set up task description history navigation
        self.setup_task_history_navigation()
        
        task_layout.addWidget(task_label)
        task_layout.addWidget(self.task_input)
        task_layout.addStretch()  # Push everything to the left

        input_layout.addLayout(project_layout)
        input_layout.addLayout(category_layout)
        input_layout.addLayout(task_layout)
        layout.addWidget(input_frame)

    def create_control_section(self, layout):
        """Create control buttons section"""
        control_frame = QFrame()
        control_frame.setObjectName("controlFrame")
        control_layout = QHBoxLayout(control_frame)
        control_layout.setSpacing(15)

        # Start/Pause button
        self.start_button = QPushButton("Start Sprint")
        self.start_button.setObjectName("startButton")
        self.start_button.clicked.connect(self.toggle_timer)

        # Stop button
        self.stop_button = QPushButton("Stop")
        self.stop_button.setObjectName("stopButton")
        self.stop_button.clicked.connect(self.stop_timer)
        self.stop_button.setEnabled(False)

        # Complete button
        self.complete_button = QPushButton("Complete Sprint")
        self.complete_button.setObjectName("completeButton")
        self.complete_button.clicked.connect(self.complete_sprint)
        self.complete_button.setEnabled(False)

        control_layout.addWidget(self.start_button)
        control_layout.addWidget(self.stop_button)
        control_layout.addWidget(self.complete_button)
        layout.addWidget(control_frame)

    def create_status_section(self, layout):
        """Create status and statistics section"""
        status_frame = QFrame()
        status_frame.setObjectName("statusFrame")
        status_layout = QVBoxLayout(status_frame)

        # Today's stats
        self.stats_label = QLabel("Today: 0 sprints completed")
        self.stats_label.setObjectName("statsLabel")
        self.stats_label.setAlignment(Qt.AlignCenter)

        status_layout.addWidget(self.stats_label)
        layout.addWidget(status_frame)

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
            if not hasattr(self, 'task_context') or not self.task_context:
                debug_print("No task context available for autocomplete selection")
                return
            
            context = self.task_context.get(completion_text)
            if not context:
                debug_print(f"No context found for task: '{completion_text}'")
                return
            
            # Find and select the project in the combo box
            project_id = context['project_id']
            for i in range(self.project_combo.count()):
                item_data = self.project_combo.itemData(i)
                if item_data == project_id:
                    self.project_combo.setCurrentIndex(i)
                    debug_print(f"Auto-populated project ID: {project_id}")
                    break
            
            # Find and select the task category in the combo box
            category_id = context['task_category_id']
            for i in range(self.task_category_combo.count()):
                item_data = self.task_category_combo.itemData(i)
                if item_data == category_id:
                    self.task_category_combo.setCurrentIndex(i)
                    debug_print(f"Auto-populated task category ID: {category_id}")
                    break
            
            info_print(f"Auto-populated fields for task '{completion_text}' with project ID {project_id}, category ID {category_id}")
            
        except Exception as e:
            error_print(f"Error handling autocomplete selection: {e}")

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

    def get_recent_task_descriptions_with_context(self, limit=50):
        """Get recent task descriptions with their project and category context"""
        try:
            session = self.db_manager.get_session()
            try:
                # Get recent sprints with just IDs (no joins needed)
                recent_sprints = session.query(
                    Sprint.task_description,
                    Sprint.project_id,
                    Sprint.task_category_id
                ).filter(
                    Sprint.task_description != None,
                    Sprint.task_description != ""
                ).order_by(Sprint.start_time.desc()).limit(limit * 2).all()  # Get extra to filter duplicates
                
                # Create context map: task_description -> {project_id, task_category_id}
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
                
                debug_print(f"Loaded {len(history)} unique task descriptions for history navigation (removed {len(raw_history) - len(history)} adjacent duplicates)")
                return history
            finally:
                session.close()
        except Exception as e:
            error_print(f"Error getting task description history: {e}")
            return []

    def eventFilter(self, obj, event):
        """Event filter to handle arrow key navigation in task input field"""
        if obj is self.task_input and event.type() == QEvent.Type.KeyPress:
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
        
        return super().eventFilter(obj, event)

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
                # Wrap to beginning or stay at end
                return
        
        # Update the input field
        if 0 <= self.task_history_index < len(self.task_history):
            self.task_input.setText(self.task_history[self.task_history_index])
            debug_print(f"History navigation: set text to '{self.task_history[self.task_history_index]}' (index {self.task_history_index})")

    def navigate_task_history_up(self):
        """Navigate up in task history (forwards in time - newer tasks)"""
        if self.task_history_index == -1:
            # Not in history navigation mode
            return
            
        if self.task_history_index > 0:
            # Move to previous item in history (newer)
            self.task_history_index -= 1
            self.task_input.setText(self.task_history[self.task_history_index])
            debug_print(f"History navigation: set text to '{self.task_history[self.task_history_index]}' (index {self.task_history_index})")
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

    def setup_sprint_shortcuts(self):
        """Setup keyboard shortcuts for sprint operations"""
        # Ctrl+S to start/pause sprint
        self.ctrl_s_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        self.ctrl_s_shortcut.activated.connect(self.toggle_timer)

        # Ctrl+C to complete sprint
        self.ctrl_c_shortcut = QShortcut(QKeySequence("Ctrl+C"), self)
        self.ctrl_c_shortcut.activated.connect(self.complete_sprint)

        debug_print("Setup Ctrl+S/Ctrl+C shortcuts for sprint operations")

    def setup_form_validation(self):
        """Set up form validation to enable/disable start button based on task description"""
        # Connect text change event to validation
        self.task_input.textChanged.connect(self.validate_form)
        
        # Perform initial validation
        self.validate_form()
        
    def validate_form(self):
        """Validate form and enable/disable start button based on task description"""
        # Only validate if timer is stopped (don't interfere with running timer)
        if self.pomodoro_timer.get_state() == TimerState.STOPPED:
            task_description = self.task_input.text().strip()
            has_description = bool(task_description)
            
            # Update start button state
            self.start_button.setEnabled(has_description)
            self.compact_start_button.setEnabled(has_description)
            
            debug_print(f"Form validation: task='{task_description}', enabled={has_description}")

    def create_menu_bar(self):
        """Create menu bar with all application features"""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu('File')

        export_action = QAction('Export to Excel...', self)
        export_action.triggered.connect(self.export_to_excel)
        file_menu.addAction(export_action)

        view_data_action = QAction('View Data...', self)
        view_data_action.triggered.connect(self.open_data_viewer)
        file_menu.addAction(view_data_action)

        file_menu.addSeparator()

        # Add sync option if using leader election sync
        if self.db_manager.sync_strategy == 'leader_election':
            sync_action = QAction('Manual Sync...', self)
            sync_action.triggered.connect(self.manual_sync)
            file_menu.addAction(sync_action)
            file_menu.addSeparator()

        quit_action = QAction('Quit', self)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # View menu
        view_menu = menubar.addMenu('View')

        self.compact_action = QAction('Toggle Compact Mode', self)
        self.compact_action.triggered.connect(self.toggle_compact_mode)
        view_menu.addAction(self.compact_action)

        # Tools menu
        tools_menu = menubar.addMenu('Tools')

        projects_action = QAction('Activity Classifications...', self)
        projects_action.triggered.connect(self.manage_activity_classifications)
        tools_menu.addAction(projects_action)

        settings_action = QAction('Settings...', self)
        settings_action.triggered.connect(self.open_settings)
        tools_menu.addAction(settings_action)

    def load_settings(self):
        """Load saved settings from local config file"""
        from tracking.local_settings import get_local_settings
        settings = get_local_settings()

        # Load theme setting
        self.theme_mode = settings.get("theme_mode", "light")

        # Load timer durations
        sprint_duration = settings.get("sprint_duration", 25)
        break_duration = settings.get("break_duration", 5)

        # Apply timer durations
        self.pomodoro_timer.set_durations(sprint_duration, break_duration)

        # Load UI state
        self.auto_compact_mode = settings.get("auto_compact_mode", True)
        # Note: compact_mode is not loaded from settings - app always starts in normal mode

    def apply_modern_styling(self, context="startup"):
        """Apply modern, colorful styling based on current mode"""
        self.theme_manager.apply_styling(context)

    def apply_dialog_styling(self, dialog):
        """Apply current theme styling to a dialog"""
        self.theme_manager.apply_dialog_styling(dialog)

    def apply_compact_styling(self):
        """Apply compact mode styling based on current theme"""
        self.theme_manager.apply_compact_styling()

    def load_projects(self):
        """Load projects into dropdown with default projects at top, then divider, then manual projects"""
        def do_load():
            try:
                # Get both task categories and projects  
                task_categories = self.db_manager.get_active_task_categories()
                projects = self.db_manager.get_active_projects()
                self.project_combo.clear()
                debug_print(f"Found {len(task_categories)} active task categories and {len(projects)} active projects")

                # Create set of task category names for quick lookup
                category_names = {tc['name'] for tc in task_categories}
                
                # Separate default projects (those with matching category names) from manual projects
                default_projects = []
                manual_projects = []
                
                for project in projects:
                    if project['name'] in category_names:
                        default_projects.append(project)
                    else:
                        manual_projects.append(project)

                # Sort both groups alphabetically
                default_projects = sorted(default_projects, key=lambda p: p['name'].lower())
                manual_projects = sorted(manual_projects, key=lambda p: p['name'].lower())

                debug_print(f"Found {len(default_projects)} default projects and {len(manual_projects)} manual projects")

                # Add default projects first
                for project in default_projects:
                    display_name = project['name']
                    debug_print(f"Adding default project: {display_name}")
                    trace_print(f"Project details: ID={project['id']}, Color={project['color']}, Active={project['active']}")
                    self.project_combo.addItem(display_name, project['id'])

                # Add divider if we have both default and manual projects
                if default_projects and manual_projects:
                    self.project_combo.insertSeparator(len(default_projects))
                    debug_print("Added separator between default and manual projects")

                # Add manual projects after the divider
                for project in manual_projects:
                    display_name = project['name']
                    debug_print(f"Adding manual project: {display_name}")
                    trace_print(f"Project details: ID={project['id']}, Color={project['color']}, Active={project['active']}")
                    self.project_combo.addItem(display_name, project['id'])

                # Handle case where no projects exist
                if not projects:
                    error_print("No projects found - database may be corrupted or misconfigured")
                    projects = []
                    category_names = {tc['name'] for tc in task_categories}
                    
                    # Re-separate and sort
                    default_projects = []
                    manual_projects = []
                    for project in projects:
                        if project['name'] in category_names:
                            default_projects.append(project)
                        else:
                            manual_projects.append(project)
                    
                    default_projects = sorted(default_projects, key=lambda p: p['name'].lower())
                    manual_projects = sorted(manual_projects, key=lambda p: p['name'].lower())
                    
                    # Add default projects
                    for project in default_projects:
                        display_name = project['name']
                        self.project_combo.addItem(display_name, project['id'])
                    
                    # Add divider if needed
                    if default_projects and manual_projects:
                        self.project_combo.insertSeparator(len(default_projects))
                    
                    # Add manual projects
                    for project in manual_projects:
                        display_name = project['name']
                        self.project_combo.addItem(display_name, project['id'])

                debug_print(f"Project combo has {self.project_combo.count()} items (including separator if present)")

                # Set default selection to "None" project if available, otherwise first project
                none_project_index = -1
                for i in range(self.project_combo.count()):
                    if self.project_combo.itemText(i) == "None":
                        none_project_index = i
                        break
                
                if none_project_index >= 0:
                    self.project_combo.setCurrentIndex(none_project_index)
                    debug_print(f"Set default project selection to 'None': (ID: {self.project_combo.currentData()})")
                elif self.project_combo.count() > 0:
                    self.project_combo.setCurrentIndex(0)
                    debug_print(f"No 'None' project found, using first project: {self.project_combo.currentText()} (ID: {self.project_combo.currentData()})")
                
                # Initialize tracking variable
                if self.project_combo.count() > 0:
                    self._last_project_text = self.project_combo.currentText()
            except Exception as e:
                error_print(f"Error loading projects: {e}")
                import traceback
                traceback.print_exc()
                # Add fallback option
                self.project_combo.addItem("Default Project", 1)
        
        # For fast operations, just run directly. For slow ones, run with progress
        try:
            # Most project loading is fast, but with progress wrapper it will automatically show progress if > 1s
            run_with_auto_progress(do_load, "Loading Projects", self, min_duration=1.0)
        except Exception:
            # Fallback to direct execution if progress wrapper fails
            do_load()

    def load_task_categories(self):
        """Load task categories from database"""
        def do_load():
            try:
                task_categories = self.db_manager.get_active_task_categories()
                self.task_category_combo.clear()
                debug_print(f"Found {len(task_categories)} active task categories")

                # Sort task categories alphabetically by name
                task_categories = sorted(task_categories, key=lambda tc: tc['name'].lower())

                for task_category in task_categories:
                    display_name = task_category['name']
                    debug_print(f"Adding task category: {display_name}")
                    trace_print(f"Task Category details: ID={task_category['id']}, Color={task_category['color']}, Active={task_category['active']}")
                    self.task_category_combo.addItem(display_name, task_category['id'])

                if not task_categories:
                    error_print("No task categories found - database may be corrupted or misconfigured")
                    task_categories = []
                    # Sort task categories alphabetically by name
                    task_categories = sorted(task_categories, key=lambda tc: tc['name'].lower())
                    for task_category in task_categories:
                        display_name = task_category['name']
                        self.task_category_combo.addItem(display_name, task_category['id'])

                debug_print(f"Task category combo has {self.task_category_combo.count()} items")

                # Set default selection to first task category if available
                if self.task_category_combo.count() > 0:
                    self.task_category_combo.setCurrentIndex(0)
                    debug_print(f"Set default task category selection: {self.task_category_combo.currentText()} (ID: {self.task_category_combo.currentData()})")
                    # Initialize tracking variable
                    self._last_category_text = self.task_category_combo.currentText()
            except Exception as e:
                error_print(f"Error loading task categories: {e}")
                import traceback
                traceback.print_exc()
                # Add fallback option
                self.task_category_combo.addItem("Default Task Category", 1)
        
        # Use progress wrapper for automatic progress display
        try:
            run_with_auto_progress(do_load, "Loading Task Categories", self, min_duration=1.0)
        except Exception:
            # Fallback to direct execution if progress wrapper fails
            do_load()

    def toggle_timer(self):
        """Start or pause the timer"""
        debug_print(f"Toggle timer called, current state: {self.pomodoro_timer.state}")
        trace_print(f"Timer remaining: {self.pomodoro_timer.get_time_remaining()}s, Task: {self.current_task_description}")

        if self.pomodoro_timer.state == TimerState.STOPPED:
            # Validate task description before starting
            task_description = self.task_input.text().strip()
            if not task_description:
                debug_print("Cannot start sprint: Task description is required")
                return
            
            # Start new sprint
            self.current_project_id = self.project_combo.currentData()
            self.current_task_category_id = self.task_category_combo.currentData()
            self.current_task_description = task_description

            self.pomodoro_timer.start_sprint()
            self.sprint_start_time = self.pomodoro_timer.start_time  # Preserve for completion
            debug_print(f"Sprint started - Project ID: {self.current_project_id}, Task Category ID: {self.current_task_category_id}, Task: '{self.current_task_description}', Start time: {self.sprint_start_time}")
            self.qt_timer.start(1000)  # Update every second
            self.start_button.setText("Pause")
            self.stop_button.setEnabled(True)
            self.complete_button.setEnabled(True)  # Enable complete button during timer
            self.sync_compact_buttons()  # Sync compact button states
            self.state_label.setText("Focus Time! 🎯")

            # Auto-enter compact mode if enabled
            if self.auto_compact_mode and not self.compact_mode:
                self.toggle_compact_mode()

        elif self.pomodoro_timer.state == TimerState.RUNNING:
            # Pause
            debug_print("Pausing timer")
            remaining_before = self.pomodoro_timer.get_time_remaining()
            debug_print(f"Time remaining before pause: {remaining_before}")
            self.pomodoro_timer.pause()
            self.qt_timer.stop()
            self.start_button.setText("Resume")
            self.sync_compact_buttons()  # Sync compact button states
            self.state_label.setText("Paused ⏸️")

        elif self.pomodoro_timer.state == TimerState.PAUSED:
            # Resume
            debug_print("Resuming timer")
            remaining_before = self.pomodoro_timer.get_time_remaining()
            debug_print(f"Time remaining before resume: {remaining_before}")
            self.pomodoro_timer.resume()
            self.qt_timer.start(1000)
            self.start_button.setText("Pause")
            self.complete_button.setEnabled(True)  # Keep complete button enabled
            self.sync_compact_buttons()  # Sync compact button states
            self.state_label.setText("Focus Time! 🎯")
            remaining_after = self.pomodoro_timer.get_time_remaining()
            debug_print(f"Time remaining after resume: {remaining_after}")

            # Auto-enter compact mode if enabled
            if self.auto_compact_mode and not self.compact_mode:
                self.toggle_compact_mode()

        elif self.pomodoro_timer.state == TimerState.BREAK:
            # During break - complete current sprint first, then start new sprint
            debug_print("Ending break early - completing current sprint and starting new one")
            
            # Save the previous sprint parameters before completing
            prev_project_id = self.current_project_id
            prev_task_category_id = self.current_task_category_id
            prev_task_description = self.current_task_description
            
            # Complete the current sprint first (uses the original sprint parameters)
            self.complete_sprint()
            
            # Now start new sprint with the SAME parameters as the just-completed sprint
            self.current_project_id = prev_project_id
            self.current_task_category_id = prev_task_category_id
            self.current_task_description = prev_task_description

            debug_print(f"New sprint started with same parameters - Project ID: {self.current_project_id}, Task Category ID: {self.current_task_category_id}, Task: '{self.current_task_description}'")
            self.pomodoro_timer.start_sprint()
            self.sprint_start_time = self.pomodoro_timer.start_time  # Preserve for completion
            self.qt_timer.start(1000)
            self.start_button.setText("Pause")
            self.stop_button.setEnabled(True)
            self.complete_button.setEnabled(True)
            self.sync_compact_buttons()  # Sync compact button states
            self.state_label.setText("Focus Time! 🎯")

            # Auto-enter compact mode if enabled
            if self.auto_compact_mode and not self.compact_mode:
                self.toggle_compact_mode()

    def stop_timer(self):
        """Stop the current timer"""
        # If stopping during break, complete the sprint first
        if self.pomodoro_timer.get_state() == TimerState.BREAK:
            debug_print("Stopping during break - completing sprint first")
            self.complete_sprint()
        
        self.pomodoro_timer.stop()
        self.qt_timer.stop()
        self.reset_ui()
        
        # Exit compact mode when stopping timer
        if self.compact_mode:
            self.toggle_compact_mode()

    def emit_sprint_complete(self):
        """Thread-safe method called from background timer thread"""
        # Capture critical sprint data immediately to avoid race conditions
        sprint_data = {
            'project_id': self.current_project_id,
            'task_category_id': self.current_task_category_id, 
            'task_description': self.current_task_description,
            'start_time': self.sprint_start_time
        }
        
        # Only emit signal if we have valid sprint data
        if (sprint_data['project_id'] and sprint_data['task_category_id'] and 
            sprint_data['task_description'] and sprint_data['start_time']):
            # Store the captured data temporarily
            self._pending_sprint_data = sprint_data
            self.sprint_completed.emit()
        else:
            debug_print(f"Sprint completion skipped - invalid data: {sprint_data}")

    def handle_sprint_complete(self):
        """Main thread handler for sprint completion"""
        info_print("Sprint completed - playing alarm and starting break")

        # Auto-save sprint to database when timer completes
        # This ensures sprints are saved even after hibernation resume
        # Use captured sprint data to avoid race conditions
        if hasattr(self, '_pending_sprint_data') and self._pending_sprint_data:
            try:
                debug_print("Auto-saving sprint on timer completion using captured data")
                self._save_sprint_with_data(self._pending_sprint_data)
                info_print("✓ Sprint auto-saved on timer completion")
                # Clear the pending data
                delattr(self, '_pending_sprint_data')
            except Exception as e:
                error_print(f"Failed to auto-save sprint on timer completion: {e}")
        else:
            error_print("No pending sprint data available for auto-save")

        # Get alarm settings
        from tracking.local_settings import get_local_settings
        settings = get_local_settings()
        volume = settings.get("alarm_volume", 0.7)
        sprint_alarm = settings.get("sprint_alarm", "gentle_chime")

        # Play sprint completion alarm
        from audio.alarm import play_alarm_sound
        import threading

        def play_alarm():
            try:
                play_alarm_sound(sprint_alarm, volume)
            except Exception as e:
                print(f"Sprint alarm error: {e}")

        # Play in separate thread to avoid blocking UI
        thread = threading.Thread(target=play_alarm, daemon=True)
        thread.start()

        # Update UI to show break state - need to refresh button states
        self.refresh_ui_state()
        self.sync_compact_buttons()  # Ensure compact buttons match main window state

    def emit_break_complete(self):
        """Thread-safe method called from background timer thread"""
        self.break_completed.emit()

    def handle_break_complete(self):
        """Main thread handler for break completion"""
        info_print("Break completed - playing alarm and auto-completing sprint")

        # Get alarm settings
        from tracking.local_settings import get_local_settings
        settings = get_local_settings()
        volume = settings.get("alarm_volume", 0.7)
        break_alarm = settings.get("break_alarm", "urgent_alert")

        # Play break completion alarm
        from audio.alarm import play_alarm_sound
        import threading

        def play_alarm():
            try:
                play_alarm_sound(break_alarm, volume)
            except Exception as e:
                print(f"Break alarm error: {e}")

        # Play in separate thread to avoid blocking UI
        thread = threading.Thread(target=play_alarm, daemon=True)
        thread.start()

        # Sprint was already saved during timer completion, just reset UI
        self.pomodoro_timer.stop()
        self.qt_timer.stop()
        self.reset_ui()
        self.state_label.setText("Sprint Completed! 🎉")
        self.refresh_data_dependent_ui()
        
        # Clear preserved sprint start time after successful completion
        self.sprint_start_time = None
        debug_print("Break completed - sprint already saved, UI reset")

    def complete_sprint(self):
        """Complete the current sprint"""
        debug_print("Complete sprint called!")
        debug_print(f"Current project_id: {self.current_project_id}")
        debug_print(f"Current task_description: '{self.current_task_description}'")
        debug_print(f"Timer state: {self.pomodoro_timer.get_state()}")
        debug_print(f"Timer remaining: {self.pomodoro_timer.get_time_remaining()}")

        try:
            # Check timer state to determine action
            timer_state = self.pomodoro_timer.get_state()
            
            if timer_state == TimerState.RUNNING:
                # Sprint is still running - save it and stop timer
                if self.current_project_id is not None:
                    debug_print(f"✓ Manual sprint completion during timer - saving sprint: {self.current_task_description} for project {self.current_project_id}")

                    # Get project name from ID
                    project = self.db_manager.get_project_by_id(self.current_project_id)
                    project_name = project.name if project else "Unknown"
                    debug_print(f"Project name resolved: {project_name}")

                    # Use the shared sprint saving logic
                    self._save_current_sprint()
                    info_print("✓ Sprint saved to database successfully")
                else:
                    error_print(f"❌ Cannot save sprint - no project selected (project_id: {self.current_project_id})")
                    
            elif timer_state == TimerState.BREAK:
                # During break - sprint already auto-saved, just reset UI
                debug_print("During break - sprint already saved, just resetting UI")
                info_print("✓ Break ended - returning to ready state")
            else:
                debug_print(f"Complete sprint called in unexpected state: {timer_state}")
                info_print("✓ Returning to ready state")

            # Update auto-completion and stats (if sprint was saved)
            if timer_state == TimerState.RUNNING:
                # Verify it was saved
                from datetime import date
                today_sprints = self.db_manager.get_sprints_by_date(date.today())
                debug_print(f"Verification: {len(today_sprints)} sprints now in database for today")

                # Refresh UI to include the new task description
                self.refresh_data_dependent_ui()

            self.pomodoro_timer.stop()
            self.qt_timer.stop()
            self.reset_ui()
            self.state_label.setText("Sprint Completed! 🎉")
            self.refresh_data_dependent_ui()
            
            # Clear preserved sprint start time after successful completion
            self.sprint_start_time = None
            debug_print("Sprint completion finished")
            
            # Note: Stay in compact mode after sprint completion
            # User must click or manually toggle to exit compact mode
        except Exception as e:
            error_print(f"Error completing sprint: {e}")
            import traceback
            traceback.print_exc()  # Full error trace
            self.pomodoro_timer.stop()
            self.qt_timer.stop()
            self.reset_ui()
            
            # Clear preserved sprint start time even on error
            self.sprint_start_time = None
            
            # Exit compact mode even when there's an error
            if self.compact_mode:
                self.toggle_compact_mode()

    def update_display(self):
        """Update the timer display"""
        remaining = self.pomodoro_timer.get_time_remaining()
        state = self.pomodoro_timer.get_state()

        # Update time display
        minutes = remaining // 60
        seconds = remaining % 60
        self.time_label.setText(f"{minutes:02d}:{seconds:02d}")

        # Update progress bar based on current state
        if state == TimerState.RUNNING:
            total = self.pomodoro_timer.sprint_duration
            if total > 0:
                progress = ((total - remaining) / total) * 100
                self.progress_bar.setValue(int(progress))
                self.state_label.setText("Focus Time! 🎯")
        elif state == TimerState.BREAK:
            total = self.pomodoro_timer.break_duration
            if total > 0:
                progress = ((total - remaining) / total) * 100
                self.progress_bar.setValue(int(progress))
                self.state_label.setText("Break Time! ☕")
        elif state == TimerState.PAUSED:
            self.state_label.setText("Paused ⏸️")
        elif state == TimerState.STOPPED:
            self.progress_bar.setValue(0)
            self.state_label.setText("Ready to focus! 🚀")

        # Only stop Qt timer when completely stopped
        if state == TimerState.STOPPED and remaining <= 0:
            self.qt_timer.stop()

    def check_date_change(self):
        """Check if date has changed and refresh stats if needed"""
        from datetime import date
        today = date.today()
        
        if self.current_date is None:
            # First time running - just set the current date
            self.current_date = today
            debug_print(f"Date tracker initialized: {today}")
        elif self.current_date != today:
            # Date has changed - refresh stats and trigger backups
            debug_print(f"Date changed from {self.current_date} to {today} - refreshing stats")
            self.current_date = today
            self.update_stats()
            
            # Trigger backups on new day
            if hasattr(self, 'db_manager') and self.db_manager:
                self._trigger_daily_backup()
            
            info_print(f"Stats refreshed for new day: {today}")

    def _trigger_daily_backup(self):
        """Trigger backups when date changes (new day)"""
        try:
            info_print("Triggering daily backup on date change")
            if hasattr(self.db_manager, 'backup_manager'):
                self.db_manager.backup_manager.perform_scheduled_backups()
            else:
                debug_print("No backup manager available for daily backup")
        except Exception as e:
            error_print(f"Daily backup failed: {e}")

    def start_periodic_sync_system(self):
        """Initialize the periodic sync system after startup sync"""
        debug_print("Starting periodic sync system")
        # Refresh UI after startup sync in case new data was downloaded
        self.refresh_data_dependent_ui()
        # Start 1-hour timer after startup sync completes
        self.on_sync_completed()
        # Start idle detection
        self.on_user_activity()
    
    def on_user_activity(self):
        """Called whenever user activity is detected"""
        # Reset idle detection timer
        if hasattr(self, 'idle_timer'):
            self.idle_timer.start(self.idle_timeout)
    
    def request_periodic_sync(self):
        """Called by periodic timer - request sync when user becomes idle"""
        debug_print("Periodic sync requested - waiting for idle period")
        if self._is_currently_idle():
            self._perform_periodic_sync()
        else:
            debug_print("User active - setting sync_requested flag")
            self.sync_requested = True
    
    def on_idle_timeout(self):
        """Called after idle timeout - perform sync if requested"""
        debug_print("Idle timeout reached")
        if self.sync_requested:
            debug_print("Sync was requested - performing periodic sync")
            self._perform_periodic_sync()
            self.sync_requested = False
        else:
            debug_print("No sync requested during idle period")
    
    def _is_currently_idle(self) -> bool:
        """Check if user is currently idle (timer not running)"""
        return not self.idle_timer.isActive()
    
    def _perform_periodic_sync(self):
        """Perform the actual periodic sync operation"""
        debug_print("Performing periodic sync")
        try:
            if hasattr(self, 'db_manager') and self.db_manager:
                success = self.db_manager.sync_if_changes_pending()
                if success:
                    debug_print("Periodic sync completed successfully")
                    # Refresh UI in case remote changes were downloaded
                    self.refresh_data_dependent_ui()
                    # Restart periodic timer for next sync
                    self.on_sync_completed()
                else:
                    debug_print("Periodic sync failed or was skipped")
                    # Still restart timer even if sync failed
                    self.on_sync_completed()
        except Exception as e:
            error_print(f"Error during periodic sync: {e}")
            # Restart timer even on error
            self.on_sync_completed()
    
    def on_sync_completed(self):
        """Called after any sync operation completes - restart periodic timer"""
        debug_print("Sync completed - restarting 1-hour periodic timer")
        if hasattr(self, 'periodic_sync_timer'):
            self.periodic_sync_timer.start(self.periodic_sync_interval)

    def _recover_hibernated_sprints(self):
        """
        Auto-complete sprints that were interrupted by hibernation/system sleep.
        
        Finds incomplete sprints where enough time has passed since start_time
        to consider them completed, then marks them as completed with appropriate
        end_time and duration.
        """
        try:
            from datetime import datetime, timedelta
            from tracking.models import Sprint
            
            session = self.db_manager.get_session()
            
            # Find incomplete sprints (started but not completed)
            debug_print("Hibernation recovery: Querying for incomplete sprints...")
            incomplete_sprints = session.query(Sprint).filter(
                Sprint.completed == False,
                Sprint.interrupted == False,
                Sprint.start_time.isnot(None),
                Sprint.end_time.is_(None)
            ).all()
            
            # Debug: Log what we found
            debug_print(f"Hibernation recovery: Query found {len(incomplete_sprints)} sprints matching criteria")
            for sprint in incomplete_sprints:
                debug_print(f"  - Sprint ID {sprint.id}: '{sprint.task_description}' started {sprint.start_time}, completed={sprint.completed}, interrupted={sprint.interrupted}, end_time={sprint.end_time}")
            
            if not incomplete_sprints:
                debug_print("Hibernation recovery: No incomplete sprints found")
                session.close()
                return
                
            debug_print(f"Hibernation recovery: Found {len(incomplete_sprints)} incomplete sprints")
            
            recovered_count = 0
            recovered_sprints = []  # Track which sprints were actually recovered
            now = datetime.now()
            
            for sprint in incomplete_sprints:
                # Calculate how much time has passed since sprint started
                elapsed_time = now - sprint.start_time
                planned_duration_timedelta = timedelta(minutes=sprint.planned_duration)
                
                # If enough time has passed for the sprint to be considered complete
                if elapsed_time >= planned_duration_timedelta:
                    # Auto-complete the sprint
                    sprint.end_time = sprint.start_time + planned_duration_timedelta
                    sprint.duration_minutes = sprint.planned_duration
                    sprint.completed = True
                    sprint.interrupted = False  # Ensure not marked as interrupted
                    
                    # Add to recovered list for operation tracking
                    recovered_sprints.append(sprint)
                    
                    start_date = sprint.start_time.strftime('%Y-%m-%d')
                    end_date = sprint.end_time.strftime('%Y-%m-%d')
                    info_print(f"Hibernation recovery: Auto-completed sprint '{sprint.task_description}' "
                             f"(started {sprint.start_time.strftime('%Y-%m-%d %H:%M')}, "
                             f"completed {sprint.end_time.strftime('%Y-%m-%d %H:%M')}, "
                             f"elapsed {elapsed_time.total_seconds()/60:.1f} min)")
                    if start_date != end_date:
                        info_print(f"Note: Sprint started on {start_date} so it will appear in {start_date}'s statistics, not today's")
                    recovered_count += 1
                else:
                    # Sprint is still within its planned duration - could be a legitimate pause
                    remaining_time = planned_duration_timedelta - elapsed_time
                    debug_print(f"Hibernation recovery: Sprint '{sprint.task_description}' still active "
                               f"({remaining_time.total_seconds()/60:.1f} min remaining)")
            
            if recovered_count > 0:
                session.commit()
                info_print(f"Hibernation recovery: Successfully recovered {recovered_count} sprint(s)")
                
                # Track hibernation recovery as operations for sync - only for sprints that were actually recovered
                debug_print(f"Hibernation recovery: Tracking operations for {len(recovered_sprints)} recovered sprints")
                for sprint in recovered_sprints:
                    debug_print(f"Hibernation recovery: Tracking operation for sprint ID {sprint.id}")
                    self.db_manager.operation_tracker.track_operation(
                        'update',
                        'sprints', 
                        {
                            'id': sprint.id, 
                            'end_time': sprint.end_time.isoformat() if sprint.end_time else None,
                            'duration_minutes': sprint.duration_minutes,
                            'completed': True,
                            'interrupted': False
                        }
                    )
                
                # Check pending operations before sync
                pending_ops = self.db_manager.operation_tracker.get_pending_operations()
                debug_print(f"Hibernation recovery: Found {len(pending_ops)} pending operations before sync")
                
                # Trigger sync to upload hibernation recovery changes to Google Drive
                if hasattr(self.db_manager, 'sync_manager') and self.db_manager.sync_manager:
                    try:
                        debug_print("Hibernation recovery: Triggering sync to upload recovered sprints")
                        self.db_manager.trigger_manual_sync()
                        debug_print("Hibernation recovery: Sync completed successfully")
                    except Exception as sync_error:
                        error_print(f"Failed to sync hibernation recovery changes: {sync_error}")
                else:
                    debug_print("Hibernation recovery: No sync manager available - changes will sync on next startup")
                
                # Update UI stats to reflect recovered sprints
                if hasattr(self, 'update_stats') and hasattr(self, 'stats_label'):
                    self.update_stats()
            else:
                debug_print("Hibernation recovery: No sprints needed recovery")
                
            session.close()
            
        except Exception as e:
            error_print(f"Error during hibernation recovery: {e}")
            if 'session' in locals():
                session.rollback()
                session.close()

    def _save_current_sprint(self):
        """
        Save the current sprint to database.
        
        Extracted from complete_sprint() to enable auto-saving on timer completion
        without duplicating the sprint saving logic.
        """
        from datetime import datetime
        from tracking.models import Sprint
        
        # Use the preserved sprint start time and calculate duration
        start_time = self.sprint_start_time
        end_time = datetime.now()
        
        if start_time is None:
            error_print("Sprint start time is None, cannot save sprint")
            return
            
        actual_duration = (end_time - start_time).total_seconds()
        debug_print(f"Saving sprint: start={start_time}, duration={actual_duration}s")

        # Ensure task description is not None
        task_desc = self.current_task_description or "Pomodoro Sprint"
        debug_print(f"Task description for sprint save: '{task_desc}'")

        sprint = Sprint(
            project_id=self.current_project_id,
            task_category_id=self.current_task_category_id,
            task_description=task_desc,
            start_time=start_time,
            end_time=end_time,
            completed=True,
            interrupted=False,
            duration_minutes=int(actual_duration / 60),
            planned_duration=int(self.pomodoro_timer.sprint_duration / 60)
        )
        debug_print(f"Created sprint object: {sprint.task_description}, duration: {actual_duration}s")

        # Save to database
        debug_print("Calling db_manager.add_sprint()...")
        self.db_manager.add_sprint(sprint)
        debug_print("Sprint saved to database successfully")

        # Update statistics
        if hasattr(self, 'update_stats'):
            self.update_stats()

    def _save_sprint_with_data(self, sprint_data):
        """
        Save sprint using captured data to avoid race conditions.
        
        Args:
            sprint_data: Dict with 'project_id', 'task_category_id', 'task_description', 'start_time'
        """
        from datetime import datetime
        from tracking.models import Sprint
        
        start_time = sprint_data['start_time']
        end_time = datetime.now()
        
        if start_time is None:
            error_print("Sprint start time is None in captured data, cannot save sprint")
            return
            
        actual_duration = (end_time - start_time).total_seconds()
        debug_print(f"Saving sprint with captured data: start={start_time}, duration={actual_duration}s")

        # Ensure task description is not None
        task_desc = sprint_data['task_description'] or "Pomodoro Sprint"
        debug_print(f"Task description for sprint save: '{task_desc}'")

        sprint = Sprint(
            project_id=sprint_data['project_id'],
            task_category_id=sprint_data['task_category_id'],
            task_description=task_desc,
            start_time=start_time,
            end_time=end_time,
            completed=True,
            interrupted=False,
            duration_minutes=int(actual_duration / 60),
            planned_duration=int(self.pomodoro_timer.sprint_duration / 60)
        )
        debug_print(f"Created sprint object with captured data: {sprint.task_description}, duration: {actual_duration}s")

        # Save to database
        debug_print("Calling db_manager.add_sprint()...")
        self.db_manager.add_sprint(sprint)
        debug_print("Sprint saved to database successfully with captured data")

        # Update statistics
        if hasattr(self, 'update_stats'):
            self.update_stats()

        debug_print("Sprint save with captured data completed successfully")

    def reset_ui(self):
        """Reset UI to initial state"""
        self.start_button.setText("Start Sprint")
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.complete_button.setEnabled(False)
        self.sync_compact_buttons()  # Sync compact button states
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)  # Ensure progress bar is visible

        # Clear task description field
        self.task_input.clear()
        
        # Clear sprint start time
        self.sprint_start_time = None

        # Set timer display to current sprint duration
        sprint_minutes = self.pomodoro_timer.sprint_duration // 60
        self.time_label.setText(f"{sprint_minutes:02d}:00")
        self.state_label.setText("Ready to Focus")
        
        # Validate form to set proper button state
        self.validate_form()

    def refresh_data_dependent_ui(self):
        """Refresh all UI elements that depend on database data"""
        self.update_stats()
        self.update_task_autocompletion()

    def update_stats(self):
        """Update today's statistics"""
        try:
            from datetime import date
            today = date.today()
            debug_print(f"Stats update: Looking for sprints on {today} (type: {type(today)})")
            sprints = self.db_manager.get_sprints_by_date(today)
            count = len(sprints)
            debug_print(f"Stats update: Found {count} sprints for {today}")
            for sprint in sprints:
                debug_print(f"  - {sprint.task_description} at {sprint.start_time}")

            stats_text = f"Today: {count} sprints completed"
            debug_print(f"Setting stats label to: '{stats_text}'")  # Debug
            self.stats_label.setText(stats_text)
            debug_print(f"Stats label text is now: '{self.stats_label.text()}'")  # Debug
            
            # Update current date tracker when stats are updated
            self.current_date = today
        except Exception as e:
            error_print(f"Error updating stats: {e}")
            import traceback
            traceback.print_exc()

    def toggle_compact_mode(self):
        """Toggle between normal and compact view"""
        self.compact_mode = not self.compact_mode

        # Compact mode state is not saved - app always starts in normal mode

        if self.compact_mode:
            # Enter compact mode
            self.enter_compact_mode()
        else:
            # Exit compact mode
            self.exit_compact_mode()

    def enter_compact_mode(self):
        """Enter compact mode with minimal layout"""
        # Store current layout state for restoration
        timer_frame = self.centralWidget().findChild(QFrame, "timerFrame")
        if timer_frame and timer_frame.layout():
            self._stored_spacing = timer_frame.layout().spacing()
            self._stored_margins = timer_frame.layout().contentsMargins()

        # Hide everything except timer
        self.centralWidget().findChild(QFrame, "headerFrame").hide()
        self.centralWidget().findChild(QFrame, "inputFrame").hide()
        self.centralWidget().findChild(QFrame, "controlFrame").hide()
        self.centralWidget().findChild(QFrame, "statusFrame").hide()

        # Show compact controls and sync their state
        self.compact_controls_frame.show()
        self.sync_compact_buttons()  # Ensure buttons show correct state for current timer

        # Resize window first
        self.setFixedSize(*self.compact_size)
        self.compact_action.setText('Exit Compact Mode')

        # Apply compact styling based on current theme
        self.apply_compact_styling()

        # Adjust layout spacing for compact mode - minimize spacing for full-window blue area
        if timer_frame and timer_frame.layout():
            timer_frame.layout().setSpacing(1)  # Minimal spacing between elements
            timer_frame.layout().setContentsMargins(0, 0, 0, 0)  # No margins around content

        # Remove main layout margins to let timer frame fill entire window
        main_layout = self.centralWidget().layout()
        if main_layout:
            self._stored_main_margins = main_layout.contentsMargins()  # Store for restoration
            main_layout.setContentsMargins(0, 0, 0, 0)  # No margins around main layout
            main_layout.setSpacing(0)  # No spacing between main layout elements

    def exit_compact_mode(self):
        """Exit compact mode and restore normal layout"""
        # Hide compact controls
        self.compact_controls_frame.hide()

        # Restore window size first
        self.setFixedSize(*self.normal_size)
        self.compact_action.setText('Toggle Compact Mode')

        # Show all elements
        self.centralWidget().findChild(QFrame, "headerFrame").show()
        self.centralWidget().findChild(QFrame, "inputFrame").show()
        self.centralWidget().findChild(QFrame, "controlFrame").show()
        self.centralWidget().findChild(QFrame, "statusFrame").show()

        # Restore layout spacing to stored values or defaults
        timer_frame = self.centralWidget().findChild(QFrame, "timerFrame")
        if timer_frame and timer_frame.layout():
            # Use stored values if available, otherwise use defaults
            spacing = getattr(self, '_stored_spacing', 10)
            margins = getattr(self, '_stored_margins', None)

            timer_frame.layout().setSpacing(spacing)
            if margins:
                timer_frame.layout().setContentsMargins(margins)
            else:
                timer_frame.layout().setContentsMargins(11, 11, 11, 11)

        # Restore main layout margins
        main_layout = self.centralWidget().layout()
        if main_layout:
            stored_main_margins = getattr(self, '_stored_main_margins', None)
            if stored_main_margins:
                main_layout.setContentsMargins(stored_main_margins)
            else:
                main_layout.setContentsMargins(25, 25, 25, 25)  # Default margins
            main_layout.setSpacing(5)  # Default spacing

        # Reapply normal styling completely
        self.apply_modern_styling()

        # Force layout update to prevent corruption
        self.centralWidget().updateGeometry()
        self.update()
        self.repaint()

    def export_to_excel(self):
        """Export data to Excel file"""
        from PySide6.QtWidgets import QFileDialog
        try:
            # Get save location
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export to Excel",
                f"pomodora_export_{datetime.now().strftime('%Y%m%d')}.xlsx",
                "Excel Files (*.xlsx)"
            )

            if file_path:
                def do_export():
                    from tracking.excel_export import ExcelExporter
                    exporter = ExcelExporter(self.db_manager)
                    exporter.export_all_data(file_path)
                    return file_path
                
                # Run export with automatic progress dialog
                exported_file = run_with_auto_progress(
                    do_export,
                    "Exporting to Excel",
                    parent=self,
                    min_duration=0.5  # Show progress for exports taking > 0.5s
                )

                self.show_sync_dialog("Export Complete", 
                                      f"Data exported successfully to:\n{exported_file}",
                                      "information")
        except Exception as e:
            self.show_sync_dialog("Export Error", 
                                 f"Failed to export data:\n{str(e)}",
                                 "critical")

    def open_data_viewer(self):
        """Open data viewer window"""
        try:
            from gui.pyside_data_viewer import PySideDataViewerWindow
            self.data_viewer = PySideDataViewerWindow(self, self.db_manager)
            self.data_viewer.show()
        except Exception as e:
            self.show_sync_dialog("Error", 
                                 f"Failed to open data viewer:\n{str(e)}",
                                 "critical")

    def manage_activity_classifications(self):
        """Open comprehensive activity classifications dialog"""
        dialog = ActivityClassificationsDialog(self, self.db_manager)
        if dialog.exec():
            self.load_projects()

    def open_settings(self):
        """Open settings dialog with theme, timer, and database options"""
        dialog = SettingsDialog(self)
        dialog.exec()

        # Refresh UI state after settings dialog closes
        self.refresh_ui_state()

    def manual_sync(self):
        """Manually trigger database sync with Google Drive"""
        try:
            success = self.db_manager.sync_with_progress(self)
            
            if success:
                # Refresh UI to reflect any new data downloaded from remote
                self.refresh_data_dependent_ui()
                
                # Restart periodic timer after manual sync
                self.on_sync_completed()
                
                self.show_sync_dialog(
                    "Sync Complete", 
                    "Database successfully synced with Google Drive.",
                    "information"
                )
            else:
                self.show_sync_dialog(
                    "Sync Failed", 
                    "Failed to sync database with Google Drive.\nCheck the logs for more details.",
                    "warning"
                )
        except Exception as e:
            self.show_sync_dialog(
                "Sync Error", 
                f"An error occurred during sync:\n{str(e)}",
                "critical"
            )

    def show_sync_dialog(self, title: str, message: str, dialog_type: str = "information"):
        """Show a properly sized sync status dialog with theme support"""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QFrame, QHBoxLayout
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QIcon, QPixmap

        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setModal(True)
        dialog.setFixedSize(400, 180)
        
        # Apply theme-aware styling
        if hasattr(self, 'theme_mode') and self.theme_mode == 'dark':
            dialog.setStyleSheet("""
                QDialog {
                    background-color: #2b2b2b;
                    color: white;
                }
                QLabel {
                    color: white;
                    background-color: transparent;
                }
                QPushButton {
                    background-color: #404040;
                    border: 1px solid #555555;
                    color: white;
                    padding: 8px 16px;
                    border-radius: 4px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #505050;
                    border-color: #666666;
                }
                QPushButton:pressed {
                    background-color: #353535;
                }
            """)
        else:
            dialog.setStyleSheet("""
                QDialog {
                    background-color: white;
                    color: black;
                }
                QLabel {
                    color: black;
                    background-color: transparent;
                }
                QPushButton {
                    background-color: #f0f0f0;
                    border: 1px solid #cccccc;
                    color: black;
                    padding: 8px 16px;
                    border-radius: 4px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #e0e0e0;
                    border-color: #aaaaaa;
                }
                QPushButton:pressed {
                    background-color: #d0d0d0;
                }
            """)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # Content area with icon and message
        content_layout = QHBoxLayout()
        
        # Add icon based on dialog type
        icon_label = QLabel()
        icon_text = ""
        if dialog_type == "information":
            icon_text = "✅"  # Success
        elif dialog_type == "warning":
            icon_text = "⚠️"   # Warning
        elif dialog_type == "critical":
            icon_text = "❌"  # Error
        
        if icon_text:
            icon_label.setText(icon_text)
            icon_label.setAlignment(Qt.AlignmentFlag.AlignTop)
            icon_label.setFixedSize(32, 32)
            icon_label.setStyleSheet("font-size: 24px;")
            content_layout.addWidget(icon_label)

        # Message label with word wrap and proper sizing
        label = QLabel(message)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        label.setMinimumHeight(50)
        content_layout.addWidget(label, 1)  # Give it stretch factor to use remaining space
        
        layout.addLayout(content_layout)

        # OK button
        ok_button = QPushButton("OK")
        ok_button.setFixedSize(80, 32)
        ok_button.clicked.connect(dialog.accept)
        
        # Center the button
        button_layout = QVBoxLayout()
        button_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        button_layout.addWidget(ok_button)
        layout.addLayout(button_layout)

        dialog.exec()

    def refresh_ui_state(self):
        """Refresh UI elements to match current timer state"""
        # Safety check - timer might be None during shutdown
        if not self.pomodoro_timer:
            debug_print("Timer is None - skipping UI refresh during shutdown")
            return
            
        timer_state = self.pomodoro_timer.get_state()

        if timer_state == TimerState.STOPPED:
            self.start_button.setText("Start")
            self.stop_button.setEnabled(False)
            self.complete_button.setEnabled(False)
            self.state_label.setText("Ready to focus! 🚀")
        elif timer_state == TimerState.RUNNING:
            self.start_button.setText("Pause")
            self.stop_button.setEnabled(True)
            self.complete_button.setEnabled(True)
            self.complete_button.setText("Complete Sprint")
            self.state_label.setText("Focus Time! 🎯")
        elif timer_state == TimerState.PAUSED:
            self.start_button.setText("Resume")
            self.stop_button.setEnabled(True)
            self.complete_button.setEnabled(True)
            self.complete_button.setText("Complete Sprint")
            self.state_label.setText("Paused ⏸️")
        elif timer_state == TimerState.BREAK:
            self.start_button.setText("Start")
            self.stop_button.setEnabled(False)  # No need to stop during break
            self.complete_button.setEnabled(True)  # Allow ending break
            self.complete_button.setText("Done")
            self.state_label.setText("Break Time! ☕")

    def on_project_changed(self, project_text):
        """Handle project field changes - if project exists as category, set category to match"""
        if not project_text:
            return

        # Rule 1: If a project is selected that exists as a category, automatically set category to match
        for i in range(self.task_category_combo.count()):
            if self.task_category_combo.itemText(i) == project_text:
                # Found matching category - update category to match project
                # Temporarily disconnect to avoid recursion
                self.task_category_combo.currentTextChanged.disconnect()
                self.task_category_combo.setCurrentIndex(i)
                self.task_category_combo.currentTextChanged.connect(self.on_category_changed)
                break

        # Update tracking
        self._last_project_text = project_text

    def on_category_changed(self, category_text):
        """Handle category field changes - if project and category were matching, update project to match new category"""
        if not category_text:
            return

        # Rule 2: If project and category field were matching and category is changed, update project to match
        # Check if they were matching before this change
        if self._last_project_text == self._last_category_text:
            # They were matching, so sync project to new category value
            for i in range(self.project_combo.count()):
                if self.project_combo.itemText(i) == category_text:
                    # Found matching project - update project to match category
                    # Temporarily disconnect to avoid recursion
                    self.project_combo.currentTextChanged.disconnect()
                    self.project_combo.setCurrentIndex(i)
                    self.project_combo.currentTextChanged.connect(self.on_project_changed)
                    self._last_project_text = category_text  # Update tracking
                    break

        # Update tracking
        self._last_category_text = category_text


def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # Modern style

    # Set the process name for Linux systems (helps with taskbar/window manager display)
    try:
        import setproctitle
        setproctitle.setproctitle("Pomodora")
    except ImportError:
        # setproctitle is optional, continue without it
        pass

    # Set application properties for proper Qt/desktop display
    app.setApplicationName("Pomodora")
    app.setApplicationDisplayName("Pomodora")
    app.setApplicationVersion("1.0")
    app.setOrganizationName("Pomodora")
    app.setOrganizationDomain("pomodora.app")

    try:
        window = ModernPomodoroWindow()
        window.show()

        result = app.exec()

        # More graceful cleanup to prevent segfault
        debug_print("Application exiting...")
        if window:
            window.hide()  # Hide first
            window.close() # Then close
            window.deleteLater()  # Schedule for deletion
            del window

        app.processEvents()  # Process any remaining events
        app.quit()

        sys.exit(result)
    except Exception as e:
        print(f"Application error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()