"""
Leader Election Sync Manager - Backend-agnostic database synchronization.
Provides unified sync logic that works with both local file and Google Drive coordination.
"""

import os
import time
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any, Callable
from datetime import datetime

from .coordination_backend import CoordinationBackend, CoordinationError, LeaderElectionTimeout
from .operation_log import OperationTracker, DatabaseMerger
from utils.logging import debug_print, error_print, info_print, trace_print


class LeaderElectionSyncManager:
    """
    Backend-agnostic database sync manager using leader election.
    Works with any coordination backend (LocalFile, GoogleDrive, etc.)
    """
    
    def __init__(self, coordination_backend: CoordinationBackend, local_cache_db_path: str):
        self.coordination = coordination_backend
        self.local_cache_db = Path(local_cache_db_path)
        self.operation_tracker = OperationTracker(str(self.local_cache_db))
        self.database_merger = DatabaseMerger()
        
        # Callbacks for progress reporting
        self.progress_callback: Optional[Callable[[str, float], None]] = None
        self.status_callback: Optional[Callable[[str], None]] = None
        
        # Sync statistics
        self.last_sync_time: Optional[datetime] = None
        self.sync_count = 0
        self.error_count = 0
        
        debug_print(f"LeaderElectionSyncManager initialized:")
        debug_print(f"  Backend: {type(coordination_backend).__name__}")
        debug_print(f"  Local cache: {self.local_cache_db}")
    
    def set_progress_callback(self, callback: Callable[[str, float], None]) -> None:
        """Set callback for progress updates during sync"""
        self.progress_callback = callback
    
    def set_status_callback(self, callback: Callable[[str], None]) -> None:
        """Set callback for status messages during sync"""
        self.status_callback = callback
    
    def _report_progress(self, message: str, progress: float) -> None:
        """Report progress to callback if set"""
        if self.progress_callback:
            self.progress_callback(message, progress)
        debug_print(f"Sync progress: {message} ({progress:.1%})")
    
    def _report_status(self, message: str) -> None:
        """Report status to callback if set"""
        if self.status_callback:
            self.status_callback(message)
        info_print(f"Sync status: {message}")
    
    def sync_database(self, force: bool = False, timeout_seconds: int = 60) -> bool:
        """
        Perform database synchronization using leader election.
        This is the main sync method that works with any coordination backend.
        """
        if not self.coordination.is_available():
            error_print("Coordination backend not available")
            return False
        
        try:
            self._report_status("Starting database sync")
            self._report_progress("Registering sync intent", 0.1)
            
            # Step 1: Register sync intent
            if not self.coordination.register_sync_intent("database_sync"):
                error_print("Failed to register sync intent")
                self.error_count += 1
                return False
            
            self._report_progress("Attempting leader election", 0.2)
            
            # Step 2: Attempt to become sync leader
            if not self.coordination.attempt_leader_election(timeout_seconds):
                debug_print("Did not become sync leader - another instance is syncing")
                self._report_status("Another instance is handling sync")
                return True  # Not an error - just wait for other instance
            
            try:
                # We are the leader - perform sync
                self._report_status("Became sync leader - performing database sync")
                return self._perform_leader_sync()
                
            finally:
                # Always release leadership
                self._report_progress("Releasing leadership", 0.9)
                self.coordination.release_leadership()
        
        except Exception as e:
            error_print(f"Sync error: {e}")
            self.error_count += 1
            return False
    
    def _perform_leader_sync(self) -> bool:
        """Perform the actual sync operation as the elected leader"""
        try:
            # Step 3: Download latest database from shared location
            self._report_progress("Downloading latest database", 0.3)
            
            # Create temporary file for downloaded database
            with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as temp_file:
                temp_db_path = temp_file.name
            
            try:
                if not self.coordination.download_database(temp_db_path):
                    error_print("Failed to download database")
                    return False
                
                # Step 4: Merge local changes with downloaded database
                self._report_progress("Merging local changes", 0.5)
                merged_db_path = self._merge_databases(temp_db_path)
                
                if not merged_db_path:
                    error_print("Failed to merge databases")
                    return False
                
                # Step 5: Upload merged database
                self._report_progress("Uploading merged database", 0.7)
                if not self.coordination.upload_database(merged_db_path):
                    error_print("Failed to upload merged database")
                    return False
                
                # Step 6: Update local cache with merged database
                self._report_progress("Updating local cache", 0.8)
                if merged_db_path != str(self.local_cache_db):
                    # Copy merged database to local cache
                    import shutil
                    shutil.copy2(merged_db_path, self.local_cache_db)
                
                # Step 7: Clear operation log (changes have been synced)
                self.operation_tracker.clear_operations()
                
                self._report_progress("Sync completed successfully", 1.0)
                self._report_status("Database sync completed successfully")
                
                self.last_sync_time = datetime.now()
                self.sync_count += 1
                
                info_print(f"Leader sync completed successfully")
                return True
                
            finally:
                # Clean up temporary files
                for temp_path in [temp_db_path, merged_db_path]:
                    if temp_path and os.path.exists(temp_path) and temp_path != str(self.local_cache_db):
                        try:
                            os.unlink(temp_path)
                        except:
                            pass
                
        except Exception as e:
            error_print(f"Leader sync error: {e}")
            return False
    
    def _merge_databases(self, downloaded_db_path: str) -> Optional[str]:
        """
        Merge local database with downloaded database using operation tracking.
        Returns path to merged database file.
        """
        try:
            if not os.path.exists(downloaded_db_path):
                debug_print("No downloaded database - using local database")
                return str(self.local_cache_db)
            
            if not self.local_cache_db.exists():
                debug_print("No local database - using downloaded database") 
                return downloaded_db_path
            
            # Both databases exist - perform merge
            debug_print("Merging local and downloaded databases")
            
            # Get pending operations from local database
            pending_operations = self.operation_tracker.get_pending_operations()
            
            if not pending_operations:
                debug_print("No pending local changes - using downloaded database")
                return downloaded_db_path
            
            # Apply local operations to downloaded database
            merged_db_path = self.database_merger.merge_operations(
                downloaded_db_path, 
                pending_operations
            )
            
            if merged_db_path:
                info_print(f"Applied {len(pending_operations)} local operations to downloaded database")
                return merged_db_path
            else:
                error_print("Database merge failed")
                return None
                
        except Exception as e:
            error_print(f"Database merge error: {e}")
            return None
    
    def cleanup_stale_coordination_files(self, max_age_hours: int = 1) -> None:
        """Clean up old coordination files"""
        try:
            self.coordination.cleanup_stale_coordination_files(max_age_hours)
        except Exception as e:
            error_print(f"Cleanup error: {e}")
    
    def force_sync_as_leader(self, timeout_seconds: int = 300) -> bool:
        """
        Force sync by becoming leader (for manual sync operations).
        Uses longer timeout for user-initiated syncs.
        """
        return self.sync_database(force=True, timeout_seconds=timeout_seconds)
    
    def get_sync_status(self) -> Dict[str, Any]:
        """Get comprehensive sync status information"""
        coordination_status = self.coordination.get_coordination_status()
        
        status = {
            "sync_manager": {
                "last_sync": self.last_sync_time.isoformat() if self.last_sync_time else None,
                "sync_count": self.sync_count,
                "error_count": self.error_count,
                "local_cache_exists": self.local_cache_db.exists(),
                "local_cache_size": self.local_cache_db.stat().st_size if self.local_cache_db.exists() else 0,
                "pending_operations": len(self.operation_tracker.get_pending_operations())
            },
            "coordination": coordination_status
        }
        
        return status
    
    def is_sync_needed(self) -> bool:
        """Check if sync is needed based on pending operations"""
        try:
            pending_operations = self.operation_tracker.get_pending_operations()
            return len(pending_operations) > 0
        except Exception as e:
            debug_print(f"Error checking sync needed: {e}")
            return False
    
    def get_pending_operations_count(self) -> int:
        """Get count of pending operations"""
        try:
            return len(self.operation_tracker.get_pending_operations())
        except Exception as e:
            debug_print(f"Error getting pending operations count: {e}")
            return 0


