"""
Universal progress wrapper for long-running operations.
Automatically shows progress dialogs when operations take longer than 1 second.
"""

import time
import threading
from typing import Callable, Any, Optional
from functools import wraps

# Optional PySide6 import for GUI functionality
try:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer, QObject, Signal, QThread
    PYSIDE6_AVAILABLE = True
except ImportError:
    # Create mock classes for testing environments
    PYSIDE6_AVAILABLE = False
    
    class QObject:
        pass
    
    class Signal:
        def __init__(self, *args):
            pass
        
        def connect(self, func):
            pass
            
        def emit(self, *args):
            pass


class ProgressMonitor(QObject):
    """Monitors operation duration and shows progress dialog when needed"""
    
    show_progress = Signal(str, str)  # operation_name, description
    update_progress = Signal(int)     # progress percentage
    hide_progress = Signal(bool)      # success status
    
    def __init__(self):
        super().__init__()
        self.current_operation = None
        self.start_time = None
        self.progress_shown = False
        
    def start_monitoring(self, operation_name: str, description: str = ""):
        """Start monitoring an operation"""
        self.current_operation = operation_name
        self.start_time = time.time()
        self.progress_shown = False
        
        # Start a timer to check if we need to show progress
        QTimer.singleShot(1000, self._check_progress_needed)
    
    def _check_progress_needed(self):
        """Check if we need to show progress dialog"""
        if self.current_operation and not self.progress_shown:
            elapsed = time.time() - self.start_time if self.start_time else 0
            if elapsed >= 1.0:  # Show progress if operation takes > 1 second
                self.progress_shown = True
                self.show_progress.emit(self.current_operation, f"Please wait...")
    
    def finish_monitoring(self, success: bool = True):
        """Finish monitoring and hide progress if shown"""
        if self.progress_shown:
            self.hide_progress.emit(success)
        self.current_operation = None
        self.start_time = None
        self.progress_shown = False


# Global progress monitor instance
_progress_monitor = None


def get_progress_monitor():
    """Get the global progress monitor instance"""
    global _progress_monitor
    if _progress_monitor is None:
        _progress_monitor = ProgressMonitor()
    return _progress_monitor


