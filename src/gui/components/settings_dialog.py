from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QSpinBox, 
                             QLabel, QMessageBox, QComboBox, QLineEdit, QFileDialog, 
                             QRadioButton, QButtonGroup, QGroupBox, QCheckBox, QSlider)
from PySide6.QtCore import Qt
from utils.logging import debug_print, error_print
import os
import platform


class SettingsDialog(QDialog):
    """Settings configuration dialog"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.setWindowTitle("Settings")
        self.setFixedSize(650, 600)
        
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
        self.current_db_type = settings.get("database_type", "local")
        self.current_db_path = settings.get("database_local_path", "")
        self.current_credentials = settings.get("google_credentials_path", "credentials.json")
        self.current_gdrive_folder = settings.get("google_drive_folder", "TimeTracking")
        
        # Create UI sections
        self.create_theme_section(layout)
        self.create_timer_section(layout)
        self.create_alarm_section(layout)
        self.create_database_section(layout)
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
        
        # Database type selection
        db_type_layout = QHBoxLayout()
        self.db_local_radio = QRadioButton("Local Directory")
        self.db_gdrive_radio = QRadioButton("Google Drive")
        self.db_local_radio.setChecked(self.current_db_type == "local")
        self.db_gdrive_radio.setChecked(self.current_db_type == "google_drive")
        
        db_type_layout.addWidget(self.db_local_radio)
        db_type_layout.addWidget(self.db_gdrive_radio)
        db_group_layout.addLayout(db_type_layout)
        
        # Local directory path
        local_path_layout = QHBoxLayout()
        local_path_layout.addWidget(QLabel("Local Directory:"))
        self.local_path_input = QLineEdit()
        self.local_path_input.setText(self.current_db_path)
        self.local_path_input.setPlaceholderText("Path to database directory")
        self.local_path_browse = QPushButton("Browse...")
        self.local_path_browse.clicked.connect(lambda: self.browse_directory(self.local_path_input))
        local_path_layout.addWidget(self.local_path_input)
        local_path_layout.addWidget(self.local_path_browse)
        db_group_layout.addLayout(local_path_layout)
        
        # Google Drive credentials
        gdrive_layout = QHBoxLayout()
        gdrive_layout.addWidget(QLabel("Credentials File:"))
        self.credentials_input = QLineEdit()
        self.credentials_input.setText(self.current_credentials)
        self.credentials_input.setPlaceholderText("credentials.json")
        self.credentials_browse = QPushButton("Browse...")
        self.credentials_browse.clicked.connect(lambda: self.browse_credentials_file(self.credentials_input))
        gdrive_layout.addWidget(self.credentials_input)
        gdrive_layout.addWidget(self.credentials_browse)
        db_group_layout.addLayout(gdrive_layout)
        
        # Google Drive folder
        gdrive_folder_layout = QHBoxLayout()
        gdrive_folder_layout.addWidget(QLabel("Google Drive Folder:"))
        self.gdrive_folder_input = QLineEdit()
        self.gdrive_folder_input.setText(self.current_gdrive_folder)
        self.gdrive_folder_input.setPlaceholderText("TimeTracking")
        gdrive_folder_layout.addWidget(self.gdrive_folder_input)
        db_group_layout.addLayout(gdrive_folder_layout)
        
        # Enable/disable controls based on selection
        def on_db_type_changed():
            is_local = self.db_local_radio.isChecked()
            self.local_path_input.setEnabled(is_local)
            self.local_path_browse.setEnabled(is_local)
            self.credentials_input.setEnabled(not is_local)
            self.credentials_browse.setEnabled(not is_local)
            self.gdrive_folder_input.setEnabled(not is_local)
        
        self.db_local_radio.toggled.connect(on_db_type_changed)
        on_db_type_changed()  # Set initial state
        
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
    
    def save_settings(self):
        """Save settings to local config file"""
        try:
            from tracking.local_settings import get_local_settings
            settings = get_local_settings()
            
            # Determine database type
            db_type = "local" if self.db_local_radio.isChecked() else "google_drive"
            theme_mode = self.theme_combo.currentText().lower()
            
            # Save all settings to local config
            settings.update({
                "theme_mode": theme_mode,
                "sprint_duration": self.sprint_spin.value(),
                "break_duration": self.break_spin.value(),
                "auto_compact_mode": self.auto_compact_checkbox.isChecked(),
                "alarm_volume": self.volume_slider.value() / 100.0,
                "sprint_alarm": self.sprint_alarm_combo.currentData(),
                "break_alarm": self.break_alarm_combo.currentData(),
                "database_type": db_type,
                "database_local_path": self.local_path_input.text().strip(),
                "google_credentials_path": self.credentials_input.text().strip() or "credentials.json",
                "google_drive_folder": self.gdrive_folder_input.text().strip() or "TimeTracking",
                "google_drive_enabled": not self.db_local_radio.isChecked()
            })
            
            # Apply settings immediately to parent window
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