class SyncScheduler:
    """
    Scheduler for automatic background sync operations.
    Handles periodic sync, idle sync, and shutdown sync triggers.
    """
    
    def __init__(self, sync_manager: LeaderElectionSyncManager):
        self.sync_manager = sync_manager
        self.auto_sync_enabled = True
        self.sync_interval_minutes = 5
        self.last_auto_sync: Optional[datetime] = None
        
    def should_auto_sync(self) -> bool:
        """Check if automatic sync should be triggered"""
        if not self.auto_sync_enabled:
            return False
            
        if not self.sync_manager.is_sync_needed():
            return False
            
        if self.last_auto_sync is None:
            return True
            
        elapsed_minutes = (datetime.now() - self.last_auto_sync).total_seconds() / 60
        return elapsed_minutes >= self.sync_interval_minutes
    
    def trigger_auto_sync(self) -> bool:
        """Trigger automatic sync if needed"""
        if self.should_auto_sync():
            debug_print("Triggering automatic sync")
            result = self.sync_manager.sync_database(timeout_seconds=30)
            if result:
                self.last_auto_sync = datetime.now()
            return result
        return True
    
    def trigger_idle_sync(self) -> bool:
        """Trigger sync when application becomes idle"""
        if self.sync_manager.is_sync_needed():
            debug_print("Triggering idle sync")
            return self.sync_manager.sync_database(timeout_seconds=60)
        return True
    
    def trigger_shutdown_sync(self) -> bool:
        """Trigger sync when application is shutting down"""
        if self.sync_manager.is_sync_needed():
            info_print("Triggering shutdown sync")
            return self.sync_manager.sync_database(timeout_seconds=120)
        return True
    
    def trigger_manual_sync(self) -> bool:
        """Trigger manual sync (user clicked sync button)"""
        info_print("Triggering manual sync")
        return self.sync_manager.force_sync_as_leader(timeout_seconds=300)