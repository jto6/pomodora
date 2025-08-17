from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QSpinBox,
                             QLabel, QMessageBox, QComboBox, QLineEdit, QFileDialog,
                             QRadioButton, QButtonGroup, QGroupBox, QCheckBox, QSlider)
from PySide6.QtCore import Qt
from utils.logging import debug_print, error_print
from pathlib import Path
import os
import platform


class SettingsDialog(QDialog):
    """Settings configuration dialog"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.setWindowTitle("Settings")
        self.setFixedSize(650, 700)

        # Apply current theme styling to dialog
        if parent:
            parent.apply_dialog_styling(self)

        self.init_ui()

    def init_ui(self):
        """Initialize the settings dialog UI"""
        layout = QVBoxLayout(self)

        # Load current settings from local config
        from tracking.local_settings import get_local_settings
        settings = get_local_settings()
        self.current_theme = settings.get("theme_mode", "light")
        self.current_sprint = settings.get("sprint_duration", 25)
        self.current_break = settings.get("break_duration", 5)
        self.current_auto_compact = settings.get("auto_compact_mode", True)
        self.current_volume = settings.get("alarm_volume", 0.7)
        self.current_sprint_alarm = settings.get("sprint_alarm", "gentle_chime")
        self.current_break_alarm = settings.get("break_alarm", "urgent_alert")
        
        # Get unified sync configuration
        from tracking.sync_config import SyncConfiguration
        self.sync_config = SyncConfiguration()
        self.current_sync_strategy = self.sync_config.get_sync_strategy()
        coordination_config = self.sync_config.get_coordination_backend_config()
        self.current_backend_type = coordination_config.get('type', 'local_file')
        
        # Extract specific backend configurations
        google_config = coordination_config.get('google_drive', {})
        local_config = coordination_config.get('local_file', {})
        self.current_credentials = google_config.get('credentials_path', 'credentials.json')
        self.current_gdrive_folder = google_config.get('folder_name', 'TimeTracking')
        self.current_local_path = local_config.get('shared_db_path', '')
        
        # For multi-workstation, show cache path instead of local path
        if self.current_sync_strategy == "leader_election":
            self.current_cache_path = self.sync_config.get_local_cache_db_path()
        else:
            self.current_cache_path = self.current_local_path

        # Create UI sections
        self.create_theme_section(layout)
        self.create_timer_section(layout)
        self.create_alarm_section(layout)
        self.create_database_section(layout)  # Re-enabled with unified sync config
        self.create_button_section(layout)

    def create_theme_section(self, layout):
        """Create theme selection section"""
        # Theme selection
        theme_layout = QHBoxLayout()
        theme_layout.addWidget(QLabel("Theme:"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Light", "Dark", "System"])
        # Set current theme
        theme_index = {"light": 0, "dark": 1, "system": 2}.get(self.current_theme, 0)
        self.theme_combo.setCurrentIndex(theme_index)
        theme_layout.addWidget(self.theme_combo)
        layout.addLayout(theme_layout)

    def create_timer_section(self, layout):
        """Create timer configuration section"""
        # Sprint duration
        sprint_layout = QHBoxLayout()
        sprint_layout.addWidget(QLabel("Sprint Duration (minutes):"))
        self.sprint_spin = QSpinBox()
        self.sprint_spin.setRange(1, 60)
        self.sprint_spin.setValue(self.current_sprint)
        sprint_layout.addWidget(self.sprint_spin)
        layout.addLayout(sprint_layout)

        # Break duration
        break_layout = QHBoxLayout()
        break_layout.addWidget(QLabel("Break Duration (minutes):"))
        self.break_spin = QSpinBox()
        self.break_spin.setRange(1, 30)
        self.break_spin.setValue(self.current_break)
        break_layout.addWidget(self.break_spin)
        layout.addLayout(break_layout)

        # Auto-compact mode
        auto_compact_layout = QHBoxLayout()
        self.auto_compact_checkbox = QCheckBox("Auto-enter compact mode when sprint starts")
        self.auto_compact_checkbox.setChecked(self.current_auto_compact)
        auto_compact_layout.addWidget(self.auto_compact_checkbox)
        layout.addLayout(auto_compact_layout)

    def create_alarm_section(self, layout):
        """Create alarm settings section"""
        # Alarm Settings
        alarm_group = QGroupBox("Alarm Settings")
        alarm_group_layout = QVBoxLayout(alarm_group)

        # Volume slider
        volume_layout = QHBoxLayout()
        volume_layout.addWidget(QLabel("Volume:"))
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(int(self.current_volume * 100))
        self.volume_value_label = QLabel(f"{int(self.current_volume * 100)}%")
        self.volume_slider.valueChanged.connect(lambda v: self.volume_value_label.setText(f"{v}%"))
        volume_layout.addWidget(self.volume_slider)
        volume_layout.addWidget(self.volume_value_label)
        alarm_group_layout.addLayout(volume_layout)

        # Import available alarms
        from audio.alarm import get_available_alarms
        available_alarms = get_available_alarms()

        # Sprint completion alarm
        sprint_alarm_layout = QHBoxLayout()
        sprint_alarm_layout.addWidget(QLabel("Sprint Complete:"))
        self.sprint_alarm_combo = QComboBox()
        for alarm_key, alarm_info in available_alarms.items():
            self.sprint_alarm_combo.addItem(alarm_info["name"], alarm_key)
        # Set current selection
        sprint_index = self.sprint_alarm_combo.findData(self.current_sprint_alarm)
        if sprint_index >= 0:
            self.sprint_alarm_combo.setCurrentIndex(sprint_index)
        sprint_alarm_layout.addWidget(self.sprint_alarm_combo)

        # Browse button for custom sound file
        browse_sprint_btn = QPushButton("Browse...")
        browse_sprint_btn.clicked.connect(lambda: self.browse_sound_file(self.sprint_alarm_combo))
        sprint_alarm_layout.addWidget(browse_sprint_btn)

        # Test button for sprint alarm
        test_sprint_btn = QPushButton("Test")
        test_sprint_btn.clicked.connect(lambda: self.test_alarm_sound(
            self.sprint_alarm_combo.currentData(), self.volume_slider.value() / 100.0
        ))
        sprint_alarm_layout.addWidget(test_sprint_btn)
        alarm_group_layout.addLayout(sprint_alarm_layout)

        # Break completion alarm
        break_alarm_layout = QHBoxLayout()
        break_alarm_layout.addWidget(QLabel("Break Complete:"))
        self.break_alarm_combo = QComboBox()
        for alarm_key, alarm_info in available_alarms.items():
            self.break_alarm_combo.addItem(alarm_info["name"], alarm_key)
        # Set current selection
        break_index = self.break_alarm_combo.findData(self.current_break_alarm)
        if break_index >= 0:
            self.break_alarm_combo.setCurrentIndex(break_index)
        break_alarm_layout.addWidget(self.break_alarm_combo)

        # Browse button for custom sound file
        browse_break_btn = QPushButton("Browse...")
        browse_break_btn.clicked.connect(lambda: self.browse_sound_file(self.break_alarm_combo))
        break_alarm_layout.addWidget(browse_break_btn)

        # Test button for break alarm
        test_break_btn = QPushButton("Test")
        test_break_btn.clicked.connect(lambda: self.test_alarm_sound(
            self.break_alarm_combo.currentData(), self.volume_slider.value() / 100.0
        ))
        break_alarm_layout.addWidget(test_break_btn)
        alarm_group_layout.addLayout(break_alarm_layout)

        layout.addWidget(alarm_group)

    def create_database_section(self, layout):
        """Create database configuration section"""
        # Database Configuration
        db_group = QGroupBox("Database Storage")
        db_group_layout = QVBoxLayout(db_group)

        # Sync strategy selection
        strategy_layout = QHBoxLayout()
        strategy_layout.addWidget(QLabel("Storage Strategy:"))
        self.strategy_local_radio = QRadioButton("Local Only")
        self.strategy_sync_radio = QRadioButton("Multi-Workstation Sync")
        self.strategy_local_radio.setChecked(self.current_sync_strategy == "local_only")
        self.strategy_sync_radio.setChecked(self.current_sync_strategy == "leader_election")

        strategy_layout.addWidget(self.strategy_local_radio)
        strategy_layout.addWidget(self.strategy_sync_radio)
        db_group_layout.addLayout(strategy_layout)

        # Database file path (changes meaning based on strategy)
        db_path_layout = QHBoxLayout()
        self.db_path_label = QLabel("Database File:")
        db_path_layout.addWidget(self.db_path_label)
        self.local_path_input = QLineEdit()
        # Show appropriate path based on current strategy
        display_path = self.current_cache_path if self.current_sync_strategy == "leader_election" else self.current_local_path
        self.local_path_input.setText(display_path)
        self.local_path_input.setPlaceholderText("Path to database file")
        self.local_path_browse = QPushButton("Browse...")
        self.local_path_browse.clicked.connect(lambda: self.browse_database_file(self.local_path_input))
        db_path_layout.addWidget(self.local_path_input)
        db_path_layout.addWidget(self.local_path_browse)
        db_group_layout.addLayout(db_path_layout)

        # Coordination backend selection (for multi-workstation sync)
        self.backend_layout = QHBoxLayout()
        self.backend_label = QLabel("Sync Backend:")
        self.backend_layout.addWidget(self.backend_label)
        self.backend_local_radio = QRadioButton("Local File")
        self.backend_gdrive_radio = QRadioButton("Google Drive")
        
        # Create a button group to ensure mutual exclusivity
        self.backend_button_group = QButtonGroup()
        self.backend_button_group.addButton(self.backend_local_radio)
        self.backend_button_group.addButton(self.backend_gdrive_radio)
        
        self.backend_local_radio.setChecked(self.current_backend_type == "local_file")
        self.backend_gdrive_radio.setChecked(self.current_backend_type == "google_drive")

        self.backend_layout.addWidget(self.backend_local_radio)
        self.backend_layout.addWidget(self.backend_gdrive_radio)
        db_group_layout.addLayout(self.backend_layout)

        # Local file backend shared location
        self.shared_file_layout = QHBoxLayout()
        self.shared_file_label = QLabel("Shared Database:")
        self.shared_file_layout.addWidget(self.shared_file_label)
        self.shared_file_input = QLineEdit()
        self.shared_file_input.setText(self.current_local_path)
        self.shared_file_input.setPlaceholderText("Path to shared database file")
        self.shared_file_browse = QPushButton("Browse...")
        self.shared_file_browse.clicked.connect(lambda: self.browse_database_file(self.shared_file_input))
        self.shared_file_layout.addWidget(self.shared_file_input)
        self.shared_file_layout.addWidget(self.shared_file_browse)
        db_group_layout.addLayout(self.shared_file_layout)

        # Google Drive credentials
        self.gdrive_layout = QHBoxLayout()
        self.credentials_label = QLabel("Credentials File:")
        self.gdrive_layout.addWidget(self.credentials_label)
        self.credentials_input = QLineEdit()
        self.credentials_input.setText(self.current_credentials)
        self.credentials_input.setPlaceholderText("credentials.json")
        self.credentials_browse = QPushButton("Browse...")
        self.credentials_browse.clicked.connect(lambda: self.browse_credentials_file(self.credentials_input))
        self.gdrive_layout.addWidget(self.credentials_input)
        self.gdrive_layout.addWidget(self.credentials_browse)
        db_group_layout.addLayout(self.gdrive_layout)

        # Google Drive folder
        self.gdrive_folder_layout = QHBoxLayout()
        self.gdrive_folder_label = QLabel("Google Drive Folder:")
        self.gdrive_folder_layout.addWidget(self.gdrive_folder_label)
        self.gdrive_folder_input = QLineEdit()
        self.gdrive_folder_input.setText(self.current_gdrive_folder)
        self.gdrive_folder_input.setPlaceholderText("TimeTracking")
        self.gdrive_folder_layout.addWidget(self.gdrive_folder_input)
        db_group_layout.addLayout(self.gdrive_folder_layout)

        # Enable/disable controls based on selection
        def on_strategy_changed():
            is_local_only = self.strategy_local_radio.isChecked()
            is_multi_workstation = self.strategy_sync_radio.isChecked()
            
            # Show/hide database path controls based on strategy
            if is_local_only:
                # Show database file selection for local-only mode
                self.db_path_label.setVisible(True)
                self.local_path_input.setVisible(True)
                self.local_path_browse.setVisible(True)
                self.db_path_label.setText("Database File:")
                self.local_path_input.setPlaceholderText("Path to database file")
                
                # Hide all multi-workstation controls
                self.backend_label.setVisible(False)
                self.backend_local_radio.setVisible(False)
                self.backend_gdrive_radio.setVisible(False)
                self.shared_file_label.setVisible(False)
                self.shared_file_input.setVisible(False)
                self.shared_file_browse.setVisible(False)
                self.credentials_label.setVisible(False)
                self.credentials_input.setVisible(False)
                self.credentials_browse.setVisible(False)
                self.gdrive_folder_label.setVisible(False)
                self.gdrive_folder_input.setVisible(False)
            else:
                # Hide local-only database path
                self.db_path_label.setVisible(False)
                self.local_path_input.setVisible(False)
                self.local_path_browse.setVisible(False)
                
                # Show multi-workstation backend selection
                self.backend_label.setVisible(True)
                self.backend_local_radio.setVisible(True)
                self.backend_gdrive_radio.setVisible(True)
                
                # Show/hide backend-specific controls
                is_local_backend = self.backend_local_radio.isChecked()
                is_gdrive_backend = self.backend_gdrive_radio.isChecked()
                
                # Local file backend controls
                self.shared_file_label.setVisible(is_local_backend)
                self.shared_file_input.setVisible(is_local_backend)
                self.shared_file_browse.setVisible(is_local_backend)
                
                # Google Drive backend controls
                self.credentials_label.setVisible(is_gdrive_backend)
                self.credentials_input.setVisible(is_gdrive_backend)
                self.credentials_browse.setVisible(is_gdrive_backend)
                self.gdrive_folder_label.setVisible(is_gdrive_backend)
                self.gdrive_folder_input.setVisible(is_gdrive_backend)

        def on_backend_changed():
            on_strategy_changed()  # Re-evaluate all controls

        self.strategy_local_radio.toggled.connect(on_strategy_changed)
        self.backend_local_radio.toggled.connect(on_backend_changed)
        self.backend_gdrive_radio.toggled.connect(on_backend_changed)
        on_strategy_changed()  # Set initial state

        layout.addWidget(db_group)

    def create_button_section(self, layout):
        """Create dialog buttons section"""
        # Buttons
        button_layout = QHBoxLayout()
        save_button = QPushButton("Save")
        save_button.clicked.connect(self.save_settings)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(save_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)

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
        # Start in platform-specific system sounds directory
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

    def browse_directory(self, line_edit):
        """Browse for a directory and set it in the line edit"""
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

    def browse_database_file(self, line_edit):
        """Browse for a database file and set it in the line edit"""
        # Start from home directory or current file's directory
        start_dir = os.path.expanduser("~/.config/pomodora")
        if line_edit.text().strip():
            current_path = os.path.dirname(line_edit.text().strip())
            if os.path.exists(current_path):
                start_dir = current_path

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Select Database File Location (Press Ctrl+H to show hidden folders)",
            os.path.join(start_dir, "pomodora.db"),
            "Database Files (*.db);;All Files (*)"
        )
        if file_path:
            line_edit.setText(file_path)

    def browse_credentials_file(self, line_edit):
        """Browse for a credentials file and set it in the line edit"""
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

    def _clear_database_cache(self):
        """Clear database cache files when configuration changes"""
        try:
            import shutil
            
            # Clear cache directory
            cache_dir = Path.home() / '.config' / 'pomodora' / 'cache'
            if cache_dir.exists():
                debug_print(f"Clearing database cache directory: {cache_dir}")
                shutil.rmtree(cache_dir)
                debug_print("Database cache cleared successfully")
            
            # Clear operations log files
            config_dir = Path.home() / '.config' / 'pomodora'
            for operations_file in config_dir.glob("*_operations.json"):
                operations_file.unlink()
                debug_print(f"Removed operations file: {operations_file}")
                
        except Exception as e:
            error_print(f"Error clearing database cache: {e}")
            # Don't fail the settings save if cache cleanup fails

    def _sync_before_config_change(self):
        """Sync any pending changes before changing database configuration"""
        try:
            if self.parent_window and hasattr(self.parent_window, 'db_manager'):
                db_manager = self.parent_window.db_manager
                
                # Check if there are pending changes
                if hasattr(db_manager, 'has_local_changes') and db_manager.has_local_changes():
                    debug_print("Syncing pending changes before database configuration change...")
                    
                    # Show progress dialog for the sync
                    from PySide6.QtWidgets import QProgressDialog
                    from PySide6.QtCore import Qt
                    
                    progress = QProgressDialog("Syncing current database changes...", None, 0, 0, self)
                    progress.setWindowTitle("Saving Changes")
                    progress.setWindowModality(Qt.WindowModal)
                    progress.setMinimumDuration(0)  # Show immediately
                    progress.setCancelButton(None)  # No cancel for this critical sync
                    progress.show()
                    
                    # Process events to show the dialog
                    from PySide6.QtWidgets import QApplication
                    QApplication.processEvents()
                    
                    # Perform the sync
                    if hasattr(db_manager, 'sync_if_changes_pending'):
                        success = db_manager.sync_if_changes_pending()
                        progress.close()
                        
                        if success:
                            debug_print("Successfully synced pending changes before config change")
                        else:
                            error_print("Warning: Failed to sync some changes before config change")
                    else:
                        progress.close()
                        debug_print("Database manager doesn't support sync - proceeding with config change")
                else:
                    debug_print("No pending changes to sync before config change")
            else:
                debug_print("No database manager available for pre-config-change sync")
                
        except Exception as e:
            error_print(f"Error during pre-config-change sync: {e}")
            # Continue with config change even if sync fails

    def save_settings(self):
        """Save settings to local config file"""
        try:
            from tracking.local_settings import get_local_settings
            settings = get_local_settings()

            theme_mode = self.theme_combo.currentText().lower()

            # Save basic settings
            settings.update({
                "theme_mode": theme_mode,
                "sprint_duration": self.sprint_spin.value(),
                "break_duration": self.break_spin.value(),
                "auto_compact_mode": self.auto_compact_checkbox.isChecked(),
                "alarm_volume": self.volume_slider.value() / 100.0,
                "sprint_alarm": self.sprint_alarm_combo.currentData(),
                "break_alarm": self.break_alarm_combo.currentData(),
            })

            # Save unified sync configuration
            sync_strategy = "local_only" if self.strategy_local_radio.isChecked() else "leader_election"
            backend_type = "local_file" if self.backend_local_radio.isChecked() else "google_drive"
            
            settings.set("sync_strategy", sync_strategy)
            
            # Build coordination backend configuration
            if sync_strategy == "local_only":
                # For local-only, save the database file path
                local_db_path = self.local_path_input.text().strip() or str(Path.home() / '.config' / 'pomodora' / 'database' / 'pomodora.db')
                coordination_config = {
                    "type": "local_file",
                    "local_file": {
                        "shared_db_path": local_db_path
                    },
                    "google_drive": {
                        "credentials_path": "credentials.json",
                        "folder_name": "TimeTracking"
                    }
                }
            else:
                # For multi-workstation, save appropriate backend config
                if backend_type == "local_file":
                    shared_db_path = self.shared_file_input.text().strip() or str(Path.home() / '.config' / 'pomodora' / 'shared' / 'pomodora.db')
                else:
                    shared_db_path = str(Path.home() / '.config' / 'pomodora' / 'database' / 'pomodora.db')
                    
                coordination_config = {
                    "type": backend_type,
                    "local_file": {
                        "shared_db_path": shared_db_path
                    },
                    "google_drive": {
                        "credentials_path": self.credentials_input.text().strip() or "credentials.json",
                        "folder_name": self.gdrive_folder_input.text().strip() or "TimeTracking"
                    }
                }
            
            settings.set("coordination_backend", coordination_config)

            # Check if database configuration changed - if so, show restart popup first
            local_path_changed = (sync_strategy == "local_only" and 
                                self.local_path_input.text().strip() != self.current_local_path)
            shared_path_changed = (sync_strategy == "leader_election" and backend_type == "local_file" and
                                 self.shared_file_input.text().strip() != self.current_local_path)
            credentials_changed = self.credentials_input.text().strip() != self.current_credentials
            folder_changed = self.gdrive_folder_input.text().strip() != self.current_gdrive_folder
            
            if (sync_strategy != self.current_sync_strategy or 
                backend_type != self.current_backend_type or
                local_path_changed or shared_path_changed or
                credentials_changed or folder_changed):
                
                # Create a custom dialog with proper sizing and text wrapping
                from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
                from PySide6.QtCore import Qt
                
                restart_dialog = QDialog(self)
                restart_dialog.setWindowTitle("Database Configuration Changed")
                restart_dialog.setModal(True)
                restart_dialog.resize(500, 200)
                restart_dialog.setMinimumSize(450, 180)
                
                layout = QVBoxLayout(restart_dialog)
                
                # Create label with word wrap enabled
                text_label = QLabel("Database storage settings have been updated.\n\n"
                                  "The application will now sync any pending changes and "
                                  "exit to apply the new configuration.\n"
                                  "Your current session will be saved properly before exiting.")
                text_label.setWordWrap(True)
                text_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
                text_label.setMargin(10)
                layout.addWidget(text_label)
                
                # Add OK button
                button_layout = QHBoxLayout()
                button_layout.addStretch()
                ok_button = QPushButton("OK")
                ok_button.clicked.connect(restart_dialog.accept)
                ok_button.setDefault(True)
                button_layout.addWidget(ok_button)
                button_layout.addStretch()
                layout.addLayout(button_layout)
                
                restart_dialog.exec()
                
                # Now sync any pending changes to the current database location
                self._sync_before_config_change()
                
                # Then clear cache for fresh start with new configuration
                self._clear_database_cache()

                # Close settings dialog
                self.accept()
                
                # Then trigger application exit
                if self.parent_window:
                    self.parent_window.close()
                return

            # Apply settings immediately to parent window for non-database changes
            if self.parent_window:
                self.parent_window.theme_mode = theme_mode
                self.parent_window.auto_compact_mode = self.auto_compact_checkbox.isChecked()
                self.parent_window.pomodoro_timer.set_durations(
                    self.sprint_spin.value(),
                    self.break_spin.value()
                )
                debug_print(f"[SETTINGS] Applying theme immediately: {theme_mode}")
                self.parent_window.apply_modern_styling("settings")  # Reapply styling with new theme
                self.parent_window.reset_ui()  # Update display with new timer duration

            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save settings: {str(e)}")