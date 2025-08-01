import sys
from datetime import datetime, timedelta
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QLabel, QPushButton, QComboBox,
                               QLineEdit, QProgressBar, QFrame, QTextEdit, QMenuBar, QMenu)
from PySide6.QtCore import QTimer, QTime, Qt, Signal
from PySide6.QtGui import QFont, QPalette, QColor, QIcon, QAction
from timer.pomodoro import PomodoroTimer, TimerState
from tracking.models import DatabaseManager, Category, Project, Sprint
from audio.alarm import play_alarm_async
from utils.logging import verbose_print, error_print, info_print, debug_print, trace_print

class ModernPomodoroWindow(QMainWindow):
    """Modern, colorful PySide6 Pomodoro timer with elegant design"""

    # Qt signals for thread-safe timer callbacks
    sprint_completed = Signal()
    break_completed = Signal()

    def __init__(self):
        super().__init__()
        # Initialize database manager with configurable location
        from tracking.local_settings import get_local_settings
        settings = get_local_settings()
        db_type = settings.get('database_type', 'local')

        if db_type == 'local':
            db_path = settings.get('database_local_path', '')
            if not db_path:
                # Use default path if not configured
                from pathlib import Path
                config_dir = Path.home() / '.config' / 'pomodora'
                config_dir.mkdir(parents=True, exist_ok=True)
                db_dir = config_dir / 'database'
                db_dir.mkdir(parents=True, exist_ok=True)
                db_path = str(db_dir / 'pomodora.db')
            else:
                # Ensure the path includes the database filename
                from pathlib import Path
                db_path = Path(db_path)
                if db_path.is_dir():
                    db_path = db_path / 'pomodora.db'
                # Create parent directories
                db_path.parent.mkdir(parents=True, exist_ok=True)
                db_path = str(db_path)
            self.db_manager = DatabaseManager(db_path)
        else:
            # For Google Drive, still use a local cache file
            from pathlib import Path
            config_dir = Path.home() / '.config' / 'pomodora'
            config_dir.mkdir(parents=True, exist_ok=True)
            cache_dir = config_dir / 'cache'
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path = str(cache_dir / 'pomodora.db')
            self.db_manager = DatabaseManager(cache_path)
        info_print("Database initialized")
        self.db_manager.initialize_default_projects()  # Ensure default projects exist
        info_print("Default projects initialized")

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

        # Sprint tracking
        self.current_project_id = None
        self.current_task_description = None

        # UI state
        self.compact_mode = False
        self.auto_compact_mode = True  # Auto-enter compact mode on sprint start
        self.theme_mode = "light"  # light, dark, or system
        self.normal_size = (500, 680)
        self.compact_size = (280, 140)

        self.init_ui()
        self.create_menu_bar()
        self.load_settings()  # Load settings before applying styling
        self.apply_modern_styling()
        self.load_projects()
        self.reset_ui()

        # App always starts in normal mode - compact mode only activated by auto-compact or manual toggle

        # Update stats on startup - call AFTER reset_ui
        debug_print("Calling update_stats() on startup")
        self.update_stats()
        debug_print(f"Stats label text after update: '{self.stats_label.text()}'")

    def mousePressEvent(self, event):
        """Handle mouse clicks - exit compact mode on any click"""
        if self.compact_mode:
            self.toggle_compact_mode()
        super().mousePressEvent(event)

    def closeEvent(self, event):
        """Handle application close event to prevent segfault"""
        try:
            debug_print("Starting application cleanup...")

            # Stop Qt timer first
            if hasattr(self, 'qt_timer') and self.qt_timer:
                self.qt_timer.stop()
                info_print("Qt timer stopped")

            # Stop pomodoro timer
            if hasattr(self, 'pomodoro_timer') and self.pomodoro_timer:
                self.pomodoro_timer.stop()
                info_print("Pomodoro timer stopped")

            # Close database connections properly
            if hasattr(self, 'db_manager') and self.db_manager:
                # Close any active sessions
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
        self.setWindowTitle("Pomodora - Modern Pomodoro Timer")
        self.setFixedSize(500, 500)

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

        title_label = QLabel("🍅 Pomodora")
        title_label.setObjectName("titleLabel")
        title_label.setAlignment(Qt.AlignCenter)

        header_layout.addWidget(title_label)
        layout.addWidget(header_frame)

    def create_timer_section(self, layout):
        """Create the main timer display with integrated progress bar"""
        timer_frame = QFrame()
        timer_frame.setObjectName("timerFrame")
        timer_frame.setFrameStyle(QFrame.StyledPanel)  # Ensure proper frame boundaries
        timer_layout = QVBoxLayout(timer_frame)
        timer_layout.setAlignment(Qt.AlignCenter)
        timer_layout.setSpacing(8)
        timer_layout.setContentsMargins(15, 15, 15, 15)

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

        timer_layout.addWidget(self.time_label)
        timer_layout.addWidget(self.state_label)
        timer_layout.addWidget(self.progress_bar)
        layout.addWidget(timer_frame)


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
        project_layout.addWidget(project_label)
        project_layout.addWidget(self.project_combo)
        project_layout.addStretch()  # Push everything to the left

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
        task_layout.addWidget(task_label)
        task_layout.addWidget(self.task_input)
        task_layout.addStretch()  # Push everything to the left

        input_layout.addLayout(project_layout)
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
        debug_print(f"[{context.upper()}] Applying styling for theme mode: {self.theme_mode}")

        if self.theme_mode == "dark":
            debug_print("Using dark mode styling")
            self.apply_dark_mode_styling()
        elif self.theme_mode == "system":
            # Use more robust system theme detection
            is_dark = self.detect_system_dark_theme(context)
            debug_print(f"[{context.upper()}] System theme detection: {'dark' if is_dark else 'light'}")
            if is_dark:
                self.apply_dark_mode_styling()
            else:
                self.apply_light_mode_styling()
        else:  # light mode
            debug_print("Using light mode styling")
            self.apply_light_mode_styling()

    def apply_dialog_styling(self, dialog):
        """Apply current theme styling to a dialog"""
        if self.theme_mode == "dark" or (self.theme_mode == "system" and self.detect_system_dark_theme("dialog")):
            self.apply_dark_dialog_styling(dialog)
        else:
            self.apply_light_dialog_styling(dialog)

    def detect_system_dark_theme(self, context="unknown"):
        """Detect if system is using dark theme"""
        debug_print(f"[{context.upper()}] Starting system theme detection...")
        try:
            import os
            import platform
            system = platform.system()

            # Priority 1: macOS dark mode detection
            if system == 'Darwin':
                try:
                    result = os.popen("defaults read -g AppleInterfaceStyle 2>/dev/null").read().strip()
                    debug_print(f"[{context.upper()}] macOS AppleInterfaceStyle: {result}")
                    if result and result.lower() == 'dark':
                        debug_print(f"[{context.upper()}] Dark theme detected via macOS system preference")
                        return True
                except Exception as e:
                    debug_print(f"[{context.upper()}] macOS detection error: {e}")

            # Priority 2: Check GNOME/GTK settings (Linux)
            elif system == 'Linux':
                try:
                    # Check color scheme preference (newer method)
                    result = os.popen("gsettings get org.gnome.desktop.interface color-scheme 2>/dev/null").read().strip()
                    debug_print(f"[{context.upper()}] GNOME color-scheme: {result}")
                    if result and 'prefer-dark' in result.lower():
                        debug_print(f"[{context.upper()}] Dark theme detected via color-scheme: {result}")
                        return True

                    # Check GTK theme name
                    result = os.popen("gsettings get org.gnome.desktop.interface gtk-theme 2>/dev/null").read().strip()
                    debug_print(f"[{context.upper()}] GTK theme: {result}")
                    if result and ('dark' in result.lower() or 'adwaita-dark' in result.lower()):
                        debug_print(f"[{context.upper()}] Dark theme detected via GTK theme: {result}")
                        return True
                except Exception as e:
                    debug_print(f"[{context.upper()}] GNOME detection error: {e}")

            # Priority 3: Check KDE settings (Linux)
            try:
                kde_config = os.path.expanduser("~/.config/kdeglobals")
                if os.path.exists(kde_config):
                    with open(kde_config, 'r') as f:
                        content = f.read()
                        if 'ColorScheme=Breeze Dark' in content or 'Name=Breeze Dark' in content:
                            debug_print(f"[{context.upper()}] Dark theme detected via KDE settings")
                            return True
            except Exception as e:
                debug_print(f"[{context.upper()}] KDE detection error: {e}")

            # Priority 3: Check environment variables
            qt_style = os.environ.get('QT_STYLE_OVERRIDE', '').lower()
            if 'dark' in qt_style:
                debug_print(f"[{context.upper()}] Dark theme detected via QT_STYLE_OVERRIDE: {qt_style}")
                return True

            # Priority 4: Qt palette check (as fallback, but more reliable with fresh app instance)
            try:
                from PySide6.QtGui import QPalette
                from PySide6.QtWidgets import QApplication

                app = QApplication.instance()
                if app:
                    # Get a fresh palette by creating a temporary widget
                    from PySide6.QtWidgets import QWidget
                    temp_widget = QWidget()
                    palette = temp_widget.palette()
                    temp_widget.deleteLater()

                    # Check window color lightness
                    window_color = palette.color(QPalette.Window)
                    window_lightness = window_color.lightness()
                    debug_print(f"[{context.upper()}] Qt window color lightness: {window_lightness}")

                    # Check text color
                    text_color = palette.color(QPalette.WindowText)
                    text_lightness = text_color.lightness()
                    debug_print(f"[{context.upper()}] Qt text color lightness: {text_lightness}")

                    # More lenient Qt detection
                    if text_lightness > window_lightness:
                        debug_print(f"[{context.upper()}] Dark theme detected via Qt palette (text > window)")
                        return True

                    if window_lightness < 150:  # More lenient threshold
                        debug_print(f"[{context.upper()}] Dark theme detected via Qt palette (window < 150)")
                        return True
            except Exception as e:
                debug_print(f"[{context.upper()}] Qt palette detection error: {e}")

            debug_print(f"[{context.upper()}] No dark theme detected, defaulting to light")
            return False

        except Exception as e:
            error_print(f"[{context.upper()}] Error detecting system theme: {e}")
            return False

    def apply_light_mode_styling(self):
        """Apply light mode styling"""
        style = """
        QMainWindow {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #f8f9fa, stop:1 #e9ecef);
        }

        #headerFrame {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #ff6b6b, stop:1 #ffa500);
            border-radius: 15px;
            padding: 0px;
            margin: 0 0 0px 0;
        }

        #titleLabel {
            font-size: 24px;
            font-weight: bold;
            color: white;
            padding: 0px;
        }

        #timerFrame {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #87ceeb, stop:1 #4682b4);
            border-radius: 20px;
            padding: 0px;
            margin: 10px 0 10px 0;
            min-height: 120px;
            max-height: 180px;
        }

        #timeLabel {
            font-size: 36px;
            font-weight: bold;
            color: white;
            margin: 5px 0;
            padding: 3px;
            qproperty-alignment: AlignCenter;
        }

        #stateLabel {
            font-size: 14px;
            color: #e8f4f8;
            margin: 5px 0;
            padding: 3px;
            qproperty-alignment: AlignCenter;
        }

        #progressBar {
            height: 8px;
            border-radius: 4px;
            background-color: rgba(255, 255, 255, 0.4);
            margin: 10px 0 5px 0;
            border: 1px solid rgba(255, 255, 255, 0.2);
            min-width: 200px;
        }

        #progressBar::chunk {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #56ab2f, stop:1 #a8e6cf);
            border-radius: 4px;
        }

        #inputFrame {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #f8f9ff, stop:1 #e8f4f8);
            border-radius: 15px;
            padding: 0px;
            border: 2px solid #d1ecf1;
            min-height: 90px;
            margin: 0px 0;
        }

        #inputLabel {
            font-size: 14px;
            font-weight: bold;
            color: #495057;
            min-width: 70px;
        }

        #projectCombo, #taskInput {
            padding: 0 0;
            border: 2px solid #dee2e6;
            border-radius: 8px;
            font-size: 14px;
            background: white;
            min-height: 25px;
            color: #333;
        }

        #projectCombo {
            background: white;
            selection-background-color: #667eea;
            selection-color: white;
        }

        #projectCombo::drop-down {
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 24px;
            border-left: 2px solid #adb5bd;
            background: #e9ecef;
            border-top-right-radius: 6px;
            border-bottom-right-radius: 6px;
        }

        #projectCombo::down-arrow {
            width: 0px;
            height: 0px;
            border-left: 6px solid transparent;
            border-right: 6px solid transparent;
            border-top: 8px solid #495057;
            margin: 5px;
        }

        #projectCombo QAbstractItemView {
            background: white;
            border: 2px solid #667eea;
            border-radius: 8px;
            selection-background-color: #667eea;
            selection-color: white;
            color: #333;
            padding: 5px;
        }

        #projectCombo QAbstractItemView::item {
            padding: 8px 12px;
            border: none;
            color: #333;
        }

        #projectCombo QAbstractItemView::item:selected {
            background: #667eea;
            color: white;
        }

        #projectCombo QAbstractItemView::item:hover {
            background: #5a6fd8;
            color: white;
        }

        #projectCombo:focus, #taskInput:focus {
            border-color: #667eea;
            outline: none;
        }

        #controlFrame {
            margin: 0px 0;
        }

        QPushButton {
            padding: 12px 20px;
            border-radius: 10px;
            font-size: 14px;
            font-weight: bold;
            border: none;
            min-height: 20px;
        }

        #startButton {
            background: #4CAF50;
            color: white;
        }

        #startButton:hover {
            background: #45a049;
        }

        #stopButton {
            background: #f44336;
            color: white;
        }

        #stopButton:hover {
            background: #da190b;
        }

        #completeButton {
            background: #2196F3;
            color: white;
        }

        #completeButton:hover {
            background: #0b7dda;
        }

        #statusFrame {
            background: white;
            border-radius: 15px;
            padding: 0px;
            border: 2px solid #dee2e6;
            margin: 0px 0 0px 0;
        }

        #statsLabel {
            font-size: 14px;
            color: #6c757d;
            font-weight: 500;
        }

        QPushButton:disabled {
            background: #e9ecef;
            color: #6c757d;
        }
        """

        self.setStyleSheet(style)

    def apply_light_dialog_styling(self, dialog):
        """Apply light mode styling to a dialog"""
        style = """
        QDialog {
            background: #f8f9fa;
            color: #333;
        }

        QTabWidget::pane {
            background: white;
            border: 1px solid #dee2e6;
            border-radius: 8px;
        }

        QTabWidget::tab-bar {
            alignment: center;
        }

        QTabBar::tab {
            background: #e9ecef;
            color: #333;
            padding: 8px 16px;
            margin-right: 2px;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
        }

        QTabBar::tab:selected {
            background: white;
            border-bottom: 2px solid #667eea;
        }

        QTabBar::tab:hover {
            background: #f1f3f4;
        }

        QGroupBox {
            font-weight: bold;
            border: 2px solid #dee2e6;
            border-radius: 8px;
            margin-top: 12px;
            padding-top: 8px;
            background: white;
        }

        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 8px 0 8px;
            background: white;
            color: #333;
        }

        QListWidget {
            background: white;
            border: 1px solid #dee2e6;
            border-radius: 8px;
            padding: 4px;
        }

        QListWidget::item {
            border-radius: 4px;
            padding: 4px;
            margin: 1px;
        }

        QListWidget::item:selected {
            background: #667eea;
            color: white;
        }

        QListWidget::item:hover {
            background: #f1f3f4;
        }

        QPushButton {
            background: #667eea;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            font-weight: 500;
        }

        QPushButton:hover {
            background: #5a6fd8;
        }

        QPushButton:pressed {
            background: #4c63d2;
        }

        QLineEdit {
            background: white;
            border: 2px solid #dee2e6;
            border-radius: 6px;
            padding: 8px;
            color: #333;
        }

        QLineEdit:focus {
            border-color: #667eea;
        }

        QComboBox {
            background: white;
            border: 2px solid #dee2e6;
            border-radius: 6px;
            padding: 8px;
            color: #333;
        }

        QComboBox:focus {
            border-color: #667eea;
        }

        QComboBox::drop-down {
            border: 1px solid #dee2e6;
            border-left: none;
            width: 20px;
            background: #f8f9fa;
            border-top-right-radius: 6px;
            border-bottom-right-radius: 6px;
        }

        QComboBox::drop-down:hover {
            background: #e9ecef;
        }

        QComboBox::down-arrow {
            image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTIiIGhlaWdodD0iOCIgdmlld0JveD0iMCAwIDEyIDgiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxwYXRoIGQ9Ik0xIDFMNiA2TDExIDEiIHN0cm9rZT0iIzMzMzMzMyIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiLz4KPC9zdmc+);
            width: 12px;
            height: 8px;
            margin: 2px;
        }

        QComboBox QAbstractItemView {
            background: white;
            border: 2px solid #667eea;
            border-radius: 6px;
            padding: 4px;
            color: #333;
            selection-background-color: #667eea;
            selection-color: white;
        }

        QComboBox QAbstractItemView::item {
            background: white;
            color: #333;
            padding: 8px;
            border: none;
            min-height: 20px;
        }

        QComboBox QAbstractItemView::item:selected {
            background: #667eea;
            color: white;
        }

        QComboBox QAbstractItemView::item:hover {
            background: #f1f3f4;
            color: #333;
        }

        QSpinBox {
            background: white;
            border: 2px solid #dee2e6;
            border-radius: 6px;
            padding: 8px;
            color: #333;
        }

        QSpinBox:focus {
            border-color: #667eea;
        }

        QSpinBox::up-button {
            background: #e9ecef;
            border: 2px solid #adb5bd;
            width: 18px;
            border-top-right-radius: 4px;
            subcontrol-origin: border;
            subcontrol-position: top right;
        }

        QSpinBox::up-button:hover {
            background: #ced4da;
            border-color: #6c757d;
        }

        QSpinBox::up-button:pressed {
            background: #adb5bd;
        }

        QSpinBox::up-arrow {
            width: 0px;
            height: 0px;
            border-left: 5px solid transparent;
            border-right: 5px solid transparent;
            border-bottom: 7px solid #495057;
            margin: 2px;
        }

        QSpinBox::down-button {
            background: #e9ecef;
            border: 2px solid #adb5bd;
            width: 18px;
            border-bottom-right-radius: 4px;
            subcontrol-origin: border;
            subcontrol-position: bottom right;
        }

        QSpinBox::down-button:hover {
            background: #ced4da;
            border-color: #6c757d;
        }

        QSpinBox::down-button:pressed {
            background: #adb5bd;
        }

        QSpinBox::down-arrow {
            width: 0px;
            height: 0px;
            border-left: 5px solid transparent;
            border-right: 5px solid transparent;
            border-top: 7px solid #495057;
            margin: 2px;
        }

        QLabel {
            color: #333;
        }

        QRadioButton {
            color: #333;
            spacing: 8px;
        }

        QRadioButton::indicator {
            width: 16px;
            height: 16px;
            border-radius: 8px;
            border: 2px solid #dee2e6;
            background: white;
        }

        QRadioButton::indicator:hover {
            border-color: #667eea;
        }

        QRadioButton::indicator:checked {
            background: #667eea;
            border: 4px solid white;
            border-radius: 8px;
        }

        QRadioButton::indicator:checked:hover {
            background: #5a6fd8;
            border: 4px solid white;
            border-radius: 8px;
        }

        QCheckBox {
            color: #333;
            spacing: 8px;
        }

        QCheckBox::indicator {
            width: 16px;
            height: 16px;
            border: 2px solid #dee2e6;
            border-radius: 3px;
            background: white;
        }

        QCheckBox::indicator:checked {
            background: #667eea;
            border: 2px solid #667eea;
            color: white;
        }


        QCheckBox::indicator:hover {
            border-color: #667eea;
        }
        """
        dialog.setStyleSheet(style)

    def apply_dark_mode_styling(self):
        """Apply dark mode styling"""
        style = """
        QMainWindow {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #2c3e50, stop:1 #34495e);
        }

        #headerFrame {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #e74c3c, stop:1 #c0392b);
            border-radius: 15px;
            padding: 0px;
            margin: 0 0 0px 0;
        }

        #titleLabel {
            font-size: 24px;
            font-weight: bold;
            color: white;
            padding: 0px;
        }

        #timerFrame {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #2980b9, stop:1 #1f4e79);
            border-radius: 20px;
            padding: 0px;
            margin: 10px 0 10px 0;
            min-height: 120px;
            max-height: 180px;
            border: 2px solid #3498db;
        }

        #timeLabel {
            font-size: 36px;
            font-weight: bold;
            color: #ecf0f1;
            margin: 5px 0;
            padding: 3px;
            qproperty-alignment: AlignCenter;
        }

        #stateLabel {
            font-size: 14px;
            color: #bdc3c7;
            margin: 5px 0;
            padding: 3px;
            qproperty-alignment: AlignCenter;
        }

        #progressBar {
            height: 8px;
            border-radius: 4px;
            background-color: rgba(255, 255, 255, 0.2);
            margin: 10px 0 5px 0;
            border: 1px solid rgba(255, 255, 255, 0.1);
            min-width: 200px;
        }

        #progressBar::chunk {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #27ae60, stop:1 #2ecc71);
            border-radius: 4px;
        }

        #inputFrame {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #455a64, stop:1 #37474f);
            border-radius: 15px;
            padding: 0px;
            border: 2px solid #546e7a;
            min-height: 90px;
            margin: -px 0;
        }

        #inputLabel {
            font-size: 14px;
            font-weight: bold;
            color: #ecf0f1;
            min-width: 70px;
        }

        #projectCombo, #taskInput {
            padding: 0 0;
            border: 2px solid #546e7a;
            border-radius: 8px;
            font-size: 14px;
            background: #455a64;
            min-height: 25px;
            color: #ecf0f1;
        }

        #projectCombo {
            background: #455a64;
            selection-background-color: #5d6d7e;
            selection-color: white;
        }

        #projectCombo::drop-down {
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 24px;
            border-left: 2px solid #37474f;
            background: #546e7a;
            border-top-right-radius: 6px;
            border-bottom-right-radius: 6px;
        }

        #projectCombo::down-arrow {
            width: 0px;
            height: 0px;
            border-left: 6px solid transparent;
            border-right: 6px solid transparent;
            border-top: 8px solid #ecf0f1;
            margin: 5px;
        }

        #projectCombo QAbstractItemView {
            background: #455a64;
            border: 2px solid #5d6d7e;
            border-radius: 8px;
            selection-background-color: #5d6d7e;
            selection-color: white;
            color: #ecf0f1;
            padding: 5px;
        }

        #projectCombo QAbstractItemView::item {
            padding: 8px 12px;
            border: none;
            color: #ecf0f1;
        }

        #projectCombo QAbstractItemView::item:selected {
            background: #5d6d7e;
            color: white;
        }

        #projectCombo QAbstractItemView::item:hover {
            background: #4a5a68;
            color: white;
        }

        #projectCombo:focus, #taskInput:focus {
            border-color: #5d6d7e;
            outline: none;
        }

        #controlFrame {
            margin: 0px 0;
        }

        QPushButton {
            padding: 12px 20px;
            border-radius: 10px;
            font-size: 14px;
            font-weight: bold;
            border: none;
            min-height: 20px;
        }

        #startButton {
            background: #27ae60;
            color: white;
        }

        #startButton:hover {
            background: #229954;
        }

        #stopButton {
            background: #e74c3c;
            color: white;
        }

        #stopButton:hover {
            background: #c0392b;
        }

        #completeButton {
            background: #3498db;
            color: white;
        }

        #completeButton:hover {
            background: #2980b9;
        }

        #statusFrame {
            background: #455a64;
            border-radius: 15px;
            padding: 0px;
            border: 2px solid #546e7a;
            margin: 0px 0 0px 0;
        }

        #statsLabel {
            font-size: 14px;
            color: #bdc3c7;
            font-weight: 500;
        }

        QPushButton:disabled {
            background: #546e7a;
            color: #95a5a6;
        }
        """

        self.setStyleSheet(style)

    def apply_dark_dialog_styling(self, dialog):
        """Apply dark mode styling to a dialog"""
        style = """
        QDialog {
            background: #2c3e50;
            color: #ecf0f1;
        }

        QTabWidget::pane {
            background: #34495e;
            border: 1px solid #546e7a;
            border-radius: 8px;
        }

        QTabWidget::tab-bar {
            alignment: center;
        }

        QTabBar::tab {
            background: #455a64;
            color: #ecf0f1;
            padding: 8px 16px;
            margin-right: 2px;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
        }

        QTabBar::tab:selected {
            background: #34495e;
            border-bottom: 2px solid #5d6d7e;
        }

        QTabBar::tab:hover {
            background: #3c4f5c;
        }

        QGroupBox {
            font-weight: bold;
            border: 2px solid #546e7a;
            border-radius: 8px;
            margin-top: 12px;
            padding-top: 8px;
            background: #34495e;
        }

        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 8px 0 8px;
            background: #34495e;
            color: #ecf0f1;
        }

        QListWidget {
            background: #34495e;
            border: 1px solid #546e7a;
            border-radius: 8px;
            padding: 4px;
        }

        QListWidget::item {
            border-radius: 4px;
            padding: 4px;
            margin: 1px;
            color: #ecf0f1;
        }

        QListWidget::item:selected {
            background: #5d6d7e;
            color: white;
        }

        QListWidget::item:hover {
            background: #455a64;
        }

        QPushButton {
            background: #5d6d7e;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            font-weight: 500;
        }

        QPushButton:hover {
            background: #6c7b8b;
        }

        QPushButton:pressed {
            background: #4e5d6c;
        }

        QLineEdit {
            background: #455a64;
            border: 2px solid #546e7a;
            border-radius: 6px;
            padding: 8px;
            color: #ecf0f1;
        }

        QLineEdit:focus {
            border-color: #5d6d7e;
        }

        QComboBox {
            background: #455a64;
            border: 2px solid #546e7a;
            border-radius: 6px;
            padding: 8px;
            color: #ecf0f1;
        }

        QComboBox:focus {
            border-color: #5d6d7e;
        }

        QComboBox::drop-down {
            border: 1px solid #546e7a;
            border-left: none;
            width: 20px;
            background: #37474f;
            border-top-right-radius: 6px;
            border-bottom-right-radius: 6px;
        }

        QComboBox::drop-down:hover {
            background: #455a64;
        }

        QComboBox::down-arrow {
            image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTIiIGhlaWdodD0iOCIgdmlld0JveD0iMCAwIDEyIDgiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxwYXRoIGQ9Ik0xIDFMNiA2TDExIDEiIHN0cm9rZT0iI2VjZjBmMSIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiLz4KPC9zdmc+);
            width: 12px;
            height: 8px;
            margin: 2px;
        }

        QComboBox QAbstractItemView {
            background: #34495e;
            border: 2px solid #5d6d7e;
            border-radius: 6px;
            padding: 4px;
            color: #ecf0f1;
            selection-background-color: #5d6d7e;
            selection-color: white;
        }

        QComboBox QAbstractItemView::item {
            background: #34495e;
            color: #ecf0f1;
            padding: 8px;
            border: none;
            min-height: 20px;
        }

        QComboBox QAbstractItemView::item:selected {
            background: #5d6d7e;
            color: white;
        }

        QComboBox QAbstractItemView::item:hover {
            background: #455a64;
            color: #ecf0f1;
        }

        QSpinBox {
            background: #455a64;
            border: 2px solid #546e7a;
            border-radius: 6px;
            padding: 8px;
            color: #ecf0f1;
        }

        QSpinBox:focus {
            border-color: #5d6d7e;
        }

        QSpinBox::up-button {
            background: #546e7a;
            border: 2px solid #37474f;
            width: 18px;
            border-top-right-radius: 4px;
            subcontrol-origin: border;
            subcontrol-position: top right;
        }

        QSpinBox::up-button:hover {
            background: #607d8b;
            border-color: #455a64;
        }

        QSpinBox::up-button:pressed {
            background: #455a64;
        }

        QSpinBox::up-arrow {
            width: 0px;
            height: 0px;
            border-left: 5px solid transparent;
            border-right: 5px solid transparent;
            border-bottom: 7px solid #ecf0f1;
            margin: 2px;
        }

        QSpinBox::down-button {
            background: #546e7a;
            border: 2px solid #37474f;
            width: 18px;
            border-bottom-right-radius: 4px;
            subcontrol-origin: border;
            subcontrol-position: bottom right;
        }

        QSpinBox::down-button:hover {
            background: #607d8b;
            border-color: #455a64;
        }

        QSpinBox::down-button:pressed {
            background: #455a64;
        }

        QSpinBox::down-arrow {
            width: 0px;
            height: 0px;
            border-left: 5px solid transparent;
            border-right: 5px solid transparent;
            border-top: 7px solid #ecf0f1;
            margin: 2px;
        }

        QLabel {
            color: #ecf0f1;
        }

        QRadioButton {
            color: #ecf0f1;
            spacing: 8px;
        }

        QRadioButton::indicator {
            width: 16px;
            height: 16px;
            border-radius: 8px;
            border: 2px solid #546e7a;
            background: #455a64;
        }

        QRadioButton::indicator:hover {
            border-color: #5d6d7e;
        }

        QRadioButton::indicator:checked {
            background: #5d6d7e;
            border: 4px solid white;
            border-radius: 8px;
        }

        QRadioButton::indicator:checked:hover {
            background: #6c7b8b;
            border: 4px solid white;
            border-radius: 8px;
        }

        QCheckBox {
            color: #ecf0f1;
            spacing: 8px;
        }

        QCheckBox::indicator {
            width: 16px;
            height: 16px;
            border: 2px solid #546e7a;
            border-radius: 3px;
            background: #455a64;
        }

        QCheckBox::indicator:checked {
            background: #5d6d7e;
            border: 2px solid #5d6d7e;
            color: white;
        }


        QCheckBox::indicator:hover {
            border-color: #6c7b8b;
        }
        """
        dialog.setStyleSheet(style)

    def apply_compact_styling(self):
        """Apply compact mode styling based on current theme"""
        if self.theme_mode == "dark" or (self.theme_mode == "system" and self.detect_system_dark_theme("compact")):
            self.apply_compact_dark_styling()
        else:
            self.apply_compact_light_styling()

    def apply_compact_light_styling(self):
        """Apply light mode compact styling"""
        compact_style = """
        QMainWindow {
            background: #f8f9fa;
        }

        #timerFrame {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #87ceeb, stop:1 #4682b4);
            border-radius: 12px;
            padding: 8px;
            margin: 3px;
            min-height: 70px;
            max-height: 80px;
        }

        #timeLabel {
            font-size: 24px;
            font-weight: bold;
            color: white;
            margin: 2px 0;
            padding: 2px;
            qproperty-alignment: AlignCenter;
        }

        #stateLabel {
            font-size: 9px;
            color: #e8f4f8;
            margin: 1px 0;
            padding: 1px;
            qproperty-alignment: AlignCenter;
        }

        #progressBar {
            height: 4px;
            border-radius: 2px;
            background-color: rgba(255, 255, 255, 0.3);
            margin: 2px 0;
            border: none;
        }

        #progressBar::chunk {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #56ab2f, stop:1 #a8e6cf);
            border-radius: 2px;
        }
        """
        self.setStyleSheet(compact_style)

    def apply_compact_dark_styling(self):
        """Apply dark mode compact styling"""
        compact_style = """
        QMainWindow {
            background: #2c3e50;
        }

        #timerFrame {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #2980b9, stop:1 #1f4e79);
            border-radius: 12px;
            padding: 8px;
            margin: 3px;
            min-height: 70px;
            max-height: 80px;
            border: 2px solid #3498db;
        }

        #timeLabel {
            font-size: 24px;
            font-weight: bold;
            color: #ecf0f1;
            margin: 2px 0;
            padding: 2px;
            qproperty-alignment: AlignCenter;
        }

        #stateLabel {
            font-size: 9px;
            color: #bdc3c7;
            margin: 1px 0;
            padding: 1px;
            qproperty-alignment: AlignCenter;
        }

        #progressBar {
            height: 4px;
            border-radius: 2px;
            background-color: rgba(255, 255, 255, 0.2);
            margin: 2px 0;
            border: none;
        }

        #progressBar::chunk {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #5d6d7e, stop:1 #7f8c8d);
            border-radius: 2px;
        }
        """
        self.setStyleSheet(compact_style)

    def load_projects(self):
        """Load projects from database"""
        try:
            projects = self.db_manager.get_active_projects()
            self.project_combo.clear()
            debug_print(f"Found {len(projects)} active projects")

            for project in projects:
                debug_print(f"Adding project: {project.name}")
                trace_print(f"Project details: ID={project.id}, Color={project.color}, Active={project.active}")
                self.project_combo.addItem(project.name, project.id)

            if not projects:
                debug_print("No projects found, creating default")
                # Add a default project
                default_project = self.db_manager.create_project("General", "#667eea")
                self.project_combo.addItem(default_project.name, default_project.id)
                info_print(f"Created default project: {default_project.name}")

            debug_print(f"Project combo has {self.project_combo.count()} items")

            # Set default selection to first project if available
            if self.project_combo.count() > 0:
                self.project_combo.setCurrentIndex(0)
                debug_print(f"Set default project selection: {self.project_combo.currentText()} (ID: {self.project_combo.currentData()})")
        except Exception as e:
            error_print(f"Error loading projects: {e}")
            # Add fallback option
            self.project_combo.addItem("Default Project", 1)

    def toggle_timer(self):
        """Start or pause the timer"""
        debug_print(f"Toggle timer called, current state: {self.pomodoro_timer.state}")
        trace_print(f"Timer remaining: {self.pomodoro_timer.get_time_remaining()}s, Task: {self.current_task_description}")

        if self.pomodoro_timer.state == TimerState.STOPPED:
            # Start new sprint
            self.current_project_id = self.project_combo.currentData()
            self.current_task_description = self.task_input.text().strip() or None

            debug_print(f"Sprint started - Project ID: {self.current_project_id}, Task: '{self.current_task_description}'")
            self.pomodoro_timer.start_sprint()
            self.qt_timer.start(1000)  # Update every second
            self.start_button.setText("Pause")
            self.stop_button.setEnabled(True)
            self.complete_button.setEnabled(True)  # Enable complete button during timer
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
            self.state_label.setText("Focus Time! 🎯")
            remaining_after = self.pomodoro_timer.get_time_remaining()
            debug_print(f"Time remaining after resume: {remaining_after}")

            # Auto-enter compact mode if enabled
            if self.auto_compact_mode and not self.compact_mode:
                self.toggle_compact_mode()

    def stop_timer(self):
        """Stop the current timer"""
        self.pomodoro_timer.stop()
        self.qt_timer.stop()
        self.reset_ui()

    def emit_sprint_complete(self):
        """Thread-safe method called from background timer thread"""
        self.sprint_completed.emit()

    def handle_sprint_complete(self):
        """Main thread handler for sprint completion"""
        info_print("Sprint completed - playing alarm and starting break")

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

        # Update UI to show break state (this happens automatically in timer)
        # The timer already transitions to BREAK state automatically

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

        # Auto-complete the sprint (now safe to call from main thread)
        self.complete_sprint()

    def complete_sprint(self):
        """Complete the current sprint"""
        debug_print("Complete sprint called!")
        debug_print(f"Current project_id: {self.current_project_id}")
        debug_print(f"Current task_description: '{self.current_task_description}'")
        debug_print(f"Timer state: {self.pomodoro_timer.get_state()}")
        debug_print(f"Timer remaining: {self.pomodoro_timer.get_time_remaining()}")

        try:
            # Save sprint to database
            if self.current_project_id is not None:
                debug_print(f"✓ Validation passed - saving sprint: {self.current_task_description} for project {self.current_project_id}")

                # Get project name from ID
                project = self.db_manager.get_project_by_id(self.current_project_id)
                project_name = project.name if project else "Unknown"
                debug_print(f"Project name resolved: {project_name}")

                # Calculate actual start time based on timer duration
                actual_duration = self.pomodoro_timer.sprint_duration - self.pomodoro_timer.get_time_remaining()
                start_time = datetime.now() - timedelta(seconds=actual_duration)
                debug_print(f"Calculated duration: {actual_duration}s, start_time: {start_time}")

                # Ensure task description is not None
                task_desc = self.current_task_description or "Pomodoro Sprint"

                sprint = Sprint(
                    project_name=project_name,
                    task_description=task_desc,
                    start_time=start_time,
                    end_time=datetime.now(),
                    completed=True,
                    duration_minutes=int(actual_duration / 60),
                    planned_duration=int(self.pomodoro_timer.sprint_duration / 60)
                )
                debug_print(f"Created sprint object: {sprint.task_description}, duration: {actual_duration}s")

                # Save to database
                debug_print("Calling db_manager.add_sprint()...")
                self.db_manager.add_sprint(sprint)
                info_print("✓ Sprint saved to database successfully")

                # Verify it was saved
                from datetime import date
                today_sprints = self.db_manager.get_sprints_by_date(date.today())
                debug_print(f"Verification: {len(today_sprints)} sprints now in database for today")

            else:
                error_print(f"❌ Cannot save sprint - no project selected (project_id: {self.current_project_id})")

            self.pomodoro_timer.stop()
            self.qt_timer.stop()
            self.reset_ui()
            self.state_label.setText("Sprint Completed! 🎉")
            self.update_stats()
            debug_print("Sprint completion finished")
        except Exception as e:
            error_print(f"Error completing sprint: {e}")
            import traceback
            traceback.print_exc()  # Full error trace
            self.pomodoro_timer.stop()
            self.qt_timer.stop()
            self.reset_ui()

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
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)  # Ensure progress bar is visible

        # Set timer display to current sprint duration
        sprint_minutes = self.pomodoro_timer.sprint_duration // 60
        self.time_label.setText(f"{sprint_minutes:02d}:00")
        self.state_label.setText("Ready to Focus")

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
        # Hide everything except timer
        self.centralWidget().findChild(QFrame, "headerFrame").hide()
        self.centralWidget().findChild(QFrame, "inputFrame").hide()
        self.centralWidget().findChild(QFrame, "controlFrame").hide()
        self.centralWidget().findChild(QFrame, "statusFrame").hide()

        # Resize window first
        self.setFixedSize(*self.compact_size)
        self.compact_action.setText('Exit Compact Mode')

        # Apply compact styling based on current theme
        self.apply_compact_styling()

        # Adjust layout spacing for compact mode
        timer_frame = self.centralWidget().findChild(QFrame, "timerFrame")
        if timer_frame and timer_frame.layout():
            timer_frame.layout().setSpacing(2)
            timer_frame.layout().setContentsMargins(8, 6, 8, 6)

    def exit_compact_mode(self):
        """Exit compact mode and restore normal layout"""
        # Restore window size first
        self.setFixedSize(*self.normal_size)
        self.compact_action.setText('Toggle Compact Mode')

        # Show all elements
        self.centralWidget().findChild(QFrame, "headerFrame").show()
        self.centralWidget().findChild(QFrame, "inputFrame").show()
        self.centralWidget().findChild(QFrame, "controlFrame").show()
        self.centralWidget().findChild(QFrame, "statusFrame").show()

        # Restore layout spacing
        timer_frame = self.centralWidget().findChild(QFrame, "timerFrame")
        if timer_frame and timer_frame.layout():
            timer_frame.layout().setSpacing(10)
            timer_frame.layout().setContentsMargins(11, 11, 11, 11)

        # Reapply normal styling completely
        self.apply_modern_styling()

        # Force update to ensure everything displays correctly
        self.update()
        self.repaint()

    def export_to_excel(self):
        """Export data to Excel file"""
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        try:
            # Get save location
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export to Excel",
                f"pomodora_export_{datetime.now().strftime('%Y%m%d')}.xlsx",
                "Excel Files (*.xlsx)"
            )

            if file_path:
                from tracking.excel_export import ExcelExporter
                exporter = ExcelExporter(self.db_manager)
                exporter.export_all_data(file_path)

                QMessageBox.information(self, "Export Complete",
                                      f"Data exported successfully to:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export data:\n{str(e)}")

    def open_data_viewer(self):
        """Open data viewer window"""
        try:
            from gui.pyside_data_viewer import PySideDataViewerWindow
            self.data_viewer = PySideDataViewerWindow(self, self.db_manager)
            self.data_viewer.show()
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error", f"Failed to open data viewer:\n{str(e)}")

    def manage_activity_classifications(self):
        """Open comprehensive activity classifications dialog"""
        from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
                                     QLabel, QListWidget, QMessageBox, QGroupBox, QGridLayout,
                                     QListWidgetItem, QColorDialog, QTabWidget, QWidget, QFrame,
                                     QCheckBox, QSplitter)
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QColor, QPalette

        dialog = QDialog(self)
        dialog.setWindowTitle("Activity Classifications")
        dialog.setFixedSize(800, 600)

        # Apply current theme styling to dialog
        self.apply_dialog_styling(dialog)

        main_layout = QVBoxLayout(dialog)

        # Create tab widget for Categories and Projects
        tab_widget = QTabWidget()

        # Categories Tab
        categories_tab = QWidget()
        categories_layout = QHBoxLayout(categories_tab)

        # Categories - Left panel (list)
        cat_left_widget = QWidget()
        cat_left_layout = QVBoxLayout(cat_left_widget)
        cat_left_layout.addWidget(QLabel("Current Categories:"))

        self.category_list = QListWidget()
        self.category_list.itemClicked.connect(self.on_category_selected)
        self.refresh_category_list()
        cat_left_layout.addWidget(self.category_list)

        # Category actions
        cat_actions = QHBoxLayout()
        cat_edit_button = QPushButton("Edit")
        cat_edit_button.clicked.connect(self.edit_selected_category)
        cat_toggle_button = QPushButton("Toggle Active")
        cat_toggle_button.clicked.connect(self.toggle_category_active)
        cat_delete_button = QPushButton("Delete")
        cat_delete_button.clicked.connect(self.delete_selected_category)

        cat_actions.addWidget(cat_edit_button)
        cat_actions.addWidget(cat_toggle_button)
        cat_actions.addWidget(cat_delete_button)
        cat_left_layout.addLayout(cat_actions)

        categories_layout.addWidget(cat_left_widget)

        # Categories - Right panel (add new)
        cat_right_widget = self.create_add_category_panel()
        categories_layout.addWidget(cat_right_widget)

        tab_widget.addTab(categories_tab, "Categories")

        # Projects Tab
        projects_tab = QWidget()
        projects_layout = QHBoxLayout(projects_tab)

        # Projects - Left panel (list)
        proj_left_widget = QWidget()
        proj_left_layout = QVBoxLayout(proj_left_widget)
        proj_left_layout.addWidget(QLabel("Current Projects:"))

        self.project_list = QListWidget()
        self.project_list.itemClicked.connect(self.on_project_selected)
        self.refresh_project_list()
        proj_left_layout.addWidget(self.project_list)

        # Project actions
        proj_actions = QHBoxLayout()
        proj_edit_button = QPushButton("Edit")
        proj_edit_button.clicked.connect(self.edit_selected_project)
        proj_toggle_button = QPushButton("Toggle Active")
        proj_toggle_button.clicked.connect(self.toggle_project_active)
        proj_delete_button = QPushButton("Delete")
        proj_delete_button.clicked.connect(self.delete_selected_project)

        proj_actions.addWidget(proj_edit_button)
        proj_actions.addWidget(proj_toggle_button)
        proj_actions.addWidget(proj_delete_button)
        proj_left_layout.addLayout(proj_actions)

        projects_layout.addWidget(proj_left_widget)

        # Projects - Right panel (add new)
        proj_right_widget = self.create_add_project_panel()
        projects_layout.addWidget(proj_right_widget)

        tab_widget.addTab(projects_tab, "Projects")

        main_layout.addWidget(tab_widget)

        # Close button
        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        main_layout.addWidget(close_button)

        if dialog.exec():
            self.load_projects()


    def refresh_project_list(self):
        """Refresh the project list with visual color indicators"""
        from PySide6.QtWidgets import QListWidgetItem, QWidget, QHBoxLayout, QLabel
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QColor

        self.project_list.clear()
        try:
            projects = self.db_manager.get_all_projects()
            debug_print(f"Found {len(projects)} projects")
            for project in projects:
                debug_print(f"Project: {project.name}, Color: {project.color}, Active: {project.active}")

                # Create custom widget for each project with prominent color indicator
                widget = QWidget()
                layout = QHBoxLayout(widget)
                layout.setContentsMargins(5, 6, 5, 6)  # Increased vertical margins

                # Color indicator (larger square)
                color_label = QLabel()
                color_label.setFixedSize(16, 16)
                if project.active:
                    color_label.setStyleSheet(f"background-color: {project.color}; border: 1px solid #333; border-radius: 2px;")
                    text_label = QLabel(project.name)
                else:
                    color_label.setStyleSheet(f"background-color: {project.color}; border: 1px solid #333; border-radius: 2px; opacity: 0.5;")
                    text_label = QLabel(f"{project.name} (inactive)")
                    text_label.setStyleSheet("color: #888;")

                # Project name (normal text color) - fix clipping by removing height constraints
                from PySide6.QtGui import QFont
                font = QFont()
                font.setPointSize(10)  # Slightly larger point size
                text_label.setFont(font)
                text_label.setStyleSheet(text_label.styleSheet())  # Keep color styling only

                # Set text eliding to clip long text with ellipsis
                from PySide6.QtCore import Qt
                from PySide6.QtGui import QFontMetrics
                text_label.setWordWrap(False)
                text_label.setTextInteractionFlags(Qt.NoTextInteraction)
                text_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)  # Center vertically
                # Remove fixed height - let the label size itself

                # Calculate available width and elide text if needed
                available_width = 200  # Approximate available width in the list
                font_metrics = text_label.fontMetrics()
                elided_text = font_metrics.elidedText(text_label.text(), Qt.ElideRight, available_width)
                text_label.setText(elided_text)

                layout.addWidget(color_label)
                layout.addWidget(text_label, 1)  # Give text label stretch factor to take available space

                # Create list item and set custom widget
                item = QListWidgetItem()
                item.setData(Qt.UserRole, project)
                # Set explicit size hint to ensure enough vertical space
                from PySide6.QtCore import QSize
                item.setSizeHint(QSize(widget.sizeHint().width(), 32))

                self.project_list.addItem(item)
                self.project_list.setItemWidget(item, widget)

        except Exception as e:
            error_print(f"Error loading projects: {e}")
            import traceback
            traceback.print_exc()

    def select_color(self, color):
        """Select a color from the palette"""
        self.selected_color = color
        self.color_preview.setStyleSheet(f"background-color: {color}; border: 1px solid #333;")
        self.hex_input.setText(color)

        # Update button borders to show selection
        for btn in self.color_buttons:
            btn.setStyleSheet(btn.styleSheet().replace("border: 3px solid #000;", "border: 2px solid #333;"))

        # Highlight selected button
        for btn in self.color_buttons:
            if color.lower() in btn.styleSheet().lower():
                btn.setStyleSheet(btn.styleSheet().replace("border: 2px solid #333;", "border: 3px solid #000;"))
                break

    def on_hex_changed(self):
        """Handle manual hex input changes"""
        hex_color = self.hex_input.text()
        if len(hex_color) == 7 and hex_color.startswith('#'):
            try:
                # Validate hex color
                QColor(hex_color)
                self.selected_color = hex_color
                self.color_preview.setStyleSheet(f"background-color: {hex_color}; border: 1px solid #333;")
            except:
                pass

    def open_color_dialog(self):
        """Open Qt color picker dialog"""
        from PySide6.QtWidgets import QColorDialog
        color = QColorDialog.getColor(QColor(self.selected_color), self, "Choose Color")
        if color.isValid():
            hex_color = color.name()
            self.select_color(hex_color)

    def add_new_project_advanced(self):
        """Add a new project with selected color and category"""
        name = self.new_project_input.text().strip()
        if not name:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Error", "Please enter a project name.")
            return

        # Get selected category
        if self.project_category_combo.currentData() is None:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Error", "Please select a category for the project.")
            return

        try:
            category_id = self.project_category_combo.currentData()
            selected_color = getattr(self, "project_selected_color", "#3498db")
            self.db_manager.create_project(name, category_id, selected_color)
            self.refresh_project_list()
            self.load_projects()  # Refresh main window dropdown
            self.new_project_input.clear()
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error", f"Failed to add project: {str(e)}")

    def on_project_selected(self, item):
        """Handle project selection"""
        from PySide6.QtCore import Qt
        project = item.data(Qt.UserRole)
        if project:
            self.selected_project = project

    def edit_selected_project(self):
        """Edit the selected project"""
        if not hasattr(self, 'selected_project'):
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Error", "Please select a project to edit.")
            return

        # TODO: Implement project editing dialog
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(self, "Info", "Project editing will be implemented in a future update.")

    def toggle_project_active(self):
        """Toggle active status of selected project"""
        if not hasattr(self, 'selected_project'):
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Error", "Please select a project to toggle.")
            return

        try:
            project = self.selected_project
            new_status = self.db_manager.toggle_project_active(project.id)

            if new_status is not None:
                status_text = "active" if new_status else "inactive"
                self.refresh_project_list()  # Refresh the activity classifications display
                self.load_projects()  # Refresh the main window dropdown
            else:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Error", "Failed to toggle project status.")

        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error", f"Failed to toggle project: {str(e)}")

    def delete_selected_project(self):
        """Delete the selected project"""
        if not hasattr(self, 'selected_project'):
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Error", "Please select a project to delete.")
            return

        try:
            project = self.selected_project

            # Confirm deletion
            from PySide6.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                self,
                "Confirm Deletion",
                f"Are you sure you want to delete project '{project.name}'?\n\nThis action cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                success, message = self.db_manager.delete_project(project.id)

                if success:
                    self.refresh_project_list()  # Refresh the activity classifications display
                    self.load_projects()  # Refresh the main window dropdown
                    # Clear selection since project is deleted
                    if hasattr(self, 'selected_project'):
                        delattr(self, 'selected_project')
                else:
                    QMessageBox.warning(self, "Cannot Delete", message)

        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error", f"Failed to delete project: {str(e)}")

    # Category management methods
    def refresh_category_list(self):
        """Refresh the category list with visual color indicators"""
        from PySide6.QtWidgets import QListWidgetItem, QWidget, QHBoxLayout, QLabel
        from PySide6.QtCore import Qt

        self.category_list.clear()
        try:
            categories = self.db_manager.get_all_categories()
            debug_print(f"Found {len(categories)} categories")
            for category in categories:
                debug_print(f"Category: {category.name}, Color: {category.color}, Active: {category.active}")

                # Create custom widget for each category with prominent color indicator
                widget = QWidget()
                layout = QHBoxLayout(widget)
                layout.setContentsMargins(5, 6, 5, 6)  # Increased vertical margins

                # Color indicator (larger square)
                color_label = QLabel()
                color_label.setFixedSize(16, 16)
                if category.active:
                    color_label.setStyleSheet(f"background-color: {category.color}; border: 1px solid #333; border-radius: 2px;")
                    text_label = QLabel(category.name)
                else:
                    color_label.setStyleSheet(f"background-color: {category.color}; border: 1px solid #333; border-radius: 2px; opacity: 0.5;")
                    text_label = QLabel(f"{category.name} (inactive)")
                    text_label.setStyleSheet("color: #888;")

                # Category name (normal text color) - fix clipping by removing height constraints
                from PySide6.QtGui import QFont
                font = QFont()
                font.setPointSize(10)  # Slightly larger point size
                text_label.setFont(font)
                text_label.setStyleSheet(text_label.styleSheet())  # Keep color styling only

                # Set text eliding to clip long text with ellipsis
                from PySide6.QtCore import Qt
                from PySide6.QtGui import QFontMetrics
                text_label.setWordWrap(False)
                text_label.setTextInteractionFlags(Qt.NoTextInteraction)
                text_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)  # Center vertically
                # Remove fixed height - let the label size itself

                # Calculate available width and elide text if needed
                available_width = 200  # Approximate available width in the list
                font_metrics = text_label.fontMetrics()
                elided_text = font_metrics.elidedText(text_label.text(), Qt.ElideRight, available_width)
                text_label.setText(elided_text)

                layout.addWidget(color_label)
                layout.addWidget(text_label, 1)  # Give text label stretch factor to take available space

                # Create list item and set custom widget
                item = QListWidgetItem()
                item.setData(Qt.UserRole, category)
                # Set explicit size hint to ensure enough vertical space
                from PySide6.QtCore import QSize
                item.setSizeHint(QSize(widget.sizeHint().width(), 32))

                self.category_list.addItem(item)
                self.category_list.setItemWidget(item, widget)

        except Exception as e:
            error_print(f"Error loading categories: {e}")
            import traceback
            traceback.print_exc()

    def on_category_selected(self, item):
        """Handle category selection"""
        from PySide6.QtCore import Qt
        category = item.data(Qt.UserRole)
        if category:
            self.selected_category = category

    def edit_selected_category(self):
        """Edit the selected category"""
        if not hasattr(self, 'selected_category'):
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Error", "Please select a category to edit.")
            return

        # TODO: Implement category editing dialog
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(self, "Info", "Category editing will be implemented in a future update.")

    def toggle_category_active(self):
        """Toggle active status of selected category"""
        if not hasattr(self, 'selected_category'):
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Error", "Please select a category to toggle.")
            return

        try:
            category = self.selected_category
            new_status = self.db_manager.toggle_category_active(category.id)

            if new_status is not None:
                self.refresh_category_list()  # Refresh the category display
                self.load_projects()  # Refresh the main window dropdown
            else:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Error", "Failed to toggle category status.")

        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error", f"Failed to toggle category: {str(e)}")

    def delete_selected_category(self):
        """Delete the selected category"""
        if not hasattr(self, 'selected_category'):
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Error", "Please select a category to delete.")
            return

        try:
            category = self.selected_category

            # Confirm deletion
            from PySide6.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                self,
                "Confirm Deletion",
                f"Are you sure you want to delete category '{category.name}' and all its projects?\n\nThis action cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                success, message = self.db_manager.delete_category(category.id)

                if success:
                    self.refresh_category_list()  # Refresh the category display
                    self.refresh_project_list()  # Refresh the project display
                    self.load_projects()  # Refresh the main window dropdown
                    # Clear selection since category is deleted
                    if hasattr(self, 'selected_category'):
                        delattr(self, 'selected_category')
                else:
                    QMessageBox.warning(self, "Cannot Delete", message)

        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error", f"Failed to delete category: {str(e)}")

    def create_add_category_panel(self):
        """Create the add category panel"""
        from PySide6.QtWidgets import QWidget, QVBoxLayout, QGroupBox, QHBoxLayout, QLineEdit, QLabel, QPushButton

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        # Add new category section
        add_group = QGroupBox("Add New Category")
        add_layout = QVBoxLayout(add_group)

        # Category name
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Name:"))
        self.new_category_input = QLineEdit()
        name_layout.addWidget(self.new_category_input)
        add_layout.addLayout(name_layout)

        # Color selection (reuse the color palette)
        color_section = self.create_color_selector("category")
        add_layout.addWidget(color_section)

        # Add button
        add_button = QPushButton("Add Category")
        add_button.clicked.connect(self.add_new_category)
        add_layout.addWidget(add_button)

        right_layout.addWidget(add_group)
        right_layout.addStretch()

        return right_widget

    def create_add_project_panel(self):
        """Create the add project panel"""
        from PySide6.QtWidgets import QWidget, QVBoxLayout, QGroupBox, QHBoxLayout, QLineEdit, QLabel, QPushButton, QComboBox

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        # Add new project section
        add_group = QGroupBox("Add New Project")
        add_layout = QVBoxLayout(add_group)

        # Project name
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Name:"))
        self.new_project_input = QLineEdit()
        name_layout.addWidget(self.new_project_input)
        add_layout.addLayout(name_layout)

        # Category selection
        category_layout = QHBoxLayout()
        category_layout.addWidget(QLabel("Category:"))
        self.project_category_combo = QComboBox()
        self.load_categories_for_project()
        category_layout.addWidget(self.project_category_combo)
        add_layout.addLayout(category_layout)

        # Color selection (reuse the color palette)
        color_section = self.create_color_selector("project")
        add_layout.addWidget(color_section)

        # Add button
        add_button = QPushButton("Add Project")
        add_button.clicked.connect(self.add_new_project_advanced)
        add_layout.addWidget(add_button)

        right_layout.addWidget(add_group)
        right_layout.addStretch()

        return right_widget

    def create_color_selector(self, prefix):
        """Create the color selection widget"""
        from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton, QLineEdit, QGroupBox, QGridLayout

        color_widget = QWidget()
        color_layout = QVBoxLayout(color_widget)

        # Color selection label
        color_label = QLabel("Choose Color:")
        color_layout.addWidget(color_label)

        # Color palette grid
        palette_layout = QGridLayout()
        setattr(self, f"{prefix}_selected_color", "#3498db")  # Default blue
        setattr(self, f"{prefix}_color_buttons", [])

        # Primary colors and distinct grays with yellow variations
        colors = [
            "#e74c3c", "#3498db", "#2ecc71", "#f39c12", "#9b59b6", "#1abc9c",  # Primary colors
            "#e67e22", "#34495e", "#95a5a6", "#16a085", "#f1c40f", "#27ae60",  # More colors with yellow
            "#2c3e50", "#7f8c8d", "#bdc3c7", "#ecf0f1", "#454545", "#f7dc6f"   # Grays with light yellow
        ]

        for i, color in enumerate(colors):
            row, col = divmod(i, 6)
            color_btn = QPushButton()
            color_btn.setFixedSize(20, 20)
            color_btn.setMinimumSize(20, 20)
            color_btn.setMaximumSize(20, 20)
            color_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color};
                    border: 1px solid #333;
                    border-radius: 2px;
                    min-height: 20px;
                    max-height: 20px;
                    height: 20px;
                    min-width: 20px;
                    max-width: 20px;
                    width: 20px;
                    margin: 0px;
                    padding: 0px;
                }}
            """)
            color_btn.clicked.connect(lambda checked, c=color, p=prefix: self.select_color_for_type(c, p))
            getattr(self, f"{prefix}_color_buttons").append(color_btn)
            palette_layout.addWidget(color_btn, row, col)

        palette_layout.setSpacing(2)
        palette_layout.setContentsMargins(0, 0, 0, 0)

        palette_widget = QWidget()
        palette_widget.setLayout(palette_layout)
        color_layout.addWidget(palette_widget)

        # Color preview section
        preview_layout = QHBoxLayout()
        preview_layout.addWidget(QLabel("Selected:"))

        color_preview = QFrame()
        color_preview.setFixedSize(40, 30)
        color_preview.setStyleSheet(f"background-color: #3498db; border: 1px solid #333;")
        setattr(self, f"{prefix}_color_preview", color_preview)
        preview_layout.addWidget(color_preview)

        custom_color_btn = QPushButton("Custom...")
        custom_color_btn.clicked.connect(lambda: self.open_color_dialog_for_type(prefix))
        preview_layout.addWidget(custom_color_btn)
        preview_layout.addStretch()

        color_layout.addWidget(QWidget())  # Spacer
        color_layout.addLayout(preview_layout)

        return color_widget

    def select_color_for_type(self, color, prefix):
        """Select a color for a specific type (category or project)"""
        setattr(self, f"{prefix}_selected_color", color)
        color_preview = getattr(self, f"{prefix}_color_preview")
        color_preview.setStyleSheet(f"background-color: {color}; border: 1px solid #333;")

    def open_color_dialog_for_type(self, prefix):
        """Open Qt color picker dialog for a specific type"""
        from PySide6.QtWidgets import QColorDialog
        from PySide6.QtGui import QColor

        current_color = getattr(self, f"{prefix}_selected_color")
        color = QColorDialog.getColor(QColor(current_color), self, "Choose Color")
        if color.isValid():
            hex_color = color.name()
            self.select_color_for_type(hex_color, prefix)

    def load_categories_for_project(self):
        """Load categories into the project category combo box"""
        self.project_category_combo.clear()
        try:
            categories = self.db_manager.get_active_categories()
            for category in categories:
                self.project_category_combo.addItem(category.name, category.id)
        except Exception as e:
            error_print(f"Error loading categories: {e}")

    def add_new_category(self):
        """Add a new category"""
        name = self.new_category_input.text().strip()
        if not name:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Error", "Please enter a category name.")
            return

        try:
            selected_color = getattr(self, "category_selected_color", "#3498db")
            self.db_manager.create_category(name, selected_color)
            self.refresh_category_list()
            self.refresh_project_list()  # Refresh projects since new auto-project was created
            self.load_projects()  # Refresh main window dropdown
            self.load_categories_for_project()  # Refresh category dropdown for projects
            self.new_category_input.clear()
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error", f"Failed to add category: {str(e)}")

    def open_settings(self):
        """Open settings dialog with theme, timer, and database options"""
        from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QSpinBox,
                                     QLabel, QMessageBox, QComboBox, QLineEdit, QFileDialog,
                                     QRadioButton, QButtonGroup, QGroupBox)

        dialog = QDialog(self)
        dialog.setWindowTitle("Settings")
        dialog.setFixedSize(650, 600)  # Increased size for alarm settings with browse buttons

        # Apply current theme styling to dialog
        self.apply_dialog_styling(dialog)

        layout = QVBoxLayout(dialog)

        # Load current settings from local config
        from tracking.local_settings import get_local_settings
        settings = get_local_settings()
        current_theme = settings.get("theme_mode", "light")
        current_sprint = settings.get("sprint_duration", 25)
        current_break = settings.get("break_duration", 5)
        current_auto_compact = settings.get("auto_compact_mode", True)
        current_volume = settings.get("alarm_volume", 0.7)
        current_sprint_alarm = settings.get("sprint_alarm", "gentle_chime")
        current_break_alarm = settings.get("break_alarm", "urgent_alert")
        current_db_type = settings.get("database_type", "local")
        current_db_path = settings.get("database_local_path", "")
        current_credentials = settings.get("google_credentials_path", "credentials.json")
        current_gdrive_folder = settings.get("google_drive_folder", "TimeTracking")

        # Theme selection
        theme_layout = QHBoxLayout()
        theme_layout.addWidget(QLabel("Theme:"))
        theme_combo = QComboBox()
        theme_combo.addItems(["Light", "Dark", "System"])
        # Set current theme
        theme_index = {"light": 0, "dark": 1, "system": 2}.get(current_theme, 0)
        theme_combo.setCurrentIndex(theme_index)
        theme_layout.addWidget(theme_combo)
        layout.addLayout(theme_layout)

        # Sprint duration
        sprint_layout = QHBoxLayout()
        sprint_layout.addWidget(QLabel("Sprint Duration (minutes):"))
        sprint_spin = QSpinBox()
        sprint_spin.setRange(1, 60)
        sprint_spin.setValue(current_sprint)
        sprint_layout.addWidget(sprint_spin)
        layout.addLayout(sprint_layout)

        # Break duration
        break_layout = QHBoxLayout()
        break_layout.addWidget(QLabel("Break Duration (minutes):"))
        break_spin = QSpinBox()
        break_spin.setRange(1, 30)
        break_spin.setValue(current_break)
        break_layout.addWidget(break_spin)
        layout.addLayout(break_layout)

        # Auto-compact mode
        from PySide6.QtWidgets import QCheckBox, QSlider
        auto_compact_layout = QHBoxLayout()
        auto_compact_checkbox = QCheckBox("Auto-enter compact mode when sprint starts")
        auto_compact_checkbox.setChecked(current_auto_compact)
        auto_compact_layout.addWidget(auto_compact_checkbox)
        layout.addLayout(auto_compact_layout)

        # Alarm Settings
        alarm_group = QGroupBox("Alarm Settings")
        alarm_group_layout = QVBoxLayout(alarm_group)

        # Volume slider
        volume_layout = QHBoxLayout()
        volume_layout.addWidget(QLabel("Volume:"))
        volume_slider = QSlider(Qt.Horizontal)
        volume_slider.setRange(0, 100)
        volume_slider.setValue(int(current_volume * 100))
        volume_value_label = QLabel(f"{int(current_volume * 100)}%")
        volume_slider.valueChanged.connect(lambda v: volume_value_label.setText(f"{v}%"))
        volume_layout.addWidget(volume_slider)
        volume_layout.addWidget(volume_value_label)
        alarm_group_layout.addLayout(volume_layout)

        # Import available alarms
        from audio.alarm import get_available_alarms
        available_alarms = get_available_alarms()

        # Sprint completion alarm
        sprint_alarm_layout = QHBoxLayout()
        sprint_alarm_layout.addWidget(QLabel("Sprint Complete:"))
        sprint_alarm_combo = QComboBox()
        for alarm_key, alarm_info in available_alarms.items():
            sprint_alarm_combo.addItem(alarm_info["name"], alarm_key)
        # Set current selection
        sprint_index = sprint_alarm_combo.findData(current_sprint_alarm)
        if sprint_index >= 0:
            sprint_alarm_combo.setCurrentIndex(sprint_index)
        sprint_alarm_layout.addWidget(sprint_alarm_combo)

        # Browse button for custom sound file
        browse_sprint_btn = QPushButton("Browse...")
        browse_sprint_btn.clicked.connect(lambda: self.browse_sound_file(sprint_alarm_combo))
        sprint_alarm_layout.addWidget(browse_sprint_btn)

        # Test button for sprint alarm
        test_sprint_btn = QPushButton("Test")
        test_sprint_btn.clicked.connect(lambda: self.test_alarm_sound(
            sprint_alarm_combo.currentData(), volume_slider.value() / 100.0
        ))
        sprint_alarm_layout.addWidget(test_sprint_btn)
        alarm_group_layout.addLayout(sprint_alarm_layout)

        # Break completion alarm
        break_alarm_layout = QHBoxLayout()
        break_alarm_layout.addWidget(QLabel("Break Complete:"))
        break_alarm_combo = QComboBox()
        for alarm_key, alarm_info in available_alarms.items():
            break_alarm_combo.addItem(alarm_info["name"], alarm_key)
        # Set current selection
        break_index = break_alarm_combo.findData(current_break_alarm)
        if break_index >= 0:
            break_alarm_combo.setCurrentIndex(break_index)
        break_alarm_layout.addWidget(break_alarm_combo)

        # Browse button for custom sound file
        browse_break_btn = QPushButton("Browse...")
        browse_break_btn.clicked.connect(lambda: self.browse_sound_file(break_alarm_combo))
        break_alarm_layout.addWidget(browse_break_btn)

        # Test button for break alarm
        test_break_btn = QPushButton("Test")
        test_break_btn.clicked.connect(lambda: self.test_alarm_sound(
            break_alarm_combo.currentData(), volume_slider.value() / 100.0
        ))
        break_alarm_layout.addWidget(test_break_btn)
        alarm_group_layout.addLayout(break_alarm_layout)

        layout.addWidget(alarm_group)

        # Database Configuration
        db_group = QGroupBox("Database Storage")
        db_group_layout = QVBoxLayout(db_group)

        # Database type selection
        db_type_layout = QHBoxLayout()
        self.db_local_radio = QRadioButton("Local Directory")
        self.db_gdrive_radio = QRadioButton("Google Drive")
        self.db_local_radio.setChecked(current_db_type == "local")
        self.db_gdrive_radio.setChecked(current_db_type == "google_drive")

        db_type_layout.addWidget(self.db_local_radio)
        db_type_layout.addWidget(self.db_gdrive_radio)
        db_group_layout.addLayout(db_type_layout)

        # Local directory path
        local_path_layout = QHBoxLayout()
        local_path_layout.addWidget(QLabel("Local Directory:"))
        self.local_path_input = QLineEdit()
        self.local_path_input.setText(current_db_path)
        self.local_path_input.setPlaceholderText("Path to database directory")
        local_path_browse = QPushButton("Browse...")
        local_path_browse.clicked.connect(lambda: self.browse_directory(self.local_path_input))
        local_path_layout.addWidget(self.local_path_input)
        local_path_layout.addWidget(local_path_browse)
        db_group_layout.addLayout(local_path_layout)

        # Google Drive credentials
        gdrive_layout = QHBoxLayout()
        gdrive_layout.addWidget(QLabel("Credentials File:"))
        self.credentials_input = QLineEdit()
        self.credentials_input.setText(current_credentials)
        self.credentials_input.setPlaceholderText("credentials.json")
        credentials_browse = QPushButton("Browse...")
        credentials_browse.clicked.connect(lambda: self.browse_credentials_file(self.credentials_input))
        gdrive_layout.addWidget(self.credentials_input)
        gdrive_layout.addWidget(credentials_browse)
        db_group_layout.addLayout(gdrive_layout)

        # Google Drive folder
        gdrive_folder_layout = QHBoxLayout()
        gdrive_folder_layout.addWidget(QLabel("Google Drive Folder:"))
        self.gdrive_folder_input = QLineEdit()
        self.gdrive_folder_input.setText(current_gdrive_folder)
        self.gdrive_folder_input.setPlaceholderText("TimeTracking")
        gdrive_folder_layout.addWidget(self.gdrive_folder_input)
        db_group_layout.addLayout(gdrive_folder_layout)

        # Enable/disable controls based on selection
        def on_db_type_changed():
            is_local = self.db_local_radio.isChecked()
            self.local_path_input.setEnabled(is_local)
            local_path_browse.setEnabled(is_local)
            self.credentials_input.setEnabled(not is_local)
            credentials_browse.setEnabled(not is_local)
            self.gdrive_folder_input.setEnabled(not is_local)

        self.db_local_radio.toggled.connect(on_db_type_changed)
        on_db_type_changed()  # Set initial state

        layout.addWidget(db_group)

        # Buttons
        button_layout = QHBoxLayout()
        save_button = QPushButton("Save")
        save_button.clicked.connect(lambda: self.save_settings(
            theme_combo.currentText().lower(),
            sprint_spin.value(),
            break_spin.value(),
            auto_compact_checkbox.isChecked(),
            dialog,
            self.db_local_radio.isChecked(),
            self.local_path_input.text(),
            self.credentials_input.text(),
            self.gdrive_folder_input.text(),
            volume_slider.value() / 100.0,
            sprint_alarm_combo.currentData(),
            break_alarm_combo.currentData()
        ))
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(dialog.reject)
        button_layout.addWidget(save_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)

        dialog.exec()

        # Refresh UI state after settings dialog closes
        self.refresh_ui_state()

    def test_alarm_sound(self, alarm_name, volume):
        """Test play an alarm sound"""
        from audio.alarm import play_alarm_sound
        import threading

        def play_test():
            try:
                play_alarm_sound(alarm_name, volume)
            except Exception as e:
                print(f"Test alarm error: {e}")

        # Play in separate thread to avoid blocking UI
        thread = threading.Thread(target=play_test, daemon=True)
        thread.start()

    def browse_sound_file(self, combo_box):
        """Browse for a custom sound file and add it to the combo box"""
        from PySide6.QtWidgets import QFileDialog
        import os

        # Start in platform-specific system sounds directory
        import platform
        system = platform.system()

        if system == 'Darwin':  # macOS
            start_dir = "/System/Library/Sounds"
        elif system == 'Linux':  # Linux
            start_dir = "/usr/share/sounds"
        else:  # Windows and others
            start_dir = os.path.expanduser("~")

        if not os.path.exists(start_dir):
            start_dir = os.path.expanduser("~")

        file_path, _ = QFileDialog.getOpenFileName(
            None,
            "Select Sound File",
            start_dir,
            "Sound Files (*.wav *.ogg *.oga *.mp3 *.aiff *.aif *.caf *.m4a);;All Files (*)"
        )

        if file_path:
            # Create display name from filename
            filename = os.path.basename(file_path)
            name_without_ext = os.path.splitext(filename)[0]
            display_name = f"Custom: {name_without_ext.replace('-', ' ').replace('_', ' ').title()}"

            # Create key for the sound file
            file_key = f"file:{file_path}"

            # Add to combo box
            combo_box.addItem(display_name, file_key)
            # Select the newly added item
            combo_box.setCurrentIndex(combo_box.count() - 1)

    def refresh_ui_state(self):
        """Refresh UI elements to match current timer state"""
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
            self.state_label.setText("Focus Time! 🎯")
        elif timer_state == TimerState.PAUSED:
            self.start_button.setText("Resume")
            self.stop_button.setEnabled(True)
            self.complete_button.setEnabled(True)
            self.state_label.setText("Paused ⏸️")
        elif timer_state == TimerState.BREAK:
            self.start_button.setText("Start")
            self.stop_button.setEnabled(False)
            self.complete_button.setEnabled(False)
            self.state_label.setText("Break Time! ☕")

    def browse_directory(self, line_edit):
        """Browse for a directory and set it in the line edit"""
        from PySide6.QtWidgets import QFileDialog
        import os

        # Start from home directory or current path
        start_dir = os.path.expanduser("~")
        if line_edit.text().strip() and os.path.exists(line_edit.text().strip()):
            start_dir = line_edit.text().strip()

        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Database Directory (Press Ctrl+H to show hidden folders)",
            start_dir
        )
        if directory:
            line_edit.setText(directory)

    def browse_credentials_file(self, line_edit):
        """Browse for a credentials file and set it in the line edit"""
        from PySide6.QtWidgets import QFileDialog
        import os

        try:
            # Start from current directory or home directory
            start_dir = os.path.expanduser("~")
            if line_edit.text().strip():
                current_path = os.path.dirname(line_edit.text())
                if os.path.exists(current_path):
                    start_dir = current_path

            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Select Google Drive Credentials File",
                start_dir,
                "JSON Files (*.json);;All Files (*)"
            )
            if file_path:
                line_edit.setText(file_path)
                debug_print(f"Selected credentials file: {file_path}")
        except Exception as e:
            error_print(f"Error in browse_credentials_file: {e}")
            import traceback
            traceback.print_exc()

    def save_settings(self, theme_mode, sprint_duration, break_duration, auto_compact_mode, dialog, use_local_db, local_path, credentials_path, gdrive_folder, alarm_volume, sprint_alarm, break_alarm):
        """Save settings to local config file"""
        try:
            from tracking.local_settings import get_local_settings
            settings = get_local_settings()

            # Determine database type
            db_type = "local" if use_local_db else "google_drive"

            # Save all settings to local config
            settings.update({
                "theme_mode": theme_mode,
                "sprint_duration": sprint_duration,
                "break_duration": break_duration,
                "auto_compact_mode": auto_compact_mode,
                "alarm_volume": alarm_volume,
                "sprint_alarm": sprint_alarm,
                "break_alarm": break_alarm,
                "database_type": db_type,
                "database_local_path": local_path.strip() if local_path else "",
                "google_credentials_path": credentials_path.strip() if credentials_path else "credentials.json",
                "google_drive_folder": gdrive_folder.strip() if gdrive_folder else "TimeTracking",
                "google_drive_enabled": not use_local_db
            })

            # Apply settings immediately
            self.theme_mode = theme_mode
            self.auto_compact_mode = auto_compact_mode
            self.pomodoro_timer.set_durations(sprint_duration, break_duration)
            debug_print(f"[SETTINGS] Applying theme immediately: {theme_mode}")
            self.apply_modern_styling("settings")  # Reapply styling with new theme
            self.reset_ui()  # Update display with new timer duration

            dialog.accept()
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(dialog, "Error", f"Failed to save settings: {str(e)}")

def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # Modern style

    # Set application properties for proper macOS menu bar display
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
