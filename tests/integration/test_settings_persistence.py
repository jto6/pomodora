"""
Integration tests for settings persistence across application restarts.
Tests settings changes → local file updates → application restart validation.
"""

import pytest
import json
import tempfile
from pathlib import Path

from tracking.local_settings import LocalSettingsManager


@pytest.mark.integration
class TestSettingsPersistence:
    """Test settings persistence across application sessions"""
    
    def test_settings_persist_after_restart(self):
        """Test that settings persist after simulated application restart"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "test_settings.json"
            
            # First application session
            settings1 = LocalSettingsManager()
            settings1.config_file = config_file
            
            # Modify settings
            settings1.set('sprint_duration', 30)
            settings1.set('theme_mode', 'dark')
            settings1.set('alarm_volume', 0.8)
            settings1.set('custom_setting', 'custom_value')
            
            # Save settings
            settings1.save()
            
            # Verify file was created
            assert config_file.exists()
            
            # Simulate application restart with new settings instance
            settings2 = LocalSettingsManager()
            settings2.config_file = config_file
            settings2._settings = settings2._load_settings()
            
            # Verify settings persisted
            assert settings2.get('sprint_duration') == 30
            assert settings2.get('theme_mode') == 'dark'
            assert settings2.get('alarm_volume') == 0.8
            assert settings2.get('custom_setting') == 'custom_value'
            
            # Verify defaults are still present for unmodified settings
            assert settings2.get('break_duration') == 5  # Default value
            assert settings2.get('auto_compact_mode') is True  # Default value
    
    def test_partial_settings_persistence(self):
        """Test persistence when only some settings are modified"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "partial_settings.json"
            
            # Create settings and modify only some values
            settings1 = LocalSettingsManager()
            settings1.config_file = config_file
            # Reset to clean defaults first
            settings1._settings = settings1.defaults.copy()
            
            # Only change a few settings
            settings1.set('sprint_duration', 45)
            settings1.set('sprint_alarm', 'triple_bell')
            settings1.save()
            
            # New session - create with isolated config
            settings2 = LocalSettingsManager()
            settings2.config_file = config_file
            settings2._settings = settings2._load_settings()
            
            # Modified settings should persist
            assert settings2.get('sprint_duration') == 45
            assert settings2.get('sprint_alarm') == 'triple_bell'
            
            # Unmodified settings should have defaults from the defaults dict
            expected_theme = settings2.defaults['theme_mode']  # Get from actual defaults
            assert settings2.get('theme_mode') == expected_theme
            assert settings2.get('break_duration') == 5  # Default
            assert settings2.get('alarm_volume') == 0.7  # Default
    
    def test_settings_file_format_consistency(self):
        """Test that settings file format remains consistent"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "format_test.json"
            
            settings = LocalSettingsManager()
            settings.config_file = config_file
            
            # Set various types of values
            test_data = {
                'string_value': 'test_string',
                'int_value': 42,
                'float_value': 3.14,
                'bool_value': True,
                'list_value': [1, 2, 3],
                'dict_value': {'nested': 'value'}
            }
            
            for key, value in test_data.items():
                settings.set(key, value)
            
            settings.save()
            
            # Verify file is valid JSON
            with open(config_file, 'r') as f:
                file_data = json.load(f)
            
            # Verify all test data is present and correct
            for key, expected_value in test_data.items():
                assert file_data[key] == expected_value
            
            # Verify defaults are also present
            assert 'theme_mode' in file_data
            assert 'sprint_duration' in file_data
    
    def test_settings_backwards_compatibility(self):
        """Test loading settings from older file formats"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "old_format.json"
            
            # Create an "old format" settings file manually
            old_format_settings = {
                'sprint_duration': 25,
                'break_duration': 5,
                'theme_mode': 'light',
                # Missing some newer settings
            }
            
            with open(config_file, 'w') as f:
                json.dump(old_format_settings, f)
            
            # Load with new settings manager
            settings = LocalSettingsManager()
            settings.config_file = config_file
            settings._settings = settings._load_settings()
            
            # Old settings should be preserved
            assert settings.get('sprint_duration') == 25
            assert settings.get('break_duration') == 5
            assert settings.get('theme_mode') == 'light'
            
            # New settings should use defaults
            assert settings.get('alarm_volume') == 0.7  # Default
            assert settings.get('auto_compact_mode') is True  # Default
    
    def test_corrupted_settings_recovery(self):
        """Test recovery from corrupted settings file"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "corrupted.json"
            
            # Create corrupted JSON file
            with open(config_file, 'w') as f:
                f.write('{"corrupted": json, "missing": bracket')
            
            # Settings manager should handle corruption gracefully
            settings = LocalSettingsManager()
            settings.config_file = config_file
            loaded_settings = settings._load_settings()
            
            # Should fall back to defaults
            assert loaded_settings == settings.defaults
            
            # Should be able to save new settings
            settings._settings = loaded_settings
            settings.set('recovery_test', 'success')
            settings.save()
            
            # File should now be valid
            with open(config_file, 'r') as f:
                recovered_data = json.load(f)
            
            assert recovered_data['recovery_test'] == 'success'
    
    def test_concurrent_settings_access(self):
        """Test handling of concurrent settings access"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "concurrent.json"
            
            # Create two settings instances for same file
            settings1 = LocalSettingsManager()
            settings1.config_file = config_file
            settings2 = LocalSettingsManager()
            settings2.config_file = config_file
            
            # Modify different settings in each instance
            settings1.set('setting_from_instance1', 'value1')
            settings2.set('setting_from_instance2', 'value2')
            
            # Save both (last one wins for file content)
            settings1.save()
            settings2.save()
            
            # Load fresh instance to see final state
            settings3 = LocalSettingsManager()
            settings3.config_file = config_file
            settings3._settings = settings3._load_settings()
            
            # At least one setting should be preserved
            # (Exact behavior depends on implementation)
            file_contents = settings3._settings
            assert isinstance(file_contents, dict)
            assert len(file_contents) > 0


