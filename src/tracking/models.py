from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import json

Base = declarative_base()

class Project(Base):
    __tablename__ = 'projects'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    color = Column(String(7), default='#3498db')  # Hex color code
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Sprint(Base):
    __tablename__ = 'sprints'
    
    id = Column(Integer, primary_key=True)
    project_name = Column(String(100), nullable=False)
    task_description = Column(Text, nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime)
    duration_minutes = Column(Integer)  # Actual duration in minutes
    planned_duration = Column(Integer, default=25)  # Planned duration
    completed = Column(Boolean, default=False)
    interrupted = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class Settings(Base):
    __tablename__ = 'settings'
    
    id = Column(Integer, primary_key=True)
    key = Column(String(50), nullable=False, unique=True)
    value = Column(Text, nullable=False)
    
    @classmethod
    def get_setting(cls, session, key, default=None):
        setting = session.query(cls).filter(cls.key == key).first()
        if setting:
            try:
                return json.loads(setting.value)
            except:
                return setting.value
        return default
    
    @classmethod
    def set_setting(cls, session, key, value):
        setting = session.query(cls).filter(cls.key == key).first()
        if not setting:
            setting = cls(key=key)
            session.add(setting)
        
        if isinstance(value, (dict, list)):
            setting.value = json.dumps(value)
        else:
            setting.value = str(value)
        session.commit()

class DatabaseManager:
    def __init__(self, db_path="pomodora.db"):
        self.db_path = db_path
        self.engine = create_engine(f'sqlite:///{db_path}')
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        
        # Google Drive integration
        self.google_drive_manager = None
        self._initialize_google_drive()
    
    def _initialize_google_drive(self):
        """Initialize Google Drive integration if enabled"""
        try:
            from .google_drive import GoogleDriveManager
            # Use direct session to avoid recursion
            session = self.Session()
            try:
                google_drive_enabled = Settings.get_setting(session, "google_drive_enabled", False)
                if google_drive_enabled:
                    self.google_drive_manager = GoogleDriveManager(self.db_path)
                    if not self.google_drive_manager.initialize():
                        print("Warning: Google Drive initialization failed")
                        self.google_drive_manager = None
            finally:
                session.close()
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
            self.google_drive_manager = GoogleDriveManager(self.db_path)
            
            if self.google_drive_manager.initialize():
                # Update settings using direct session
                session = self.Session()
                try:
                    Settings.set_setting(session, "google_drive_enabled", True)
                    return True
                finally:
                    session.close()
        except Exception as e:
            print(f"Failed to enable Google Drive sync: {e}")
        
        return False
    
    def disable_google_drive_sync(self):
        """Disable Google Drive synchronization"""
        self.google_drive_manager = None
        session = self.Session()
        try:
            Settings.set_setting(session, "google_drive_enabled", False)
        finally:
            session.close()
    
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
                default_projects = [
                    ("Admin", "#e74c3c"),
                    ("Learning", "#9b59b6"),
                    ("Development", "#3498db"),
                    ("Research", "#1abc9c"),
                    ("Meeting", "#f39c12"),
                    ("Documentation", "#95a5a6"),
                    ("Testing", "#2ecc71"),
                    ("Planning", "#e67e22"),
                ]
                
                for name, color in default_projects:
                    project = Project(name=name, color=color)
                    session.add(project)
                
                session.commit()
        finally:
            session.close()
    
    def initialize_default_settings(self):
        session = self.get_session()
        try:
            Settings.set_setting(session, "sprint_duration", 25)
            Settings.set_setting(session, "break_duration", 5)
            Settings.set_setting(session, "alarm_volume", 0.7)
            Settings.set_setting(session, "google_drive_enabled", False)
        finally:
            session.close()