def with_progress(operation_name: str, description: str = "", parent=None):
    """
    Decorator that automatically shows progress dialog for long-running operations.
    
    Args:
        operation_name: Human-readable name for the operation
        description: Optional description text
        parent: Parent widget for progress dialog (auto-detected if None)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Try to detect parent widget from args
            detected_parent = parent
            if detected_parent is None:
                for arg in args:
                    if hasattr(arg, 'show') and hasattr(arg, 'hide'):  # Likely a Qt widget
                        detected_parent = arg
                        break
            
            # Check if GUI is available
            app = QApplication.instance()
            if not app:
                # No GUI, just run the function normally
                return func(*args, **kwargs)
            
            monitor = get_progress_monitor()
            
            # For methods, check if the first argument (self) has progress dialog capabilities
            progress_dialog = None
            if args and hasattr(args[0], '_show_operation_progress'):
                progress_dialog = args[0]._show_operation_progress
            
            if progress_dialog:
                # Use the object's progress dialog method
                def run_with_progress():
                    return func(*args, **kwargs)
                
                return progress_dialog(run_with_progress, operation_name, description)
            else:
                # Use global progress monitoring
                monitor.start_monitoring(operation_name, description)
                
                try:
                    result = func(*args, **kwargs)
                    monitor.finish_monitoring(True)
                    return result
                except Exception as e:
                    monitor.finish_monitoring(False)
                    raise
        
        return wrapper
    return decorator


class ProgressCapableMixin:
    """
    Mixin for classes that want to show progress dialogs for their operations.
    Provides automatic progress dialog capability.
    """
    
    def _show_operation_progress(self, operation: Callable, operation_name: str, description: str = "") -> Any:
        """
        Show progress dialog while running an operation.
        
        Args:
            operation: Function to run
            operation_name: Name to display
            description: Description to display
            
        Returns:
            Result of the operation
        """
        # If PySide6 is not available (testing environment), just run operation directly
        if not PYSIDE6_AVAILABLE:
            return operation()
        
        # Import here to avoid circular imports
        try:
            from gui.components.sync_progress_dialog import show_sync_progress
            # Find a suitable Qt widget parent
            parent = None
            if hasattr(self, 'parent') and hasattr(self.parent, 'show'):
                parent = self.parent
            elif hasattr(self, 'show'):  # Self is a Qt widget
                parent = self
            else:
                # Try to find active Qt application window
                from PySide6.QtWidgets import QApplication
                app = QApplication.instance()
                if app:
                    parent = app.activeWindow()
            
            return show_sync_progress(parent, operation, operation_name, "Operation Progress")
        except (ImportError, Exception):
            # Fallback: just run the operation
            return operation()


class ThreadedProgressDialog:
    """
    Manages a progress dialog that runs operations in a background thread.
    Automatically shows/hides based on operation duration.
    """
    
    def __init__(self, parent=None):
        self.parent = parent
        self.dialog = None
        self.thread = None
        
    def run_with_progress(self, operation: Callable, operation_name: str, 
                         min_duration: float = 1.0) -> Any:
        """
        Run an operation with automatic progress dialog.
        
        Args:
            operation: Function to execute
            operation_name: Display name for the operation
            min_duration: Minimum duration before showing progress (seconds)
            
        Returns:
            Result of the operation
        """
        start_time = time.time()
        
        # Start operation in background thread
        class OperationThread(QThread):
            finished_signal = Signal(object, object)  # result, exception
            
            def run(self):
                try:
                    result = operation()
                    self.finished_signal.emit(result, None)
                except Exception as e:
                    self.finished_signal.emit(None, e)
        
        self.thread = OperationThread()
        result_container = {"result": None, "exception": None, "finished": False}
        
        def on_finished(result, exception):
            result_container["result"] = result
            result_container["exception"] = exception  
            result_container["finished"] = True
            if self.dialog:
                self.dialog.accept()
        
        self.thread.finished_signal.connect(on_finished)
        self.thread.start()
        
        # Wait briefly to see if operation completes quickly
        while not result_container["finished"] and (time.time() - start_time) < min_duration:
            QApplication.processEvents()
            time.sleep(0.1)
        
        # If still running, show progress dialog
        if not result_container["finished"]:
            from PySide6.QtWidgets import QProgressDialog
            from PySide6.QtCore import Qt
            
            # Ensure parent is a valid Qt widget or None
            parent = self.parent
            if parent and not hasattr(parent, 'show'):
                parent = None
            
            self.dialog = QProgressDialog(
                f"{operation_name}...",
                "Cancel",
                0, 0,  # Indeterminate progress
                parent
            )
            self.dialog.setWindowTitle("Please Wait")
            self.dialog.setWindowModality(Qt.WindowModal)
            self.dialog.canceled.connect(self._cancel_operation)
            
            # Show dialog and wait for completion
            self.dialog.exec()
        
        # Wait for thread to finish
        if self.thread and self.thread.isRunning():
            self.thread.wait(5000)  # 5 second timeout
        
        # Return result or raise exception
        if result_container["exception"]:
            raise result_container["exception"]
        
        return result_container["result"]
    
    def _cancel_operation(self):
        """Handle operation cancellation"""
        if self.thread and self.thread.isRunning():
            self.thread.terminate()
            self.thread.wait(2000)


def run_with_auto_progress(operation: Callable, operation_name: str, 
                          parent=None, min_duration: float = 1.0) -> Any:
    """
    Convenience function to run an operation with automatic progress dialog.
    
    Args:
        operation: Function to execute
        operation_name: Display name for the operation
        parent: Parent widget for dialog (must be a Qt widget or None)
        min_duration: Minimum duration before showing progress (seconds)
        
    Returns:
        Result of the operation
    """
    # Validate parent is a Qt widget or None
    if parent and not hasattr(parent, 'show'):
        parent = None
        
    dialog = ThreadedProgressDialog(parent)
    return dialog.run_with_progress(operation, operation_name, min_duration)


# Example usage:
if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget
    
    @with_progress("Test Operation", "Processing data...")
    def slow_operation():
        time.sleep(3)
        return "Operation completed!"
    
    def fast_operation():
        time.sleep(0.5)
        return "Fast operation completed!"
    
    app = QApplication(sys.argv)
    
    window = QMainWindow()
    central = QWidget()
    layout = QVBoxLayout(central)
    
    slow_btn = QPushButton("Slow Operation (3s)")
    fast_btn = QPushButton("Fast Operation (0.5s)")
    
    def test_slow():
        result = slow_operation()
        print(result)
    
    def test_fast():
        result = run_with_auto_progress(fast_operation, "Fast Operation", window)
        print(result)
    
    slow_btn.clicked.connect(test_slow)
    fast_btn.clicked.connect(test_fast)
    
    layout.addWidget(slow_btn)
    layout.addWidget(fast_btn)
    
    window.setCentralWidget(central)
    window.show()
    
    sys.exit(app.exec())