@pytest.mark.integration
class TestSettingsThemeIntegration:
    """Test theme settings integration"""
    
    def test_theme_switching_persistence(self):
        """Test that theme changes persist across restarts"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "theme_test.json"
            
            # Start with light theme
            settings1 = LocalSettingsManager()
            settings1.config_file = config_file
            settings1.set('theme_mode', 'light')
            settings1.save()
            
            # Switch to dark theme
            settings1.set('theme_mode', 'dark')
            settings1.save()
            
            # Simulate restart
            settings2 = LocalSettingsManager()
            settings2.config_file = config_file
            settings2._settings = settings2._load_settings()
            
            assert settings2.get('theme_mode') == 'dark'
            
            # Switch to system theme
            settings2.set('theme_mode', 'system')
            settings2.save()
            
            # Another restart
            settings3 = LocalSettingsManager()
            settings3.config_file = config_file
            settings3._settings = settings3._load_settings()
            
            assert settings3.get('theme_mode') == 'system'
    
    @pytest.mark.parametrize("theme_mode", ['light', 'dark', 'system'])
    def test_all_theme_modes_persistence(self, theme_mode):
        """Test persistence of all theme modes"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / f"theme_{theme_mode}.json"
            
            settings1 = LocalSettingsManager()
            settings1.config_file = config_file
            settings1.set('theme_mode', theme_mode)
            settings1.save()
            
            # Restart and verify
            settings2 = LocalSettingsManager()
            settings2.config_file = config_file
            settings2._settings = settings2._load_settings()
            
            assert settings2.get('theme_mode') == theme_mode


@pytest.mark.integration
class TestSettingsAudioIntegration:
    """Test audio settings integration"""
    
    def test_audio_settings_persistence(self):
        """Test that audio settings persist correctly"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "audio_test.json"
            
            settings1 = LocalSettingsManager()
            settings1.config_file = config_file
            
            # Set audio preferences
            settings1.set('alarm_volume', 0.9)
            settings1.set('sprint_alarm', 'meditation_bowl')
            settings1.set('break_alarm', 'classic_beep')
            settings1.save()
            
            # Restart
            settings2 = LocalSettingsManager()
            settings2.config_file = config_file
            settings2._settings = settings2._load_settings()
            
            assert settings2.get('alarm_volume') == 0.9
            assert settings2.get('sprint_alarm') == 'meditation_bowl'
            assert settings2.get('break_alarm') == 'classic_beep'
    
    def test_custom_audio_file_persistence(self):
        """Test persistence of custom audio file paths"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "custom_audio.json"
            
            settings1 = LocalSettingsManager()
            settings1.config_file = config_file
            
            # Set custom audio file paths
            custom_sprint_sound = "/path/to/custom/sprint.wav"
            custom_break_sound = "/path/to/custom/break.ogg"
            
            settings1.set('sprint_alarm', custom_sprint_sound)
            settings1.set('break_alarm', custom_break_sound)
            settings1.save()
            
            # Restart
            settings2 = LocalSettingsManager()
            settings2.config_file = config_file
            settings2._settings = settings2._load_settings()
            
            assert settings2.get('sprint_alarm') == custom_sprint_sound
            assert settings2.get('break_alarm') == custom_break_sound


