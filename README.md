# Pomodora - Cross-Platform Pomodoro Activity Tracker

A modern cross-platform GUI application for Pomodoro technique activity tracking with Google Drive synchronization and comprehensive audio alarm system.

## Features

### Timer & Audio
- **Automatic Timer Flow**: Sprint → Alarm → Break → Alarm → Auto-complete
- **Customizable Durations**: Sprint (1-60 min), Break (1-30 min)
- **Rich Audio System**: Generated tones, system sounds, and custom sound files
- **Dual Alarms**: Separate configurable sounds for sprint and break completion
- **Volume Control**: Adjustable alarm volume with test buttons

### Activity Management
- **Hierarchical Organization**: Categories → Projects → Sprints data model
- **Color-Coded Projects**: Visual organization with customizable colors
- **Task Logging**: Detailed descriptions for each sprint session
- **Activity Classifications**: Manage categories and projects with active/inactive states

### Interface & Modes
- **Modern GUI**: PySide6-based interface with dark/light themes
- **Compact Mode**: Minimal timer view with click-anywhere-to-exit
- **Auto-Compact Setting**: Automatically enter compact mode when sprint starts
- **Responsive Design**: Properly sized dialogs and modern styling

### Data Storage & Sync
- **Local Settings**: Platform-specific preferences storage
  - Linux: `~/.config/pomodora/`
  - macOS: `~/Library/Application Support/pomodora/`
  - Windows: `~/AppData/Local/pomodora/`
- **SQLite Database**: Fast, reliable sprint data storage with SQLAlchemy ORM
- **Google Drive Sync**: Multi-workstation database sharing with configurable folder
- **Smart Folder Detection**: Automatically finds existing Google Drive folders
- **Leader Election Sync**: Race-condition-free multi-workstation synchronization
- **Thread-Safe Operations**: Qt signal/slot mechanism prevents GUI threading issues

### Platform Support
- **Linux**: Full support with GNOME/KDE theme detection and system sounds
- **macOS**: Native dark mode detection with afplay fallback for audio compatibility
- **Windows**: Basic functionality with fallback theme detection

## Installation

### Prerequisites
- **Python 3.8+** with pip package manager
- **Desktop environment** with GUI support (Linux, macOS, Windows)
- **PySide6 dependencies** (usually installed automatically via pip)

#### Ubuntu/Debian System Dependencies
For Ubuntu systems, install the required Qt and audio system packages:

```bash
# Essential Qt/PySide6 dependencies
sudo apt update
sudo apt install -y \
    libxcb-cursor0 \
    libxcb1 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-randr0 \
    libxcb-render0 \
    libxcb-shape0 \
    libxcb-util1 \
    libxcb-xfixes0 \
    libxcb-xinerama0 \
    libxcb-xkb1 \
    libxkbcommon-x11-0 \
    libxkbcommon0 \
    qt6-qpa-plugins \
    libgl1-mesa-glx

# Audio system dependencies (for alarm sounds)
sudo apt install -y \
    libasound2-dev \
    portaudio19-dev \
    libpulse-dev
```

**Note**: The `libxcb-cursor0` package is specifically required for Qt 6.5.0+ and will prevent "Qt platform plugin could not be initialized" errors.

### Quick Start
```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the application
python src/main.py

# Run with different logging levels (for troubleshooting)
python src/main.py -v          # Info: basic status messages
python src/main.py -vv         # Debug: detailed debugging info
python src/main.py -vvv        # Trace: very detailed tracing

# Run in silent mode (disable audio alarms)
python src/main.py --no-audio
```

### Desktop Integration (Optional)
```bash
# Create desktop shortcut (if pomodora.desktop exists)
cp pomodora.desktop ~/.local/share/applications/
```

### Google Drive Sync Setup (Optional)
For multi-workstation database synchronization:

1. **Create Google Cloud Project** at [console.cloud.google.com](https://console.cloud.google.com)
2. **Enable Google Drive API** in the project
3. **Create credentials** (Desktop Application type) and download as `credentials.json`
4. **Place credentials file** in `~/.config/pomodora/`
5. **Enable sync** in Settings → Database Storage → Google Drive
6. **Configure folder** name (default: "TimeTracking")

## Usage

### Basic Workflow
1. **Select Project**: Choose from dropdown or create new via "Activity Classifications"
2. **Enter Task**: Describe what you'll work on during this sprint
3. **Start Sprint**: Click "Start Sprint" - timer begins countdown
4. **Sprint Complete**: Alarm sounds automatically, break timer starts
5. **Break Complete**: Second alarm sounds, sprint auto-completes and logs to database
6. **Manual Actions**: Use "Stop" to terminate early or "Complete Sprint" to finish manually

### Audio Configuration
- **Settings → Alarm Settings**: Configure volume and sound types
- **Sprint/Break Alarms**: Choose different sounds for each event
- **Sound Options**: Generated tones, system sounds, or browse custom files
- **Test Buttons**: Preview any alarm sound before saving
- **Cross-Platform Audio**: Automatic fallback to native system audio on macOS

### Interface Modes
- **Normal Mode**: Full interface with project selection and controls
- **Compact Mode**: Minimal timer-only view (toggle via menu or auto-activate)
- **Themes**: Switch between light and dark modes in Settings
- **Auto-Compact**: Automatically enter compact mode when sprints start

### Project Management
- **Activity Classifications**: Hierarchical Categories → Projects system
- **Color Coding**: Assign colors to projects for visual organization
- **Active/Inactive**: Toggle project visibility without deleting data
- **Default Projects**: Admin, Comm, Strategy, Research, SelfDev (configurable)

## Configuration

### Settings Location
All configuration stored in `~/.config/pomodora/settings.json`:

```json
{
  "theme_mode": "dark",
  "sprint_duration": 25,
  "break_duration": 5,
  "alarm_volume": 0.7,
  "sprint_alarm": "gentle_chime",
  "break_alarm": "urgent_alert",
  "auto_compact_mode": true,
  "database_type": "google_drive",
  "google_credentials_path": "~/.config/pomodora/credentials.json",
  "google_drive_folder": "TimeTracking"
}
```

### Database Schema
- **Categories**: Top-level organization (Admin, Comm, Strategy, etc.)
- **Projects**: Specific work areas within categories, with colors
- **Sprints**: Individual timed work sessions with task descriptions

## Project Structure
```
pomodora/
├── src/
│   ├── main.py                     # Application entry point
│   ├── gui/
│   │   └── pyside_main_window.py   # Complete PySide6 GUI implementation
│   ├── timer/
│   │   └── pomodoro_timer.py       # Timer state machine and logic
│   ├── audio/
│   │   └── alarm.py                # Audio system (generated + file-based)
│   └── tracking/
│       ├── models.py               # SQLAlchemy database models
│       ├── local_settings.py      # Local configuration management
│       └── google_drive.py         # Google Drive API integration
├── requirements.txt                # Python dependencies
├── CLAUDE.md                      # Development documentation
└── README.md                      # User documentation
```

## Development

### Technology Stack
- **PySide6**: Modern Qt6-based GUI framework with thread-safe signal/slot architecture
- **SQLAlchemy**: Database ORM with SQLite backend
- **Google Drive API v3**: Cloud synchronization with distributed leader election
- **pygame + numpy**: Audio generation and playback

### Commit Convention
Format: `<subsystem>: one-line summary`

Examples:
- `timer: add automatic break transition with dual alarms`
- `gui: implement dark/light theme with modern styling`
- `audio: add system sound browser with custom file support`
- `tracking: add Google Drive sync with smart folder detection`
