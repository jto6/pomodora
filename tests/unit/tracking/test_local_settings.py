"""
Unit tests for local settings management.
Tests configuration persistence, validation, and cross-platform handling.
"""

import pytest
import json
import os
from pathlib import Path

from tracking.local_settings import LocalSettingsManager


@pytest.mark.unit
class TestLocalSettingsManager:
    """Test local settings manager functionality"""
    
    def test_initialization_with_defaults(self, temp_settings):
        """Test settings manager initializes with default values"""
        settings = temp_settings
        
        # Verify default values are set
        assert settings.get('theme_mode') == 'light'
        assert settings.get('sprint_duration') == 25
        assert settings.get('break_duration') == 5
        assert settings.get('alarm_volume') == 0.7
        assert settings.get('sprint_alarm') == 'gentle_chime'
        assert settings.get('break_alarm') == 'urgent_alert'
        assert settings.get('auto_compact_mode') is True
        assert settings.get('database_type') == 'local'
    
    def test_config_file_creation(self, temp_settings):
        """Test that config file is created when saving"""
        settings = temp_settings
        
        # Config file should not exist initially
        assert not settings.config_file.exists()
        
        # Save settings
        settings.save()
        
        # Config file should now exist
        assert settings.config_file.exists()
        
        # Verify file contains JSON data
        with open(settings.config_file, 'r') as f:
            data = json.load(f)
            assert isinstance(data, dict)
            assert 'theme_mode' in data
    
    def test_get_setting(self, temp_settings):
        """Test getting individual settings"""
        settings = temp_settings
        
        # Test getting existing setting
        assert settings.get('sprint_duration') == 25
        
        # Test getting non-existent setting with default
        assert settings.get('non_existent', 'default_value') == 'default_value'
        
        # Test getting non-existent setting without default
        assert settings.get('non_existent') is None
    
    def test_set_setting(self, temp_settings):
        """Test setting individual settings"""
        settings = temp_settings
        
        # Set a new value
        settings.set('sprint_duration', 30)
        assert settings.get('sprint_duration') == 30
        
        # Set a new key
        settings.set('new_setting', 'new_value')
        assert settings.get('new_setting') == 'new_value'
    
    def test_settings_persistence(self, temp_settings):
        """Test that settings persist after save/load cycle"""
        settings = temp_settings
        
        # Modify settings
        settings.set('sprint_duration', 30)
        settings.set('theme_mode', 'dark')
        settings.set('custom_setting', 'custom_value')
        
        # Save settings
        settings.save()
        
        # Create new settings manager with same config file
        new_settings = LocalSettingsManager()
        new_settings.config_file = settings.config_file
        new_settings._settings = new_settings._load_settings()
        
        # Verify settings were persisted
        assert new_settings.get('sprint_duration') == 30
        assert new_settings.get('theme_mode') == 'dark'
        assert new_settings.get('custom_setting') == 'custom_value'
    
    def test_load_corrupted_file(self, temp_settings):
        """Test handling of corrupted config file"""
        settings = temp_settings
        
        # Create corrupted JSON file
        settings.config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(settings.config_file, 'w') as f:
            f.write("corrupted json {")
        
        # Loading should fall back to defaults
        loaded_settings = settings._load_settings()
        assert loaded_settings == settings.defaults
    
    def test_load_missing_file(self, temp_settings):
        """Test handling of missing config file"""
        settings = temp_settings
        
        # Ensure file doesn't exist
        if settings.config_file.exists():
            settings.config_file.unlink()
        
        # Loading should return defaults
        loaded_settings = settings._load_settings()
        assert loaded_settings == settings.defaults
    
    @pytest.mark.parametrize("theme_mode", ['light', 'dark', 'system'])
    def test_theme_mode_values(self, temp_settings, theme_mode):
        """Test valid theme mode values"""
        settings = temp_settings
        settings.set('theme_mode', theme_mode)
        assert settings.get('theme_mode') == theme_mode
    
    @pytest.mark.parametrize("duration", [1, 5, 15, 25, 30, 45, 60])
    def test_sprint_duration_values(self, temp_settings, duration):
        """Test valid sprint duration values"""
        settings = temp_settings
        settings.set('sprint_duration', duration)
        assert settings.get('sprint_duration') == duration
    
    @pytest.mark.parametrize("duration", [1, 5, 10, 15, 30])
    def test_break_duration_values(self, temp_settings, duration):
        """Test valid break duration values"""
        settings = temp_settings
        settings.set('break_duration', duration)
        assert settings.get('break_duration') == duration
    
    @pytest.mark.parametrize("volume", [0.0, 0.1, 0.5, 0.7, 1.0])
    def test_alarm_volume_values(self, temp_settings, volume):
        """Test valid alarm volume values"""
        settings = temp_settings
        settings.set('alarm_volume', volume)
        assert settings.get('alarm_volume') == volume
    
    def test_alarm_sound_settings(self, temp_settings):
        """Test alarm sound settings"""
        settings = temp_settings
        
        # Test built-in alarm sounds
        built_in_alarms = ['gentle_chime', 'classic_beep', 'triple_bell', 
                          'urgent_alert', 'meditation_bowl', 'none']
        
        for alarm in built_in_alarms:
            settings.set('sprint_alarm', alarm)
            assert settings.get('sprint_alarm') == alarm
            
            settings.set('break_alarm', alarm)
            assert settings.get('break_alarm') == alarm
        
        # Test custom file path
        custom_path = '/path/to/custom/sound.wav'
        settings.set('sprint_alarm', custom_path)
        assert settings.get('sprint_alarm') == custom_path
    
    def test_database_settings(self, temp_settings):
        """Test database-related settings"""
        settings = temp_settings
        
        # Test database type
        settings.set('database_type', 'google_drive')
        assert settings.get('database_type') == 'google_drive'
        
        settings.set('database_type', 'local')
        assert settings.get('database_type') == 'local'
        
        # Test database paths
        local_path = '/custom/database/path'
        settings.set('database_local_path', local_path)
        assert settings.get('database_local_path') == local_path
        
        # Test Google Drive settings
        settings.set('google_drive_enabled', True)
        assert settings.get('google_drive_enabled') is True
        
        settings.set('google_drive_folder', 'CustomTimeTracking')
        assert settings.get('google_drive_folder') == 'CustomTimeTracking'
        
        creds_path = '/path/to/credentials.json'
        settings.set('google_credentials_path', creds_path)
        assert settings.get('google_credentials_path') == creds_path
    
    def test_window_settings(self, temp_settings):
        """Test window position and size settings"""
        settings = temp_settings
        
        # Test window position
        position = {'x': 100, 'y': 200}
        settings.set('window_position', position)
        assert settings.get('window_position') == position
        
        # Test window size
        size = {'width': 800, 'height': 600}
        settings.set('window_size', size)
        assert settings.get('window_size') == size
        
        # Test compact mode
        settings.set('compact_mode', True)
        assert settings.get('compact_mode') is True
    
    def test_auto_compact_mode(self, temp_settings):
        """Test auto compact mode setting"""
        settings = temp_settings
        
        # Test enabling/disabling auto compact mode
        settings.set('auto_compact_mode', False)
        assert settings.get('auto_compact_mode') is False
        
        settings.set('auto_compact_mode', True)
        assert settings.get('auto_compact_mode') is True