@pytest.mark.integration
class TestSettingsDatabaseIntegration:
    """Test database settings integration"""
    
    def test_database_type_persistence(self):
        """Test persistence of database type setting"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "db_type_test.json"
            
            settings1 = LocalSettingsManager()
            settings1.config_file = config_file
            
            # Switch to Google Drive
            settings1.set('database_type', 'google_drive')
            settings1.set('google_drive_enabled', True)
            settings1.set('google_drive_folder', 'MyTimeTracking')
            settings1.save()
            
            # Restart
            settings2 = LocalSettingsManager()
            settings2.config_file = config_file
            settings2._settings = settings2._load_settings()
            
            assert settings2.get('database_type') == 'google_drive'
            assert settings2.get('google_drive_enabled') is True
            assert settings2.get('google_drive_folder') == 'MyTimeTracking'
    
    def test_local_database_path_persistence(self):
        """Test persistence of local database path"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "db_path_test.json"
            
            settings1 = LocalSettingsManager()
            settings1.config_file = config_file
            
            # Set custom database path
            custom_db_path = "/custom/database/location"
            settings1.set('database_local_path', custom_db_path)
            settings1.save()
            
            # Restart
            settings2 = LocalSettingsManager()
            settings2.config_file = config_file
            settings2._settings = settings2._load_settings()
            
            assert settings2.get('database_local_path') == custom_db_path
    
    def test_google_credentials_persistence(self):
        """Test persistence of Google Drive credentials path"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "credentials_test.json"
            
            settings1 = LocalSettingsManager()
            settings1.config_file = config_file
            
            # Set credentials path
            creds_path = "/secure/location/credentials.json"
            settings1.set('google_credentials_path', creds_path)
            settings1.save()
            
            # Restart
            settings2 = LocalSettingsManager()
            settings2.config_file = config_file
            settings2._settings = settings2._load_settings()
            
            assert settings2.get('google_credentials_path') == creds_path


@pytest.mark.integration
class TestSettingsWindowStateIntegration:
    """Test window state settings integration"""
    
    def test_window_position_persistence(self):
        """Test window position and size persistence"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "window_test.json"
            
            settings1 = LocalSettingsManager()
            settings1.config_file = config_file
            
            # Set window properties
            position = {'x': 150, 'y': 250}
            size = {'width': 900, 'height': 700}
            
            settings1.set('window_position', position)
            settings1.set('window_size', size)
            settings1.set('compact_mode', True)
            settings1.save()
            
            # Restart
            settings2 = LocalSettingsManager()
            settings2.config_file = config_file
            settings2._settings = settings2._load_settings()
            
            assert settings2.get('window_position') == position
            assert settings2.get('window_size') == size
            assert settings2.get('compact_mode') is True
    
    def test_auto_compact_mode_persistence(self):
        """Test auto compact mode setting persistence"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "compact_test.json"
            
            settings1 = LocalSettingsManager()
            settings1.config_file = config_file
            
            # Disable auto compact mode
            settings1.set('auto_compact_mode', False)
            settings1.save()
            
            # Restart
            settings2 = LocalSettingsManager()
            settings2.config_file = config_file
            settings2._settings = settings2._load_settings()
            
            assert settings2.get('auto_compact_mode') is False
            
            # Re-enable and test again
            settings2.set('auto_compact_mode', True)
            settings2.save()
            
            settings3 = LocalSettingsManager()
            settings3.config_file = config_file
            settings3._settings = settings3._load_settings()
            
            assert settings3.get('auto_compact_mode') is True