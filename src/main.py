#!/usr/bin/env python3
"""
Pomodora - Linux GUI Pomodoro Activity Tracker

A comprehensive Pomodoro timer application with activity tracking,
project management, and Excel export capabilities.
"""

import sys
import os
import tkinter as tk
from tkinter import ttk
import argparse
from pathlib import Path

# Add src directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui.main_window import MainWindow

def setup_styles():
    """Setup ttk styles for better appearance"""
    style = ttk.Style()
    
    # Use a modern theme if available
    available_themes = style.theme_names()
    preferred_themes = ['clam', 'alt', 'default']
    
    for theme in preferred_themes:
        if theme in available_themes:
            style.theme_use(theme)
            break
    
    # Configure custom styles
    style.configure('Accent.TButton', foreground='white', background='#3498db')
    style.map('Accent.TButton', 
              background=[('active', '#2980b9'), ('pressed', '#21618c')])

def check_dependencies():
    """Check if all required dependencies are available"""
    missing = []
    
    try:
        import pygame
    except ImportError:
        missing.append('pygame')
    
    try:
        import sqlalchemy
    except ImportError:
        missing.append('sqlalchemy')
    
    try:
        import openpyxl
    except ImportError:
        missing.append('openpyxl')
    
    if missing:
        print("Missing required dependencies:")
        for dep in missing:
            print(f"  - {dep}")
        print("\nInstall them with: pip install " + " ".join(missing))
        return False
    
    return True

def create_data_directory():
    """Create data directory if it doesn't exist"""
    data_dir = Path.home() / '.pomodora'
    data_dir.mkdir(exist_ok=True)
    return data_dir

def main():
    """Main application entry point"""
    parser = argparse.ArgumentParser(description='Pomodora - Pomodoro Activity Tracker')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--data-dir', type=str, help='Custom data directory path')
    args = parser.parse_args()
    
    # Check dependencies
    if not check_dependencies():
        sys.exit(1)
    
    # Setup data directory
    if args.data_dir:
        data_dir = Path(args.data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
    else:
        data_dir = create_data_directory()
    
    # Change to data directory for database files
    os.chdir(data_dir)
    
    try:
        # Create and run application
        setup_styles()
        app = MainWindow()
        
        if args.debug:
            print(f"Starting Pomodora in debug mode")
            print(f"Data directory: {data_dir}")
        
        # Run the application
        app.run()
        
    except KeyboardInterrupt:
        print("\nApplication interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"Fatal error: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()