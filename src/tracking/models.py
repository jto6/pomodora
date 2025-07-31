from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text, ForeignKey, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os
from utils.logging import verbose_print, error_print, info_print, debug_print, trace_print
from .database_backup import DatabaseBackupManager
from .operation_log import OperationTracker, DatabaseMerger

Base = declarative_base()

class TaskCategory(Base):
    __tablename__ = 'task_categories'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    color = Column(String(7), default='#3498db')  # Hex color code
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship to sprints
    sprints = relationship("Sprint", back_populates="task_category")

class Project(Base):
    __tablename__ = 'projects'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    color = Column(String(7), default='#3498db')  # Hex color code
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship to sprints
    sprints = relationship("Sprint", back_populates="project")

class Sprint(Base):
    __tablename__ = 'sprints'
    
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey('projects.id'), nullable=False)
    task_category_id = Column(Integer, ForeignKey('task_categories.id'), nullable=False)
    task_description = Column(Text, nullable=False)
    start_time = Column(DateTime, nullable=False)  # When the sprint actually started
    end_time = Column(DateTime)  # When the sprint ended (if completed)
    duration_minutes = Column(Integer)  # Actual duration in minutes
    planned_duration = Column(Integer, default=25)  # Planned duration
    completed = Column(Boolean, default=False)
    interrupted = Column(Boolean, default=False)
    
    # Relationships to access project and task category objects
    project = relationship("Project", back_populates="sprints")
    task_category = relationship("TaskCategory", back_populates="sprints")
    
    # Compatibility properties for backward compatibility with old code
    @property
    def project_name(self):
        """Get project name via relationship for backward compatibility"""
        return self.project.name if self.project else None
    
    @property
    def task_category_name(self):
        """Get task category name via relationship for backward compatibility"""
        return self.task_category.name if self.task_category else None

# Settings are now stored locally in ~/.config/pomodora/local_settings.json
# The database only contains task_categories, projects, and sprints for sharing between desktops

