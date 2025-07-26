# Pomodora - Linux GUI Pomodoro Activity Tracker

A comprehensive Linux-based GUI application for Pomodoro technique activity tracking with multi-user database synchronization via Google Drive.

## Features

### Core Functionality
- **Pomodoro Timer**: Customizable 25-minute work sprints with 5-minute breaks
- **Audio Alarms**: Distinct sounds for sprint completion and break completion
- **Activity Tracking**: Log project and task descriptions for each sprint
- **Project Management**: Organize work by projects with color coding
- **Compact Mode**: Minimize to show only timer for unobtrusive monitoring

### Data Management
- **Local SQLite Database**: Fast, reliable local storage
- **Google Drive Sync**: Multi-user database synchronization across workstations
- **Data Views**: View activity by day, week, or month
- **Excel Export**: Generate detailed spreadsheets matching provided template format

## Installation

### Prerequisites
- Python 3.8 or higher
- pip package manager
- Linux desktop environment with GUI support

### Basic Install
```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the application
python src/main.py
```

### Desktop Integration

#### Ubuntu/GNOME
```bash
# Add to application launcher sidebar
cp pomodora.desktop ~/.local/share/applications/
```

### Google Drive Integration (Optional)
To enable multi-user database synchronization:

1. Create a Google Cloud Project
2. Enable the Google Drive API
3. Download credentials.json to the application data directory
4. Enable Google Drive sync in settings

## Usage

### Basic Operation
1. **Start a Sprint**: Select project, enter task description, click "Start Sprint"
2. **During Sprint**: Timer counts down from 25 minutes (or custom duration)
3. **Sprint Complete**: Alarm sounds, break timer begins automatically
4. **Complete Sprint**: Click "Complete Sprint" to log the activity
5. **Stop Early**: Click "Stop" to terminate current sprint

### Advanced Usage
- **Compact Mode**: View → Toggle Compact Mode for minimal screen footprint
- **Project Management**: Tools → Manage Projects to add/edit projects with colors
- **Data Export**: File → View Data → Export to Excel for detailed reports
- **Settings**: Tools → Settings to customize timer durations and audio

## Project Structure
```
pomodora/
├── src/
│   ├── main.py              # Application entry point
│   ├── gui/                 # GUI components
│   │   ├── main_window.py   # Main application window
│   │   ├── project_manager.py # Project management dialog
│   │   ├── settings_dialog.py # Settings configuration
│   │   ├── data_viewer.py   # Data viewing and export
│   │   └── alarm.py         # Audio alarm system
│   ├── timer/
│   │   └── pomodoro.py      # Timer logic and state management
│   └── tracking/
│       ├── models.py        # Database models and management
│       ├── excel_export.py  # Excel export functionality
│       └── google_drive.py  # Google Drive synchronization
├── tests/                   # Unit tests
├── requirements.txt         # Python dependencies
└── CLAUDE.md               # Development documentation
```

## Development

### Running Tests
```bash
python -m pytest tests/
```

### Commit Convention
All commits follow the format: `<subsystem>: one-line summary`

Examples:
- `timer: add customizable sprint duration`
- `gui: implement compact view mode`
- `tracking: add Google Drive synchronization`
