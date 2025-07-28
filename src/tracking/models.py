from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os
from utils.logging import verbose_print, error_print, info_print, debug_print, trace_print

Base = declarative_base()

class Category(Base):
    __tablename__ = 'categories'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    color = Column(String(7), default='#3498db')  # Hex color code
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Project(Base):
    __tablename__ = 'projects'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    category_id = Column(Integer, nullable=False)  # Reference to category
    color = Column(String(7), default='#3498db')  # Hex color code
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Sprint(Base):
    __tablename__ = 'sprints'
    
    id = Column(Integer, primary_key=True)
    project_name = Column(String(100), nullable=False)
    task_description = Column(Text, nullable=False)
    start_time = Column(DateTime, nullable=False)  # When the sprint actually started
    end_time = Column(DateTime)  # When the sprint ended (if completed)
    duration_minutes = Column(Integer)  # Actual duration in minutes
    planned_duration = Column(Integer, default=25)  # Planned duration
    completed = Column(Boolean, default=False)
    interrupted = Column(Boolean, default=False)
    # Note: created_at removed - start_time serves this purpose

# Settings are now stored locally in ~/.config/pomodora/local_settings.json
# The database only contains categories, projects, and sprints for sharing between desktops

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
        
        # Google Drive integration
        self.google_drive_manager = None
        self._initialize_google_drive()
    
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
        # Auto-sync before database operations if Google Drive is enabled
        if self.google_drive_manager and self.google_drive_manager.is_enabled():
            self.google_drive_manager.auto_sync()
        
        return self.Session()
    
    def sync_to_cloud(self) -> bool:
        """Manually trigger cloud sync"""
        if self.google_drive_manager and self.google_drive_manager.is_enabled():
            return self.google_drive_manager.sync_now()
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
        session = self.get_session()
        try:
            # Check if projects already exist
            if session.query(Project).count() == 0:
                default_categories = [
                    ("Admin", "#e74c3c"),      # Red
                    ("Comm", "#3498db"),       # Blue  
                    ("Strategy", "#9b59b6"),   # Purple
                    ("Research", "#1abc9c"),   # Teal
                    ("SelfDev", "#2ecc71"),    # Green
                ]
                
                for name, color in default_categories:
                    # Create category
                    category = Category(name=name, color=color)
                    session.add(category)
                    session.flush()  # Get the category ID
                    
                    # Auto-create project with same name
                    project = Project(name=name, category_id=category.id, color=color)
                    session.add(project)
                
                session.commit()
        finally:
            session.close()
    
# Settings initialization removed - all settings are now stored locally
    
    # Category management methods
    def get_all_categories(self):
        """Get all categories (active and inactive)"""
        session = self.get_session()
        try:
            return session.query(Category).all()
        finally:
            session.close()
    
    def get_active_categories(self):
        """Get only active categories"""
        session = self.get_session()
        try:
            return session.query(Category).filter(Category.active == True).all()
        finally:
            session.close()
    
    def create_category(self, name, color="#3498db"):
        """Create a new category and auto-create a project with the same name"""
        session = self.get_session()
        try:
            # Create category
            category = Category(name=name, color=color)
            session.add(category)
            session.flush()  # Get the category ID
            
            # Auto-create project with same name
            project = Project(name=name, category_id=category.id, color=color)
            session.add(project)
            session.commit()
            
            # Return the category ID instead of the object
            return category.id
        finally:
            session.close()
    
    def get_category_by_id(self, category_id):
        """Get category by ID"""
        session = self.get_session()
        try:
            return session.query(Category).filter(Category.id == category_id).first()
        finally:
            session.close()
    
    def toggle_category_active(self, category_id):
        """Toggle the active status of a category"""
        session = self.get_session()
        try:
            category = session.query(Category).filter(Category.id == category_id).first()
            if category:
                category.active = not category.active
                session.commit()
                return category.active
            return None
        finally:
            session.close()
    
    def update_category(self, category_id, name=None, color=None, active=None):
        """Update category properties"""
        session = self.get_session()
        try:
            category = session.query(Category).filter(Category.id == category_id).first()
            if category:
                if name is not None:
                    category.name = name
                if color is not None:
                    category.color = color
                if active is not None:
                    category.active = active
                session.commit()
                return category
            return None
        finally:
            session.close()
    
    def delete_category(self, category_id):
        """Delete a category and all its projects"""
        session = self.get_session()
        try:
            category = session.query(Category).filter(Category.id == category_id).first()
            if category:
                # Check if any projects in this category have sprints
                projects_in_category = session.query(Project).filter(Project.category_id == category_id).all()
                total_sprints = 0
                for project in projects_in_category:
                    sprint_count = session.query(Sprint).filter(Sprint.project_name == project.name).count()
                    total_sprints += sprint_count
                
                if total_sprints > 0:
                    return False, f"Cannot delete category '{category.name}' - it has {total_sprints} sprint(s) in its projects."
                
                # Delete all projects in this category first
                for project in projects_in_category:
                    session.delete(project)
                
                # Delete the category
                session.delete(category)
                session.commit()
                return True, f"Category '{category.name}' and its projects deleted successfully."
            return False, "Category not found."
        except Exception as e:
            session.rollback()
            return False, f"Error deleting category: {str(e)}"
        finally:
            session.close()

    # Project management methods
    def get_all_projects(self):
        """Get all projects (active and inactive)"""
        session = self.get_session()
        try:
            return session.query(Project).all()
        finally:
            session.close()
    
    def get_active_projects(self):
        """Get only active projects"""
        session = self.get_session()
        try:
            return session.query(Project).filter(Project.active == True).all()
        finally:
            session.close()
    
    def create_project(self, name, category_id, color="#3498db"):
        """Create a new project"""
        session = self.get_session()
        try:
            project = Project(name=name, category_id=category_id, color=color)
            session.add(project)
            session.commit()
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
                project.active = not project.active
                session.commit()
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
                if name is not None:
                    project.name = name
                if color is not None:
                    project.color = color
                if active is not None:
                    project.active = active
                session.commit()
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
                sprint_count = session.query(Sprint).filter(Sprint.project_name == project.name).count()
                if sprint_count > 0:
                    return False, f"Cannot delete project '{project.name}' - it has {sprint_count} sprint(s) associated with it."
                
                session.delete(project)
                session.commit()
                return True, f"Project '{project.name}' deleted successfully."
            return False, "Project not found."
        except Exception as e:
            session.rollback()
            return False, f"Error deleting project: {str(e)}"
        finally:
            session.close()
    
    # Sprint management methods
    def add_sprint(self, sprint):
        """Add a new sprint to the database"""
        session = self.get_session()
        try:
            session.add(sprint)
            session.commit()
            debug_print(f"Sprint saved: {sprint.task_description} at {sprint.start_time}")
            trace_print(f"Sprint details: ID={sprint.id}, Duration={sprint.duration_minutes}min, Project={sprint.project_name}")
            
            # Verify it was saved
            saved_sprint = session.query(Sprint).filter(
                Sprint.task_description == sprint.task_description,
                Sprint.start_time == sprint.start_time
            ).first()
            if saved_sprint:
                print(f"Verification: Sprint found in database with ID {saved_sprint.id}")
            else:
                error_print("Warning: Sprint not found after save!")
        finally:
            session.close()
    
    def get_sprints_by_date(self, date):
        """Get sprints for a specific date"""
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