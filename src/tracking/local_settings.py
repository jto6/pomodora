"""
Local settings manager for workstation-specific preferences.
Stores settings in a local JSON file, separate from the shared database.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict
from utils.logging import verbose_print, error_print, info_print, debug_print

class LocalSettingsManager:
    def __init__(self):
        # Use platform-specific config directories
        import platform
        system = platform.system()

        if system == 'Darwin':  # macOS
            config_dir = Path.home() / 'Library' / 'Application Support' / 'pomodora'
        elif system == 'Linux':  # Linux
            config_dir = Path.home() / '.config' / 'pomodora'
        else:  # Windows and other systems
            config_dir = Path.home() / 'AppData' / 'Local' / 'pomodora'

        config_dir.mkdir(parents=True, exist_ok=True)
        self.config_file = config_dir / 'settings.json'

        # Default settings
        self.defaults = {
            'theme_mode': 'light',  # light, dark, system
            'sprint_duration': 25,   # minutes
            'break_duration': 5,     # minutes
            'alarm_volume': 0.7,     # 0.0 to 1.0
            'sprint_alarm': 'gentle_chime',  # alarm sound for sprint completion
            'break_alarm': 'urgent_alert',   # alarm sound for break completion
            'auto_compact_mode': True,  # auto-enter compact mode when sprint starts
            'window_position': None, # {'x': int, 'y': int}
            'window_size': None,     # {'width': int, 'height': int}
            'compact_mode': False,   # boolean (runtime state, not persistent)
            # Database and sync configuration
            'sync_strategy': 'local_only',  # 'local_only', 'leader_election'
            'coordination_backend': {
                'type': 'local_file',  # 'local_file', 'google_drive'  
                'local_file': {
                    'shared_db_path': str(config_dir / 'database' / 'pomodora.db')
                },
                'google_drive': {
                    'credentials_path': 'credentials.json',
                    'folder_name': 'TimeTracking'
                }
            },
            'local_cache_db_path': str(config_dir / 'cache' / 'pomodora.db'),
            
            # Legacy settings (for backward compatibility)
            'database_type': 'local',  # deprecated - use sync_strategy
            'google_drive_enabled': False,  # deprecated - use sync_strategy
            'google_credentials_path': 'credentials.json',  # deprecated
            'google_drive_folder': 'TimeTracking'  # deprecated
        }

        self._settings = self._load_settings()

    def _load_settings(self) -> Dict[str, Any]:
        """Load settings from file, creating defaults if file doesn't exist"""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r') as f:
                    settings = json.load(f)
                # Merge with defaults to ensure all keys exist
                merged = self.defaults.copy()
                merged.update(settings)
                return merged
            else:
                return self.defaults.copy()
        except (json.JSONDecodeError, IOError) as e:
            error_print(f"Error loading settings: {e}")
            return self.defaults.copy()

    def _save_settings(self):
        """Save current settings to file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self._settings, f, indent=2)
        except IOError as e:
            error_print(f"Error saving settings: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """Get a setting value"""
        return self._settings.get(key, default)

    def set(self, key: str, value: Any):
        """Set a setting value and save to file"""
        self._settings[key] = value
        self._save_settings()

    def get_all(self) -> Dict[str, Any]:
        """Get all settings"""
        return self._settings.copy()

    def update(self, settings: Dict[str, Any]):
        """Update multiple settings at once"""
        self._settings.update(settings)
        self._save_settings()

    def reset_to_defaults(self):
        """Reset all settings to default values"""
        self._settings = self.defaults.copy()
        self._save_settings()

    def save(self):
        """Save current settings to file (public interface)"""
        self._save_settings()

    def get_config_path(self) -> str:
        """Get the path to the config file"""
        return str(self.config_file)

# Global instance
_local_settings = None

def get_local_settings() -> LocalSettingsManager:
    """Get the global local settings instance"""
    global _local_settings
    if _local_settings is None:
        _local_settings = LocalSettingsManager()
    return _local_settings