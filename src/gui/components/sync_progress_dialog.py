"""
Reusable progress dialog for database sync operations.
Provides a non-blocking progress indicator during time-consuming sync operations.
"""

from PySide6.QtWidgets import QProgressDialog, QApplication
from PySide6.QtCore import QTimer, Qt, QThread, Signal
import threading
import time
from typing import Callable, Optional


class SyncProgressThread(QThread):
    """Background thread that monitors sync operations and reports progress"""
    
    progress_update = Signal(int)  # Progress percentage (0-100)
    status_update = Signal(str)    # Status message
    finished = Signal(bool)        # Success/failure result
    
    def __init__(self, sync_operation: Callable[[], bool], operation_name: str = "Syncing"):
        super().__init__()
        self.sync_operation = sync_operation
        self.operation_name = operation_name
        self._cancelled = False
        
    def run(self):
        """Execute the sync operation in background thread"""
        progress_timer = None
        try:
            self.status_update.emit(f"{self.operation_name}...")
            self.progress_update.emit(10)
            
            # Simulate progress updates during sync
            # Since we can't get real progress from Google Drive API, we'll use time-based estimates
            progress_timer = QTimer()
            progress_timer.moveToThread(self)
            current_progress = 10
            
            def update_progress():
                nonlocal current_progress
                if current_progress < 90 and not self._cancelled:
                    current_progress += 5
                    self.progress_update.emit(current_progress)
            
            progress_timer.timeout.connect(update_progress)
            progress_timer.start(200)  # Update every 200ms
            
            # Execute the actual sync operation
            result = self.sync_operation()
            
            # Clean up timer
            if progress_timer:
                progress_timer.stop()
                progress_timer.deleteLater()
                progress_timer = None
            
            if self._cancelled:
                self.finished.emit(False)
                return
                
            if result:
                self.progress_update.emit(100)
                self.status_update.emit("Sync completed successfully")
            else:
                self.status_update.emit("Sync failed")
                
            self.finished.emit(result)
            
        except Exception as e:
            # Clean up timer in exception case too
            if progress_timer:
                progress_timer.stop()
                progress_timer.deleteLater()
            self.status_update.emit(f"Sync error: {str(e)}")
            self.finished.emit(False)
    
    def cancel(self):
        """Cancel the sync operation"""
        self._cancelled = True


class SyncProgressDialog:
    """
    Reusable progress dialog for database sync operations.
    Shows progress during time-consuming sync operations to prevent UI blocking.
    """
    
    def __init__(self, parent=None, title: str = "Database Sync"):
        self.parent = parent
        self.title = title
        self.dialog = None
        self.thread = None
        
    def show_progress(self, sync_operation: Callable[[], bool], 
                     operation_name: str = "Syncing database",
                     timeout_ms: int = 30000) -> bool:
        """
        Show progress dialog and execute sync operation in background.
        
        Args:
            sync_operation: Function that performs the sync and returns bool success
            operation_name: Display name for the operation
            timeout_ms: Maximum time to wait (default 30 seconds)
            
        Returns:
            bool: True if sync succeeded, False if failed or cancelled
        """
        if not sync_operation:
            return False
            
        # Create progress dialog
        self.dialog = QProgressDialog(
            f"{operation_name}...",
            "Cancel",
            0, 100,
            self.parent
        )
        self.dialog.setWindowTitle(self.title)
        self.dialog.setWindowModality(Qt.WindowModal)
        self.dialog.setMinimumDuration(500)  # Show after 500ms
        self.dialog.setAutoClose(True)
        self.dialog.setAutoReset(True)
        
        # Create and configure sync thread
        self.thread = SyncProgressThread(sync_operation, operation_name)
        
        # Connect signals
        self.thread.progress_update.connect(self.dialog.setValue)
        self.thread.status_update.connect(self.dialog.setLabelText)
        self.thread.finished.connect(self._on_sync_finished)
        self.dialog.canceled.connect(self._on_cancel)
        
        # Start the sync operation
        self.thread.start()
        
        # Show dialog and wait for completion
        result = self.dialog.exec()
        
        # Ensure thread is properly cleaned up
        if self.thread and self.thread.isRunning():
            self.thread.cancel()
            if not self.thread.wait(3000):  # Wait up to 3 seconds for graceful shutdown
                # Force terminate if thread won't stop
                self.thread.terminate()
                self.thread.wait(1000)  # Wait for termination
                
        # Clean up thread reference
        self.thread = None
            
        # Return success if dialog completed normally and sync succeeded
        return hasattr(self, '_sync_result') and self._sync_result
    
    def _on_sync_finished(self, success: bool):
        """Handle sync operation completion"""
        self._sync_result = success
        if self.dialog:
            if success:
                self.dialog.setValue(100)
                # Brief delay to show completion
                QTimer.singleShot(500, self.dialog.accept)
            else:
                self.dialog.reject()
    
    def _on_cancel(self):
        """Handle user cancellation"""
        if self.thread:
            self.thread.cancel()
            # First try graceful shutdown
            if not self.thread.wait(2000):  # Wait up to 2 seconds for graceful shutdown
                # If thread doesn't finish gracefully, force terminate
                self.thread.terminate()
                self.thread.wait(1000)  # Wait up to 1 second for termination
        self._sync_result = False


def show_sync_progress(parent, sync_operation: Callable[[], bool], 
                      operation_name: str = "Syncing database",
                      title: str = "Database Sync") -> bool:
    """
    Convenience function to show sync progress dialog.
    
    Args:
        parent: Parent widget
        sync_operation: Function that performs sync and returns bool success
        operation_name: Display name for the operation  
        title: Dialog window title
        
    Returns:
        bool: True if sync succeeded, False if failed or cancelled
    """
    dialog = SyncProgressDialog(parent, title)
    return dialog.show_progress(sync_operation, operation_name)


# Example usage for testing
if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget
    
    def mock_sync_operation():
        """Mock sync operation that takes some time"""
        time.sleep(3)  # Simulate 3 second sync
        return True
    
    app = QApplication(sys.argv)
    
    window = QMainWindow()
    central = QWidget()
    layout = QVBoxLayout(central)
    
    button = QPushButton("Test Sync Progress")
    
    def test_sync():
        success = show_sync_progress(
            window, 
            mock_sync_operation,
            "Testing sync operation"
        )
        print(f"Sync result: {success}")
    
    button.clicked.connect(test_sync)
    layout.addWidget(button)
    
    window.setCentralWidget(central)
    window.show()
    
    sys.exit(app.exec())