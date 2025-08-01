#!/usr/bin/env python3
"""
Pomodora - Modern Linux GUI Pomodoro Activity Tracker

A comprehensive Pomodoro timer application with modern PySide6 interface,
activity tracking, project management, and Excel export capabilities.
"""

import sys
import os
import argparse
import signal
from pathlib import Path

# Add src directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.logging import set_verbose_level, info_print
from gui.pyside_main_window import main

def parse_args():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(description="Pomodora - Linux GUI Pomodoro Activity Tracker")
    
    # Support multiple verbose levels
    verbose_group = parser.add_mutually_exclusive_group()
    verbose_group.add_argument("-v", "--verbose", action="count", default=0,
                             help="Increase verbosity (use -v, -vv, -vvv for levels 1-3)")
    
    parser.add_argument("--no-audio", action="store_true",
                       help="Disable audio alarms (silent mode)")
    return parser.parse_args()

def setup_signal_handlers():
    """Setup signal handlers for graceful shutdown"""
    def signal_handler(signum, frame):
        info_print(f"Received signal {signum}, initiating graceful shutdown...")
        
        # Try to access the main window if it exists
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            # Find the main window
            for widget in app.allWidgets():
                if hasattr(widget, 'db_manager') and widget.db_manager:
                    info_print("Completing pending database syncs before exit...")
                    if hasattr(widget.db_manager, 'wait_for_pending_syncs'):
                        widget.db_manager.wait_for_pending_syncs(timeout=10.0)
                    break
            
            # Close the application gracefully
            app.quit()
        else:
            sys.exit(0)
    
    # Register handlers for common termination signals
    signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # Termination request

if __name__ == "__main__":
    args = parse_args()
    
    # Set global verbose level
    set_verbose_level(args.verbose)
    
    # Set global audio disable flag
    if args.no_audio:
        import os
        os.environ['POMODORA_NO_AUDIO'] = '1'
    
    # Show startup messages based on verbosity level
    if args.verbose == 1:
        print("Pomodora starting with info logging...")
    elif args.verbose == 2:
        print("Pomodora starting with debug logging...")
    elif args.verbose >= 3:
        print("Pomodora starting with trace logging...")
    
    if args.no_audio:
        print("Pomodora starting in silent mode (no audio alarms)...")
    
    # Setup signal handlers for graceful shutdown
    setup_signal_handlers()
    
    main()