class DatabaseManager:
    def __init__(self, db_path=None):
        if db_path is None:
            # Create database in the same directory as this script
            script_dir = os.path.dirname(os.path.abspath(__file__))
            # Go up one level to src directory
            src_dir = os.path.dirname(script_dir)
            db_path = os.path.join(src_dir, "pomodora.db")
            
        self.db_path = os.path.abspath(db_path)
        info_print(f"Database location: {self.db_path}")
        
        
        self.engine = create_engine(f'sqlite:///{self.db_path}')
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.session = None  # Reusable session property
        
        # Background sync tracking
        self._background_sync_threads = []
        
        # Database backup manager - use actual storage location, not cache
        backup_db_path, backup_base_dir = self._get_backup_storage_location()
        self.backup_manager = DatabaseBackupManager(backup_db_path, backup_base_dir)
        
        # Operation tracking for proper merge synchronization
        self.operation_tracker = OperationTracker(self.db_path)
        
        # Flag to prevent sync during initialization
        self._initializing = True
        
        # Google Drive integration
        self.google_drive_manager = None
        
        # Store local sprint count before any sync operations
        local_sprint_count = 0
        try:
            temp_session = self.Session()
            local_sprint_count = temp_session.query(Sprint).count()
            temp_session.close()
            debug_print(f"Local database has {local_sprint_count} sprints before sync")
        except:
            debug_print("Could not count local sprints (table might not exist yet)")
        
        self._initialize_google_drive_sync()  # Changed to synchronous
        
        # Check if we lost any local sprints and warn user
        try:
            temp_session = self.Session()
            new_sprint_count = temp_session.query(Sprint).count()
            temp_session.close()
            if new_sprint_count < local_sprint_count:
                error_print(f"⚠️  WARNING: Lost {local_sprint_count - new_sprint_count} sprints during sync!")
                error_print("Local changes were overwritten by older remote database")
            elif new_sprint_count > local_sprint_count:
                info_print(f"✓ Gained {new_sprint_count - local_sprint_count} sprints from remote database")
        except:
            pass
        
        # Initialization complete
        self._initializing = False
        
        # Perform initial backup after initialization
        self._perform_backup_if_needed()
    
    
    def _get_backup_storage_location(self) -> tuple[str, str]:
        """Get the actual storage location for backups (not cache)
        
        Returns:
            Tuple of (db_path_for_backup, backup_base_directory)
        """
        try:
            from .local_settings import get_local_settings
            settings = get_local_settings()
            db_type = settings.get('database_type', 'local')
            
            if db_type == 'local':
                # For local storage, use the configured local path
                local_path = settings.get('database_local_path', '')
                if local_path:
                    from pathlib import Path
                    local_path = Path(local_path)
                    if local_path.is_dir():
                        # If it's a directory, add the database filename
                        db_path = str(local_path / 'pomodora.db')
                        backup_base = str(local_path)
                    else:
                        # It's already a full path to the database file
                        db_path = str(local_path)
                        backup_base = str(local_path.parent)
                else:
                    # Use default local path
                    from pathlib import Path
                    config_dir = Path.home() / '.config' / 'pomodora'
                    db_dir = config_dir / 'database'
                    db_path = str(db_dir / 'pomodora.db')
                    backup_base = str(db_dir)
                
                info_print(f"Local backup location: {backup_base}/Backup/")
                return db_path, backup_base
            else:
                # For Google Drive mode, backups go to a local directory
                # but represent the Google Drive database
                from pathlib import Path
                config_dir = Path.home() / '.config' / 'pomodora'
                backup_base = config_dir / 'google_drive_backups'
                backup_base.mkdir(parents=True, exist_ok=True)
                
                # Use the cache database for creating backups, but store them 
                # in the google_drive_backups directory
                db_path = self.db_path  # The cache database
                
                info_print(f"Google Drive backup location: {backup_base}/Backup/")
                return str(db_path), str(backup_base)
                
        except Exception as e:
            error_print(f"Error determining backup location, using cache: {e}")
            # Fallback to cache location
            return self.db_path, str(Path(self.db_path).parent)
    
    def _initialize_google_drive_sync(self):
        """Initialize Google Drive integration synchronously to ensure database is loaded before defaults"""
        try:
            self._initialize_google_drive()
            # Clean up any orphaned lock files from previous sessions
            if self.google_drive_manager and self.google_drive_manager.is_enabled():
                self._cleanup_orphaned_locks()
        except Exception as e:
            error_print(f"Google Drive initialization failed: {e}")
            # Continue without Google Drive if it fails
    
    def _initialize_google_drive(self):
        """Initialize Google Drive integration if enabled"""
        try:
            from .google_drive import GoogleDriveManager
            from .local_settings import get_local_settings
            
            # Check local settings for Google Drive enablement
            settings = get_local_settings()
            google_drive_enabled = settings.get("google_drive_enabled", False)
            
            if google_drive_enabled:
                # Get credentials path and folder name from settings
                credentials_path = settings.get("google_credentials_path", "credentials.json")
                drive_folder = settings.get("google_drive_folder", "Pomodora Data")
                
                # Initialize Google Drive manager with custom credentials path and folder
                self.google_drive_manager = GoogleDriveManager(self.db_path)
                self.google_drive_manager.drive_sync.credentials_path = credentials_path
                self.google_drive_manager.folder_name = drive_folder
                
                if not self.google_drive_manager.initialize():
                    error_print("Warning: Google Drive initialization failed")
                    self.google_drive_manager = None
        except Exception as e:
            print(f"Google Drive integration not available: {e}")
    
    def get_session(self):
        # Auto-sync before database operations if Google Drive is enabled (but not during initialization)
        if (not self._initializing and 
            self.google_drive_manager and 
            self.google_drive_manager.is_enabled()):
            self.google_drive_manager.auto_sync()
            # Ensure all tables exist after sync
            Base.metadata.create_all(self.engine)
        
        return self.Session()
    
    def _sync_after_commit(self):
        """Trigger non-blocking sync to Google Drive after database commits"""
        if self.google_drive_manager and self.google_drive_manager.is_enabled():
            # Clean up finished threads first
            self._cleanup_finished_sync_threads()
            
            # Start background sync to avoid blocking UI
            import threading
            import time
            
            def background_sync():
                try:
                    debug_print("Starting background sync to Google Drive...")
                    start_time = time.time()
                    
                    success = self._leader_election_sync()
                    
                    elapsed = time.time() - start_time
                    if success:
                        info_print(f"Database changes synced to Google Drive ({elapsed:.1f}s)")
                    else:
                        error_print(f"Failed to sync database changes to Google Drive ({elapsed:.1f}s)")
                        
                except Exception as e:
                    elapsed = time.time() - start_time if 'start_time' in locals() else 0
                    error_print(f"Error syncing to Google Drive ({elapsed:.1f}s): {e}")
                finally:
                    # Remove this thread from tracking list
                    try:
                        self._background_sync_threads.remove(threading.current_thread())
                    except ValueError:
                        pass  # Thread might have been cleaned up already
            
            # Run sync in background thread (daemon so it doesn't prevent app exit)
            sync_thread = threading.Thread(target=background_sync, daemon=True, name="GoogleDriveSync")
            self._background_sync_threads.append(sync_thread)
            sync_thread.start()
            debug_print(f"Background sync thread started (active threads: {len(self._background_sync_threads)})")
    
    def _cleanup_finished_sync_threads(self):
        """Remove finished sync threads from tracking list"""
        self._background_sync_threads = [t for t in self._background_sync_threads if t.is_alive()]
    
    def wait_for_pending_syncs(self, timeout=10.0):
        """Wait for pending background syncs to complete (with timeout)"""
        if not self._background_sync_threads:
            return True
            
        info_print(f"Waiting for {len(self._background_sync_threads)} background sync(s) to complete...")
        
        import time
        start_time = time.time()
        
        while self._background_sync_threads and (time.time() - start_time) < timeout:
            # Clean up finished threads
            self._cleanup_finished_sync_threads()
            
            if self._background_sync_threads:
                time.sleep(0.1)  # Small delay before checking again
        
        remaining = len(self._background_sync_threads)
        if remaining == 0:
            info_print("All background syncs completed")
            return True
        else:
            error_print(f"Timeout: {remaining} background sync(s) still running after {timeout}s")
            return False
    
    def sync_to_cloud(self) -> bool:
        """Manually trigger cloud sync"""
        if self.google_drive_manager and self.google_drive_manager.is_enabled():
            return self._leader_election_sync()
        return False
    
    def enable_google_drive_sync(self) -> bool:
        """Enable Google Drive synchronization"""
        try:
            from .google_drive import GoogleDriveManager
            from .local_settings import get_local_settings
            
            self.google_drive_manager = GoogleDriveManager(self.db_path)
            
            if self.google_drive_manager.initialize():
                # Update local settings
                settings = get_local_settings()
                settings.set("google_drive_enabled", True)
                return True
        except Exception as e:
            error_print(f"Failed to enable Google Drive sync: {e}")
        
        return False
    
    def disable_google_drive_sync(self):
        """Disable Google Drive synchronization"""
        self.google_drive_manager = None
        from .local_settings import get_local_settings
        settings = get_local_settings()
        settings.set("google_drive_enabled", False)
    
    def get_google_drive_status(self):
        """Get Google Drive sync status"""
        if self.google_drive_manager:
            return self.google_drive_manager.get_status()
        return {'enabled': False}
    
    def initialize_default_projects(self):
        """Ensure default task categories and projects exist in the database"""
        session = self.get_session()
        try:
            default_task_categories = [
                ("Admin", "#e74c3c"),      # Red
                ("Comm", "#3498db"),       # Blue  
                ("Strategy", "#9b59b6"),   # Purple
                ("Research", "#1abc9c"),   # Teal
                ("SelfDev", "#2ecc71"),    # Green
            ]
            
            changes_made = False
            
            for name, color in default_task_categories:
                # Check if task category already exists
                existing_task_category = session.query(TaskCategory).filter(TaskCategory.name == name).first()
                
                if not existing_task_category:
                    # Create missing task category
                    debug_print(f"Creating default task category: {name}")
                    task_category = TaskCategory(name=name, color=color)
                    session.add(task_category)
                    changes_made = True
                
                # Check if corresponding project exists (independent of task category now)
                existing_project = session.query(Project).filter(Project.name == name).first()
                
                if not existing_project:
                    # Create missing project (no category_id needed anymore)
                    debug_print(f"Creating default project: {name}")
                    project = Project(name=name, color=color)
                    session.add(project)
                    changes_made = True
            
            if changes_made:
                session.commit()
                info_print("Default task categories and projects created/restored")
                
                # Sync changes to Google Drive if enabled
                self._sync_after_commit()
                
                # Create backup after adding defaults
                self._perform_backup_if_needed()
            else:
                debug_print("All default task categories and projects already exist")
                
        except Exception as e:
            error_print(f"Error initializing default projects: {e}")
            session.rollback()
        finally:
            session.close()
    
