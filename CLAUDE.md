# Pomodora - Cross-Platform Activity Tracker

A modern cross-platform GUI application for Pomodoro technique activity tracking with Google Drive synchronization.

## Project Overview

This application provides:
- **Pomodoro Timer**: Customizable sprint (1-60 min) and break (1-30 min) durations with automatic transitions
- **Audio Alarms**: Configurable alarms with system sounds, generated tones, and custom sound files
- **Activity Tracking**: Independent Task Categories and Projects with 3-field Sprint logging (Project + Task Category + Description)
- **Google Drive Sync**: Multi-workstation database synchronization with configurable folder location
- **Modern GUI**: PySide6-based interface with dark/light themes and compact mode
- **Data Export**: Excel export functionality with detailed sprint reports

## Technology Stack

- **Language**: Python 3.8+
- **GUI Framework**: PySide6 (Qt6)
- **Database**: SQLAlchemy ORM with SQLite backend
- **Cloud Sync**: Google Drive API v3
- **Audio**: pygame (optional) with numpy for sound generation and file playback
- **Export**: openpyxl for Excel file generation

## Development Commands

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the application
python src/main.py

# Run with different logging levels
python src/main.py -v          # Info level (basic status messages)
python src/main.py -vv         # Debug level (detailed debugging info)
python src/main.py -vvv        # Trace level (very detailed tracing)

# Run in silent mode (no audio alarms)
python src/main.py --no-audio

# Run tests (IMPORTANT: must be run from activated venv)
source venv/bin/activate  # Activate venv first!
python -m pytest tests/

