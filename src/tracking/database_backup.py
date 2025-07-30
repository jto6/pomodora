import os
import shutil
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional
from utils.logging import debug_print, info_print, error_print


class DatabaseBackupManager:
    """Manages database backups with daily, monthly, and yearly retention policies"""
    
    def __init__(self, db_path: str, backup_base_dir: str = None):
        self.db_path = Path(db_path)
        
        # Use custom backup directory if provided, otherwise use database parent directory
        if backup_base_dir:
            self.backup_dir = Path(backup_base_dir) / 'Backup'
        else:
            self.backup_dir = self.db_path.parent / 'Backup'
            
        self.daily_dir = self.backup_dir / 'Daily'
        self.monthly_dir = self.backup_dir / 'Monthly'
        self.yearly_dir = self.backup_dir / 'Yearly'
        
        # Create backup directories if they don't exist
        self._ensure_backup_directories()
    
    def _ensure_backup_directories(self):
        """Create backup directories if they don't exist"""
        for directory in [self.backup_dir, self.daily_dir, self.monthly_dir, self.yearly_dir]:
            directory.mkdir(parents=True, exist_ok=True)
            debug_print(f"Ensured backup directory exists: {directory}")
    
    def create_backup(self, backup_type: str = "daily") -> Optional[Path]:
        """Create a backup of the database
        
        Args:
            backup_type: Type of backup ('daily', 'monthly', 'yearly')
            
        Returns:
            Path to the created backup file, or None if failed
        """
        if not self.db_path.exists():
            error_print(f"Database file not found: {self.db_path}")
            return None
        
        try:
            now = datetime.now()
            
            if backup_type == "daily":
                backup_filename = f"pomodora_daily_{now.strftime('%Y%m%d_%H%M%S')}.db"
                backup_path = self.daily_dir / backup_filename
            elif backup_type == "monthly":
                backup_filename = f"pomodora_monthly_{now.strftime('%Y%m')}.db"
                backup_path = self.monthly_dir / backup_filename
            elif backup_type == "yearly":
                backup_filename = f"pomodora_yearly_{now.strftime('%Y')}.db"
                backup_path = self.yearly_dir / backup_filename
            else:
                error_print(f"Unknown backup type: {backup_type}")
                return None
            
            # Copy the database file
            shutil.copy2(self.db_path, backup_path)
            info_print(f"Created {backup_type} backup: {backup_path}")
            return backup_path
            
        except Exception as e:
            error_print(f"Failed to create {backup_type} backup: {e}")
            return None
    
    def cleanup_old_backups(self):
        """Clean up old backups according to retention policy"""
        try:
            self._cleanup_daily_backups()
            self._cleanup_monthly_backups()
            # Yearly backups are kept indefinitely
            debug_print("Backup cleanup completed")
        except Exception as e:
            error_print(f"Error during backup cleanup: {e}")
    
    def _cleanup_daily_backups(self):
        """Keep only the last 7 daily backups"""
        daily_backups = sorted(
            [f for f in self.daily_dir.glob("pomodora_daily_*.db")],
            key=lambda x: x.stat().st_mtime,
            reverse=True  # Most recent first
        )
        
        # Keep the 7 most recent, delete the rest
        backups_to_delete = daily_backups[7:]
        for backup_file in backups_to_delete:
            try:
                backup_file.unlink()
                debug_print(f"Deleted old daily backup: {backup_file.name}")
            except Exception as e:
                error_print(f"Failed to delete daily backup {backup_file}: {e}")
        
        debug_print(f"Daily backups: kept {min(len(daily_backups), 7)}, deleted {len(backups_to_delete)}")
    
    def _cleanup_monthly_backups(self):
        """Keep only the last 12 monthly backups"""
        monthly_backups = sorted(
            [f for f in self.monthly_dir.glob("pomodora_monthly_*.db")],
            key=lambda x: x.stat().st_mtime,
            reverse=True  # Most recent first
        )
        
        # Keep the 12 most recent, delete the rest
        backups_to_delete = monthly_backups[12:]
        for backup_file in backups_to_delete:
            try:
                backup_file.unlink()
                debug_print(f"Deleted old monthly backup: {backup_file.name}")
            except Exception as e:
                error_print(f"Failed to delete monthly backup {backup_file}: {e}")
        
        debug_print(f"Monthly backups: kept {min(len(monthly_backups), 12)}, deleted {len(backups_to_delete)}")
    
    def should_create_monthly_backup(self) -> bool:
        """Check if we should create a monthly backup (first day of month or no backup exists)"""
        today = date.today()
        current_month_str = today.strftime('%Y%m')
        monthly_backup_path = self.monthly_dir / f"pomodora_monthly_{current_month_str}.db"
        
        # Create monthly backup if it doesn't exist for current month
        return not monthly_backup_path.exists()
    
    def should_create_yearly_backup(self) -> bool:
        """Check if we should create a yearly backup (first day of year or no backup exists)"""
        today = date.today()
        current_year_str = today.strftime('%Y')
        yearly_backup_path = self.yearly_dir / f"pomodora_yearly_{current_year_str}.db"
        
        # Create yearly backup if it doesn't exist for current year
        return not yearly_backup_path.exists()
    
    def perform_scheduled_backups(self):
        """Perform all scheduled backups based on current date"""
        try:
            # Always create daily backup
            daily_backup = self.create_backup("daily")
            if daily_backup:
                debug_print(f"Daily backup created: {daily_backup.name}")
            
            # Create monthly backup if needed
            if self.should_create_monthly_backup():
                monthly_backup = self.create_backup("monthly")
                if monthly_backup:
                    info_print(f"Monthly backup created: {monthly_backup.name}")
            
            # Create yearly backup if needed
            if self.should_create_yearly_backup():
                yearly_backup = self.create_backup("yearly")
                if yearly_backup:
                    info_print(f"Yearly backup created: {yearly_backup.name}")
            
            # Clean up old backups
            self.cleanup_old_backups()
            
        except Exception as e:
            error_print(f"Error during scheduled backups: {e}")
    
    def get_backup_status(self) -> dict:
        """Get current backup status and statistics"""
        try:
            daily_count = len(list(self.daily_dir.glob("pomodora_daily_*.db")))
            monthly_count = len(list(self.monthly_dir.glob("pomodora_monthly_*.db")))
            yearly_count = len(list(self.yearly_dir.glob("pomodora_yearly_*.db")))
            
            # Get latest backup dates
            latest_daily = None
            daily_backups = list(self.daily_dir.glob("pomodora_daily_*.db"))
            if daily_backups:
                latest_daily_file = max(daily_backups, key=lambda x: x.stat().st_mtime)
                latest_daily = datetime.fromtimestamp(latest_daily_file.stat().st_mtime)
            
            latest_monthly = None
            monthly_backups = list(self.monthly_dir.glob("pomodora_monthly_*.db"))
            if monthly_backups:
                latest_monthly_file = max(monthly_backups, key=lambda x: x.stat().st_mtime)
                latest_monthly = datetime.fromtimestamp(latest_monthly_file.stat().st_mtime)
            
            latest_yearly = None
            yearly_backups = list(self.yearly_dir.glob("pomodora_yearly_*.db"))
            if yearly_backups:
                latest_yearly_file = max(yearly_backups, key=lambda x: x.stat().st_mtime)
                latest_yearly = datetime.fromtimestamp(latest_yearly_file.stat().st_mtime)
            
            return {
                'backup_dir': str(self.backup_dir),
                'daily_backups': daily_count,
                'monthly_backups': monthly_count,
                'yearly_backups': yearly_count,
                'latest_daily': latest_daily,
                'latest_monthly': latest_monthly,
                'latest_yearly': latest_yearly
            }
            
        except Exception as e:
            error_print(f"Error getting backup status: {e}")
            return {
                'error': str(e),
                'backup_dir': str(self.backup_dir),
                'daily_backups': 0,
                'monthly_backups': 0,
                'yearly_backups': 0
            }