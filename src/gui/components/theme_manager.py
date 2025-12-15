"""
Theme management and styling system for the Pomodoro application.
Handles light mode, dark mode, and system theme detection with comprehensive styling.
"""

import os
import platform
from utils.logging import debug_print, error_print


class ThemeManager:
    """Manages theme detection and styling for the application"""

    def __init__(self, main_window):
        self.main_window = main_window

    def detect_system_dark_theme(self, context="unknown"):
        """Detect if system is using dark theme"""
        debug_print(f"[{context.upper()}] Starting system theme detection...")
        try:
            system = platform.system()

            # Priority 1: macOS dark mode detection
            if system == 'Darwin':
                try:
                    result = os.popen("defaults read -g AppleInterfaceStyle 2>/dev/null").read().strip()
                    debug_print(f"[{context.upper()}] macOS AppleInterfaceStyle: {result}")
                    if result and result.lower() == 'dark':
                        debug_print(f"[{context.upper()}] Dark theme detected via macOS system preference")
                        return True
                except Exception as e:
                    debug_print(f"[{context.upper()}] macOS detection error: {e}")

            # Priority 2: Check GNOME/GTK settings (Linux)
            elif system == 'Linux':
                try:
                    # Check color scheme preference (newer method)
                    result = os.popen("gsettings get org.gnome.desktop.interface color-scheme 2>/dev/null").read().strip()
                    debug_print(f"[{context.upper()}] GNOME color-scheme: {result}")
                    if result and 'prefer-dark' in result.lower():
                        debug_print(f"[{context.upper()}] Dark theme detected via color-scheme: {result}")
                        return True

                    # Check GTK theme name
                    result = os.popen("gsettings get org.gnome.desktop.interface gtk-theme 2>/dev/null").read().strip()
                    debug_print(f"[{context.upper()}] GTK theme: {result}")
                    if result and ('dark' in result.lower() or 'adwaita-dark' in result.lower()):
                        debug_print(f"[{context.upper()}] Dark theme detected via GTK theme: {result}")
                        return True
                except Exception as e:
                    debug_print(f"[{context.upper()}] GNOME detection error: {e}")

            # Priority 3: Check KDE settings (Linux)
            try:
                kde_config = os.path.expanduser("~/.config/kdeglobals")
                if os.path.exists(kde_config):
                    with open(kde_config, 'r') as f:
                        content = f.read()
                        if 'ColorScheme=Breeze Dark' in content or 'Name=Breeze Dark' in content:
                            debug_print(f"[{context.upper()}] Dark theme detected via KDE settings")
                            return True
            except Exception as e:
                debug_print(f"[{context.upper()}] KDE detection error: {e}")

            # Priority 3: Check environment variables
            qt_style = os.environ.get('QT_STYLE_OVERRIDE', '').lower()
            if 'dark' in qt_style:
                debug_print(f"[{context.upper()}] Dark theme detected via QT_STYLE_OVERRIDE: {qt_style}")
                return True

            # Priority 4: Qt palette check (as fallback, but more reliable with fresh app instance)
            try:
                from PySide6.QtGui import QPalette
                from PySide6.QtWidgets import QApplication, QWidget

                app = QApplication.instance()
                if app:
                    # Get a fresh palette by creating a temporary widget
                    temp_widget = QWidget()
                    palette = temp_widget.palette()
                    temp_widget.deleteLater()

                    # Check window color lightness
                    window_color = palette.color(QPalette.Window)
                    window_lightness = window_color.lightness()
                    debug_print(f"[{context.upper()}] Qt window color lightness: {window_lightness}")

                    # Check text color
                    text_color = palette.color(QPalette.WindowText)
                    text_lightness = text_color.lightness()
                    debug_print(f"[{context.upper()}] Qt text color lightness: {text_lightness}")

                    # More lenient Qt detection
                    if text_lightness > window_lightness:
                        debug_print(f"[{context.upper()}] Dark theme detected via Qt palette (text > window)")
                        return True

                    if window_lightness < 150:  # More lenient threshold
                        debug_print(f"[{context.upper()}] Dark theme detected via Qt palette (window < 150)")
                        return True
            except Exception as e:
                debug_print(f"[{context.upper()}] Qt palette detection error: {e}")

            debug_print(f"[{context.upper()}] No dark theme detected, defaulting to light")
            return False

        except Exception as e:
            error_print(f"[{context.upper()}] Error detecting system theme: {e}")
            return False

    def apply_styling(self, context="startup"):
        """Apply modern, colorful styling based on current mode"""
        debug_print(f"[{context.upper()}] Applying styling for theme mode: {self.main_window.theme_mode}")

        if self.main_window.theme_mode == "dark":
            debug_print("Using dark mode styling")
            self.apply_dark_mode_styling()
        elif self.main_window.theme_mode == "system":
            # Use more robust system theme detection
            is_dark = self.detect_system_dark_theme(context)
            debug_print(f"[{context.upper()}] System theme detection: {'dark' if is_dark else 'light'}")
            if is_dark:
                self.apply_dark_mode_styling()
            else:
                self.apply_light_mode_styling()
        else:  # light mode
            debug_print("Using light mode styling")
            self.apply_light_mode_styling()

    def apply_dialog_styling(self, dialog):
        """Apply current theme styling to a dialog"""
        if self.main_window.theme_mode == "dark" or (self.main_window.theme_mode == "system" and self.detect_system_dark_theme("dialog")):
            self.apply_dark_dialog_styling(dialog)
        else:
            self.apply_light_dialog_styling(dialog)

    def apply_light_mode_styling(self):
        """Apply light mode styling"""
        style = """
        QMainWindow {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #f8f9fa, stop:1 #e9ecef);
        }

        #headerFrame {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #ff6b6b, stop:1 #ffa500);
            border-radius: 15px;
            padding: 0px;
            margin: 0 0 0px 0;
        }

        #titleLabel {
            font-size: 24px;
            font-weight: bold;
            color: white;
            padding: 0px;
        }

        #timerFrame {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #87ceeb, stop:1 #4682b4);
            border-radius: 20px;
            padding: 0px;
            margin: 10px 0 10px 0;
            min-height: 120px;
            max-height: 180px;
        }

        #timeLabel {
            font-size: 36px;
            font-weight: bold;
            color: white;
            margin: 5px 0;
            padding: 3px;
            qproperty-alignment: AlignCenter;
        }

        #stateLabel {
            font-size: 14px;
            color: #e8f4f8;
            margin: 5px 0;
            padding: 3px;
            qproperty-alignment: AlignCenter;
        }

        #progressBar {
            height: 8px;
            border-radius: 4px;
            background-color: rgba(255, 255, 255, 0.4);
            margin: 10px 0 5px 0;
            border: 1px solid rgba(255, 255, 255, 0.2);
            min-width: 200px;
        }

        #progressBar::chunk {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #56ab2f, stop:1 #a8e6cf);
            border-radius: 4px;
        }

        #inputFrame {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #f8f9ff, stop:1 #e8f4f8);
            border-radius: 15px;
            padding: 0px;
            border: 2px solid #d1ecf1;
            min-height: 90px;
            margin: 0px 0;
        }

        #inputLabel {
            font-size: 14px;
            font-weight: bold;
            color: #495057;
            min-width: 70px;
        }

        #projectCombo, #taskCategoryCombo, #taskInput {
            padding: 0 0;
            border: 2px solid #dee2e6;
            border-radius: 8px;
            font-size: 14px;
            background: white;
            min-height: 25px;
            color: #333;
        }

        #projectCombo, #taskCategoryCombo {
            background: white;
            selection-background-color: #667eea;
            selection-color: white;
        }

        #projectCombo::drop-down, #taskCategoryCombo::drop-down {
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 24px;
            border-left: 2px solid #adb5bd;
            background: #e9ecef;
            border-top-right-radius: 6px;
            border-bottom-right-radius: 6px;
        }

        #projectCombo::down-arrow, #taskCategoryCombo::down-arrow {
            width: 0px;
            height: 0px;
            border-left: 6px solid transparent;
            border-right: 6px solid transparent;
            border-top: 8px solid #495057;
            margin: 5px;
        }

        #projectCombo QAbstractItemView, #taskCategoryCombo QAbstractItemView {
            background: white;
            border: 2px solid #667eea;
            border-radius: 8px;
            selection-background-color: #667eea;
            selection-color: white;
            color: #333;
            padding: 5px;
        }

        #projectCombo QAbstractItemView::item, #taskCategoryCombo QAbstractItemView::item {
            padding: 8px 12px;
            border: none;
            color: #333;
        }

        #projectCombo QAbstractItemView::item:selected, #taskCategoryCombo QAbstractItemView::item:selected {
            background: #667eea;
            color: white;
        }

        #projectCombo QAbstractItemView::item:hover, #taskCategoryCombo QAbstractItemView::item:hover {
            background: #5a6fd8;
            color: white;
        }

        #projectCombo:focus, #taskCategoryCombo:focus, #taskInput:focus {
            border-color: #667eea;
            outline: none;
        }

        #controlFrame {
            margin: 0px 0;
        }

        QPushButton {
            padding: 12px 20px;
            border-radius: 10px;
            font-size: 14px;
            font-weight: bold;
            border: none;
            min-height: 20px;
        }

        #startButton {
            background: #4CAF50;
            color: white;
        }

        #startButton:hover {
            background: #45a049;
        }

        #stopButton {
            background: #f44336;
            color: white;
        }

        #stopButton:hover {
            background: #da190b;
        }

        #completeButton {
            background: #2196F3;
            color: white;
        }

        #completeButton:hover {
            background: #0b7dda;
        }

        #statusFrame {
            background: white;
            border-radius: 15px;
            padding: 0px;
            border: 2px solid #dee2e6;
            margin: 0px 0 0px 0;
        }

        #statsLabel {
            font-size: 14px;
            color: #6c757d;
            font-weight: 500;
        }

        QPushButton:disabled {
            background: #e9ecef;
            color: #6c757d;
        }

        QCheckBox {
            color: #333;
            spacing: 8px;
            font-size: 13px;
        }

        QCheckBox::indicator {
            width: 16px;
            height: 16px;
            border: 2px solid #dee2e6;
            border-radius: 3px;
            background: white;
        }

        QCheckBox::indicator:checked {
            background: #667eea;
            border: 2px solid #667eea;
        }

        QCheckBox::indicator:hover {
            border-color: #667eea;
        }
        """

        self.main_window.setStyleSheet(style)

    def apply_light_dialog_styling(self, dialog):
        """Apply light mode styling to a dialog"""
        style = """
        QDialog {
            background: #f8f9fa;
            color: #333;
        }

        QTabWidget::pane {
            background: white;
            border: 1px solid #dee2e6;
            border-radius: 8px;
        }

        QTabWidget::tab-bar {
            alignment: center;
        }

        QTabBar::tab {
            background: #e9ecef;
            color: #333;
            padding: 8px 16px;
            margin-right: 2px;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
        }

        QTabBar::tab:selected {
            background: white;
            border-bottom: 2px solid #667eea;
        }

        QTabBar::tab:hover {
            background: #f1f3f4;
        }

        QGroupBox {
            font-weight: bold;
            border: 2px solid #dee2e6;
            border-radius: 8px;
            margin-top: 12px;
            padding-top: 8px;
            background: white;
        }

        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 8px 0 8px;
            background: white;
            color: #333;
        }

        QListWidget {
            background: white;
            border: 1px solid #dee2e6;
            border-radius: 8px;
            padding: 4px;
        }

        QListWidget::item {
            border-radius: 4px;
            padding: 4px;
            margin: 1px;
        }

        QListWidget::item:selected {
            background: #667eea;
            color: white;
        }

        QListWidget::item:hover {
            background: #f1f3f4;
        }

        QPushButton {
            background: #667eea;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            font-weight: 500;
        }

        QPushButton:hover {
            background: #5a6fd8;
        }

        QPushButton:pressed {
            background: #4c63d2;
        }

        QLineEdit {
            background: white;
            border: 2px solid #dee2e6;
            border-radius: 6px;
            padding: 8px;
            color: #333;
        }

        QLineEdit:focus {
            border-color: #667eea;
        }

        QComboBox {
            background: white;
            border: 2px solid #dee2e6;
            border-radius: 6px;
            padding: 8px;
            color: #333;
        }

        QComboBox:focus {
            border-color: #667eea;
        }

        QComboBox::drop-down {
            border: 1px solid #dee2e6;
            border-left: none;
            width: 20px;
            background: #f8f9fa;
            border-top-right-radius: 6px;
            border-bottom-right-radius: 6px;
        }

        QComboBox::drop-down:hover {
            background: #e9ecef;
        }

        QComboBox::down-arrow {
            image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTIiIGhlaWdodD0iOCIgdmlld0JveD0iMCAwIDEyIDgiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxwYXRoIGQ9Ik0xIDFMNiA2TDExIDEiIHN0cm9rZT0iIzMzMzMzMyIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiLz4KPC9zdmc+);
            width: 12px;
            height: 8px;
            margin: 2px;
        }

        QComboBox QAbstractItemView {
            background: white;
            border: 2px solid #667eea;
            border-radius: 6px;
            padding: 4px;
            color: #333;
            selection-background-color: #667eea;
            selection-color: white;
        }

        QComboBox QAbstractItemView::item {
            background: white;
            color: #333;
            padding: 8px;
            border: none;
            min-height: 20px;
        }

        QComboBox QAbstractItemView::item:selected {
            background: #667eea;
            color: white;
        }

        QComboBox QAbstractItemView::item:hover {
            background: #f1f3f4;
            color: #333;
        }

        QSpinBox {
            background: white;
            border: 2px solid #dee2e6;
            border-radius: 6px;
            padding: 8px;
            color: #333;
        }

        QSpinBox:focus {
            border-color: #667eea;
        }

        QSpinBox::up-button {
            background: #e9ecef;
            border: 2px solid #adb5bd;
            width: 18px;
            border-top-right-radius: 4px;
            subcontrol-origin: border;
            subcontrol-position: top right;
        }

        QSpinBox::up-button:hover {
            background: #ced4da;
            border-color: #6c757d;
        }

        QSpinBox::up-button:pressed {
            background: #adb5bd;
        }

        QSpinBox::up-arrow {
            width: 0px;
            height: 0px;
            border-left: 5px solid transparent;
            border-right: 5px solid transparent;
            border-bottom: 7px solid #495057;
            margin: 2px;
        }

        QSpinBox::down-button {
            background: #e9ecef;
            border: 2px solid #adb5bd;
            width: 18px;
            border-bottom-right-radius: 4px;
            subcontrol-origin: border;
            subcontrol-position: bottom right;
        }

        QSpinBox::down-button:hover {
            background: #ced4da;
            border-color: #6c757d;
        }

        QSpinBox::down-button:pressed {
            background: #adb5bd;
        }

        QSpinBox::down-arrow {
            width: 0px;
            height: 0px;
            border-left: 5px solid transparent;
            border-right: 5px solid transparent;
            border-top: 7px solid #495057;
            margin: 2px;
        }

        QLabel {
            color: #333;
        }

        QRadioButton {
            color: #333;
            spacing: 8px;
        }

        QRadioButton::indicator {
            width: 16px;
            height: 16px;
            border-radius: 8px;
            border: 2px solid #dee2e6;
            background: white;
        }

        QRadioButton::indicator:hover {
            border-color: #667eea;
        }

        QRadioButton::indicator:checked {
            background: #667eea;
            border: 4px solid white;
            border-radius: 8px;
        }

        QRadioButton::indicator:checked:hover {
            background: #5a6fd8;
            border: 4px solid white;
            border-radius: 8px;
        }

        QCheckBox {
            color: #333;
            spacing: 8px;
        }

        QCheckBox::indicator {
            width: 16px;
            height: 16px;
            border: 2px solid #dee2e6;
            border-radius: 3px;
            background: white;
        }

        QCheckBox::indicator:checked {
            background: #667eea;
            border: 2px solid #667eea;
            color: white;
        }

        QCheckBox::indicator:hover {
            border-color: #667eea;
        }
        """
        dialog.setStyleSheet(style)

    def apply_dark_mode_styling(self):
        """Apply dark mode styling"""
        style = """
        QMainWindow {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #2c3e50, stop:1 #34495e);
        }

        #headerFrame {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #e74c3c, stop:1 #c0392b);
            border-radius: 15px;
            padding: 0px;
            margin: 0 0 0px 0;
        }

        #titleLabel {
            font-size: 24px;
            font-weight: bold;
            color: white;
            padding: 0px;
        }

        #timerFrame {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #2980b9, stop:1 #1f4e79);
            border-radius: 20px;
            padding: 0px;
            margin: 10px 0 10px 0;
            min-height: 120px;
            max-height: 180px;
            border: 2px solid #3498db;
        }

        #timeLabel {
            font-size: 36px;
            font-weight: bold;
            color: #ecf0f1;
            margin: 5px 0;
            padding: 3px;
            qproperty-alignment: AlignCenter;
        }

        #stateLabel {
            font-size: 14px;
            color: #bdc3c7;
            margin: 5px 0;
            padding: 3px;
            qproperty-alignment: AlignCenter;
        }

        #progressBar {
            height: 8px;
            border-radius: 4px;
            background-color: rgba(255, 255, 255, 0.2);
            margin: 10px 0 5px 0;
            border: 1px solid rgba(255, 255, 255, 0.1);
            min-width: 200px;
        }

        #progressBar::chunk {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #27ae60, stop:1 #2ecc71);
            border-radius: 4px;
        }

        #inputFrame {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #455a64, stop:1 #37474f);
            border-radius: 15px;
            padding: 0px;
            border: 2px solid #546e7a;
            min-height: 90px;
            margin: 0px 0;
        }

        #inputLabel {
            font-size: 14px;
            font-weight: bold;
            color: #ecf0f1;
            min-width: 70px;
        }

        #projectCombo, #taskCategoryCombo, #taskInput {
            padding: 0 0;
            border: 2px solid #546e7a;
            border-radius: 8px;
            font-size: 14px;
            background: #455a64;
            min-height: 25px;
            color: #ecf0f1;
        }

        #projectCombo, #taskCategoryCombo {
            background: #455a64;
            selection-background-color: #5d6d7e;
            selection-color: white;
        }

        #projectCombo::drop-down, #taskCategoryCombo::drop-down {
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 24px;
            border-left: 2px solid #37474f;
            background: #546e7a;
            border-top-right-radius: 6px;
            border-bottom-right-radius: 6px;
        }

        #projectCombo::down-arrow, #taskCategoryCombo::down-arrow {
            width: 0px;
            height: 0px;
            border-left: 6px solid transparent;
            border-right: 6px solid transparent;
            border-top: 8px solid #ecf0f1;
            margin: 5px;
        }

        #projectCombo QAbstractItemView, #taskCategoryCombo QAbstractItemView {
            background: #455a64;
            border: 2px solid #5d6d7e;
            border-radius: 8px;
            selection-background-color: #5d6d7e;
            selection-color: white;
            color: #ecf0f1;
            padding: 5px;
        }

        #projectCombo QAbstractItemView::item, #taskCategoryCombo QAbstractItemView::item {
            padding: 8px 12px;
            border: none;
            color: #ecf0f1;
        }

        #projectCombo QAbstractItemView::item:selected, #taskCategoryCombo QAbstractItemView::item:selected {
            background: #5d6d7e;
            color: white;
        }

        #projectCombo QAbstractItemView::item:hover, #taskCategoryCombo QAbstractItemView::item:hover {
            background: #4a5a68;
            color: white;
        }

        #projectCombo:focus, #taskCategoryCombo:focus, #taskInput:focus {
            border-color: #5d6d7e;
            outline: none;
        }

        #controlFrame {
            margin: 0px 0;
        }

        QPushButton {
            padding: 12px 20px;
            border-radius: 10px;
            font-size: 14px;
            font-weight: bold;
            border: none;
            min-height: 20px;
        }

        #startButton {
            background: #27ae60;
            color: white;
        }

        #startButton:hover {
            background: #229954;
        }

        #stopButton {
            background: #e74c3c;
            color: white;
        }

        #stopButton:hover {
            background: #c0392b;
        }

        #completeButton {
            background: #3498db;
            color: white;
        }

        #completeButton:hover {
            background: #2980b9;
        }

        #statusFrame {
            background: #455a64;
            border-radius: 15px;
            padding: 0px;
            border: 2px solid #546e7a;
            margin: 0px 0 0px 0;
        }

        #statsLabel {
            font-size: 14px;
            color: #bdc3c7;
            font-weight: 500;
        }

        QPushButton:disabled {
            background: #546e7a;
            color: #95a5a6;
        }

        QCheckBox {
            color: #ecf0f1;
            spacing: 8px;
            font-size: 13px;
        }

        QCheckBox::indicator {
            width: 16px;
            height: 16px;
            border: 2px solid #546e7a;
            border-radius: 3px;
            background: #455a64;
        }

        QCheckBox::indicator:checked {
            background: #5d6d7e;
            border: 2px solid #5d6d7e;
        }

        QCheckBox::indicator:hover {
            border-color: #6c7b8b;
        }
        """

        self.main_window.setStyleSheet(style)

    def apply_dark_dialog_styling(self, dialog):
        """Apply dark mode styling to a dialog"""
        style = """
        QDialog {
            background: #2c3e50;
            color: #ecf0f1;
        }

        QTabWidget::pane {
            background: #34495e;
            border: 1px solid #546e7a;
            border-radius: 8px;
        }

        QTabWidget::tab-bar {
            alignment: center;
        }

        QTabBar::tab {
            background: #455a64;
            color: #ecf0f1;
            padding: 8px 16px;
            margin-right: 2px;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
        }

        QTabBar::tab:selected {
            background: #34495e;
            border-bottom: 2px solid #5d6d7e;
        }

        QTabBar::tab:hover {
            background: #3c4f5c;
        }

        QGroupBox {
            font-weight: bold;
            border: 2px solid #546e7a;
            border-radius: 8px;
            margin-top: 12px;
            padding-top: 8px;
            background: #34495e;
        }

        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 8px 0 8px;
            background: #34495e;
            color: #ecf0f1;
        }

        QListWidget {
            background: #34495e;
            border: 1px solid #546e7a;
            border-radius: 8px;
            padding: 4px;
        }

        QListWidget::item {
            border-radius: 4px;
            padding: 4px;
            margin: 1px;
            color: #ecf0f1;
        }

        QListWidget::item:selected {
            background: #5d6d7e;
            color: white;
        }

        QListWidget::item:hover {
            background: #455a64;
        }

        QPushButton {
            background: #5d6d7e;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            font-weight: 500;
        }

        QPushButton:hover {
            background: #6c7b8b;
        }

        QPushButton:pressed {
            background: #4e5d6c;
        }

        QLineEdit {
            background: #455a64;
            border: 2px solid #546e7a;
            border-radius: 6px;
            padding: 8px;
            color: #ecf0f1;
        }

        QLineEdit:focus {
            border-color: #5d6d7e;
        }

        QComboBox {
            background: #455a64;
            border: 2px solid #546e7a;
            border-radius: 6px;
            padding: 8px;
            color: #ecf0f1;
        }

        QComboBox:focus {
            border-color: #5d6d7e;
        }

        QComboBox::drop-down {
            border: 1px solid #546e7a;
            border-left: none;
            width: 20px;
            background: #37474f;
            border-top-right-radius: 6px;
            border-bottom-right-radius: 6px;
        }

        QComboBox::drop-down:hover {
            background: #455a64;
        }

        QComboBox::down-arrow {
            image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTIiIGhlaWdodD0iOCIgdmlld0JveD0iMCAwIDEyIDgiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxwYXRoIGQ9Ik0xIDFMNiA2TDExIDEiIHN0cm9rZT0iI2VjZjBmMSIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiLz4KPC9zdmc+);
            width: 12px;
            height: 8px;
            margin: 2px;
        }

        QComboBox QAbstractItemView {
            background: #34495e;
            border: 2px solid #5d6d7e;
            border-radius: 6px;
            padding: 4px;
            color: #ecf0f1;
            selection-background-color: #5d6d7e;
            selection-color: white;
        }

        QComboBox QAbstractItemView::item {
            background: #34495e;
            color: #ecf0f1;
            padding: 8px;
            border: none;
            min-height: 20px;
        }

        QComboBox QAbstractItemView::item:selected {
            background: #5d6d7e;
            color: white;
        }

        QComboBox QAbstractItemView::item:hover {
            background: #455a64;
            color: #ecf0f1;
        }

        QSpinBox {
            background: #455a64;
            border: 2px solid #546e7a;
            border-radius: 6px;
            padding: 8px;
            color: #ecf0f1;
        }

        QSpinBox:focus {
            border-color: #5d6d7e;
        }

        QSpinBox::up-button {
            background: #546e7a;
            border: 2px solid #37474f;
            width: 18px;
            border-top-right-radius: 4px;
            subcontrol-origin: border;
            subcontrol-position: top right;
        }

        QSpinBox::up-button:hover {
            background: #607d8b;
            border-color: #455a64;
        }

        QSpinBox::up-button:pressed {
            background: #455a64;
        }

        QSpinBox::up-arrow {
            width: 0px;
            height: 0px;
            border-left: 5px solid transparent;
            border-right: 5px solid transparent;
            border-bottom: 7px solid #ecf0f1;
            margin: 2px;
        }

        QSpinBox::down-button {
            background: #546e7a;
            border: 2px solid #37474f;
            width: 18px;
            border-bottom-right-radius: 4px;
            subcontrol-origin: border;
            subcontrol-position: bottom right;
        }

        QSpinBox::down-button:hover {
            background: #607d8b;
            border-color: #455a64;
        }

        QSpinBox::down-button:pressed {
            background: #455a64;
        }

        QSpinBox::down-arrow {
            width: 0px;
            height: 0px;
            border-left: 5px solid transparent;
            border-right: 5px solid transparent;
            border-top: 7px solid #ecf0f1;
            margin: 2px;
        }

        QLabel {
            color: #ecf0f1;
        }

        QRadioButton {
            color: #ecf0f1;
            spacing: 8px;
        }

        QRadioButton::indicator {
            width: 16px;
            height: 16px;
            border-radius: 8px;
            border: 2px solid #546e7a;
            background: #455a64;
        }

        QRadioButton::indicator:hover {
            border-color: #5d6d7e;
        }

        QRadioButton::indicator:checked {
            background: #5d6d7e;
            border: 4px solid white;
            border-radius: 8px;
        }

        QRadioButton::indicator:checked:hover {
            background: #6c7b8b;
            border: 4px solid white;
            border-radius: 8px;
        }

        QCheckBox {
            color: #ecf0f1;
            spacing: 8px;
        }

        QCheckBox::indicator {
            width: 16px;
            height: 16px;
            border: 2px solid #546e7a;
            border-radius: 3px;
            background: #455a64;
        }

        QCheckBox::indicator:checked {
            background: #5d6d7e;
            border: 2px solid #5d6d7e;
            color: white;
        }

        QCheckBox::indicator:hover {
            border-color: #6c7b8b;
        }
        """
        dialog.setStyleSheet(style)

    def apply_compact_styling(self):
        """Apply compact mode styling based on current theme"""
        if self.main_window.theme_mode == "dark" or (self.main_window.theme_mode == "system" and self.detect_system_dark_theme("compact")):
            self.apply_compact_dark_styling()
        else:
            self.apply_compact_light_styling()

    def apply_compact_light_styling(self):
        """Apply light mode compact styling"""
        compact_style = """
        QMainWindow {
            background: #f8f9fa;
        }

        #timerFrame {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #87ceeb, stop:1 #4682b4);
            border-radius: 0px;  /* No rounded corners for full window */
            padding: 8px;        /* Minimal internal padding */
            margin: 0px;         /* No external margins */
            min-height: 100%;    /* Fill entire window height */
        }

        #timeLabel {
            font-size: 24px;
            font-weight: bold;
            color: white;
            margin: 2px 0;
            padding: 2px;
            qproperty-alignment: AlignCenter;
        }

        #stateLabel {
            font-size: 9px;
            color: #e8f4f8;
            margin: 1px 0;
            padding: 1px;
            qproperty-alignment: AlignCenter;
        }

        #progressBar {
            height: 4px;
            border-radius: 2px;
            background-color: rgba(255, 255, 255, 0.3);
            margin: 2px 0;
            border: none;
        }

        #progressBar::chunk {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #56ab2f, stop:1 #a8e6cf);
            border-radius: 2px;
        }

        /* Compact Control Buttons */
        #compactControlsFrame {
            background: transparent;
            margin: 2px 0;
        }

        #compactStartButton {
            font-size: 11px;
            font-weight: 600;
            border: 2px solid #45a049;
            border-radius: 6px;
            padding: 4px 8px;
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #4CAF50, stop:1 #45a049);
            color: white;
            margin: 0 2px;
            min-width: 50px;
        }

        #compactStopButton {
            font-size: 11px;
            font-weight: 600;
            border: 2px solid #da190b;
            border-radius: 6px;
            padding: 4px 8px;
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #f44336, stop:1 #da190b);
            color: white;
            margin: 0 2px;
            min-width: 40px;
        }

        #compactCompleteButton {
            font-size: 11px;
            font-weight: 600;
            border: 2px solid #0b7dda;
            border-radius: 6px;
            padding: 4px 8px;
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #2196F3, stop:1 #0b7dda);
            color: white;
            margin: 0 2px;
            min-width: 40px;
        }

        #compactStartButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #66BB6A, stop:1 #4CAF50);
            border: 2px solid #4CAF50;
        }

        #compactStopButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #f66359, stop:1 #f44336);
            border: 2px solid #f44336;
        }

        #compactCompleteButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #42A5F5, stop:1 #2196F3);
            border: 2px solid #2196F3;
        }

        #compactStartButton:pressed {
            background: #45a049;
        }

        #compactStopButton:pressed {
            background: #da190b;
        }

        #compactCompleteButton:pressed {
            background: #0b7dda;
        }

        #compactStartButton:disabled, #compactStopButton:disabled, #compactCompleteButton:disabled {
            background: #bdc3c7;
            color: #7f8c8d;
            border: 2px solid #95a5a6;
        }
        """
        self.main_window.setStyleSheet(compact_style)

    def apply_compact_dark_styling(self):
        """Apply dark mode compact styling"""
        compact_style = """
        QMainWindow {
            background: #2c3e50;
        }

        #timerFrame {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #2980b9, stop:1 #1f4e79);
            border-radius: 0px;  /* No rounded corners for full window */
            padding: 8px;        /* Minimal internal padding */
            margin: 0px;         /* No external margins */
            min-height: 100%;    /* Fill entire window height */
            border: none;        /* No border for seamless fill */
        }

        #timeLabel {
            font-size: 24px;
            font-weight: bold;
            color: #ecf0f1;
            margin: 2px 0;
            padding: 2px;
            qproperty-alignment: AlignCenter;
        }

        #stateLabel {
            font-size: 9px;
            color: #bdc3c7;
            margin: 1px 0;
            padding: 1px;
            qproperty-alignment: AlignCenter;
        }

        #progressBar {
            height: 4px;
            border-radius: 2px;
            background-color: rgba(255, 255, 255, 0.2);
            margin: 2px 0;
            border: none;
        }

        #progressBar::chunk {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #5d6d7e, stop:1 #7f8c8d);
            border-radius: 2px;
        }

        /* Compact Control Buttons */
        #compactControlsFrame {
            background: transparent;
            margin: 2px 0;
        }

        #compactStartButton {
            font-size: 11px;
            font-weight: 600;
            border: 2px solid #229954;
            border-radius: 6px;
            padding: 4px 8px;
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #27ae60, stop:1 #229954);
            color: white;
            margin: 0 2px;
            min-width: 50px;
        }

        #compactStopButton {
            font-size: 11px;
            font-weight: 600;
            border: 2px solid #c0392b;
            border-radius: 6px;
            padding: 4px 8px;
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #e74c3c, stop:1 #c0392b);
            color: white;
            margin: 0 2px;
            min-width: 40px;
        }

        #compactCompleteButton {
            font-size: 11px;
            font-weight: 600;
            border: 2px solid #2980b9;
            border-radius: 6px;
            padding: 4px 8px;
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #3498db, stop:1 #2980b9);
            color: white;
            margin: 0 2px;
            min-width: 40px;
        }

        #compactStartButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #2ecc71, stop:1 #27ae60);
            border: 2px solid #27ae60;
        }

        #compactStopButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #ec7063, stop:1 #e74c3c);
            border: 2px solid #e74c3c;
        }

        #compactCompleteButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #5dade2, stop:1 #3498db);
            border: 2px solid #3498db;
        }

        #compactStartButton:pressed {
            background: #229954;
        }

        #compactStopButton:pressed {
            background: #c0392b;
        }

        #compactCompleteButton:pressed {
            background: #2980b9;
        }

        #compactStartButton:disabled, #compactStopButton:disabled, #compactCompleteButton:disabled {
            background: #566573;
            color: #85929e;
            border: 2px solid #5d6d7e;
        }
        """
        self.main_window.setStyleSheet(compact_style)