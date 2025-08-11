"""
Unified Database Manager using Leader Election Sync.
Replaces the old DatabaseManager with unified coordination backend support.
"""

import os
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from typing import Optional, Dict, Any, List
from datetime import datetime

from .models import Base, Project, TaskCategory, Sprint
from .sync_config import SyncConfiguration
from .leader_election_sync import LeaderElectionSyncManager, SyncScheduler
from .database_backup import DatabaseBackupManager
from .operation_log import OperationTracker
from utils.logging import verbose_print, error_print, info_print, debug_print, trace_print
from utils.progress_wrapper import with_progress, ProgressCapableMixin


class UnifiedDatabaseManager(ProgressCapableMixin):
    """
    Unified database manager that supports both local-only and leader election sync.
    Uses configuration-driven backend selection for coordination.
    """
    
    def __init__(self, db_path: Optional[str] = None, sync_config: Optional[SyncConfiguration] = None):
        """
        Initialize database manager with unified sync configuration.
        
        Args:
            db_path: Optional override for database path (for testing)
            sync_config: Optional sync configuration (uses default if None)
        """
        # Initialize configuration
        self.sync_config = sync_config if sync_config else SyncConfiguration()
        
        # Determine database path and sync strategy
        if db_path:
            # Override path provided (usually for testing)
            self.db_path = Path(db_path).resolve()
            self.sync_strategy = 'local_only'  # Override mode
            self.coordination_backend = None
            self.sync_manager = None
        else:
            # Use configuration
            config_db_path, needs_coordination = self.sync_config.get_database_path_for_strategy()
            self.db_path = Path(config_db_path).resolve()
            self.sync_strategy = self.sync_config.get_sync_strategy()
            
            if needs_coordination:
                self.coordination_backend = self.sync_config.create_coordination_backend()
                if self.coordination_backend:
                    self.sync_manager = LeaderElectionSyncManager(
                        self.coordination_backend, 
                        str(self.db_path)
                    )
                    self.sync_scheduler = SyncScheduler(self.sync_manager)
                else:
                    error_print("Failed to create coordination backend - falling back to local-only")
                    self.sync_strategy = 'local_only'
                    self.coordination_backend = None
                    self.sync_manager = None
            else:
                self.coordination_backend = None
                self.sync_manager = None
        
        info_print(f"Database initialized:")
        info_print(f"  Path: {self.db_path}")
        info_print(f"  Strategy: {self.sync_strategy}")
        if self.coordination_backend:
            info_print(f"  Backend: {type(self.coordination_backend).__name__}")
        
        # Ensure database directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize SQLite engine
        self._initialize_database_engine()
        
        # Initialize backup manager
        self._initialize_backup_manager()
        
        # Initialize operation tracking (for sync)
        if self.sync_manager:
            self.operation_tracker = self.sync_manager.operation_tracker
        else:
            self.operation_tracker = OperationTracker(str(self.db_path))
        
        # Initialize default data if needed
        self._initialize_default_data()
        
        # Perform initial sync if using leader election
        if self.sync_manager:
            self._perform_initial_sync()
    
    def _initialize_database_engine(self) -> None:
        """Initialize SQLite database engine with optimal settings"""
        # Use WAL mode for better concurrency
        connect_args = {
            'check_same_thread': False,  # Allow multi-threading
        }
        
        self.engine = create_engine(
            f'sqlite:///{self.db_path}',
            connect_args=connect_args,
            echo=False  # Set to True for SQL debugging
        )
        
        # Create tables
        Base.metadata.create_all(self.engine)
        
        # Configure SQLite for better concurrency
        with self.engine.connect() as conn:
            # Enable WAL mode for better concurrency
            conn.execute(text("PRAGMA journal_mode=WAL"))
            # Set reasonable timeout for lock contention
            conn.execute(text("PRAGMA busy_timeout=30000"))  # 30 seconds
            # Enable foreign key constraints
            conn.execute(text("PRAGMA foreign_keys=ON"))
            conn.commit()
        
        # Create session factory
        self.Session = sessionmaker(bind=self.engine)
        self.session = None
        
        debug_print("Database engine initialized with WAL mode")
    
    def _initialize_backup_manager(self) -> None:
        """Initialize backup manager based on sync strategy"""
        if self.sync_strategy == 'leader_election':
            # For leader election, backup the shared database location
            if self.coordination_backend and hasattr(self.coordination_backend, 'shared_db_path'):
                # Local file backend - backup shared database
                shared_path = Path(self.coordination_backend.shared_db_path)
                backup_base_dir = shared_path.parent / 'Backup'
                self.backup_manager = DatabaseBackupManager(str(shared_path), str(backup_base_dir))
            else:
                # Google Drive backend - backup local cache
                backup_base_dir = self.db_path.parent / 'Backup'
                self.backup_manager = DatabaseBackupManager(str(self.db_path), str(backup_base_dir))
        else:
            # Local only - backup local database
            backup_base_dir = self.db_path.parent / 'Backup'
            self.backup_manager = DatabaseBackupManager(str(self.db_path), str(backup_base_dir))
        
        debug_print(f"Backup manager initialized: {self.backup_manager.backup_base_dir}")
    
    def _initialize_default_data(self) -> None:
        """Initialize default projects and categories if database is empty"""
        try:
            session = self.get_session()
            try:
                # Check if we have any projects
                project_count = session.query(Project).count()
                category_count = session.query(TaskCategory).count()
                
                if project_count == 0 or category_count == 0:
                    info_print("Initializing default projects and categories")
                    self.initialize_default_projects()
                    self.backup_manager.create_backup_if_needed('daily')
                else:
                    debug_print(f"Database has {project_count} projects and {category_count} categories")
                    
            finally:
                session.close()
        except Exception as e:
            error_print(f"Error checking default data: {e}")
    
    def _perform_initial_sync(self) -> None:
        """Perform initial sync if using leader election strategy"""
        if not self.sync_manager:
            return
            
        try:
            info_print("Performing initial sync")
            self.sync_manager.sync_database(timeout_seconds=120)
        except Exception as e:
            error_print(f"Initial sync failed: {e}")
    
    def get_session(self):
        """Get a database session"""
        return self.Session()
    
    def initialize_default_projects(self):
        """Initialize default projects and categories"""
        session = self.get_session()
        try:
            # Default task categories
            default_categories = [
                {"name": "Development", "color": "#3498db"},
                {"name": "Testing", "color": "#2ecc71"},
                {"name": "Documentation", "color": "#f39c12"},
                {"name": "Planning", "color": "#9b59b6"},
                {"name": "Meeting", "color": "#e74c3c"},
                {"name": "Learning", "color": "#1abc9c"},
                {"name": "Bug Fix", "color": "#e67e22"},
                {"name": "Review", "color": "#34495e"}
            ]
            
            for cat_data in default_categories:
                existing = session.query(TaskCategory).filter(TaskCategory.name == cat_data["name"]).first()
                if not existing:
                    category = TaskCategory(name=cat_data["name"], color=cat_data["color"])
                    session.add(category)
                    debug_print(f"Added default category: {cat_data['name']}")
            
            # Default projects
            default_projects = [
                {"name": "General", "color": "#3498db"},
                {"name": "Personal", "color": "#2ecc71"},
                {"name": "Work", "color": "#f39c12"},
                {"name": "Learning", "color": "#9b59b6"}
            ]
            
            for proj_data in default_projects:
                existing = session.query(Project).filter(Project.name == proj_data["name"]).first()
                if not existing:
                    project = Project(name=proj_data["name"], color=proj_data["color"])
                    session.add(project)
                    debug_print(f"Added default project: {proj_data['name']}")
            
            session.commit()
            info_print("Default projects and categories initialized")
            
        except Exception as e:
            session.rollback()
            error_print(f"Failed to initialize default data: {e}")
            raise
        finally:
            session.close()
    
    def add_sprint(self, project_id: int, task_category_id: int, task_description: str, 
                   start_time: datetime, planned_duration: int) -> Optional[Sprint]:
        """Add a new sprint and track operation for sync"""
        session = self.get_session()
        try:
            sprint = Sprint(
                project_id=project_id,
                task_category_id=task_category_id,
                task_description=task_description,
                start_time=start_time,
                planned_duration=planned_duration
            )
            
            session.add(sprint)
            session.commit()
            session.refresh(sprint)
            
            # Track operation for sync
            self.operation_tracker.track_operation('insert', 'sprints', {
                'project_id': project_id,
                'task_category_id': task_category_id,
                'task_description': task_description,
                'start_time': start_time.isoformat(),
                'planned_duration': planned_duration
            })
            
            debug_print(f"Added sprint: {task_description}")
            return sprint
            
        except Exception as e:
            session.rollback()
            error_print(f"Failed to add sprint: {e}")
            return None
        finally:
            session.close()
    
    def complete_sprint(self, sprint_id: int, end_time: datetime, duration_minutes: int) -> bool:
        """Mark sprint as completed and track operation for sync"""
        session = self.get_session()
        try:
            sprint = session.query(Sprint).filter(Sprint.id == sprint_id).first()
            if not sprint:
                error_print(f"Sprint not found: {sprint_id}")
                return False
            
            sprint.completed = True
            sprint.end_time = end_time
            sprint.duration_minutes = duration_minutes
            
            session.commit()
            
            # Track operation for sync
            self.operation_tracker.track_operation('update', 'sprints', {
                'id': sprint_id,
                'completed': True,
                'end_time': end_time.isoformat(),
                'duration_minutes': duration_minutes
            })
            
            debug_print(f"Completed sprint: {sprint_id}")
            return True
            
        except Exception as e:
            session.rollback()
            error_print(f"Failed to complete sprint: {e}")
            return False
        finally:
            session.close()
    
    def trigger_manual_sync(self) -> bool:
        """Trigger manual sync (user clicked sync button)"""
        if not self.sync_manager:
            debug_print("No sync manager - manual sync not available")
            return True  # Not an error for local-only mode
        
        return self.sync_scheduler.trigger_manual_sync()
    
    def trigger_idle_sync(self) -> bool:
        """Trigger sync when application becomes idle"""
        if not self.sync_manager:
            return True  # Not an error for local-only mode
        
        return self.sync_scheduler.trigger_idle_sync()
    
    def trigger_shutdown_sync(self) -> bool:
        """Trigger sync when application is shutting down"""
        if not self.sync_manager:
            return True  # Not an error for local-only mode
        
        return self.sync_scheduler.trigger_shutdown_sync()
    
    def trigger_auto_sync(self) -> bool:
        """Trigger automatic sync based on time interval"""
        if not self.sync_manager:
            return True  # Not an error for local-only mode
        
        return self.sync_scheduler.trigger_auto_sync()
    
    def get_sync_status(self) -> Dict[str, Any]:
        """Get comprehensive sync status"""
        status = {
            'sync_strategy': self.sync_strategy,
            'database_path': str(self.db_path),
            'database_exists': self.db_path.exists(),
            'database_size': self.db_path.stat().st_size if self.db_path.exists() else 0
        }
        
        if self.sync_manager:
            status.update(self.sync_manager.get_sync_status())
        
        # Add database statistics
        try:
            session = self.get_session()
            try:
                status['database_stats'] = {
                    'projects': session.query(Project).count(),
                    'categories': session.query(TaskCategory).count(),
                    'sprints': session.query(Sprint).count(),
                    'completed_sprints': session.query(Sprint).filter(Sprint.completed == True).count()
                }
            finally:
                session.close()
        except Exception as e:
            status['database_stats_error'] = str(e)
        
        return status
    
    def cleanup_stale_coordination_files(self) -> None:
        """Clean up stale coordination files"""
        if self.sync_manager:
            self.sync_manager.cleanup_stale_coordination_files()
    
    def is_sync_needed(self) -> bool:
        """Check if sync is needed"""
        if not self.sync_manager:
            return False
        return self.sync_manager.is_sync_needed()
    
    def get_pending_operations_count(self) -> int:
        """Get count of pending sync operations"""
        if not self.sync_manager:
            return 0
        return self.sync_manager.get_pending_operations_count()


# Backward compatibility alias
DatabaseManager = UnifiedDatabaseManager