@pytest.mark.unit 
class TestLocalSettingsValidation:
    """Test settings validation and error handling"""
    
    def test_json_serializable_values(self, temp_settings):
        """Test that all values are JSON serializable"""
        settings = temp_settings
        
        # Set various types of values
        settings.set('string_value', 'test')
        settings.set('int_value', 42)
        settings.set('float_value', 3.14)
        settings.set('bool_value', True)
        settings.set('list_value', [1, 2, 3])
        settings.set('dict_value', {'key': 'value'})
        
        # Should be able to save without errors
        settings.save()
        
        # Verify file was created and is valid JSON
        assert settings.config_file.exists()
        with open(settings.config_file, 'r') as f:
            data = json.load(f)  # Should not raise exception
            assert isinstance(data, dict)
    
    def test_file_permission_handling(self, temp_settings):
        """Test handling of file permission issues"""
        settings = temp_settings
        
        # Create parent directory
        settings.config_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Try to handle read-only directory (platform dependent)
        try:
            # Make parent directory read-only (Unix systems)
            if hasattr(os, 'chmod'):
                original_mode = settings.config_file.parent.stat().st_mode
                os.chmod(settings.config_file.parent, 0o444)  # Read-only
                
                # Save should handle permission error gracefully
                try:
                    settings.save()
                except PermissionError:
                    # Expected behavior - settings manager should handle this
                    pass
                
                # Restore permissions
                os.chmod(settings.config_file.parent, original_mode)
        except (OSError, AttributeError):
            # Skip permission test on platforms that don't support it
            pytest.skip("Platform doesn't support permission testing")
    
    def test_config_directory_creation(self, temp_settings):
        """Test that config directory is created if it doesn't exist"""
        settings = temp_settings
        
        # Remove parent directory
        if settings.config_file.parent.exists():
            settings.config_file.unlink(missing_ok=True)
            settings.config_file.parent.rmdir()
        
        # Save should create directory
        settings.save()
        
        # Directory and file should exist
        assert settings.config_file.parent.exists()
        assert settings.config_file.exists()


@pytest.mark.unit
class TestCrossPlatformBehavior:
    """Test cross-platform settings behavior"""
    
    def test_path_handling(self, temp_settings):
        """Test cross-platform path handling"""
        settings = temp_settings
        
        # Test various path formats
        unix_path = '/home/user/database'
        windows_path = r'C:\Users\user\database'
        
        settings.set('database_local_path', unix_path)
        assert settings.get('database_local_path') == unix_path
        
        settings.set('database_local_path', windows_path)
        assert settings.get('database_local_path') == windows_path
    
    def test_default_config_location(self):
        """Test that default config location is platform appropriate"""
        import platform
        
        settings = LocalSettingsManager()
        config_path = str(settings.config_file)
        system = platform.system()
        
        if system == 'Darwin':  # macOS
            assert 'Library/Application Support/pomodora' in config_path
        elif system == 'Linux':
            assert '.config/pomodora' in config_path
        # Windows and other systems would have their own paths
        
        assert config_path.endswith('settings.json')
    
    def test_unicode_handling(self, temp_settings):
        """Test handling of unicode characters in settings"""
        settings = temp_settings
        
        # Test unicode strings
        unicode_strings = [
            'café',  # Accented characters
            '测试',   # Chinese characters  
            '🍅',    # Emoji
            'Ñoño',  # Spanish characters
        ]
        
        for i, unicode_str in enumerate(unicode_strings):
            key = f'unicode_test_{i}'
            settings.set(key, unicode_str)
            assert settings.get(key) == unicode_str
        
        # Save and reload to test persistence
        settings.save()
        
        new_settings = LocalSettingsManager()
        new_settings.config_file = settings.config_file
        new_settings._settings = new_settings._load_settings()
        
        # Verify unicode strings were preserved
        for i, unicode_str in enumerate(unicode_strings):
            key = f'unicode_test_{i}'
            assert new_settings.get(key) == unicode_str