# Check syntax
python -m py_compile src/main.py
```

## Project Structure

```
pomodora/
├── src/
│   ├── main.py                     # Application entry point
│   ├── gui/
│   │   └── pyside_main_window.py   # Main PySide6 GUI implementation
│   ├── timer/
│   │   └── pomodoro_timer.py       # Timer state machine and logic
│   ├── audio/
│   │   ├── __init__.py
│   │   └── alarm.py                # Audio alarm system (generated + file-based)
│   └── tracking/
│       ├── __init__.py
│       ├── models.py                       # SQLAlchemy database models
│       ├── database_manager_unified.py     # Main database interface (UnifiedDatabaseManager)
│       ├── sync_config.py                  # Sync strategy and backend configuration
│       ├── leader_election_sync.py         # Leader election sync manager
│       ├── coordination_backend.py         # Abstract coordination interface
│       ├── local_file_backend.py           # Local file coordination backend
│       ├── google_drive_backend.py         # Google Drive coordination backend
│       ├── operation_log.py                # Operation tracking for database merging
│       ├── database_backup.py              # Database backup management system
│       └── local_settings.py              # Local configuration management
├── requirements.txt                # Python dependencies
├── CLAUDE.md                      # Development documentation
└── README.md                      # User documentation
```

## Architecture

The application uses a modern, configurable sync architecture with two strategies:

### Local-Only Strategy (`sync_strategy: "local_only"`)
- **Use Case**: Single workstation, no cloud sync needed
- **Database**: Single SQLite file stored locally
- **Coordination**: None required
- **Backup**: Local backups only

### Leader Election Strategy (`sync_strategy: "leader_election"`)
- **Use Case**: Multi-workstation sync with conflict resolution
- **Database**: Local cache synchronized with shared storage
- **Coordination**: Distributed leader election prevents race conditions
- **Backends Available**:
  - **Local File Backend**: Shared database file for multi-process coordination
  - **Google Drive Backend**: Cloud sync for multi-device coordination

### Components

- **UnifiedDatabaseManager**: Main database interface that handles both strategies
- **SyncConfiguration**: Configuration management for sync strategy and backends
- **LeaderElectionSyncManager**: Handles leader election and conflict resolution
- **CoordinationBackend**: Abstract interface for different coordination mechanisms
- **OperationTracker**: Tracks database changes for intelligent merging

## Key Features

### Timer System
- **Automatic Flow**: Sprint → Alarm → Break → Alarm → Auto-complete
- **Customizable Durations**: Sprint (1-60 min), Break (1-30 min)
- **Timer States**: IDLE, RUNNING, PAUSED, BREAK
- **Compact Mode**: Minimal timer view with auto-compact setting

### Audio System
- **Generated Sounds**: 6 built-in alarm types (gentle_chime, classic_beep, triple_bell, urgent_alert, meditation_bowl, none)
- **System Sounds**: Auto-discovers sounds from `/usr/share/sounds`
- **Custom Files**: Browse and select .wav, .ogg, .oga, .mp3 files
- **Separate Alarms**: Different sounds for sprint vs break completion

### Data Management
- **Local Settings**: JSON files in `~/.config/pomodora/` for workstation-specific preferences
- **Modern Database Schema**: SQLite with foreign key relationships (Task Categories ↔ Projects ↔ Sprints)
- **Independent Task Categories**: Task categories and projects are decoupled for flexible organization
- **Foreign Key Integrity**: Database uses proper foreign key relationships instead of string references
- **Google Drive Sync**: Multi-workstation database sharing with intelligent merge operations
- **Operation-Based Merging**: In-memory operation tracking ensures proper conflict resolution
- **Leader Election Sync**: Distributed leader election algorithm prevents race conditions
- **Thread-Safe Operations**: Qt signal/slot mechanism ensures GUI thread safety
- **Automatic Backups**: Local backup system with daily/monthly/yearly retention policies

### User Interface
- **Themes**: Dark/Light mode with modern PySide6 styling
- **Compact Mode**: Click-anywhere-to-exit minimal timer view
- **Activity Classifications**: Independent task categories and projects with flexible assignment
- **3-Field Sprint Creation**: Project, Task Category, and Task Description for detailed tracking
- **Task Description History Navigation**: Use Up/Down arrow keys in the task description field to navigate through previously used task descriptions chronologically
- **Settings Dialog**: Comprehensive configuration with browse buttons and test features

## Logging Levels

The application supports multiple verbosity levels for debugging and troubleshooting:

- **Level 0** (default): Errors and warnings only
- **Level 1** (`-v`): Basic info messages (database init, folder creation, sync status)
- **Level 2** (`-vv`): Debug messages (timer state changes, project loading, database queries)
- **Level 3** (`-vvv`): Trace messages (detailed object info, timer internals, API calls)

## Settings Configuration

All settings stored in `~/.config/pomodora/settings.json`:

### Application Settings
- `theme_mode`: "light" or "dark"
- `sprint_duration`, `break_duration`: Timer durations in minutes
- `alarm_volume`: 0.0 to 1.0
- `sprint_alarm`, `break_alarm`: Sound identifiers or file paths
- `auto_compact_mode`: Auto-enter compact mode when sprint starts

### Sync Configuration
- `sync_strategy`: "local_only" or "leader_election"
- `coordination_backend`: Configuration for sync coordination
  - `type`: "local_file" or "google_drive"
  - `local_file.shared_db_path`: Path to shared database file
  - `google_drive.credentials_path`: Path to Google Drive credentials file
  - `google_drive.folder_name`: Folder name in Google Drive for database storage
- `local_cache_db_path`: Path to local cache database (for leader_election strategy)

## Database Backup System

The application includes an automatic backup system that protects your data with configurable retention policies.

### Backup Structure

**Local-Only Strategy (`sync_strategy: "local_only"`):**
- Database: `~/.config/pomodora/database/pomodora.db`
- Backups: `~/.config/pomodora/database/Backup/`

**Leader Election Strategy (`sync_strategy: "leader_election"`):**
- Database: `~/.config/pomodora/cache/pomodora.db` (local cache of synced database)
- Backups: 
  - Local File Backend: `~/.config/pomodora/cache/Backup/`
  - Google Drive Backend: `~/.config/pomodora/google_drive_backups/Backup/`

### Backup Types and Retention

- **Daily Backups** (`Backup/Daily/`): Created automatically, keeps last 7 days
  - **Smart Daily Logic**: Only ONE backup created per day, regardless of how many times the app runs
  - **No Overwrites**: Each daily backup has a unique timestamp (`YYYYMMDD_HHMMSS`)
  - **Multiple Operations**: Second sprint, third sprint, etc. on same day are skipped - "Daily backup already exists for today"
- **Monthly Backups** (`Backup/Monthly/`): Created once per month, keeps last 12 months
- **Yearly Backups** (`Backup/Yearly/`): Created once per year, kept indefinitely

### Automatic Backup Triggers

Backups are created automatically when:
- Application starts (if needed based on date)
- Default categories/projects are initialized
- New categories or projects are created
- Sprints are completed and saved

**Important**: Multiple operations on the same day will NOT create multiple daily backups. The system checks for existing daily backups and skips creation if one already exists for today.

### File Naming Convention

- Daily: `pomodora_daily_YYYYMMDD_HHMMSS.db`
- Monthly: `pomodora_monthly_YYYYMM.db`
- Yearly: `pomodora_yearly_YYYY.db`

### Backup Cleanup

The system automatically removes old backups beyond the retention limits to prevent unlimited disk usage while maintaining comprehensive data protection.

## Multi-Workstation Deployment

The application is **production-ready** for deployment across multiple workstations:

### Leader Election Synchronization
- **Race-Condition Free**: Distributed leader election algorithm ensures only one workstation syncs at a time
- **4-Phase Process**: Intent registration → Coordination wait → Leader election → Atomic sync
- **Fault Tolerant**: Failed syncs don't affect other workstations, automatic cleanup and retry
- **Operation-Based Merging**: In-memory operation tracking replays local changes onto remote database
- **Data Integrity**: All sprints from all workstations are preserved through intelligent conflict resolution

### Synchronization Triggers

The application synchronizes the local cache with shared storage through these 4 triggers only:

#### 1. Startup Sync
- **When**: Application starts (only for `leader_election` strategy)
- **Implementation**: `UnifiedDatabaseManager._perform_initial_sync()`
- **Timeout**: 120 seconds
- **Purpose**: Download remote changes from other workstations before local use

#### 2. Exit/Shutdown Sync  
- **When**: Application exits or receives termination signals (SIGINT, SIGTERM)
- **Implementation**: Signal handlers in `main.py` call `trigger_shutdown_sync()`
- **Timeout**: 120 seconds (graceful), 10 seconds (wait for pending syncs)
- **Purpose**: Upload local changes before shutdown to avoid data loss

#### 3. Manual Sync
- **When**: User selects "Force Sync" from File menu
- **Implementation**: GUI calls `trigger_manual_sync()` → `force_sync_as_leader()`
- **Timeout**: 300 seconds (5 minutes)
- **Purpose**: User-initiated immediate sync for testing or before critical operations

#### 4. Idle Sync
- **When**: After 10 minutes of user inactivity
- **Implementation**: `perform_idle_sync()` triggered by single-shot QTimer
- **Timeout**: 60 seconds
- **Purpose**: Sync pending changes during user breaks
- **Reset**: Timer resets on any user activity (typing, clicking, timer operations)

#### Operation Tracking
Database operations (sprint completion, project creation, etc.) are **tracked** in the operation log for later synchronization but do **not** trigger immediate sync. All pending operations are synchronized during the 4 trigger points above.

**Note**: For `local_only` strategy, no synchronization occurs as there is no shared storage.

### Thread Safety
- **Qt Signal/Slot Architecture**: Timer callbacks use Qt signals to prevent threading issues
- **Main Thread GUI Updates**: All UI operations happen on the main thread via signal connections
- **Background Timer Operations**: Timer logic runs in background threads without blocking UI

### Deployment Benefits
- **Local-First**: All functionality works offline, sync happens when available
- **Automatic Conflict Resolution**: Database merging handles simultaneous sprint completion
- **Self-Healing**: System recovers from network failures and API errors
- **Clean Logging**: Multi-level logging (`-v`, `-vv`, `-vvv`) for production troubleshooting

## Coding Style

Each source file should contain only 1 logically coherent component of the system.  Source files should be kept small, so that if any source file grows to a large size, it should then be refactored into logically independent and coherent components.  Ideally, all source files should be less that 1000 lines.  This allows:
- Maintainability: Each component has a single responsibility
- Reusability: Components can be used independently
- Readability: Smaller, focused files are easier to understand
- Testability: Individual components can be tested in isolation

A general coding principle to follow is to have a debug logging facility that supports multiple levels of detail.  Make sure that the key steps of your algorithms or code flow are captured in this logging, so that when bugs are found, I can send the debug output to you for easier triaging.  For hard to reproduce issues, have a mode where logging is always occuring, but output to a file in /tmp, one for each invocation of the application, (and thus not polluting the terminal from where the application is being run).  Then I can go back and find past runs of the application that had exhibited the defect.

Since my editor flags trailing whitespaces (tab or space), make sure they are removed.

## Testing Architecture

### Test Structure and Organization

The test suite follows a hierarchical organization pattern:

```
tests/
├── unit/                          # Isolated component tests
│   ├── gui/                       # GUI component tests
│   ├── tracking/                  # Database and sync logic tests
│   ├── timer/                     # Timer functionality tests
│   └── utils/                     # Utility function tests
├── integration/                   # Multi-component interaction tests
├── feature/                       # End-to-end feature tests
├── concurrency/                   # Multi-threading and sync tests
├── helpers/                       # Test utilities and fixtures
│   ├── test_database_manager.py   # Lightweight test database manager
│   ├── database_helpers.py        # Database setup and teardown utilities
│   └── unified_sync_simulators.py # Multi-workstation sync simulators
└── conftest.py                    # pytest configuration and fixtures
```

### Database Testing Patterns

#### Database Manager Initialization
```python
# Standard pattern for tests
from tracking.database_manager_unified import UnifiedDatabaseManager as DatabaseManager

