"""
Unit tests for database backup logic.

Tests the fix for multiple daily backups being created.
"""

import pytest
import os
import tempfile
import shutil
from pathlib import Path
from datetime import date, datetime, timedelta
from unittest.mock import patch

# Add src to path for imports
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from tracking.database_backup import DatabaseBackupManager


class TestDailyBackupLogic:
    """Test daily backup creation logic"""
    
    @pytest.fixture
    def temp_backup_setup(self):
        """Create temporary backup directory with test database"""
        temp_dir = tempfile.mkdtemp()
        temp_path = Path(temp_dir)
        
        # Create test database
        test_db = temp_path / "test.db"
        test_db.write_text("test_database_content")
        
        backup_manager = DatabaseBackupManager(str(test_db), str(temp_path))
        
        yield backup_manager, temp_path
        
        shutil.rmtree(temp_dir)
    
    def test_should_create_daily_backup_when_none_exist(self, temp_backup_setup):
        """Test that daily backup should be created when none exist for today"""
        backup_manager, temp_path = temp_backup_setup
        
        # No backups exist yet
        assert backup_manager.should_create_daily_backup() == True
    
    def test_should_not_create_daily_backup_when_exists(self, temp_backup_setup):
        """Test that daily backup should not be created when one already exists for today"""
        backup_manager, temp_path = temp_backup_setup
        
        # Create a daily backup for today
        backup_manager.create_backup("daily")
        
        # Should not create another one
        assert backup_manager.should_create_daily_backup() == False
    
    def test_should_create_daily_backup_different_day(self, temp_backup_setup):
        """Test that daily backup should be created for different days"""
        backup_manager, temp_path = temp_backup_setup
        
        # Create fake backup from yesterday
        yesterday = date.today() - timedelta(days=1)
        yesterday_str = yesterday.strftime('%Y%m%d')
        
        daily_dir = backup_manager.daily_dir
        daily_dir.mkdir(parents=True, exist_ok=True)
        
        fake_yesterday_backup = daily_dir / f"pomodora_daily_{yesterday_str}_120000.db"
        fake_yesterday_backup.write_text("yesterday_backup")
        
        # Should still create backup for today
        assert backup_manager.should_create_daily_backup() == True
    
    def test_perform_scheduled_backups_creates_only_one_daily(self, temp_backup_setup):
        """
        Test the core bug fix: perform_scheduled_backups should only create
        one daily backup per day, even when called multiple times.
        
        This test would have caught the original bug.
        """
        backup_manager, temp_path = temp_backup_setup
        
        # Call perform_scheduled_backups multiple times (simulating multiple app runs per day)
        backup_manager.perform_scheduled_backups()
        backup_manager.perform_scheduled_backups()
        backup_manager.perform_scheduled_backups()
        
        # Count daily backups for today
        daily_dir = backup_manager.daily_dir
        if daily_dir.exists():
            today_str = date.today().strftime('%Y%m%d')
            today_backups = list(daily_dir.glob(f"pomodora_daily_{today_str}_*.db"))
            
            # CRITICAL: Should only have one backup for today
            assert len(today_backups) <= 1, (
                f"Expected at most 1 daily backup for today, but found {len(today_backups)}. "
                f"Multiple daily backups indicate the bug is not fixed."
            )
    
    def test_multiple_backups_different_days_allowed(self, temp_backup_setup):
        """Test that multiple backups are allowed for different days"""
        backup_manager, temp_path = temp_backup_setup
        
        daily_dir = backup_manager.daily_dir
        daily_dir.mkdir(parents=True, exist_ok=True)
        
        # Create backups for different days
        today = date.today()
        yesterday = today - timedelta(days=1)
        day_before = today - timedelta(days=2)
        
        for day in [day_before, yesterday, today]:
            day_str = day.strftime('%Y%m%d')
            backup_file = daily_dir / f"pomodora_daily_{day_str}_120000.db"
            backup_file.write_text(f"backup_for_{day_str}")
        
        # Should have 3 total backups (different days)
        all_backups = list(daily_dir.glob("pomodora_daily_*.db"))
        assert len(all_backups) == 3
        
        # But should not create another backup for today
        assert backup_manager.should_create_daily_backup() == False
    
    def test_backup_filename_format(self, temp_backup_setup):
        """Test that backup filenames include date to prevent conflicts"""
        backup_manager, temp_path = temp_backup_setup
        
        # Create daily backup
        backup_path = backup_manager.create_backup("daily")
        
        # Should include today's date in filename
        today_str = date.today().strftime('%Y%m%d')
        assert today_str in backup_path.name
        assert backup_path.name.startswith("pomodora_daily_")
        assert backup_path.name.endswith(".db")
    
    def test_backup_detection_with_different_timestamps(self, temp_backup_setup):
        """Test that backup detection works regardless of timestamp differences"""
        backup_manager, temp_path = temp_backup_setup
        
        daily_dir = backup_manager.daily_dir
        daily_dir.mkdir(parents=True, exist_ok=True)
        
        today_str = date.today().strftime('%Y%m%d')
        
        # Create backups with different timestamps for same day
        backup1 = daily_dir / f"pomodora_daily_{today_str}_080000.db"
        backup2 = daily_dir / f"pomodora_daily_{today_str}_120000.db"
        backup3 = daily_dir / f"pomodora_daily_{today_str}_180000.db"
        
        backup1.write_text("backup1")
        backup2.write_text("backup2") 
        backup3.write_text("backup3")
        
        # Should detect that backups exist for today
        assert backup_manager.should_create_daily_backup() == False
        
        # Count backups for today
        today_backups = list(daily_dir.glob(f"pomodora_daily_{today_str}_*.db"))
        assert len(today_backups) == 3  # All from same day


class TestBackupBugRegression:
    """Regression tests to ensure the backup bug doesn't return"""
    
    def test_no_multiple_daily_backups_regression(self):
        """
        Comprehensive regression test for the multiple daily backups bug.
        
        This test simulates the exact scenario that was causing problems:
        - Multiple app starts during the same day
        - Each calling perform_scheduled_backups
        - Should result in only one daily backup
        """
        import tempfile
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create test database
            test_db = temp_path / "pomodora.db"
            test_db.write_text("production_database_content")
            
            # Simulate multiple app launches during the same day
            for app_launch in range(5):  # 5 separate app launches
                backup_manager = DatabaseBackupManager(str(test_db), str(temp_path))
                
                # Each app launch calls perform_scheduled_backups
                backup_manager.perform_scheduled_backups()
            
            # Check results
            daily_dir = temp_path / "Daily"
            if daily_dir.exists():
                today_str = date.today().strftime('%Y%m%d')
                today_backups = list(daily_dir.glob(f"pomodora_daily_{today_str}_*.db"))
                
                # REGRESSION CHECK: Must not have multiple backups for same day
                assert len(today_backups) <= 1, (
                    f"REGRESSION: Found {len(today_backups)} daily backups for today. "
                    f"The multiple daily backups bug has returned!"
                )
                
                if len(today_backups) == 1:
                    print(f"✓ Correctly created exactly one daily backup: {today_backups[0].name}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])