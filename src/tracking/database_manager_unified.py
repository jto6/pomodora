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
                debug_print(f"Creating coordination backend for strategy: {self.sync_strategy}")
                self.coordination_backend = self.sync_config.create_coordination_backend()
                if self.coordination_backend:
                    debug_print(f"Coordination backend created: {type(self.coordination_backend).__name__}")
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
        
        # Perform scheduled backups on startup
        self._perform_startup_backups()
        
        # Perform initial sync if using leader election
        if self.sync_manager:
            self._perform_initial_sync()
    
    def _initialize_database_engine(self) -> None:
        """Initialize SQLite database engine with optimal settings"""
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
        
        # Configure SQLite settings based on sync strategy
        with self.engine.connect() as conn:
            if self.sync_strategy == 'leader_election':
                # Leader election ensures single writer - use DELETE journal mode
                conn.execute(text("PRAGMA journal_mode=DELETE"))
                debug_print("Database engine initialized with DELETE journal mode (leader election)")
            else:
                # Local-only might have multiple threads - use WAL mode
                conn.execute(text("PRAGMA journal_mode=WAL"))
                debug_print("Database engine initialized with WAL mode (local-only)")
            
            # Set reasonable timeout for lock contention
            conn.execute(text("PRAGMA busy_timeout=30000"))  # 30 seconds
            # Enable foreign key constraints
            conn.execute(text("PRAGMA foreign_keys=ON"))
            conn.commit()
        
        # Create session factory
        self.Session = sessionmaker(bind=self.engine)
        self.session = None
    
    def _initialize_backup_manager(self) -> None:
        """Initialize backup manager based on sync strategy"""
        if self.sync_strategy == 'leader_election':
            # For leader election, backup the shared database location
            if self.coordination_backend and hasattr(self.coordination_backend, 'shared_db_path'):
                # Local file backend - backup shared database
                shared_path = Path(self.coordination_backend.shared_db_path)
                backup_base_dir = shared_path.parent
                self.backup_manager = DatabaseBackupManager(str(shared_path), str(backup_base_dir))
            else:
                # Google Drive backend - use dedicated google_drive_backups directory
                config_dir = Path.home() / '.config' / 'pomodora'
                backup_base_dir = config_dir / 'google_drive_backups'
                backup_base_dir.mkdir(parents=True, exist_ok=True)
                self.backup_manager = DatabaseBackupManager(str(self.db_path), str(backup_base_dir))
        else:
            # Local only - backup local database
            backup_base_dir = self.db_path.parent
            self.backup_manager = DatabaseBackupManager(str(self.db_path), str(backup_base_dir))
        
        debug_print(f"Backup manager initialized: {self.backup_manager.backup_dir}")
    
    def _initialize_default_data(self) -> None:
        """Initialize default projects and categories if database is empty"""
        try:
            session = self.get_session()
            try:
                # Check if we have any projects
                project_count = session.query(Project).count()
                category_count = session.query(TaskCategory).count()
                
                if project_count == 0 and category_count == 0:
                    info_print("Initializing default projects and categories for empty database")
                    self.initialize_default_projects()
                    self.backup_manager.create_backup('daily')
                else:
                    debug_print(f"Database has {project_count} projects and {category_count} categories - skipping defaults")
                    
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
    
    def _perform_startup_backups(self) -> None:
        """Perform scheduled backups on application startup"""
        try:
            info_print("Checking for scheduled backups on startup")
            self.backup_manager.perform_scheduled_backups()
        except Exception as e:
            error_print(f"Startup backup failed: {e}")
    
    def get_session(self):
        """Get a database session"""
        return self.Session()
    
    def initialize_default_projects(self):
        """Initialize default projects and categories"""
        session = self.get_session()
        try:
            # Default task categories - only for completely empty databases
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
                    # Create task category directly (don't use create_task_category method 
                    # which auto-creates matching projects)
                    category = TaskCategory(name=cat_data["name"], color=cat_data["color"])
                    session.add(category)
                    debug_print(f"Added default category: {cat_data['name']}")
            
            # Default projects - only "None" as default
            default_projects = [
                {"name": "None", "color": "#3498db"}
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
    
    def cleanup_stale_coordination_files(self, max_age_hours: int = 1) -> None:
        """Clean up stale coordination files"""
        if self.sync_manager:
            self.sync_manager.cleanup_stale_coordination_files(max_age_hours)
    
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
    
    # GUI compatibility methods - delegate to session-based operations
    
    def get_all_task_categories(self):
        """Get all task categories (active and inactive)"""
        session = self.get_session()
        try:
            task_categories_query = session.query(TaskCategory).all()
            # Convert to dictionaries to avoid session detachment issues
            task_categories = []
            for task_category in task_categories_query:
                task_categories.append({
                    'id': task_category.id,
                    'name': task_category.name,
                    'color': task_category.color,
                    'active': task_category.active,
                    'created_at': task_category.created_at
                })
            return task_categories
        finally:
            session.close()
    
    def get_all_projects(self):
        """Get all projects (active and inactive)"""
        session = self.get_session()
        try:
            projects_query = session.query(Project).all()
            # Convert to dictionaries to avoid session detachment issues
            projects = []
            for project in projects_query:
                projects.append({
                    'id': project.id,
                    'name': project.name,
                    'color': project.color,
                    'active': project.active,
                    'created_at': project.created_at
                })
            return projects
        finally:
            session.close()
    
    def get_active_task_categories(self):
        """Get only active task categories"""
        session = self.get_session()
        try:
            task_categories_query = session.query(TaskCategory).filter(TaskCategory.active == True).all()
            # Convert to dictionaries to avoid session detachment issues
            task_categories = []
            for task_category in task_categories_query:
                task_categories.append({
                    'id': task_category.id,
                    'name': task_category.name,
                    'color': task_category.color,
                    'active': task_category.active,
                    'created_at': task_category.created_at
                })
            return task_categories
        finally:
            session.close()
    
    def get_active_projects(self):
        """Get only active projects"""
        session = self.get_session()
        try:
            projects_query = session.query(Project).filter(Project.active == True).all()
            # Convert to dictionaries to avoid session detachment issues
            projects = []
            for project in projects_query:
                projects.append({
                    'id': project.id,
                    'name': project.name,
                    'color': project.color,
                    'active': project.active,
                    'created_at': project.created_at
                })
            return projects
        finally:
            session.close()
    
    def get_project_by_id(self, project_id):
        """Get project by ID"""
        session = self.get_session()
        try:
            return session.query(Project).filter(Project.id == project_id).first()
        finally:
            session.close()
    
    def get_sprints_by_date(self, date):
        """Get sprints for a specific date"""
        session = self.get_session()
        try:
            from datetime import datetime, timedelta
            start_of_day = datetime.combine(date, datetime.min.time())
            end_of_day = start_of_day + timedelta(days=1)

            debug_print(f"Stats update: Looking for sprints between {start_of_day} and {end_of_day}")

            # Filter by date
            filtered_sprints = session.query(Sprint).filter(
                Sprint.start_time >= start_of_day,
                Sprint.start_time < end_of_day
            ).all()

            debug_print(f"Found {len(filtered_sprints)} sprints for {date}")
            return filtered_sprints
        finally:
            session.close()
    
    def has_local_changes(self):
        """Check if there are local changes that need to be synced"""
        if not self.sync_manager:
            return False
        # Check for local pending operations
        pending_ops = self.operation_tracker.get_pending_operations()
        return len(pending_ops) > 0
    
    def has_remote_changes(self):
        """Check if remote database has changed since last sync"""
        if not self.sync_manager:
            return False
        return self.sync_manager.is_sync_needed()
    
    def sync_if_changes_pending(self):
        """Sync if there are local changes OR remote database has changed"""
        if not self.sync_manager:
            debug_print("No sync manager - skipping sync")
            return True
        
        # Use the enhanced sync check that provides detailed metadata comparison
        sync_needed = self.sync_manager.is_sync_needed()
        
        if not sync_needed:
            debug_print("No local or remote changes - skipping sync")
            return True
            
        debug_print("Changes detected - starting sync...")
        return self.sync_manager.sync_database()
    
    def sync_with_progress(self, parent_widget=None) -> bool:
        """
        Perform database sync with progress dialog (for user-initiated syncs).
        """
        if not self.sync_manager:
            debug_print("No sync manager - manual sync not available")
            return True
            
        # Set up progress callback if we have a parent widget
        if parent_widget and hasattr(parent_widget, 'show_progress'):
            self.sync_manager.set_progress_callback(parent_widget.show_progress)
        
        return self.trigger_manual_sync()
    
    def add_sprint(self, sprint_or_project_id, task_category_id=None, task_description=None, 
                   start_time=None, planned_duration=None):
        """Add a sprint - supports both Sprint objects and individual parameters"""
        if isinstance(sprint_or_project_id, Sprint) or hasattr(sprint_or_project_id, 'project_id'):
            # Sprint object passed - save it directly without losing data
            sprint = sprint_or_project_id
            return self._add_sprint_object(sprint)
        elif isinstance(sprint_or_project_id, dict):
            # Dictionary passed
            return self._add_sprint_from_params(
                sprint_or_project_id['project_id'],
                sprint_or_project_id['task_category_id'],
                sprint_or_project_id['task_description'],
                sprint_or_project_id['start_time'],
                sprint_or_project_id['planned_duration']
            )
        else:
            # Individual parameters passed
            return self._add_sprint_from_params(
                sprint_or_project_id,  # project_id
                task_category_id,
                task_description,
                start_time,
                planned_duration
            )
    
    def _add_sprint_object(self, sprint: Sprint) -> Optional[Sprint]:
        """Add a complete Sprint object to database without losing any fields"""
        session = self.get_session()
        try:
            debug_print(f"Adding sprint object: {sprint.task_description}")
            debug_print(f"Sprint fields: start_time={sprint.start_time}, end_time={sprint.end_time}, completed={sprint.completed}, duration_minutes={sprint.duration_minutes}")
            
            # Add the complete sprint object to session
            session.add(sprint)
            session.commit()
            session.refresh(sprint)
            
            # Track operation for sync - include ALL fields
            self.operation_tracker.track_operation('insert', 'sprints', {
                'id': sprint.id,
                'project_id': sprint.project_id,
                'task_category_id': sprint.task_category_id,
                'task_description': sprint.task_description,
                'start_time': sprint.start_time.isoformat() if sprint.start_time else None,
                'end_time': sprint.end_time.isoformat() if sprint.end_time else None,
                'duration_minutes': sprint.duration_minutes,
                'planned_duration': sprint.planned_duration,
                'completed': sprint.completed,
                'interrupted': sprint.interrupted
            })
            
            debug_print(f"Added sprint object successfully: {sprint.task_description}")
            return sprint
            
        except Exception as e:
            session.rollback()
            error_print(f"Failed to add sprint object: {e}")
            return None
        finally:
            session.close()
    
    def _add_sprint_from_params(self, project_id: int, task_category_id: int, task_description: str, 
                               start_time: datetime, planned_duration: int) -> Optional[Sprint]:
        """Internal method to add sprint from individual parameters"""
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

    def toggle_project_active(self, project_id):
        """Toggle project active status"""
        session = self.get_session()
        try:
            project = session.query(Project).filter(Project.id == project_id).first()
            if project:
                old_active = project.active
                project.active = not project.active
                session.commit()
                
                # Track operation for sync
                self.operation_tracker.track_operation('update', 'projects', {
                    'id': project_id,
                    'active': project.active,
                    'name': project.name,
                    'color': project.color
                })
                
                debug_print(f"Toggled project {project.name} active status to: {project.active}")
                return project.active
            return None
        except Exception as e:
            session.rollback()
            error_print(f"Failed to toggle project active status: {e}")
            return None
        finally:
            session.close()

    def toggle_task_category_active(self, category_id):
        """Toggle task category active status"""
        session = self.get_session()
        try:
            category = session.query(TaskCategory).filter(TaskCategory.id == category_id).first()
            if category:
                old_active = category.active
                category.active = not category.active
                session.commit()
                
                # Track operation for sync
                self.operation_tracker.track_operation('update', 'task_categories', {
                    'id': category_id,
                    'active': category.active,
                    'name': category.name,
                    'color': category.color
                })
                
                debug_print(f"Toggled category {category.name} active status to: {category.active}")
                return category.active
            return None
        except Exception as e:
            session.rollback()
            error_print(f"Failed to toggle category active status: {e}")
            return None
        finally:
            session.close()

    def delete_project(self, project_id):
        """Delete a project if it has no associated sprints"""
        session = self.get_session()
        try:
            project = session.query(Project).filter(Project.id == project_id).first()
            if not project:
                return False, "Project not found"

            # Check for associated sprints
            sprint_count = session.query(Sprint).filter(Sprint.project_id == project_id).count()
            if sprint_count > 0:
                return False, f"Cannot delete project '{project.name}' - it has {sprint_count} associated sprints"

            project_name = project.name
            project_data = {
                'id': project_id,
                'name': project.name,
                'color': project.color,
                'active': project.active
            }
            session.delete(project)
            session.commit()
            
            # Track operation for sync
            self.operation_tracker.track_operation('delete', 'projects', project_data)
            
            debug_print(f"Deleted project: {project_name}")
            return True, f"Project '{project_name}' deleted successfully"
            
        except Exception as e:
            session.rollback()
            error_print(f"Failed to delete project: {e}")
            return False, f"Failed to delete project: {e}"
        finally:
            session.close()

    def delete_task_category(self, category_id):
        """Delete a task category if it has no associated sprints"""
        session = self.get_session()
        try:
            category = session.query(TaskCategory).filter(TaskCategory.id == category_id).first()
            if not category:
                return False, "Task category not found"

            # Check for associated sprints
            sprint_count = session.query(Sprint).filter(Sprint.task_category_id == category_id).count()
            if sprint_count > 0:
                return False, f"Cannot delete category '{category.name}' - it has {sprint_count} associated sprints"

            category_name = category.name
            category_data = {
                'id': category_id,
                'name': category.name,
                'color': category.color,
                'active': category.active
            }
            session.delete(category)
            session.commit()
            
            # Track operation for sync
            self.operation_tracker.track_operation('delete', 'task_categories', category_data)
            
            debug_print(f"Deleted task category: {category_name}")
            return True, f"Task category '{category_name}' deleted successfully"
            
        except Exception as e:
            session.rollback()
            error_print(f"Failed to delete task category: {e}")
            return False, f"Failed to delete task category: {e}"
        finally:
            session.close()

    def delete_sprint(self, sprint_id):
        """Delete a sprint by ID"""
        session = self.get_session()
        try:
            sprint = session.query(Sprint).filter(Sprint.id == sprint_id).first()
            if not sprint:
                return False, "Sprint not found"

            # Capture sprint data for operation tracking
            sprint_data = {
                'id': sprint_id,
                'project_id': sprint.project_id,
                'task_category_id': sprint.task_category_id,
                'task_description': sprint.task_description,
                'start_time': sprint.start_time.isoformat() if sprint.start_time else None,
                'planned_duration': sprint.planned_duration
            }
            
            session.delete(sprint)
            session.commit()
            
            # Track operation for sync
            self.operation_tracker.track_operation('delete', 'sprints', sprint_data)
            
            debug_print(f"Deleted sprint: {sprint.task_description} (ID: {sprint_id})")
            return True, f"Sprint '{sprint.task_description}' deleted successfully"
            
        except Exception as e:
            session.rollback()
            error_print(f"Failed to delete sprint: {e}")
            return False, f"Failed to delete sprint: {e}"
        finally:
            session.close()

    def create_task_category(self, name, color):
        """Create a new task category"""
        session = self.get_session()
        try:
            # Check if category already exists
            existing = session.query(TaskCategory).filter(TaskCategory.name == name).first()
            if existing:
                return False, f"Task category '{name}' already exists"

            category = TaskCategory(name=name, color=color, active=True)
            session.add(category)
            session.commit()
            session.refresh(category)
            
            # Track operation for sync
            self.operation_tracker.track_operation('insert', 'task_categories', {
                'id': category.id,
                'name': name,
                'color': color,
                'active': True
            })
            
            debug_print(f"Created task category: {name} with color {color}")
            return True, f"Task category '{name}' created successfully"
            
        except Exception as e:
            session.rollback()
            error_print(f"Failed to create task category: {e}")
            return False, f"Failed to create task category: {e}"
        finally:
            session.close()

    def create_project(self, name, color):
        """Create a new project"""
        session = self.get_session()
        try:
            # Check if project already exists
            existing = session.query(Project).filter(Project.name == name).first()
            if existing:
                return False, f"Project '{name}' already exists"

            project = Project(name=name, color=color, active=True)
            session.add(project)
            session.commit()
            session.refresh(project)
            
            # Track operation for sync
            self.operation_tracker.track_operation('insert', 'projects', {
                'id': project.id,
                'name': name,
                'color': color,
                'active': True
            })
            
            debug_print(f"Created project: {name} with color {color}")
            return True, f"Project '{name}' created successfully"
            
        except Exception as e:
            session.rollback()
            error_print(f"Failed to create project: {e}")
            return False, f"Failed to create project: {e}"
        finally:
            session.close()


# Backward compatibility alias
DatabaseManager = UnifiedDatabaseManager