# For unit tests - simple initialization
self.db_manager = DatabaseManager(db_path=self.db_path)

# For integration tests with temporary database
temp_dir = tempfile.TemporaryDirectory()
db_path = os.path.join(temp_dir.name, "test.db")
db_manager = DatabaseManager(db_path=db_path)
```

#### Test Database Setup
```python
# Standard test setup pattern
@pytest.fixture(autouse=True)
def setup_method(self):
    # Create temporary database
    self.temp_dir = tempfile.TemporaryDirectory()
    self.db_path = os.path.join(self.temp_dir.name, "test.db")
    self.db_manager = DatabaseManager(db_path=self.db_path)
    
    # Create test data
    self.setup_test_data()
    
def teardown_method(self):
    self.temp_dir.cleanup()
```

### GUI Testing Patterns

#### Qt Application Setup
```python
# Required for any GUI component testing
@pytest.fixture(autouse=True)
def setup_method(self):
    # Create QApplication if it doesn't exist (needed for Qt widgets)
    if not QApplication.instance():
        self.app = QApplication([])
```

#### Mock GUI Components
```python
# Pattern for testing GUI components in isolation
class MockMainWindow(QObject):  # Must inherit from QObject for event filters
    def __init__(self, db_manager):
        super().__init__()  # Essential for Qt integration
        self.db_manager = db_manager
        self.widget = QLineEdit()  # Or other Qt widget
        
        # Install event filters if needed
        self.widget.installEventFilter(self)
