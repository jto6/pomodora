# Pomodora - Cross-Platform Activity Tracker

A modern cross-platform GUI application for Pomodoro technique activity tracking with Google Drive synchronization.

## Project Overview

This application provides:
- **Pomodoro Timer**: Customizable sprint (1-60 min) and break (1-30 min) durations with automatic transitions
- **Audio Alarms**: Configurable alarms with system sounds, generated tones, and custom sound files
- **Activity Tracking**: Hierarchical Categories → Projects → Sprints data model with task logging
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

When Claude tries to run the app to debug itself, it should always use a local test database or create a temporary test version of the app that doesn't require credentials, so that
- the production database isn't compromised
- credentials are not required by Claude to access Google drive

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
- **Shared Database**: SQLite database with Categories → Projects → Sprints hierarchy
- **Google Drive Sync**: Multi-workstation database sharing with configurable folder location

### User Interface
- **Themes**: Dark/Light mode with modern PySide6 styling
- **Compact Mode**: Click-anywhere-to-exit minimal timer view
- **Activity Classifications**: Hierarchical project management with color coding
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

## Commit Convention

Format: `<subsystem>: one-line summary`

Examples:
- `timer: add automatic break transition with alarm`
- `gui: implement dark/light theme switching`
- `audio: add system sound file browser support`
- `tracking: add Google Drive database synchronization`

Only commit files that are part of the development.  Do not commit all files blindly or include files that were not part of the development effort that is being committed.
