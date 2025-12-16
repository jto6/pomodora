"""
Sync mixin for ModernPomodoroWindow.

Provides functionality for periodic sync, idle detection, and manual sync operations.
"""

from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
from PySide6.QtCore import Qt

from utils.logging import debug_print, error_print


class SyncMixin:
    """Mixin providing sync functionality."""

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
            icon_text = "\u2705"  # Success checkmark
        elif dialog_type == "warning":
            icon_text = "\u26a0\ufe0f"   # Warning
        elif dialog_type == "critical":
            icon_text = "\u274c"  # Error X

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