```

#### Event Filter Testing
```python
# Pattern for testing keyboard/mouse event handling
def test_event_handling(self):
    # Create mock event
    mock_event = Mock()
    mock_event.type.return_value = QEvent.Type.KeyPress
    mock_event.key.return_value = Qt.Key.Key_Down
    
    # Test event processing
    result = self.window.eventFilter(self.widget, mock_event)
    assert result is True  # Event consumed
```

### Test Data Creation Patterns

#### Sprint Test Data
```python
def create_test_sprints(self, session, project, category):
    """Standard pattern for creating chronological test data"""
    base_time = datetime.now() - timedelta(hours=5)
    
    test_sprints = [
        (base_time + timedelta(hours=4), "Most recent task"),
        (base_time + timedelta(hours=3), "Middle task"),
        (base_time + timedelta(hours=2), "Oldest task"),
    ]
    
    for start_time, task_desc in test_sprints:
        sprint = Sprint(
            project_id=project.id,
            task_category_id=category.id,
            task_description=task_desc,
            start_time=start_time,
            end_time=start_time + timedelta(minutes=25),
            completed=True,
            duration_minutes=25
        )
        session.add(sprint)
    
    session.commit()
```

### Import Path Configuration

```python
# Standard pattern for all test files
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))
```

### Test Categories and When to Use Each

#### Unit Tests (`tests/unit/`)
- **Purpose**: Test individual components in isolation
- **Database**: Temporary SQLite files or in-memory databases
- **Scope**: Single class or function functionality
- **Examples**: Database models, timer logic, GUI components

#### Integration Tests (`tests/integration/`)
- **Purpose**: Test component interactions and workflows
- **Database**: Temporary file databases with realistic data
- **Scope**: Multi-component functionality
- **Examples**: GUI-database integration, sync workflows

#### Feature Tests (`tests/feature/`)
- **Purpose**: Test complete user-facing features
- **Database**: Full temporary database with complex scenarios
- **Scope**: End-to-end feature validation
- **Examples**: Complete sprint workflows, data export features

#### Concurrency Tests (`tests/concurrency/`)
- **Purpose**: Test multi-threading and synchronization
- **Database**: Multiple database instances for sync testing
- **Scope**: Race conditions, deadlocks, data consistency
- **Examples**: Multi-workstation sync, leader election

### Common Test Utilities

#### Database Helpers (`tests/helpers/database_helpers.py`)
```python
from helpers.database_helpers import (
    create_empty_db,           # Empty database
    create_basic_db,           # Database with default categories/projects  
    create_populated_db,       # Database with sample sprints
    create_test_project,       # Single project creation
    create_test_category,      # Single category creation
    create_test_sprint         # Single sprint creation
)
```

#### Test Database Manager (`tests/helpers/test_database_manager.py`)
```python
# Lightweight alternative for simple unit tests
from helpers.test_database_manager import UnitTestDatabaseManager as DatabaseManager
```

### Running Tests

```bash
# Full test suite
source venv/bin/activate
python -m pytest tests/ -v

