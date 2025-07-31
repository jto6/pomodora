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

# Run tests (if implemented)
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
│       ├── models.py               # SQLAlchemy database models
│       ├── database_backup.py      # Database backup management system
│       ├── operation_log.py        # In-memory operation tracking for database merging
│       ├── local_settings.py      # Local configuration management
│       └── google_drive.py         # Google Drive API integration
├── requirements.txt                # Python dependencies
├── CLAUDE.md                      # Development documentation
└── README.md                      # User documentation
```

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
- **Settings Dialog**: Comprehensive configuration with browse buttons and test features

## Logging Levels

The application supports multiple verbosity levels for debugging and troubleshooting:

- **Level 0** (default): Errors and warnings only
- **Level 1** (`-v`): Basic info messages (database init, folder creation, sync status)
- **Level 2** (`-vv`): Debug messages (timer state changes, project loading, database queries)
- **Level 3** (`-vvv`): Trace messages (detailed object info, timer internals, API calls)

## Settings Configuration

All settings stored in `~/.config/pomodora/settings.json`:
- `theme_mode`: "light" or "dark"
- `sprint_duration`, `break_duration`: Timer durations in minutes
- `alarm_volume`: 0.0 to 1.0
- `sprint_alarm`, `break_alarm`: Sound identifiers or file paths
- `auto_compact_mode`: Auto-enter compact mode when sprint starts
- `database_type`: "local" or "google_drive"
- `google_credentials_path`: Path to Google Drive credentials file
- `google_drive_folder`: Folder name in Google Drive for database storage

## Database Backup System

The application includes an automatic backup system that protects your data with configurable retention policies.

### Backup Structure

**Local Database Mode:**
- Database: `/your/configured/path/pomodora.db`
- Backups: `/your/configured/path/Backup/`

**Google Drive Mode:**
- Database: `~/.config/pomodora/cache/pomodora.db` (synced from Google Drive)
- Backups: `~/.config/pomodora/google_drive_backups/Backup/`

### Backup Types and Retention

- **Daily Backups** (`Backup/Daily/`): Created automatically, keeps last 7 days
- **Monthly Backups** (`Backup/Monthly/`): Created once per month, keeps last 12 months
- **Yearly Backups** (`Backup/Yearly/`): Created once per year, kept indefinitely

### Automatic Backup Triggers

Backups are created automatically when:
- Application starts (if needed based on date)
- Default categories/projects are initialized
- New categories or projects are created
- Sprints are completed and saved

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

## Testing

When Claude tries to run the app to debug itself, it should always use a local test database or create a temporary test version of the app that doesn't require credentials, so that
- the production database isn't compromised
- credentials are not required by Claude to access Google drive

DO NOT try to run the app directly (eg, python src/main.py) without having a way to pass in options to use a local test database or otherwise avoid requiring Google API credentials.  If you create a test app that will interface with the database, it should access a local test database.

## Commit Convention

Format: `<subsystem>: one-line summary`

Examples:
- `timer: add automatic break transition with alarm`
- `gui: implement dark/light theme switching`
- `audio: add system sound file browser support`
- `tracking: add Google Drive database synchronization`
- `sync: implement leader election for multi-workstation deployment`

Only commit files that are part of the development.  Do not commit all files blindly or include files that were not part of the development effort that is being committed.
