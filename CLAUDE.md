# Pomodora - Linux GUI Activity Tracker

A Linux-based GUI application for Pomodoro technique activity tracking.

## Project Overview

This application provides:
- Pomodoro timer functionality (25-minute work sessions, 5-minute breaks)
- Activity tracking and logging
- Session statistics and productivity metrics
- Native Linux GUI interface

## Technology Stack

- Language: Python 3
- GUI Framework: Tkinter (built-in) or PyQt5/6
- Data Storage: SQLite for session history
- Build System: setuptools/pip

## Development Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python src/main.py

# Run tests
python -m pytest tests/

# Build application
python setup.py build

# Package for distribution
python setup.py sdist bdist_wheel
```

## Project Structure

```
pomodora/
├── src/
│   ├── main.py          # Application entry point
│   ├── gui/             # GUI components
│   ├── timer/           # Pomodoro timer logic
│   └── tracking/        # Activity tracking
├── tests/               # Unit tests
├── requirements.txt     # Python dependencies
└── setup.py            # Build configuration
```

## Commit Convention

Format: `<subsystem>: one-line summary`

Examples:
- `timer: add basic pomodoro countdown functionality`
- `gui: implement main window layout`
- `tracking: add session history storage`