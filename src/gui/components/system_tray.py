from pathlib import Path
from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QApplication
from PySide6.QtGui import QIcon, QAction, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import QObject, Signal, Qt
from timer.pomodoro import TimerState
from utils.logging import info_print, error_print, debug_print


class SystemTrayManager(QObject):
    """Manages system tray icon and related functionality"""

    # Signals
    show_hide_requested = Signal()
    timer_toggle_requested = Signal()
    timer_stop_requested = Signal()
    sprint_complete_requested = Signal()
    settings_requested = Signal()
    force_quit_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.tray_icon = None
        self.tray_start_action = None
        self.tray_show_action = None

    def init_system_tray(self):
        """Initialize system tray icon and menu"""
        # Check if system tray is available
        if not QSystemTrayIcon.isSystemTrayAvailable():
            info_print("System tray not available")
            return False

        # Load the icon
        icon = self._load_tray_icon()

        # Create system tray icon
        self.tray_icon = QSystemTrayIcon(icon, self.parent_window)

        # Create tray menu
        tray_menu = self._create_tray_menu()

        # Set the menu and show the tray icon
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_icon_activated)
        self.tray_icon.show()

        info_print("System tray icon initialized")
        return True

    def _load_tray_icon(self):
        """Load the tray icon with fallback"""
        try:
            # Try to load the main icon.png file (now based on logo.svg)
            icon_path = Path(__file__).parent.parent.parent.parent / "icon.png"
            if icon_path.exists():
                return QIcon(str(icon_path))
            
            # Fallback to assets directory
            asset_icon_path = Path(__file__).parent.parent.parent.parent / "assets" / "pomodora_icon.png"
            if asset_icon_path.exists():
                return QIcon(str(asset_icon_path))
            else:
                # Final fallback to system icon
                if self.parent_window:
                    return self.parent_window.style().standardIcon(
                        self.parent_window.style().SP_ComputerIcon
                    )
                else:
                    return QIcon()
        except Exception as e:
            error_print(f"Error loading tray icon: {e}")
            if self.parent_window:
                return self.parent_window.style().standardIcon(
                    self.parent_window.style().SP_ComputerIcon
                )
            else:
                return QIcon()

    def _create_tray_menu(self):
        """Create the tray context menu"""
        tray_menu = QMenu()

        # Show/Hide action
        self.tray_show_action = QAction("Show/Hide", self.parent_window)
        self.tray_show_action.triggered.connect(self.show_hide_requested.emit)
        tray_menu.addAction(self.tray_show_action)

        tray_menu.addSeparator()

        # Timer controls
        self.tray_start_action = QAction("Start Sprint", self.parent_window)
        self.tray_start_action.triggered.connect(self.timer_toggle_requested.emit)
        tray_menu.addAction(self.tray_start_action)

        stop_action = QAction("Stop Timer", self.parent_window)
        stop_action.triggered.connect(self.timer_stop_requested.emit)
        tray_menu.addAction(stop_action)

        complete_action = QAction("Complete Sprint", self.parent_window)
        complete_action.triggered.connect(self.sprint_complete_requested.emit)
        tray_menu.addAction(complete_action)

        tray_menu.addSeparator()

        # Settings action
        settings_action = QAction("Settings...", self.parent_window)
        settings_action.triggered.connect(self.settings_requested.emit)
        tray_menu.addAction(settings_action)

        tray_menu.addSeparator()

        # Exit action
        exit_action = QAction("Exit", self.parent_window)
        exit_action.triggered.connect(self.force_quit_requested.emit)
        tray_menu.addAction(exit_action)

        return tray_menu

    def _on_tray_icon_activated(self, reason):
        """Handle tray icon activation (clicks)"""
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_hide_requested.emit()

    def update_tray_tooltip(self, timer_state, remaining_time):
        """Update tray icon tooltip with current timer status"""
        if not self.tray_icon:
            return

        if timer_state == TimerState.RUNNING:
            tooltip = f"Pomodora - Sprint: {remaining_time}"
        elif timer_state == TimerState.BREAK:
            tooltip = f"Pomodora - Break: {remaining_time}"
        elif timer_state == TimerState.PAUSED:
            tooltip = f"Pomodora - Paused: {remaining_time}"
        else:
            tooltip = "Pomodora - Ready"

        self.tray_icon.setToolTip(tooltip)

    def update_tray_menu(self, timer_state):
        """Update tray menu based on current timer state"""
        if not self.tray_start_action:
            return

        if timer_state == TimerState.RUNNING or timer_state == TimerState.BREAK:
            self.tray_start_action.setText("Pause Timer")
        else:
            self.tray_start_action.setText("Start Sprint")

    def show_message(self, title, message, icon_type=QSystemTrayIcon.Information, duration=3000):
        """Show a tray notification message"""
        if self.tray_icon and self.tray_icon.isVisible():
            self.tray_icon.showMessage(title, message, icon_type, duration)

    def hide_tray_icon(self):
        """Hide the tray icon"""
        if self.tray_icon:
            self.tray_icon.hide()
            self.tray_icon = None

    def is_tray_available(self):
        """Check if tray icon is available and visible"""
        return (self.tray_icon is not None and
                self.tray_icon.isVisible() and
                QSystemTrayIcon.isSystemTrayAvailable())