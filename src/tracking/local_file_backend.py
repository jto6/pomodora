"""
Local file coordination backend for leader election sync.
Uses file system operations for coordination between multiple app instances.
"""

import os
import json
import shutil
import time
import fcntl  # Unix file locking
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from .coordination_backend import CoordinationBackend, CoordinationError, LeaderElectionTimeout
from utils.logging import debug_print, error_print, info_print, trace_print


class LocalFileBackend(CoordinationBackend):
    """
    Coordination backend using local/network file system.
    Suitable for shared network drives or local multi-instance testing.
    """
    
    def __init__(self, shared_db_path: str):
        super().__init__()
        self.shared_db_path = Path(shared_db_path).resolve()
        
        # Ensure parent directory exists for shared database
        parent_dir = self.shared_db_path.parent
        debug_print(f"Creating parent directory: {parent_dir}")
        
        try:
            # Check if path exists and what type it is
            if parent_dir.exists():
                if parent_dir.is_file():
                    raise FileExistsError(f"Cannot create directory '{parent_dir}' - a file with that name already exists")
                elif parent_dir.is_dir():
                    debug_print(f"Parent directory already exists: {parent_dir}")
                else:
                    debug_print(f"Path exists but is neither file nor directory: {parent_dir}")
            else:
                parent_dir.mkdir(parents=True, exist_ok=True)
                debug_print(f"Created parent directory: {parent_dir}")
        except Exception as e:
            error_print(f"Failed to create parent directory {parent_dir}: {e}")
            raise
        
        self.coordination_dir = self.shared_db_path.parent / ".pomodora_sync"
        self.coordination_dir.mkdir(exist_ok=True)
        
        # Coordination files
        self.intent_file = self.coordination_dir / f"intent_{self.instance_id}.json"
        self.leader_lock_file = self.coordination_dir / "sync_leader.lock" 
        self.leader_info_file = self.coordination_dir / "sync_leader.json"
        
        self._leader_lock_fd = None
        self._is_leader = False
        
        debug_print(f"LocalFileBackend initialized:")
        debug_print(f"  Shared DB: {self.shared_db_path}")
        debug_print(f"  Coordination dir: {self.coordination_dir}")
        debug_print(f"  Instance ID: {self.instance_id}")
    
    def register_sync_intent(self, operation_type: str = "sync") -> bool:
        """Register intent to perform sync operation"""
        try:
            intent_data = {
                "instance_id": self.instance_id,
                "operation_type": operation_type,
                "timestamp": datetime.now().isoformat(),
                "pid": os.getpid()
            }
            
            # Write intent file atomically
            temp_intent_file = self.intent_file.with_suffix('.tmp')
            with open(temp_intent_file, 'w') as f:
                json.dump(intent_data, f, indent=2)
            
            temp_intent_file.rename(self.intent_file)
            debug_print(f"Registered sync intent: {operation_type}")
            return True
            
        except Exception as e:
            error_print(f"Failed to register sync intent: {e}")
            return False
    
    def attempt_leader_election(self, timeout_seconds: int = 30) -> bool:
        """Try to become the sync leader using file locking"""
        try:
            start_time = time.time()
            
            while time.time() - start_time < timeout_seconds:
                try:
                    # Try to acquire exclusive lock on leader lock file
                    self._leader_lock_fd = open(self.leader_lock_file, 'w')
                    fcntl.flock(self._leader_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    
                    # Successfully acquired lock - we are the leader
                    leader_info = {
                        "instance_id": self.instance_id,
                        "elected_at": datetime.now().isoformat(),
                        "pid": os.getpid(),
                        "operation": "database_sync"
                    }
                    
                    # Write leader info to lock file
                    self._leader_lock_fd.write(json.dumps(leader_info, indent=2))
                    self._leader_lock_fd.flush()
                    
                    # Also create readable leader info file
                    with open(self.leader_info_file, 'w') as f:
                        json.dump(leader_info, f, indent=2)
                    
                    self._is_leader = True
                    info_print(f"Became sync leader (instance: {self.instance_id})")
                    return True
                    
                except (IOError, OSError):
                    # Lock file is held by another instance
                    if self._leader_lock_fd:
                        try:
                            self._leader_lock_fd.close()
                        except:
                            pass
                        self._leader_lock_fd = None
                    
                    # Wait and retry
                    time.sleep(0.5)
                    continue
            
            # Timeout reached
            debug_print(f"Leader election timeout after {timeout_seconds}s")
            return False
            
        except Exception as e:
            error_print(f"Leader election error: {e}")
            return False
    
    def upload_database(self, local_db_path: str, backup_info: Optional[Dict[str, Any]] = None) -> bool:
        """Upload (copy) database to shared location"""
        try:
            local_path = Path(local_db_path)
            if not local_path.exists():
                error_print(f"Local database not found: {local_path}")
                return False
            
            # Create backup of existing shared database
            if self.shared_db_path.exists():
                backup_path = self.shared_db_path.with_suffix(f'.backup_{int(time.time())}')
                shutil.copy2(self.shared_db_path, backup_path)
                debug_print(f"Created backup: {backup_path}")
            
            # Copy local database to shared location
            # Use copy2 to preserve timestamps and metadata
            shutil.copy2(local_path, self.shared_db_path)
            
            # Verify copy succeeded
            if not self.shared_db_path.exists():
                error_print("Database upload failed - shared file not created")
                return False
            
            # Check file sizes match
            local_size = local_path.stat().st_size
            shared_size = self.shared_db_path.stat().st_size
            
            if local_size != shared_size:
                error_print(f"Database upload failed - size mismatch: {local_size} != {shared_size}")
                return False
            
            info_print(f"Database uploaded successfully ({local_size} bytes)")
            return True
            
        except Exception as e:
            error_print(f"Database upload error: {e}")
            return False
    
    def download_database(self, local_cache_path: str) -> bool:
        """Download (copy) database from shared location"""
        try:
            if not self.shared_db_path.exists():
                debug_print("No shared database found - nothing to download")
                return True  # Not an error - first sync scenario
            
            local_path = Path(local_cache_path)
            
            # Ensure local directory exists
            local_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy shared database to local cache
            shutil.copy2(self.shared_db_path, local_path)
            
            # Verify copy succeeded
            if not local_path.exists():
                error_print("Database download failed - local file not created")
                return False
            
            # Check file sizes match
            shared_size = self.shared_db_path.stat().st_size
            local_size = local_path.stat().st_size
            
            if shared_size != local_size:
                error_print(f"Database download failed - size mismatch: {shared_size} != {local_size}")
                return False
            
            info_print(f"Database downloaded successfully ({shared_size} bytes)")
            return True
            
        except Exception as e:
            error_print(f"Database download error: {e}")
            return False
    
    def release_leadership(self) -> None:
        """Release leadership and clean up coordination files"""
        try:
            # Remove intent file
            if self.intent_file.exists():
                self.intent_file.unlink()
                debug_print("Removed intent file")
            
            # Release lock and close file
            if self._leader_lock_fd:
                try:
                    fcntl.flock(self._leader_lock_fd, fcntl.LOCK_UN)
                    self._leader_lock_fd.close()
                except:
                    pass
                self._leader_lock_fd = None
                debug_print("Released leader lock")
            
            # Remove leader info file
            if self.leader_info_file.exists():
                self.leader_info_file.unlink()
                debug_print("Removed leader info file")
            
            # Remove leader lock file
            if self.leader_lock_file.exists():
                try:
                    self.leader_lock_file.unlink()
                    debug_print("Removed leader lock file")
                except:
                    pass  # May fail if another instance is waiting for lock
            
            self._is_leader = False
            info_print("Released sync leadership")
            
        except Exception as e:
            error_print(f"Error releasing leadership: {e}")
    
    def cleanup_stale_coordination_files(self, max_age_hours: int = 1) -> None:
        """Remove old coordination files from crashed instances"""
        try:
            cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
            
            # Clean up old intent files
            for intent_file in self.coordination_dir.glob("intent_*.json"):
                try:
                    file_time = datetime.fromtimestamp(intent_file.stat().st_mtime)
                    if file_time < cutoff_time:
                        # Check if process still exists
                        with open(intent_file, 'r') as f:
                            intent_data = json.load(f)
                        
                        pid = intent_data.get('pid')
                        if pid and not self._is_process_running(pid):
                            intent_file.unlink()
                            debug_print(f"Cleaned up stale intent file: {intent_file.name}")
                except Exception:
                    # If we can't read the file, just remove it if it's old enough
                    try:
                        if datetime.fromtimestamp(intent_file.stat().st_mtime) < cutoff_time:
                            intent_file.unlink()
                    except:
                        pass
            
            # Clean up database backups older than 24 hours
            backup_cutoff = datetime.now() - timedelta(hours=24)
            for backup_file in self.shared_db_path.parent.glob(f"{self.shared_db_path.name}.backup_*"):
                try:
                    backup_time = datetime.fromtimestamp(backup_file.stat().st_mtime)
                    if backup_time < backup_cutoff:
                        backup_file.unlink()
                        debug_print(f"Cleaned up old backup: {backup_file.name}")
                except Exception:
                    pass
            
        except Exception as e:
            error_print(f"Error cleaning up stale files: {e}")
    
    def _is_process_running(self, pid: int) -> bool:
        """Check if a process with given PID is still running"""
        try:
            os.kill(pid, 0)  # Signal 0 just checks if process exists
            return True
        except OSError:
            return False
    
    def get_coordination_status(self) -> Dict[str, Any]:
        """Get current coordination status"""
        status = {
            "backend_type": "local_file",
            "instance_id": self.instance_id,
            "is_leader": self._is_leader,
            "coordination_dir": str(self.coordination_dir),
            "shared_db_path": str(self.shared_db_path)
        }
        
        try:
            # Check if leader info file exists
            if self.leader_info_file.exists():
                with open(self.leader_info_file, 'r') as f:
                    leader_info = json.load(f)
                status["current_leader"] = leader_info
            else:
                status["current_leader"] = None
            
            # List active intent files
            intent_files = list(self.coordination_dir.glob("intent_*.json"))
            status["active_intents"] = len(intent_files)
            
            # Check shared database status
            if self.shared_db_path.exists():
                stat = self.shared_db_path.stat()
                status["shared_db"] = {
                    "exists": True,
                    "size_bytes": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat()
                }
            else:
                status["shared_db"] = {"exists": False}
            
        except Exception as e:
            status["status_error"] = str(e)
        
        return status
    
    def has_database_changed(self, last_sync_metadata: Optional[Dict[str, Any]] = None) -> tuple[bool, Optional[Dict[str, Any]]]:
        """
        Check if shared database file has changed since last sync.
        Conservative approach - returns True if uncertain.
        """
        try:
            if not self.shared_db_path.exists():
                debug_print("No shared database file found - considering as changed")
                return True, None  # Conservative: no file = changed
            
            stat = self.shared_db_path.stat()
            current_metadata = {
                "modified_time": stat.st_mtime,
                "size": stat.st_size
            }
            
            # Conservative: download if no previous metadata
            if not last_sync_metadata:
                debug_print("No previous sync metadata - considering as changed")
                return True, current_metadata
            
            # Compare filesystem metadata
            if (current_metadata["modified_time"] != last_sync_metadata.get("modified_time") or
                current_metadata["size"] != last_sync_metadata.get("size")):
                debug_print(f"Shared database changed: modTime={current_metadata['modified_time']}, size={current_metadata['size']}")
                return True, current_metadata
            
            debug_print("Shared database unchanged since last sync")
            return False, current_metadata
            
        except Exception as e:
            debug_print(f"Error checking shared database changes: {e}")
            return True, None  # Conservative: download on any error
    
    def is_available(self) -> bool:
        """Check if local file backend is available"""
        try:
            # Check if coordination directory is accessible
            if not self.coordination_dir.exists():
                self.coordination_dir.mkdir(parents=True)
            
            # Test write access
            test_file = self.coordination_dir / f"test_{self.instance_id}"
            test_file.write_text("test")
            test_file.unlink()
            
            return True
            
        except Exception as e:
            debug_print(f"LocalFileBackend not available: {e}")
            return False