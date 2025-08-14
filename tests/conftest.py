"""
Global pytest configuration and shared fixtures for Pomodora tests.
Provides isolated test environments with zero impact on production data.
"""

import pytest
import tempfile
import os
import sys
import json
from pathlib import Path

# Add src to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

# Import after path setup
import sys
sys.path.insert(0, str(Path(__file__).parent))  # Add tests directory
from helpers.test_database_manager import UnitTestDatabaseManager as DatabaseManager, TaskCategory, Project
from tracking.local_settings import LocalSettingsManager
from timer.pomodoro import PomodoroTimer
from unittest.mock import patch


@pytest.fixture(scope="function", autouse=True)
def protect_production_settings():
    """Automatically protect production settings from being modified by tests"""
    import tempfile
    import shutil
    
    # Create a completely isolated temporary directory for all test settings
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_config_dir = Path(temp_dir)
        temp_settings_file = temp_config_dir / 'settings.json'
        
        # Write minimal safe test config
        with open(temp_settings_file, 'w') as f:
            json.dump({
                "sync_strategy": "local_only",
                "coordination_backend": {
                    "type": "local_file",
                    "local_file": {
                        "shared_db_path": str(temp_config_dir / "pomodora.db")
                    }
                },
                "local_cache_db_path": str(temp_config_dir / "pomodora.db")
            }, f)
        
        # Create an isolated LocalSettingsManager that uses temp directory
        test_settings_manager = LocalSettingsManager.__new__(LocalSettingsManager)
        test_settings_manager.config_file = temp_settings_file
        test_settings_manager.defaults = {
            'theme_mode': 'light',
            'sprint_duration': 25,
            'break_duration': 5,
            'alarm_volume': 0.7,
            'sprint_alarm': 'gentle_chime',
            'break_alarm': 'urgent_alert',
            'auto_compact_mode': True,
            'window_position': None,
            'window_size': None,
            'compact_mode': False,
            'sync_strategy': 'local_only',
            'coordination_backend': {
                'type': 'local_file',
                'local_file': {
                    'shared_db_path': str(temp_config_dir / "pomodora.db")
                }
            },
            'local_cache_db_path': str(temp_config_dir / "pomodora.db"),
        }
        test_settings_manager._settings = test_settings_manager.defaults.copy()
        
        # Patch ALL possible ways settings can be accessed
        with patch('tracking.local_settings.get_local_settings', return_value=test_settings_manager), \
             patch('tracking.sync_config.get_local_settings', return_value=test_settings_manager), \
             patch('tracking.local_settings.LocalSettingsManager', return_value=test_settings_manager):
            yield


@pytest.fixture(scope="function")
def isolated_db():
    """Creates a fresh in-memory database for each test - NO impact on production"""
    # Tables are created automatically in __init__
    db_manager = DatabaseManager(":memory:")
    try:
        # Initialize with default data
        db_manager.initialize_default_projects()
        yield db_manager
    finally:
        # Clean up session if it exists
        if hasattr(db_manager, 'session') and db_manager.session:
            db_manager.session.close()


@pytest.fixture(scope="function") 
def temp_test_db():
    """Creates temporary SQLite file database for integration tests"""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_db:
        db_path = tmp_db.name
    try:
        # DatabaseManager expects just the path, not a full URI
        db_manager = DatabaseManager(db_path)
        db_manager.initialize_default_projects()
        yield db_manager
    finally:
        # Clean up session if it exists
        if hasattr(db_manager, 'session') and db_manager.session:
            db_manager.session.close()
        if os.path.exists(db_path):
            os.unlink(db_path)


@pytest.fixture(scope="function")
def temp_settings():
    """Temporary settings that don't persist to disk"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create temporary settings manager
        settings = LocalSettingsManager()
        # Override config file to temporary location
        settings.config_file = Path(temp_dir) / "test_settings.json"
        
        # Reset to clean defaults by overriding _settings
        settings._settings = settings.defaults.copy()
        yield settings


@pytest.fixture(scope="function")
def test_timer():
    """Basic timer instance for testing"""
    return PomodoroTimer(sprint_duration=1, break_duration=1)  # 1 minute for fast tests


@pytest.fixture(scope="function")
def sample_project(isolated_db):
    """Creates a sample project for testing"""
    session = isolated_db.get_session()
    try:
        # Get an existing project or create a unique one
        existing_project = session.query(Project).first()
        if existing_project:
            yield existing_project
        else:
            project = Project(name="Sample Test Project", color="#ff0000")
            session.add(project)
            session.commit()
            session.refresh(project)
            yield project
    finally:
        session.close()


@pytest.fixture(scope="function")
def sample_category(isolated_db):
    """Creates a sample task category for testing"""
    session = isolated_db.get_session()
    try:
        # Get an existing category or create a unique one
        existing_category = session.query(TaskCategory).first()
        if existing_category:
            yield existing_category
        else:
            category = TaskCategory(name="Sample Test Category", color="#00ff00")
            session.add(category)
            session.commit()
            session.refresh(category)
            yield category
    finally:
        session.close()


@pytest.fixture(scope="session")
def test_audio_disabled():
    """Disable audio for all tests to prevent hardware dependencies"""
    original_env = os.environ.get('PYGAME_HIDE_SUPPORT_PROMPT')
    os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
    os.environ['POMODORA_TEST_NO_AUDIO'] = '1'
    yield
    if original_env is None:
        os.environ.pop('PYGAME_HIDE_SUPPORT_PROMPT', None)
    else:
        os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = original_env
    os.environ.pop('POMODORA_TEST_NO_AUDIO', None)


@pytest.fixture(scope="function")
def mock_google_drive():
    """Mock Google Drive API for testing sync operations"""
    class MockGoogleDrive:
        def __init__(self):
            self.files = {}
            self.call_count = 0
            
        def upload_file(self, file_path, folder_name):
            self.call_count += 1
            self.files[folder_name] = file_path
            return {"id": f"mock_file_{self.call_count}"}
            
        def download_file(self, file_id, destination):
            self.call_count += 1
            return True
            
        def list_files(self, folder_name):
            return [{"id": "mock_file", "name": "pomodora.db"}] if folder_name in self.files else []
    
    return MockGoogleDrive()


# Pytest configuration hooks
def pytest_configure(config):
    """Configure pytest with custom markers"""
    config.addinivalue_line("markers", "unit: Unit tests (Tier 1) - fast, isolated component testing")
    config.addinivalue_line("markers", "integration: Integration tests (Tier 2) - cross-component validation")
    config.addinivalue_line("markers", "feature: Feature tests (Tier 3) - end-to-end user scenarios")
    config.addinivalue_line("markers", "concurrency: Concurrency tests (Tier 4) - multi-app database stress")
    config.addinivalue_line("markers", "system: System tests (Tier 5) - comprehensive release validation")
    config.addinivalue_line("markers", "gui: Tests requiring PySide6 GUI components")
    config.addinivalue_line("markers", "audio: Tests requiring audio hardware or pygame")
    config.addinivalue_line("markers", "network: Tests requiring network connectivity or Google Drive API")
    config.addinivalue_line("markers", "slow: Tests taking more than 10 seconds")
    config.addinivalue_line("markers", "database: Tests requiring database operations")
    config.addinivalue_line("markers", "cross_platform: Tests that must pass on all supported platforms")