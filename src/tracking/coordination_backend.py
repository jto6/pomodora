"""
Unified coordination backend interface for leader election sync.
Provides abstract interface for both local file and Google Drive coordination.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime
import uuid
import os
import json
from pathlib import Path
from utils.logging import debug_print, error_print, info_print


class CoordinationBackend(ABC):
    """Abstract base class for database sync coordination backends"""
    
    def __init__(self):
        self.instance_id = self._generate_instance_id()
    
    def _generate_instance_id(self) -> str:
        """Generate unique instance ID for this app instance"""
        return f"{os.getpid()}_{uuid.uuid4().hex[:8]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    @abstractmethod
    def register_sync_intent(self, operation_type: str = "sync") -> bool:
        """
        Step 1: Register intent to perform sync operation.
        Returns True if intent registered successfully.
        """
        pass
    
    @abstractmethod
    def attempt_leader_election(self, timeout_seconds: int = 30) -> bool:
        """
        Step 2: Try to become the sync leader.
        Returns True if this instance became the leader.
        """
        pass
    
    @abstractmethod
    def upload_database(self, local_db_path: str, backup_info: Optional[Dict[str, Any]] = None) -> bool:
        """
        Step 3: Upload merged database to shared location.
        Returns True if upload successful.
        """
        pass
        
    @abstractmethod
    def download_database(self, local_cache_path: str) -> bool:
        """
        Step 4: Download latest database from shared location.
        Returns True if download successful.
        """
        pass
    
    @abstractmethod
    def release_leadership(self) -> None:
        """
        Step 5: Clean up leadership and coordination files.
        Called when sync operation completes (success or failure).
        """
        pass
    
    @abstractmethod
    def cleanup_stale_coordination_files(self, max_age_hours: int = 1) -> None:
        """
        Cleanup old coordination files that may be left from crashed instances.
        Should be called periodically to prevent coordination file buildup.
        """
        pass
    
    @abstractmethod
    def get_coordination_status(self) -> Dict[str, Any]:
        """
        Get current coordination status for debugging/monitoring.
        Returns dict with current leader, pending intents, etc.
        """
        pass
    
    @abstractmethod
    def has_database_changed(self, last_sync_metadata: Optional[Dict[str, Any]] = None) -> tuple[bool, Optional[Dict[str, Any]]]:
        """
        Check if remote database has changed since last sync.
        Conservative approach - returns True if uncertain.
        
        Args:
            last_sync_metadata: Metadata from previous sync (modTime, size, etc.)
        
        Returns:
            tuple: (has_changed: bool, current_metadata: dict)
            - has_changed: True if database changed OR if uncertain
            - current_metadata: Current file metadata for future comparisons
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if coordination backend is available and functional.
        Returns True if backend can be used for coordination.
        """
        pass


class CoordinationError(Exception):
    """Exception raised for coordination backend errors"""
    pass


class LeaderElectionTimeout(CoordinationError):
    """Exception raised when leader election times out"""
    pass


class CoordinationBackendUnavailable(CoordinationError):
    """Exception raised when coordination backend is not available"""
    pass