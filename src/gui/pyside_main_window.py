import sys
from datetime import datetime, timedelta
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QLabel, QPushButton, QComboBox, QCheckBox,
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

# Import mixin classes for modular functionality
from gui.mixins import (
    TaskInputMixin,
    TimerControlMixin,
    SprintMixin,
    SyncMixin,
    CompactModeMixin
)


class ModernPomodoroWindow(
    QMainWindow,
    TaskInputMixin,
    TimerControlMixin,
    SprintMixin,
    SyncMixin,
    CompactModeMixin
):
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

        # Work block reminder timer - reminds user to start a new sprint
        self.work_block_reminder_timer = QTimer()
        self.work_block_reminder_timer.setSingleShot(True)  # Single-shot, manually restarted
        self.work_block_reminder_timer.timeout.connect(self.on_work_block_reminder)
        self.work_block_mode = False  # Whether work block mode is enabled
        self.work_block_reminder_interval = 5 * 60 * 1000  # 5 minutes default (in ms)

        # Hyperfocus prevention - track consecutive identical sprints
        self._last_completed_sprint = None  # Dict with project_id, task_category_id, task_description
        self._consecutive_sprint_count = 0

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
        self.init_hyperfocus_tracking_from_history()  # Initialize from DB before UI setup
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

        # Hibernation recovery: auto-complete sprints that were interrupted by system sleep
        # IMPORTANT: Must run AFTER GUI initialization to avoid crashes
        # Use Qt's event loop to defer execution until after __init__ completes
        QTimer.singleShot(0, self._recover_hibernated_sprints)

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

    def eventFilter(self, obj, event):
        """Filter events for child widgets.

        Delegates to mixin event handlers to avoid MRO conflicts with QObject.eventFilter.
        When using multiple inheritance with Qt classes, mixins cannot directly override
        eventFilter because QObject.eventFilter is found first in the MRO.
        """
        # Handle task input events (arrow key history navigation)
        if self._handle_task_input_event(obj, event):
            return True

        return super().eventFilter(obj, event)

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
            if hasattr(self, 'work_block_reminder_timer') and self.work_block_reminder_timer:
                self.work_block_reminder_timer.stop()
                info_print("Work block reminder timer stopped")

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

        # Install event filter for task input (handles arrow key history navigation)
        # This must be done here in the main window class to avoid MRO conflicts
        # with QObject.eventFilter when using multiple inheritance with mixins
        self.task_input.installEventFilter(self)

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
        control_frame_layout = QVBoxLayout(control_frame)
        control_frame_layout.setSpacing(10)

        # Buttons row
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(15)

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

        buttons_layout.addWidget(self.start_button)
        buttons_layout.addWidget(self.stop_button)
        buttons_layout.addWidget(self.complete_button)
        control_frame_layout.addLayout(buttons_layout)

        # Work block mode toggle (below buttons)
        self.work_block_checkbox = QCheckBox("Work Block Mode")
        self.work_block_checkbox.setObjectName("workBlockCheckbox")
        self.work_block_checkbox.setToolTip("Remind me to start a new sprint after each one completes")
        self.work_block_checkbox.setChecked(False)  # Will be set in load_settings
        self.work_block_checkbox.stateChanged.connect(self.toggle_work_block_mode)
        control_frame_layout.addWidget(self.work_block_checkbox, alignment=Qt.AlignCenter)

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

        # Load work block mode settings
        self.work_block_mode = settings.get("work_block_mode", False)
        self.work_block_reminder_interval = settings.get("work_block_reminder_interval", 5) * 60 * 1000  # minutes to ms
        # Update checkbox if it exists (may not exist during early initialization)
        if hasattr(self, 'work_block_checkbox'):
            self.work_block_checkbox.setChecked(self.work_block_mode)

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
        self.refresh_task_history()

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