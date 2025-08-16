"""
Leader Election Sync Manager - Backend-agnostic database synchronization.
Provides unified sync logic that works with both local file and Google Drive coordination.
"""

import os
import time
import tempfile
import json
from pathlib import Path
from typing import Optional, Dict, Any, Callable
from datetime import datetime

from .coordination_backend import CoordinationBackend, CoordinationError, LeaderElectionTimeout
from .operation_log import OperationTracker, DatabaseMerger
from .models import Base
from utils.logging import debug_print, error_print, info_print, trace_print
from sqlalchemy import create_engine, text


class LeaderElectionSyncManager:
    """
    Backend-agnostic database sync manager using leader election.
    Works with any coordination backend (LocalFile, GoogleDrive, etc.)
    """
    
    def __init__(self, coordination_backend: CoordinationBackend, local_cache_db_path: str):
        self.coordination = coordination_backend
        self.local_cache_db = Path(local_cache_db_path)
        self.operation_tracker = OperationTracker(str(self.local_cache_db))
        # DatabaseMerger created on-demand during sync operations
        
        # Callbacks for progress reporting
        self.progress_callback: Optional[Callable[[str, float], None]] = None
        self.status_callback: Optional[Callable[[str], None]] = None
        
        # Sync statistics
        self.last_sync_time: Optional[datetime] = None
        self.sync_count = 0
        self.error_count = 0
        
        # Sync metadata persistence
        self.sync_metadata_file = Path(local_cache_db_path).parent / "last_sync_metadata.json"
        
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
    
    def _ensure_database_schema(self, db_path: str) -> bool:
        """
        Ensure database has proper schema (tables) and default data before using it.
        
        Args:
            db_path: Path to database file to validate/fix
            
        Returns:
            True if schema and default data exist or were successfully created, False on error
        """
        try:
            if not os.path.exists(db_path):
                debug_print(f"Database file does not exist: {db_path}")
                return False
            
            # Check if database has tables
            engine = create_engine(f'sqlite:///{db_path}', echo=False)
            
            try:
                with engine.connect() as conn:
                    # Check if core tables exist
                    result = conn.execute(text(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('projects', 'task_categories', 'sprints')"
                    ))
                    existing_tables = [row[0] for row in result.fetchall()]
                    
                    schema_complete = len(existing_tables) == 3
                    
                    if not schema_complete:
                        # Schema missing or incomplete - create it
                        info_print(f"Creating missing database schema in: {db_path}")
                        Base.metadata.create_all(engine)
                        
                        # Verify schema was created
                        result = conn.execute(text(
                            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('projects', 'task_categories', 'sprints')"
                        ))
                        created_tables = [row[0] for row in result.fetchall()]
                        
                        if len(created_tables) != 3:
                            error_print(f"Failed to create complete schema in: {db_path}")
                            return False
                        
                        info_print(f"Successfully created database schema in: {db_path}")
                    
                    # Check if default data exists
                    result = conn.execute(text("SELECT COUNT(*) FROM projects"))
                    project_count = result.fetchone()[0]
                    
                    result = conn.execute(text("SELECT COUNT(*) FROM task_categories"))
                    category_count = result.fetchone()[0]
                    
                    if project_count == 0 or category_count == 0:
                        info_print(f"Creating default data in database: {db_path}")
                        # Create default data directly to avoid circular imports
                        from sqlalchemy.orm import sessionmaker
                        from .models import Project, TaskCategory
                        
                        Session = sessionmaker(bind=engine)
                        session = Session()
                        
                        try:
                            # Default task categories
                            default_categories = [
                                {"name": "Admin", "color": "#3498db"},
                                {"name": "Comm", "color": "#2ecc71"},
                                {"name": "Strategy", "color": "#f39c12"},
                                {"name": "Research", "color": "#9b59b6"},
                                {"name": "SelfDev", "color": "#e74c3c"},
                                {"name": "Dev", "color": "#1abc9c"}
                            ]
                            
                            for cat_data in default_categories:
                                existing = session.query(TaskCategory).filter(TaskCategory.name == cat_data["name"]).first()
                                if not existing:
                                    category = TaskCategory(name=cat_data["name"], color=cat_data["color"])
                                    session.add(category)
                            
                            # Default projects - only "None" as default
                            default_projects = [
                                {"name": "None", "color": "#3498db"}
                            ]
                            
                            for proj_data in default_projects:
                                existing = session.query(Project).filter(Project.name == proj_data["name"]).first()
                                if not existing:
                                    project = Project(name=proj_data["name"], color=proj_data["color"])
                                    session.add(project)
                            
                            session.commit()
                            info_print(f"Successfully created default data in: {db_path}")
                            
                        except Exception as e:
                            session.rollback()
                            error_print(f"Failed to create default data: {e}")
                            return False
                        finally:
                            session.close()
                    
                    debug_print(f"Database schema and data validated: {db_path}")
                    return True
                        
            finally:
                engine.dispose()
                
        except Exception as e:
            error_print(f"Failed to validate/create database schema for {db_path}: {e}")
            return False
    
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
            # Check if download is needed using change detection
            last_metadata = self._load_last_sync_metadata()
            has_changed, current_metadata = self.coordination.has_database_changed(last_metadata)
            
            # Get pending operations to determine if we need to upload
            pending_operations = self.operation_tracker.get_pending_operations()
            
            if not has_changed and not pending_operations:
                debug_print("No remote changes and no local operations - skipping sync")
                self._report_progress("No changes detected - sync complete", 1.0)
                return True
            
            # Step 3: Download latest database from shared location (if changed or we have local ops)
            self._report_progress("Downloading latest database", 0.3)
            
            # Create temporary file for downloaded database
            with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as temp_file:
                temp_db_path = temp_file.name
            
            try:
                if not self.coordination.download_database(temp_db_path):
                    error_print("Failed to download database")
                    return False
                
                # Get pending operations before processing
                pending_operations = self.operation_tracker.get_pending_operations()
                
                # Validate and ensure downloaded database has proper schema
                if not self._ensure_database_schema(temp_db_path):
                    error_print("Downloaded database lacks proper schema - will use local database as authoritative source")
                    # Use local database as the source of truth when remote is corrupted
                    merged_db_path = str(self.local_cache_db)
                    info_print("Using local database as authoritative source due to remote corruption")
                else:
                    # Step 4: Merge local changes with downloaded database
                    self._report_progress("Merging local changes", 0.5)
                    merged_db_path = self._merge_databases(temp_db_path)
                
                    if not merged_db_path:
                        error_print("Failed to merge databases")
                        return False
                
                # Step 5: Upload merged database if there were local changes OR if remote was corrupted
                if pending_operations or not self._ensure_database_schema(temp_db_path):
                    # Database was merged with local changes - upload required
                    self._report_progress("Uploading merged database", 0.7)
                    if not self.coordination.upload_database(merged_db_path):
                        error_print("Failed to upload merged database")
                        return False
                    debug_print("Uploaded merged database with local changes")
                else:
                    # No local changes were applied - skip upload
                    debug_print("No local changes applied - skipping database upload")
                    self._report_progress("No upload needed", 0.7)
                
                # Step 6: Update local cache with merged database
                self._report_progress("Updating local cache", 0.8)
                if merged_db_path != str(self.local_cache_db):
                    # Validate merged database has proper schema before replacing local
                    if not self._ensure_database_schema(merged_db_path):
                        error_print("Merged database lacks proper schema - cannot replace local database")
                        return False
                    
                    # Copy merged database to local cache
                    import shutil
                    shutil.copy2(merged_db_path, self.local_cache_db)
                    info_print("Successfully updated local database with validated schema")
                
                # Step 7: Clear operation log (changes have been synced)
                self.operation_tracker.clear_operations()
                
                self._report_progress("Sync completed successfully", 1.0)
                self._report_status("Database sync completed successfully")
                
                self.last_sync_time = datetime.now()
                self.sync_count += 1
                
                # Save current metadata for future change detection
                if current_metadata:
                    self._save_last_sync_metadata(current_metadata)
                
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
            
            # Create DatabaseMerger on-demand for this sync operation
            from .operation_log import DatabaseMerger
            database_merger = DatabaseMerger(
                str(self.local_cache_db),  # local_db_path
                downloaded_db_path,       # remote_db_path (downloaded temp file)
                self.operation_tracker    # Use existing tracker
            )
            
            # Apply local operations to downloaded database
            merged_db_path = database_merger.merge_operations(
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
    
    def _load_last_sync_metadata(self) -> Optional[Dict[str, Any]]:
        """Load metadata from last sync operation"""
        try:
            if self.sync_metadata_file.exists():
                with open(self.sync_metadata_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            debug_print(f"Error loading sync metadata: {e}")
        return None
    
    def _save_last_sync_metadata(self, metadata: Dict[str, Any]) -> None:
        """Save metadata from sync operation"""
        try:
            self.sync_metadata_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.sync_metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
            debug_print(f"Saved sync metadata: {metadata}")
        except Exception as e:
            debug_print(f"Error saving sync metadata: {e}")
    
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
    Scheduler for sync operations.
    Handles idle sync, manual sync, and shutdown sync triggers.
    """
    
    def __init__(self, sync_manager: LeaderElectionSyncManager):
        self.sync_manager = sync_manager
    
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