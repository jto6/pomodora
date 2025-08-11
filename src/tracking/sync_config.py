"""
Sync configuration management for leader election sync.
Handles both new unified configuration and legacy settings migration.
"""

from typing import Dict, Any, Optional, Tuple
from pathlib import Path

from .coordination_backend import CoordinationBackend
from .local_file_backend import LocalFileBackend
from .google_drive_backend import GoogleDriveBackend
from .local_settings import get_local_settings
from utils.logging import debug_print, error_print, info_print, trace_print


class SyncConfiguration:
    """
    Configuration manager for database sync strategies.
    Handles migration from legacy settings to new unified config.
    """
    
    def __init__(self):
        self.settings = get_local_settings()
        self._migrate_legacy_settings()
    
    def _migrate_legacy_settings(self) -> None:
        """Migrate legacy settings to new unified configuration"""
        try:
            # Check if migration is needed
            database_type = self.settings.get('database_type', 'local')
            google_drive_enabled = self.settings.get('google_drive_enabled', False)
            sync_strategy = self.settings.get('sync_strategy')
            
            # If new settings already exist, no migration needed
            if sync_strategy and sync_strategy != 'local_only':
                debug_print("New sync configuration already exists")
                return
            
            # Migrate legacy settings
            migrated = False
            
            if database_type == 'google_drive' or google_drive_enabled:
                # Check if Google Drive credentials actually exist before migrating
                credentials_path = self.settings.get('google_credentials_path', 'credentials.json')
                
                if Path(credentials_path).exists():
                    # Legacy Google Drive configuration with valid credentials
                    info_print("Migrating legacy Google Drive configuration")
                    self.settings.set('sync_strategy', 'leader_election')
                    
                    coordination_config = self.settings.get('coordination_backend', {})
                    coordination_config['type'] = 'google_drive'
                    
                    google_config = coordination_config.get('google_drive', {})
                    google_config['credentials_path'] = credentials_path
                    google_config['folder_name'] = self.settings.get('google_drive_folder', 'TimeTracking')
                    
                    coordination_config['google_drive'] = google_config
                    self.settings.set('coordination_backend', coordination_config)
                    migrated = True
                else:
                    # Legacy Google Drive config but no credentials - disable it
                    info_print("Legacy Google Drive configuration found but no credentials - disabling")
                    self.settings.set('sync_strategy', 'local_only')
                    self.settings.set('google_drive_enabled', False)
                    migrated = True
                
            elif database_type == 'local':
                # Legacy local database - check if it should be shared
                database_local_path = self.settings.get('database_local_path')
                if database_local_path and not database_local_path.startswith(str(Path.home())):
                    # Path outside user directory might be shared
                    info_print("Migrating legacy shared database configuration")
                    self.settings.set('sync_strategy', 'leader_election')
                    
                    coordination_config = self.settings.get('coordination_backend', {})
                    coordination_config['type'] = 'local_file'
                    
                    local_config = coordination_config.get('local_file', {})
                    local_config['shared_db_path'] = database_local_path
                    
                    coordination_config['local_file'] = local_config
                    self.settings.set('coordination_backend', coordination_config)
                    migrated = True
            
            if migrated:
                info_print("Legacy settings migration completed")
            else:
                debug_print("No legacy settings migration needed")
                
        except Exception as e:
            error_print(f"Error migrating legacy settings: {e}")
    
    def get_sync_strategy(self) -> str:
        """Get the sync strategy: 'local_only' or 'leader_election'"""
        return self.settings.get('sync_strategy', 'local_only')
    
    def get_coordination_backend_config(self) -> Dict[str, Any]:
        """Get coordination backend configuration"""
        return self.settings.get('coordination_backend', {
            'type': 'local_file',
            'local_file': {
                'shared_db_path': str(Path.home() / '.config' / 'pomodora' / 'database' / 'pomodora.db')
            }
        })
    
    def get_local_cache_db_path(self) -> str:
        """Get local cache database path"""
        default_cache = str(Path.home() / '.config' / 'pomodora' / 'cache' / 'pomodora.db')
        return self.settings.get('local_cache_db_path', default_cache)
    
    def create_coordination_backend(self) -> Optional[CoordinationBackend]:
        """Create appropriate coordination backend based on configuration"""
        try:
            strategy = self.get_sync_strategy()
            debug_print(f"Creating coordination backend for strategy: {strategy}")
            
            if strategy == 'local_only':
                debug_print("Using local-only sync strategy (no coordination backend)")
                return None
            
            if strategy != 'leader_election':
                error_print(f"Unknown sync strategy: {strategy}")
                return None
            
            backend_config = self.get_coordination_backend_config()
            backend_type = backend_config.get('type', 'local_file')
            debug_print(f"Backend type: {backend_type}")
            
            if backend_type == 'local_file':
                local_config = backend_config.get('local_file', {})
                shared_db_path = local_config.get('shared_db_path')
                
                if not shared_db_path:
                    error_print("Missing shared_db_path for local_file backend")
                    return None
                
                debug_print(f"Creating LocalFileBackend: {shared_db_path}")
                return LocalFileBackend(shared_db_path)
                
            elif backend_type == 'google_drive':
                google_config = backend_config.get('google_drive', {})
                credentials_path = google_config.get('credentials_path', 'credentials.json')
                folder_name = google_config.get('folder_name', 'TimeTracking')
                
                debug_print(f"Creating GoogleDriveBackend: folder={folder_name}, credentials={credentials_path}")
                backend = GoogleDriveBackend(credentials_path, folder_name)
                
                # Check if it's available
                if not backend.is_available():
                    error_print(f"GoogleDriveBackend not available - credentials or connectivity issue")
                    return None
                
                return backend
                
            else:
                error_print(f"Unknown coordination backend type: {backend_type}")
                return None
                
        except Exception as e:
            error_print(f"Error creating coordination backend: {e}")
            return None
    
    def get_database_path_for_strategy(self) -> Tuple[str, bool]:
        """
        Get database path and whether it needs coordination backend.
        Returns (db_path, needs_coordination)
        """
        strategy = self.get_sync_strategy()
        
        if strategy == 'local_only':
            # Legacy local database path
            config_dir = Path.home() / '.config' / 'pomodora'
            default_local = str(config_dir / 'database' / 'pomodora.db')
            db_path = self.settings.get('database_local_path', default_local)
            return db_path, False
            
        elif strategy == 'leader_election':
            # Use local cache database
            cache_path = self.get_local_cache_db_path()
            return cache_path, True
            
        else:
            error_print(f"Unknown sync strategy: {strategy}")
            # Fallback to local
            config_dir = Path.home() / '.config' / 'pomodora'
            return str(config_dir / 'database' / 'pomodora.db'), False
    
    def set_sync_strategy(self, strategy: str) -> None:
        """Set sync strategy"""
        if strategy not in ['local_only', 'leader_election']:
            raise ValueError(f"Invalid sync strategy: {strategy}")
        
        self.settings.set('sync_strategy', strategy)
        info_print(f"Sync strategy set to: {strategy}")
    
    def set_local_file_backend(self, shared_db_path: str) -> None:
        """Configure local file coordination backend"""
        self.set_sync_strategy('leader_election')
        
        coordination_config = self.settings.get('coordination_backend', {})
        coordination_config['type'] = 'local_file'
        coordination_config['local_file'] = {
            'shared_db_path': shared_db_path
        }
        
        self.settings.set('coordination_backend', coordination_config)
        info_print(f"Configured local file backend: {shared_db_path}")
    
    def set_google_drive_backend(self, credentials_path: str, folder_name: str) -> None:
        """Configure Google Drive coordination backend"""
        self.set_sync_strategy('leader_election')
        
        coordination_config = self.settings.get('coordination_backend', {})
        coordination_config['type'] = 'google_drive'
        coordination_config['google_drive'] = {
            'credentials_path': credentials_path,
            'folder_name': folder_name
        }
        
        self.settings.set('coordination_backend', coordination_config)
        info_print(f"Configured Google Drive backend: {folder_name}")
    
    def disable_sync(self) -> None:
        """Disable sync and use local-only mode"""
        self.set_sync_strategy('local_only')
        info_print("Sync disabled - using local-only mode")
    
    def get_sync_status(self) -> Dict[str, Any]:
        """Get current sync configuration status"""
        strategy = self.get_sync_strategy()
        
        status = {
            'sync_strategy': strategy,
            'local_cache_db_path': self.get_local_cache_db_path()
        }
        
        if strategy == 'leader_election':
            backend_config = self.get_coordination_backend_config()
            status['coordination_backend'] = backend_config
            
            # Test if backend can be created
            backend = self.create_coordination_backend()
            status['backend_available'] = backend is not None
            if backend:
                status['backend_status'] = backend.is_available()
            
        db_path, needs_coordination = self.get_database_path_for_strategy()
        status['database_path'] = db_path
        status['needs_coordination'] = needs_coordination
        
        return status
    
    def validate_configuration(self) -> Tuple[bool, Optional[str]]:
        """
        Validate current sync configuration.
        Returns (is_valid, error_message)
        """
        try:
            strategy = self.get_sync_strategy()
            
            if strategy == 'local_only':
                db_path, _ = self.get_database_path_for_strategy()
                db_parent = Path(db_path).parent
                if not db_parent.exists():
                    try:
                        db_parent.mkdir(parents=True)
                    except Exception as e:
                        return False, f"Cannot create database directory: {e}"
                return True, None
                
            elif strategy == 'leader_election':
                # Check cache directory
                cache_path = Path(self.get_local_cache_db_path())
                cache_parent = cache_path.parent
                if not cache_parent.exists():
                    try:
                        cache_parent.mkdir(parents=True)
                    except Exception as e:
                        return False, f"Cannot create cache directory: {e}"
                
                # Check coordination backend
                backend = self.create_coordination_backend()
                if not backend:
                    return False, "Cannot create coordination backend"
                
                if not backend.is_available():
                    return False, "Coordination backend is not available"
                
                return True, None
                
            else:
                return False, f"Unknown sync strategy: {strategy}"
                
        except Exception as e:
            return False, f"Configuration validation error: {e}"