# Specific categories
python -m pytest tests/unit/ -v                    # All unit tests
python -m pytest tests/unit/gui/ -v                # GUI unit tests
python -m pytest tests/integration/ -v             # Integration tests

# Specific test files or methods
python -m pytest tests/unit/gui/test_task_description_history.py -v
python -m pytest tests/unit/gui/test_task_description_history.py::TestTaskDescriptionHistory::test_basic -v
```

### Testing Guidelines

1. **Always use temporary databases** - Never test against production data
2. **Activate virtual environment** - Required for dependencies: `source venv/bin/activate`
3. **Import path setup** - Always add src to path in test files
4. **Qt integration** - Create QApplication for any GUI tests
5. **Database cleanup** - Use `tempfile.TemporaryDirectory()` with proper cleanup
6. **Realistic test data** - Create chronologically ordered, realistic test scenarios
7. **Edge case coverage** - Test empty databases, error conditions, boundary cases
8. **Mock external dependencies** - Don't require Google Drive credentials in tests

### Application Testing Safety

When Claude tries to run the app for debugging:

- **Always use local database configuration** so Google Drive credentials are not required
- **Never run `python src/main.py` directly** without local database options  
- **Use test database paths** to avoid compromising production data
- **Pass `--no-audio` flag** to avoid audio system dependencies during testing

## Commit Convention

Format: `<subsystem>: one-line summary`

Examples:
- `timer: add automatic break transition with alarm`
- `gui: implement dark/light theme switching`
- `audio: add system sound file browser support`
- `tracking: add Google Drive database synchronization`
- `sync: implement leader election for multi-workstation deployment`

Only commit files that are part of the development.  Do not commit all files blindly or include files that were not part of the development effort that is being committed.

Before each commit, run the full set of tests to ensure that the commit isn't breaking any of them.

When creating a commit and asking me if it should be applied, also list the files that are affected by the commit
