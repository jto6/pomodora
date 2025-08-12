"""
Google Drive coordination backend for leader election sync.
Uses Google Drive API for coordination between multiple app instances.
"""

import os
import json
import time
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from .coordination_backend import CoordinationBackend, CoordinationError, LeaderElectionTimeout
from .google_drive import GoogleDriveSync
from utils.logging import debug_print, error_print, info_print, trace_print


class GoogleDriveBackend(CoordinationBackend):
    """
    Coordination backend using Google Drive API.
    Suitable for multi-workstation sync across different networks.
    """
    
    def __init__(self, credentials_path: str, folder_name: str):
        super().__init__()
        self.credentials_path = credentials_path
        self.folder_name = folder_name
        self.drive_sync = GoogleDriveSync(credentials_path)
        
        self._intent_filename = None
        self._leader_filename = None
        self._is_leader = False
        
        debug_print(f"GoogleDriveBackend initialized:")
        debug_print(f"  Credentials: {credentials_path}")
        debug_print(f"  Folder: {folder_name}")
        debug_print(f"  Instance ID: {self.instance_id}")
    
    def register_sync_intent(self, operation_type: str = "sync") -> bool:
        """Register intent to perform sync operation via Google Drive"""
        try:
            if not self.drive_sync.authenticate():
                error_print("Failed to authenticate with Google Drive")
                return False
            
            if not self.drive_sync.ensure_folder_exists(self.folder_name):
                error_print(f"Failed to access Google Drive folder: {self.folder_name}")
                return False
            
            intent_data = {
                "instance_id": self.instance_id,
                "operation_type": operation_type,
                "timestamp": datetime.now().isoformat(),
                "pid": os.getpid()
            }
            
            # Create intent file
            self._intent_filename = f"sync_intent_{self.instance_id}.json"
            
            # Upload intent file to Google Drive
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp_file:
                json.dump(intent_data, tmp_file, indent=2)
                tmp_file.flush()
                
                success = self.drive_sync.upload_file(tmp_file.name, self._intent_filename)
                os.unlink(tmp_file.name)
                
                if success:
                    debug_print(f"Registered sync intent: {operation_type}")
                    return True
                else:
                    error_print("Failed to upload intent file to Google Drive")
                    return False
            
        except Exception as e:
            error_print(f"Failed to register sync intent: {e}")
            return False
    
    def attempt_leader_election(self, timeout_seconds: int = 30) -> bool:
        """Try to become sync leader using Google Drive coordination"""
        try:
            start_time = time.time()
            self._leader_filename = f"sync_leader_{self.instance_id}.json"
            
            while time.time() - start_time < timeout_seconds:
                # Check if any leader currently exists
                existing_leaders = self.drive_sync.list_files_by_pattern("sync_leader_*.json")
                
                if not existing_leaders:
                    # No leader exists - try to claim leadership
                    leader_info = {
                        "instance_id": self.instance_id,
                        "elected_at": datetime.now().isoformat(),
                        "pid": os.getpid(),
                        "operation": "database_sync"
                    }
                    
                    # Upload leader file
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp_file:
                        json.dump(leader_info, tmp_file, indent=2)
                        tmp_file.flush()
                        
                        success = self.drive_sync.upload_file(tmp_file.name, self._leader_filename)
                        os.unlink(tmp_file.name)
                        
                        if success:
                            # Double-check we're the only leader (handle race condition)
                            time.sleep(1)  # Give other instances time to upload
                            current_leaders = self.drive_sync.list_files_by_pattern("sync_leader_*.json")
                            
                            # Check if our leader file is the oldest (wins ties)
                            our_leader_time = None
                            oldest_leader = None
                            oldest_time = None
                            
                            for leader in current_leaders:
                                if leader['name'] == self._leader_filename:
                                    our_leader_time = leader['createdTime']
                                
                                leader_time = leader['createdTime']
                                if oldest_time is None or leader_time < oldest_time:
                                    oldest_time = leader_time
                                    oldest_leader = leader
                            
                            if oldest_leader and oldest_leader['name'] == self._leader_filename:
                                self._is_leader = True
                                info_print(f"Became sync leader (instance: {self.instance_id})")
                                return True
                            else:
                                # Another instance won - clean up our leader file
                                self.drive_sync.delete_file_by_name(self._leader_filename)
                                debug_print("Lost leader election race condition")
                else:
                    # Leader exists - check if it's stale
                    for leader in existing_leaders:
                        # Check if leader file is older than timeout
                        leader_time = datetime.fromisoformat(leader['createdTime'].replace('Z', '+00:00'))
                        if datetime.now(leader_time.tzinfo) - leader_time > timedelta(minutes=5):
                            # Stale leader - try to remove it
                            debug_print(f"Removing stale leader: {leader['name']}")
                            self.drive_sync.delete_file_by_name(leader['name'])
                            continue  # Try leader election again
                
                # Wait and retry
                time.sleep(2)
            
            debug_print(f"Leader election timeout after {timeout_seconds}s")
            return False
            
        except Exception as e:
            error_print(f"Leader election error: {e}")
            return False
    
    def upload_database(self, local_db_path: str, backup_info: Optional[Dict[str, Any]] = None) -> bool:
        """Upload database to Google Drive"""
        try:
            local_path = Path(local_db_path)
            if not local_path.exists():
                error_print(f"Local database not found: {local_path}")
                return False
            
            # Use timestamped filename to avoid conflicts during upload
            timestamp = int(time.time())
            temp_filename = f"pomodora_sync_{timestamp}.db"
            final_filename = "pomodora.db"
            
            # Upload to temporary name first
            if not self.drive_sync.upload_file(str(local_path), temp_filename):
                error_print("Failed to upload database to Google Drive")
                return False
            
            # Note: Database backups are handled locally, not in Google Drive
            
            # Clean up any existing files with the final name (to avoid duplicates)
            existing_final_files = self.drive_sync.list_files_by_name(final_filename)
            if len(existing_final_files) > 1:
                debug_print(f"Found {len(existing_final_files)} existing files named '{final_filename}', cleaning up duplicates")
                # Keep only the most recent one, delete the rest
                existing_final_files.sort(key=lambda f: f.get('modifiedTime', ''), reverse=True)
                for file_to_delete in existing_final_files[1:]:  # Delete all but the first (most recent)
                    debug_print(f"Deleting duplicate file: {file_to_delete['id']}")
                    self.drive_sync.service.files().delete(fileId=file_to_delete['id']).execute()
            
            # Rename temporary file to final name (atomic operation)
            temp_files = self.drive_sync.list_files_by_name(temp_filename)
            if temp_files:
                success = self.drive_sync.rename_file(temp_files[0]['id'], final_filename)
                if not success:
                    error_print("Failed to finalize database upload")
                    # Clean up temp file
                    self.drive_sync.delete_file_by_name(temp_filename)
                    return False
            
            file_size = local_path.stat().st_size
            info_print(f"Database uploaded successfully to Google Drive ({file_size} bytes)")
            return True
            
        except Exception as e:
            error_print(f"Database upload error: {e}")
            return False
    
    def download_database(self, local_cache_path: str) -> bool:
        """Download database from Google Drive"""
        try:
            # Look for main database file
            db_files = self.drive_sync.list_files_by_name("pomodora.db")
            
            if not db_files:
                debug_print("No database found on Google Drive - nothing to download")
                return True  # Not an error - first sync scenario
            
            local_path = Path(local_cache_path)
            local_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Download database file
            file_id = db_files[0]['id']
            if not self.drive_sync.download_file(file_id, str(local_path)):
                error_print("Failed to download database from Google Drive")
                return False
            
            # Verify download
            if not local_path.exists():
                error_print("Database download failed - local file not created")
                return False
            
            file_size = local_path.stat().st_size
            info_print(f"Database downloaded successfully from Google Drive ({file_size} bytes)")
            return True
            
        except Exception as e:
            error_print(f"Database download error: {e}")
            return False
    
    def release_leadership(self) -> None:
        """Release leadership and clean up coordination files"""
        try:
            # Remove intent file
            if self._intent_filename:
                self.drive_sync.delete_file_by_name(self._intent_filename)
                debug_print("Removed intent file from Google Drive")
                self._intent_filename = None
            
            # Remove leader file
            if self._leader_filename:
                self.drive_sync.delete_file_by_name(self._leader_filename)
                debug_print("Removed leader file from Google Drive")
                self._leader_filename = None
            
            self._is_leader = False
            info_print("Released sync leadership")
            
        except Exception as e:
            error_print(f"Error releasing leadership: {e}")
    
    def cleanup_stale_coordination_files(self, max_age_hours: int = 1) -> None:
        """Remove old coordination files from crashed instances"""
        try:
            cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
            
            # Clean up old intent files
            intent_files = self.drive_sync.list_files_by_pattern("sync_intent_*.json")
            for intent_file in intent_files:
                file_time = datetime.fromisoformat(intent_file['createdTime'].replace('Z', '+00:00'))
                if file_time < cutoff_time:
                    self.drive_sync.delete_file_by_name(intent_file['name'])
                    debug_print(f"Cleaned up stale intent file: {intent_file['name']}")
            
            # Clean up old leader files (should be rare, but handle crashed instances)
            leader_files = self.drive_sync.list_files_by_pattern("sync_leader_*.json")
            for leader_file in leader_files:
                file_time = datetime.fromisoformat(leader_file['createdTime'].replace('Z', '+00:00'))
                if file_time < cutoff_time:
                    self.drive_sync.delete_file_by_name(leader_file['name'])
                    debug_print(f"Cleaned up stale leader file: {leader_file['name']}")
            
            # Clean up any backup files (they shouldn't exist in Google Drive)
            backup_files = self.drive_sync.list_files_by_pattern("pomodora_backup_*.db")
            for backup_file in backup_files:
                self.drive_sync.delete_file_by_name(backup_file['name'])
                debug_print(f"Removed inappropriate backup file from Google Drive: {backup_file['name']}")
            
            # Clean up temporary sync files
            temp_files = self.drive_sync.list_files_by_pattern("pomodora_sync_*.db")
            for temp_file in temp_files:
                file_time = datetime.fromisoformat(temp_file['createdTime'].replace('Z', '+00:00'))
                if file_time < cutoff_time:
                    self.drive_sync.delete_file_by_name(temp_file['name'])
                    debug_print(f"Cleaned up temp sync file: {temp_file['name']}")
            
        except Exception as e:
            error_print(f"Error cleaning up stale files: {e}")
    
    def get_coordination_status(self) -> Dict[str, Any]:
        """Get current coordination status"""
        status = {
            "backend_type": "google_drive",
            "instance_id": self.instance_id,
            "is_leader": self._is_leader,
            "folder_name": self.folder_name,
            "credentials_path": self.credentials_path
        }
        
        try:
            # Check authentication status
            status["authenticated"] = self.drive_sync.service is not None
            
            if not status["authenticated"]:
                status["error"] = "Not authenticated with Google Drive"
                return status
            
            # List current leader files
            leader_files = self.drive_sync.list_files_by_pattern("sync_leader_*.json")
            if leader_files:
                status["current_leader"] = leader_files[0]['name']
            else:
                status["current_leader"] = None
            
            # Count active intent files
            intent_files = self.drive_sync.list_files_by_pattern("sync_intent_*.json")
            status["active_intents"] = len(intent_files)
            
            # Check database file status
            db_files = self.drive_sync.list_files_by_name("pomodora.db")
            if db_files:
                db_file = db_files[0]
                status["remote_db"] = {
                    "exists": True,
                    "size_bytes": int(db_file.get('size', 0)),
                    "modified_at": db_file['modifiedTime']
                }
            else:
                status["remote_db"] = {"exists": False}
            
        except Exception as e:
            status["status_error"] = str(e)
        
        return status
    
    def is_available(self) -> bool:
        """Check if Google Drive backend is available"""
        try:
            # Check if credentials file exists
            if not os.path.exists(self.credentials_path):
                debug_print(f"Google Drive credentials not found: {self.credentials_path}")
                return False
            
            # Try to authenticate
            if not self.drive_sync.authenticate():
                debug_print("Failed to authenticate with Google Drive")
                return False
            
            # Try to access the folder
            if not self.drive_sync.ensure_folder_exists(self.folder_name):
                debug_print(f"Cannot access Google Drive folder: {self.folder_name}")
                return False
            
            return True
            
        except Exception as e:
            debug_print(f"GoogleDriveBackend not available: {e}")
            return False