# Settings initialization removed - all settings are now stored locally
    
    # Task Category management methods
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
    
    def create_task_category(self, name, color="#3498db"):
        """Create a new task category and auto-create a project with the same name"""
        session = self.get_session()
        try:
            # Create task category
            task_category = TaskCategory(name=name, color=color)
            session.add(task_category)
            
            # Auto-create project with same name (no category_id needed anymore)
            project = Project(name=name, color=color)
            session.add(project)
            session.commit()
            
            # Log the insert operations for merge tracking
            if hasattr(self, 'operation_tracker') and not self._initializing:
                task_category_data = {
                    'id': task_category.id,
                    'name': task_category.name,
                    'color': task_category.color,
                    'active': task_category.active,
                    'created_at': task_category.created_at.isoformat() if task_category.created_at else None
                }
                self.operation_tracker.log_insert('task_categories', task_category.id, task_category_data)
                
                project_data = {
                    'id': project.id,
                    'name': project.name,
                    'color': project.color,
                    'active': project.active,
                    'created_at': project.created_at.isoformat() if project.created_at else None
                }
                self.operation_tracker.log_insert('projects', project.id, project_data)
            
            # Sync changes to Google Drive if enabled
            self._sync_after_commit()
            
            # Create backup after adding task category
            self._perform_backup_if_needed()
            
            # Return the task category ID instead of the object
            return task_category.id
        finally:
            session.close()
    
    def get_task_category_by_id(self, task_category_id):
        """Get task category by ID"""
        session = self.get_session()
        try:
            return session.query(TaskCategory).filter(TaskCategory.id == task_category_id).first()
        finally:
            session.close()
    
    def toggle_task_category_active(self, task_category_id):
        """Toggle the active status of a task category"""
        session = self.get_session()
        try:
            task_category = session.query(TaskCategory).filter(TaskCategory.id == task_category_id).first()
            if task_category:
                old_data = {
                    'id': task_category.id,
                    'name': task_category.name,
                    'color': task_category.color,
                    'active': task_category.active,
                    'created_at': task_category.created_at.isoformat() if task_category.created_at else None
                }
                
                task_category.active = not task_category.active
                session.commit()
                
                # Log the update operation for merge tracking
                if hasattr(self, 'operation_tracker') and not self._initializing:
                    new_data = {
                        'id': task_category.id,
                        'name': task_category.name,
                        'color': task_category.color,
                        'active': task_category.active,
                        'created_at': task_category.created_at.isoformat() if task_category.created_at else None
                    }
                    self.operation_tracker.log_update('task_categories', task_category.id, old_data, new_data)
                
                return task_category.active
            return None
        finally:
            session.close()
    
    def update_task_category(self, task_category_id, name=None, color=None, active=None):
        """Update task category properties"""
        session = self.get_session()
        try:
            task_category = session.query(TaskCategory).filter(TaskCategory.id == task_category_id).first()
            if task_category:
                old_data = {
                    'id': task_category.id,
                    'name': task_category.name,
                    'color': task_category.color,
                    'active': task_category.active,
                    'created_at': task_category.created_at.isoformat() if task_category.created_at else None
                }
                
                if name is not None:
                    task_category.name = name
                if color is not None:
                    task_category.color = color
                if active is not None:
                    task_category.active = active
                session.commit()
                
                # Log the update operation for merge tracking
                if hasattr(self, 'operation_tracker') and not self._initializing:
                    new_data = {
                        'id': task_category.id,
                        'name': task_category.name,
                        'color': task_category.color,
                        'active': task_category.active,
                        'created_at': task_category.created_at.isoformat() if task_category.created_at else None
                    }
                    self.operation_tracker.log_update('task_categories', task_category.id, old_data, new_data)
                
                return task_category
            return None
        finally:
            session.close()
    
    def delete_task_category(self, task_category_id):
        """Delete a task category (projects are now independent)"""
        session = self.get_session()
        try:
            task_category = session.query(TaskCategory).filter(TaskCategory.id == task_category_id).first()
            if task_category:
                # Check if any sprints use this task category
                sprint_count = session.query(Sprint).filter(Sprint.task_category_id == task_category_id).count()
                
                if sprint_count > 0:
                    return False, f"Cannot delete task category '{task_category.name}' - it has {sprint_count} sprint(s) using it."
                
                # Store data for logging before deletion
                task_category_data = {
                    'id': task_category.id,
                    'name': task_category.name,
                    'color': task_category.color,
                    'active': task_category.active,
                    'created_at': task_category.created_at.isoformat() if task_category.created_at else None
                }
                
                # Delete the task category (projects are independent now)
                session.delete(task_category)
                session.commit()
                
                # Log the delete operation for merge tracking
                if hasattr(self, 'operation_tracker') and not self._initializing:
                    self.operation_tracker.log_delete('task_categories', task_category_id, task_category_data)
                
                return True, f"Task category '{task_category_data['name']}' deleted successfully."
            return False, "Task category not found."
        except Exception as e:
            session.rollback()
            return False, f"Error deleting task category: {str(e)}"
        finally:
            session.close()

    # Project management methods
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
    
    def create_project(self, name, color="#3498db"):
        """Create a new project (no category relationship needed)"""
        session = self.get_session()
        try:
            project = Project(name=name, color=color)
            session.add(project)
            session.commit()
            
            # Log the insert operation for merge tracking
            if hasattr(self, 'operation_tracker') and not self._initializing:
                project_data = {
                    'id': project.id,
                    'name': project.name,
                    'color': project.color,
                    'active': project.active,
                    'created_at': project.created_at.isoformat() if project.created_at else None
                }
                self.operation_tracker.log_insert('projects', project.id, project_data)
            
            # Sync changes to Google Drive if enabled
            self._sync_after_commit()
            
            # Create backup after adding project
            self._perform_backup_if_needed()
            
            return project
        finally:
            session.close()
    
    def get_project_by_id(self, project_id):
        """Get project by ID"""
        session = self.get_session()
        try:
            return session.query(Project).filter(Project.id == project_id).first()
        finally:
            session.close()
    
    def toggle_project_active(self, project_id):
        """Toggle the active status of a project"""
        session = self.get_session()
        try:
            project = session.query(Project).filter(Project.id == project_id).first()
            if project:
                old_data = {
                    'id': project.id,
                    'name': project.name,
                    'color': project.color,
                    'active': project.active,
                    'created_at': project.created_at.isoformat() if project.created_at else None
                }
                
                project.active = not project.active
                session.commit()
                
                # Log the update operation for merge tracking
                if hasattr(self, 'operation_tracker') and not self._initializing:
                    new_data = {
                        'id': project.id,
                        'name': project.name,
                        'color': project.color,
                        'active': project.active,
                        'created_at': project.created_at.isoformat() if project.created_at else None
                    }
                    self.operation_tracker.log_update('projects', project.id, old_data, new_data)
                
                return project.active
            return None
        finally:
            session.close()
    
    def update_project(self, project_id, name=None, color=None, active=None):
        """Update project properties"""
        session = self.get_session()
        try:
            project = session.query(Project).filter(Project.id == project_id).first()
            if project:
                old_data = {
                    'id': project.id,
                    'name': project.name,
                    'color': project.color,
                    'active': project.active,
                    'created_at': project.created_at.isoformat() if project.created_at else None
                }
                
                if name is not None:
                    project.name = name
                if color is not None:
                    project.color = color
                if active is not None:
                    project.active = active
                session.commit()
                
                # Log the update operation for merge tracking
                if hasattr(self, 'operation_tracker') and not self._initializing:
                    new_data = {
                        'id': project.id,
                        'name': project.name,
                        'color': project.color,
                        'active': project.active,
                        'created_at': project.created_at.isoformat() if project.created_at else None
                    }
                    self.operation_tracker.log_update('projects', project.id, old_data, new_data)
                
                return project
            return None
        finally:
            session.close()
    
    def delete_project(self, project_id):
        """Delete a project"""
        session = self.get_session()
        try:
            project = session.query(Project).filter(Project.id == project_id).first()
            if project:
                # Check if project has any sprints
                sprint_count = session.query(Sprint).filter(Sprint.project_id == project.id).count()
                if sprint_count > 0:
                    return False, f"Cannot delete project '{project.name}' - it has {sprint_count} sprint(s) associated with it."
                
                # Store data for logging before deletion
                project_data = {
                    'id': project.id,
                    'name': project.name,
                    'color': project.color,
                    'active': project.active,
                    'created_at': project.created_at.isoformat() if project.created_at else None
                }
                
                session.delete(project)
                session.commit()
                
                # Log the delete operation for merge tracking
                if hasattr(self, 'operation_tracker') and not self._initializing:
                    self.operation_tracker.log_delete('projects', project_id, project_data)
                
                return True, f"Project '{project_data['name']}' deleted successfully."
            return False, "Project not found."
        except Exception as e:
            session.rollback()
            return False, f"Error deleting project: {str(e)}"
        finally:
            session.close()
    
    # Sprint management methods
    def add_sprint(self, sprint):
        """Add a new sprint to the database"""
        debug_print(f"add_sprint called with: {sprint.task_description}")
        debug_print(f"Sprint details before save: project_id={sprint.project_id}, task_category_id={sprint.task_category_id}, start={sprint.start_time}, end={sprint.end_time}")
        
        # Get session WITHOUT auto-sync to avoid overwriting local changes
        session = self.Session()
        try:
            debug_print("Adding sprint to session...")
            session.add(sprint)
            
            debug_print("Committing session...")
            session.commit()
            
            debug_print(f"✓ Sprint saved: {sprint.task_description} at {sprint.start_time}")
            debug_print(f"Sprint ID after commit: {sprint.id}")
            trace_print(f"Sprint details: ID={sprint.id}, Duration={sprint.duration_minutes}min, Project ID={sprint.project_id}, Task Category ID={sprint.task_category_id}")
            
            # Log the insert operation for merge tracking
            if hasattr(self, 'operation_tracker') and not self._initializing:
                sprint_data = {
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
                }
                self.operation_tracker.log_insert('sprints', sprint.id, sprint_data)
            
            # Check total sprint count after save
            total_sprints = session.query(Sprint).count()
            debug_print(f"Total sprints in database after save: {total_sprints}")
            
            # Verify it was saved
            saved_sprint = session.query(Sprint).filter(
                Sprint.task_description == sprint.task_description,
                Sprint.start_time == sprint.start_time
            ).first()
            if saved_sprint:
                debug_print(f"✓ Verification: Sprint found in database with ID {saved_sprint.id}")
            else:
                error_print("❌ WARNING: Sprint not found after save!")
                
            # Also check by ID if available
            if sprint.id:
                by_id = session.query(Sprint).filter(Sprint.id == sprint.id).first()
                if by_id:
                    debug_print(f"✓ Verification by ID: Sprint {sprint.id} found")
                else:
                    error_print(f"❌ WARNING: Sprint with ID {sprint.id} not found!")
                
        except Exception as e:
            error_print(f"❌ ERROR saving sprint: {e}")
            session.rollback()
            raise
        finally:
            session.close()
            
        # AFTER saving locally, sync to Google Drive
        self._sync_after_commit()
        
        # Create backup after adding sprint
        self._perform_backup_if_needed()
    
    def _leader_election_sync(self) -> bool:
        """Sync database using leader election and proper merge operations"""
        try:
            # Use leader election to determine who gets to sync
            if not self._acquire_database_sync_lock():
                debug_print("Another workstation is syncing, our changes are already saved locally")
                return True  # Our sprint is saved locally, sync will happen eventually
            
            try:
                debug_print("Won leader election, performing database sync...")
                
                # Check if we have any unsynced operations
                unsynced_ops = self.operation_tracker.get_unsynced_operations()
                if not unsynced_ops:
                    debug_print("No unsynced operations, sync not needed")
                    return True
                
                info_print(f"Found {len(unsynced_ops)} unsynced operations to merge")
                
                # Download current remote database to a temporary location
                import tempfile
                import shutil
                
                # Create temp file in system temp directory, not in Google Drive sync folder
                with tempfile.NamedTemporaryFile(suffix='.db', delete=False, prefix='pomodora_sync_') as tmp_file:
                    remote_db_path = tmp_file.name
                
                # Backup our local database
                local_backup_path = f"{self.db_path}.backup"
                shutil.copy2(self.db_path, local_backup_path)
                
                try:
                    # Download remote database to the temp location
                    if not self._download_remote_database(remote_db_path):
                        error_print("Failed to download remote database")
                        return False
                    
                    # Perform proper merge operation using existing operation tracker
                    merger = DatabaseMerger(self.db_path, remote_db_path, self.operation_tracker)
                    if not merger.merge_databases():
                        error_print("Failed to merge local operations into remote database")
                        # Restore local database backup
                        shutil.copy2(local_backup_path, self.db_path)
                        return False
                    
                    # Create a properly named copy for upload (Google Drive upload requires 'pomodora.db' name)
                    upload_db_path = f"{remote_db_path}.upload"  
                    shutil.copy2(remote_db_path, upload_db_path)
                    
                    # Rename to pomodora.db for upload
                    final_upload_path = os.path.join(os.path.dirname(upload_db_path), "pomodora.db")
                    shutil.move(upload_db_path, final_upload_path)
                    
                    # Upload the merged database to Google Drive
                    # (it doesn't have operation_log table, which should stay local-only)
                    if not self.google_drive_manager.drive_sync.upload_database(final_upload_path):
                        error_print("Failed to upload merged database to Google Drive")
                        return False
                    
                    # Clean up upload file
                    try:
                        os.unlink(final_upload_path)
                    except:
                        pass
                    
                    # Copy merged database back to local (will re-create operation_log on next access)
                    shutil.copy2(remote_db_path, self.db_path)
                    
                    # Recreate engine/session since database was replaced
                    self.engine = create_engine(f'sqlite:///{self.db_path}')
                    self.Session = sessionmaker(bind=self.engine)
                    
                    # Re-initialize operation tracker to recreate operation_log table locally
                    self.operation_tracker = OperationTracker(self.db_path)
                    
                    info_print(f"✓ Successfully merged and synced {len(unsynced_ops)} operations")
                    return True
                        
                finally:
                    # Cleanup temporary files
                    try:
                        os.unlink(remote_db_path)
                        os.unlink(local_backup_path)
                    except:
                        pass
                        
            finally:
                # Always release the sync lock
                self._release_database_sync_lock()
                
        except Exception as e:
            error_print(f"Leader election sync failed: {e}")
            return False
    
    def _download_remote_database(self, remote_db_path: str) -> bool:
        """Download remote database from Google Drive to specified path"""
        try:
            import os
            db_filename = os.path.basename(self.db_path)  # Get "pomodora.db"
            
            # Find the remote database file
            results = self.google_drive_manager.drive_sync.service.files().list(
                q=f"name='{db_filename}' and parents in '{self.google_drive_manager.drive_sync.folder_id}' and trashed=false",
                fields="files(id, name, modifiedTime)"
            ).execute()
            
            files = results.get('files', [])
            if not files:
                error_print(f"Database file not found in Google Drive: {db_filename}")
                return False
            
            # Download the remote database to our temp location
            file_id = files[0]['id']
            request = self.google_drive_manager.drive_sync.service.files().get_media(fileId=file_id)
            import io
            from googleapiclient.http import MediaIoBaseDownload
            
            file_io = io.BytesIO()
            downloader = MediaIoBaseDownload(file_io, request)
            
            done = False
            while done is False:
                status, done = downloader.next_chunk()
            
            # Write to temp file
            with open(remote_db_path, 'wb') as f:
                f.write(file_io.getvalue())
            
            debug_print(f"Downloaded remote database to: {remote_db_path}")
            return True
            
        except Exception as e:
            error_print(f"Failed to download remote database: {e}")
            return False
    
    def _merge_local_into_remote(self, local_db_path: str, remote_db_path: str) -> int:
        """Merge local sprints into remote database, return count of new sprints added"""
        try:
            # Connect to both databases
            local_engine = create_engine(f'sqlite:///{local_db_path}')
            remote_engine = create_engine(f'sqlite:///{remote_db_path}')
            
            # Ensure remote database has the proper schema
            Base.metadata.create_all(remote_engine)
            debug_print("Ensured remote database schema exists")
            
            LocalSession = sessionmaker(bind=local_engine)
            RemoteSession = sessionmaker(bind=remote_engine)
            
            local_session = LocalSession()
            remote_session = RemoteSession()
            
            try:
                # Get all data from both databases
                local_task_categories = local_session.query(TaskCategory).all()
                local_projects = local_session.query(Project).all()
                local_sprints = local_session.query(Sprint).all()
                
                remote_task_categories = remote_session.query(TaskCategory).all()
                remote_projects = remote_session.query(Project).all()
                remote_sprints = remote_session.query(Sprint).all()
                
                debug_print(f"Local DB has {len(local_task_categories)} task categories, {len(local_projects)} projects, {len(local_sprints)} sprints")
                debug_print(f"Remote DB has {len(remote_task_categories)} task categories, {len(remote_projects)} projects, {len(remote_sprints)} sprints")
                
                total_new_items = 0
                
                # Merge task categories
                remote_task_category_names = {tc.name for tc in remote_task_categories}
                new_task_categories = []
                for local_task_category in local_task_categories:
                    if local_task_category.name not in remote_task_category_names:
                        new_task_categories.append(local_task_category)
                
                debug_print(f"Found {len(new_task_categories)} new task categories to merge")
                for task_category in new_task_categories:
                    new_remote_task_category = TaskCategory(
                        name=task_category.name,
                        color=task_category.color,
                        active=task_category.active,
                        created_at=task_category.created_at
                    )
                    remote_session.add(new_remote_task_category)
                    debug_print(f"Added task category: {task_category.name}")
                total_new_items += len(new_task_categories)
                
                # Merge projects
                remote_project_names = {p.name for p in remote_projects}
                new_projects = []
                for local_project in local_projects:
                    if local_project.name not in remote_project_names:
                        new_projects.append(local_project)
                
                debug_print(f"Found {len(new_projects)} new projects to merge")
                for project in new_projects:
                    new_remote_project = Project(
                        name=project.name,
                        color=project.color,
                        active=project.active,
                        created_at=project.created_at
                    )
                    remote_session.add(new_remote_project)
                    debug_print(f"Added project: {project.name}")
                total_new_items += len(new_projects)
                
                # Merge sprints (now includes task_category_name)
                remote_sprint_keys = {(s.project_name, s.task_category_name or 'Research', s.task_description, s.start_time) for s in remote_sprints}
                new_sprints = []
                for local_sprint in local_sprints:
                    key = (local_sprint.project_name, local_sprint.task_category_name or 'Research', local_sprint.task_description, local_sprint.start_time)
                    if key not in remote_sprint_keys:
                        new_sprints.append(local_sprint)
                
                debug_print(f"Found {len(new_sprints)} new sprints to merge")
                for sprint in new_sprints:
                    new_remote_sprint = Sprint(
                        project_name=sprint.project_name,
                        task_category_name=sprint.task_category_name or 'Research',  # Handle None values
                        task_description=sprint.task_description,
                        start_time=sprint.start_time,
                        end_time=sprint.end_time,
                        completed=sprint.completed,
                        interrupted=sprint.interrupted,
                        duration_minutes=sprint.duration_minutes,
                        planned_duration=sprint.planned_duration
                    )
                    remote_session.add(new_remote_sprint)
                    debug_print(f"Added sprint: {sprint.task_description}")
                total_new_items += len(new_sprints)
                
                remote_session.commit()
                debug_print(f"Successfully merged {len(new_task_categories)} task categories, {len(new_projects)} projects, {len(new_sprints)} sprints into remote database")
                
                return total_new_items
                
            finally:
                local_session.close()
                remote_session.close()
                
        except Exception as e:
            error_print(f"Database merge failed: {e}")
            import traceback
            traceback.print_exc()
            return -1
    
    def _get_workstation_id(self) -> str:
        """Get unique identifier for this workstation"""
        import socket
        import hashlib
        hostname = socket.gethostname()
        return hashlib.md5(hostname.encode()).hexdigest()[:8]
    
    def _acquire_database_sync_lock(self) -> bool:
        """Acquire distributed lock for database sync using leader election algorithm"""
        try:
            import json
            import tempfile
            import time
            import random
            from datetime import timedelta
            
            workstation_id = self._get_workstation_id()
            current_time = datetime.now()
            
            # Phase 1: All workstations register their intent to sync
            intent_filename = f"sync_intent_{workstation_id}.json"
            intent_data = {
                'workstation_id': workstation_id,
                'timestamp': current_time.isoformat(),
                'random_priority': random.random()  # Tie-breaker
            }
            
            # Upload our intent file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp_file:
                json.dump(intent_data, tmp_file, indent=2)
                tmp_path = tmp_file.name
            
            success = self.google_drive_manager.drive_sync.upload_file(tmp_path, intent_filename)
            os.unlink(tmp_path)
            
            if not success:
                debug_print("Failed to register consolidation intent")
                return False
            
            debug_print(f"Registered sync intent with priority {intent_data['random_priority']:.6f}")
            
            # Phase 2: Wait for other workstations to register (small random delay)
            wait_time = random.uniform(2, 5)  # 2-5 seconds
            debug_print(f"Waiting {wait_time:.1f}s for other workstations...")
            time.sleep(wait_time)
            
            # Phase 3: Download all intent files and determine leader
            intent_files = self.google_drive_manager.drive_sync.list_files_by_pattern("sync_intent_*.json")
            
            all_intents = []
            for file_info in intent_files:
                intent_data = self.google_drive_manager.drive_sync.download_json_file_by_id(file_info['id'])
                if intent_data:
                    intent_time = datetime.fromisoformat(intent_data['timestamp'])
                    # Only consider recent intents (within last 30 seconds)
                    if (current_time - intent_time).total_seconds() < 30:
                        all_intents.append(intent_data)
            
            debug_print(f"Found {len(all_intents)} sync candidates")
            
            if not all_intents:
                debug_print("No valid sync intents found")
                self._cleanup_intent_file(intent_filename)
                return False
            
            # Phase 4: Leader election - earliest timestamp wins, random priority as tie-breaker
            leader = min(all_intents, key=lambda x: (x['timestamp'], -x['random_priority']))
            
            is_leader = leader['workstation_id'] == workstation_id
            
            debug_print(f"Leader election result: {leader['workstation_id']} (we are {'leader' if is_leader else 'follower'})")
            
            if is_leader:
                # We are the leader - create the actual lock file
                lock_data = {
                    'workstation_id': workstation_id,
                    'timestamp': current_time.isoformat(),
                    'action': 'database_sync',
                    'intent_timestamp': intent_data['timestamp']
                }
                
                lock_filename = "database_sync_lock.json"
                with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp_file:
                    json.dump(lock_data, tmp_file, indent=2)
                    tmp_path = tmp_file.name
                
                lock_success = self.google_drive_manager.drive_sync.upload_file(tmp_path, lock_filename)
                os.unlink(tmp_path)
                
                if lock_success:
                    debug_print("✓ Successfully acquired database sync lock as leader")
                    # Clean up our intent file
                    self._cleanup_intent_file(intent_filename)
                    return True
                else:
                    error_print("Failed to create lock file despite being leader")
                    self._cleanup_intent_file(intent_filename)
                    return False
            else:
                # We are not the leader - clean up and exit
                debug_print("Not selected as leader, backing off")
                self._cleanup_intent_file(intent_filename)
                return False
                
        except Exception as e:
            error_print(f"Lock acquisition failed: {e}")
            # Clean up on error
            try:
                self._cleanup_intent_file(f"sync_intent_{self._get_workstation_id()}.json")
            except:
                pass
            return False
    
    def _cleanup_intent_file(self, intent_filename: str):
        """Clean up our intent file"""
        try:
            self.google_drive_manager.drive_sync.delete_file_by_name(intent_filename)
            debug_print(f"Cleaned up intent file: {intent_filename}")
        except Exception as e:
            debug_print(f"Failed to clean up intent file: {e}")
            # Not critical - files will be ignored if too old
    
    def _release_database_sync_lock(self):
        """Release distributed sync lock"""
        try:
            lock_filename = "database_sync_lock.json"
            workstation_id = self._get_workstation_id()
            
            # Verify we own the lock before deleting
            existing_lock = self.google_drive_manager.drive_sync.download_json_file(lock_filename)
            if existing_lock and existing_lock.get('workstation_id') == workstation_id:
                self.google_drive_manager.drive_sync.delete_file_by_name(lock_filename)
                debug_print(f"✓ Released database sync lock for workstation {workstation_id}")
            
        except Exception as e:
            error_print(f"Lock release failed: {e}")
            # Not critical - lock will expire anyway
    
    def _cleanup_orphaned_locks(self):
        """Clean up any orphaned lock files from previous app sessions"""
        try:
            from datetime import datetime, timedelta
            
            # Check for main database sync lock
            lock_filename = "database_sync_lock.json"
            existing_lock = self.google_drive_manager.drive_sync.download_json_file(lock_filename)
            
            if existing_lock:
                lock_time = datetime.fromisoformat(existing_lock['timestamp'])
                # If lock is older than 10 minutes, consider it orphaned
                if (datetime.now() - lock_time).total_seconds() > 600:
                    debug_print(f"Cleaning up orphaned sync lock from {lock_time}")
                    self.google_drive_manager.drive_sync.delete_file_by_name(lock_filename)
                else:
                    debug_print(f"Found recent sync lock from {lock_time}, leaving it")
            
            # Clean up old intent files (older than 5 minutes)
            intent_files = self.google_drive_manager.drive_sync.list_files_by_pattern("sync_intent_*.json")
            current_time = datetime.now()
            
            for file_info in intent_files:
                try:
                    intent_data = self.google_drive_manager.drive_sync.download_json_file_by_id(file_info['id'])
                    if intent_data:
                        intent_time = datetime.fromisoformat(intent_data['timestamp'])
                        if (current_time - intent_time).total_seconds() > 300:  # 5 minutes
                            debug_print(f"Cleaning up old intent file: {file_info['name']}")
                            self.google_drive_manager.drive_sync.delete_file_by_name(file_info['name'])
                except Exception as e:
                    debug_print(f"Error cleaning intent file {file_info['name']}: {e}")
            
            # Clean up orphaned temporary database files (tmp*.db)
            self._cleanup_orphaned_temp_files()
                    
        except Exception as e:
            debug_print(f"Error during lock cleanup: {e}")
            # Not critical - continue startup
    
    def _cleanup_orphaned_temp_files(self):
        """Clean up orphaned temporary database files from Google Drive"""
        try:
            # Look for files that match temporary file patterns
            temp_patterns = ["tmp*.db", "pomodora_sync_*.db"]
            
            for pattern in temp_patterns:
                # Use a more general search since Google Drive pattern matching is limited
                if pattern.startswith("tmp"):
                    # Search for files starting with "tmp" and ending with ".db"
                    results = self.google_drive_manager.drive_sync.service.files().list(
                        q=f"parents in '{self.google_drive_manager.drive_sync.folder_id}' and trashed=false and name contains 'tmp' and name contains '.db'",
                        fields="files(id, name, modifiedTime)"
                    ).execute()
                elif pattern.startswith("pomodora_sync_"):
                    # Search for sync temporary files
                    results = self.google_drive_manager.drive_sync.service.files().list(
                        q=f"parents in '{self.google_drive_manager.drive_sync.folder_id}' and trashed=false and name contains 'pomodora_sync_' and name contains '.db'",
                        fields="files(id, name, modifiedTime)"
                    ).execute()
                else:
                    continue
                
                files = results.get('files', [])
                
                for file_info in files:
                    try:
                        # Check if file is older than 1 hour (should be safe to delete)
                        from datetime import datetime, timedelta
                        modified_time = datetime.fromisoformat(file_info['modifiedTime'].replace('Z', '+00:00'))
                        if (datetime.now(modified_time.tzinfo) - modified_time).total_seconds() > 3600:  # 1 hour
                            debug_print(f"Cleaning up orphaned temp file: {file_info['name']}")
                            self.google_drive_manager.drive_sync.service.files().delete(fileId=file_info['id']).execute()
                        else:
                            debug_print(f"Temporary file {file_info['name']} is recent, keeping it")
                    except Exception as e:
                        debug_print(f"Error cleaning temp file {file_info['name']}: {e}")
                        
        except Exception as e:
            debug_print(f"Error during temp file cleanup: {e}")
            # Not critical - continue
    
    def _perform_backup_if_needed(self):
        """Perform database backup if needed (daily/monthly/yearly)"""
        try:
            if not self._initializing:
                self.backup_manager.perform_scheduled_backups()
        except Exception as e:
            error_print(f"Error during backup: {e}")
            # Don't let backup failures stop the app
    
    def get_backup_status(self) -> dict:
        """Get database backup status"""
        return self.backup_manager.get_backup_status()
    
    def create_manual_backup(self, backup_type: str = "daily") -> bool:
        """Create a manual backup of the database"""
        try:
            backup_path = self.backup_manager.create_backup(backup_type)
            return backup_path is not None
        except Exception as e:
            error_print(f"Error creating manual backup: {e}")
            return False
    
    def get_sprints_by_date(self, date):
        """Get sprints for a specific date"""
        # For read operations, use auto-sync to get latest data
        session = self.get_session()
        try:
            from datetime import datetime, timedelta
            start_of_day = datetime.combine(date, datetime.min.time())
            end_of_day = start_of_day + timedelta(days=1)
            
            debug_print(f"Searching for sprints between {start_of_day} and {end_of_day}")
            
            # Get all sprints to debug
            all_sprints = session.query(Sprint).all()
            debug_print(f"Total sprints in database: {len(all_sprints)}")
            
            for sprint in all_sprints:
                debug_print(f"  Sprint: {sprint.task_description} at {sprint.start_time} (type: {type(sprint.start_time)})")
            
            # Filter by date
            filtered_sprints = session.query(Sprint).filter(
                Sprint.start_time >= start_of_day,
                Sprint.start_time < end_of_day
            ).all()
            
            debug_print(f"Filtered sprints for {date}: {len(filtered_sprints)}")
            
            return filtered_sprints
        finally:
            session.close()