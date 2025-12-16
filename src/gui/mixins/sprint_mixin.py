"""
Sprint mixin for ModernPomodoroWindow.

Provides functionality for sprint completion, saving, recovery, and date tracking.
"""

from datetime import datetime, timedelta, date

from timer.pomodoro import TimerState
from tracking.models import Sprint
from utils.logging import debug_print, info_print, error_print


class SprintMixin:
    """Mixin providing sprint management functionality."""

    def complete_sprint(self):
        """Complete the current sprint"""
        debug_print("Complete sprint called!")
        debug_print(f"Current project_id: {self.current_project_id}")
        debug_print(f"Current task_description: '{self.current_task_description}'")
        debug_print(f"Timer state: {self.pomodoro_timer.get_state()}")
        debug_print(f"Timer remaining: {self.pomodoro_timer.get_time_remaining()}")

        try:
            # Check timer state to determine action
            timer_state = self.pomodoro_timer.get_state()

            if timer_state == TimerState.RUNNING:
                # Sprint is still running - save it and stop timer
                if self.current_project_id is not None:
                    debug_print(f"Manual sprint completion during timer - saving sprint: {self.current_task_description} for project {self.current_project_id}")

                    # Get project name from ID
                    project = self.db_manager.get_project_by_id(self.current_project_id)
                    project_name = project.name if project else "Unknown"
                    debug_print(f"Project name resolved: {project_name}")

                    # Use the shared sprint saving logic
                    self._save_current_sprint()
                    info_print("Sprint saved to database successfully")
                else:
                    error_print(f"Cannot save sprint - no project selected (project_id: {self.current_project_id})")

            elif timer_state == TimerState.BREAK:
                # During break - sprint already auto-saved, just reset UI
                debug_print("During break - sprint already saved, just resetting UI")
                info_print("Break ended - returning to ready state")
            else:
                debug_print(f"Complete sprint called in unexpected state: {timer_state}")
                info_print("Returning to ready state")

            # Update auto-completion and stats (if sprint was saved)
            if timer_state == TimerState.RUNNING:
                # Verify it was saved
                today_sprints = self.db_manager.get_sprints_by_date(date.today())
                debug_print(f"Verification: {len(today_sprints)} sprints now in database for today")

                # Refresh UI to include the new task description
                self.refresh_data_dependent_ui()

            self.pomodoro_timer.stop()
            self.qt_timer.stop()
            self.reset_ui()
            self.state_label.setText("Sprint Completed! \U0001f389")
            self.refresh_data_dependent_ui()

            # Clear preserved sprint start time after successful completion
            self.sprint_start_time = None
            debug_print("Sprint completion finished")

            # Note: Stay in compact mode after sprint completion
            # User must click or manually toggle to exit compact mode
        except Exception as e:
            error_print(f"Error completing sprint: {e}")
            import traceback
            traceback.print_exc()  # Full error trace
            self.pomodoro_timer.stop()
            self.qt_timer.stop()
            self.reset_ui()

            # Clear preserved sprint start time even on error
            self.sprint_start_time = None

            # Exit compact mode even when there's an error
            if self.compact_mode:
                self.toggle_compact_mode()

    def check_date_change(self):
        """Check if date has changed and refresh stats if needed"""
        today = date.today()

        if self.current_date is None:
            # First time running - just set the current date
            self.current_date = today
            debug_print(f"Date tracker initialized: {today}")
        elif self.current_date != today:
            # Date has changed - refresh stats and trigger backups
            debug_print(f"Date changed from {self.current_date} to {today} - refreshing stats")
            self.current_date = today
            self.update_stats()

            # Trigger backups on new day
            if hasattr(self, 'db_manager') and self.db_manager:
                self._trigger_daily_backup()

            info_print(f"Stats refreshed for new day: {today}")

    def _trigger_daily_backup(self):
        """Trigger backups when date changes (new day)"""
        try:
            info_print("Triggering daily backup on date change")
            if hasattr(self.db_manager, 'backup_manager'):
                self.db_manager.backup_manager.perform_scheduled_backups()
            else:
                debug_print("No backup manager available for daily backup")
        except Exception as e:
            error_print(f"Daily backup failed: {e}")

    def _recover_hibernated_sprints(self):
        """
        Auto-complete sprints that were interrupted by hibernation/system sleep.

        Finds incomplete sprints where enough time has passed since start_time
        to consider them completed, then marks them as completed with appropriate
        end_time and duration.
        """
        try:
            session = self.db_manager.get_session()

            # Find incomplete sprints (started but not completed)
            debug_print("Hibernation recovery: Querying for incomplete sprints...")
            incomplete_sprints = session.query(Sprint).filter(
                Sprint.completed == False,
                Sprint.interrupted == False,
                Sprint.start_time.isnot(None),
                Sprint.end_time.is_(None)
            ).all()

            # Debug: Log what we found
            debug_print(f"Hibernation recovery: Query found {len(incomplete_sprints)} sprints matching criteria")
            for sprint in incomplete_sprints:
                debug_print(f"  - Sprint ID {sprint.id}: '{sprint.task_description}' started {sprint.start_time}, completed={sprint.completed}, interrupted={sprint.interrupted}, end_time={sprint.end_time}")

            if not incomplete_sprints:
                debug_print("Hibernation recovery: No incomplete sprints found")
                session.close()
                return

            debug_print(f"Hibernation recovery: Found {len(incomplete_sprints)} incomplete sprints")

            recovered_count = 0
            recovered_sprints = []  # Track which sprints were actually recovered
            now = datetime.now()

            for sprint in incomplete_sprints:
                # Calculate how much time has passed since sprint started
                elapsed_time = now - sprint.start_time
                planned_duration_timedelta = timedelta(minutes=sprint.planned_duration)

                # If enough time has passed for the sprint to be considered complete
                if elapsed_time >= planned_duration_timedelta:
                    # Auto-complete the sprint
                    sprint.end_time = sprint.start_time + planned_duration_timedelta
                    sprint.duration_minutes = sprint.planned_duration
                    sprint.completed = True
                    sprint.interrupted = False  # Ensure not marked as interrupted

                    # Add to recovered list for operation tracking
                    recovered_sprints.append(sprint)

                    start_date = sprint.start_time.strftime('%Y-%m-%d')
                    end_date = sprint.end_time.strftime('%Y-%m-%d')
                    info_print(f"Hibernation recovery: Auto-completed sprint '{sprint.task_description}' "
                             f"(started {sprint.start_time.strftime('%Y-%m-%d %H:%M')}, "
                             f"completed {sprint.end_time.strftime('%Y-%m-%d %H:%M')}, "
                             f"elapsed {elapsed_time.total_seconds()/60:.1f} min)")
                    if start_date != end_date:
                        info_print(f"Note: Sprint started on {start_date} so it will appear in {start_date}'s statistics, not today's")
                    recovered_count += 1
                else:
                    # Sprint is still within its planned duration - could be a legitimate pause
                    remaining_time = planned_duration_timedelta - elapsed_time
                    debug_print(f"Hibernation recovery: Sprint '{sprint.task_description}' still active "
                               f"({remaining_time.total_seconds()/60:.1f} min remaining)")

            if recovered_count > 0:
                session.commit()
                info_print(f"Hibernation recovery: Successfully recovered {recovered_count} sprint(s)")

                # Track hibernation recovery as operations for sync - only for sprints that were actually recovered
                debug_print(f"Hibernation recovery: Tracking operations for {len(recovered_sprints)} recovered sprints")
                for sprint in recovered_sprints:
                    debug_print(f"Hibernation recovery: Tracking operation for sprint ID {sprint.id}")
                    self.db_manager.operation_tracker.track_operation(
                        'update',
                        'sprints',
                        {
                            'id': sprint.id,
                            'end_time': sprint.end_time.isoformat() if sprint.end_time else None,
                            'duration_minutes': sprint.duration_minutes,
                            'completed': True,
                            'interrupted': False
                        }
                    )

                # Check pending operations before sync
                pending_ops = self.db_manager.operation_tracker.get_pending_operations()
                debug_print(f"Hibernation recovery: Found {len(pending_ops)} pending operations before sync")

                # Trigger sync to upload hibernation recovery changes to Google Drive
                if hasattr(self.db_manager, 'sync_manager') and self.db_manager.sync_manager:
                    try:
                        debug_print("Hibernation recovery: Triggering sync to upload recovered sprints")
                        self.db_manager.trigger_manual_sync()
                        debug_print("Hibernation recovery: Sync completed successfully")
                    except Exception as sync_error:
                        error_print(f"Failed to sync hibernation recovery changes: {sync_error}")
                else:
                    debug_print("Hibernation recovery: No sync manager available - changes will sync on next startup")

                # Update UI stats to reflect recovered sprints
                if hasattr(self, 'update_stats') and hasattr(self, 'stats_label'):
                    self.update_stats()
            else:
                debug_print("Hibernation recovery: No sprints needed recovery")

            session.close()

        except Exception as e:
            error_print(f"Error during hibernation recovery: {e}")
            if 'session' in locals():
                session.rollback()
                session.close()

    def _save_current_sprint(self):
        """
        Save the current sprint to database.

        Extracted from complete_sprint() to enable auto-saving on timer completion
        without duplicating the sprint saving logic.
        """
        # Use the preserved sprint start time and calculate duration
        start_time = self.sprint_start_time
        end_time = datetime.now()

        if start_time is None:
            error_print("Sprint start time is None, cannot save sprint")
            return

        actual_duration = (end_time - start_time).total_seconds()
        debug_print(f"Saving sprint: start={start_time}, duration={actual_duration}s")

        # Ensure task description is not None
        task_desc = self.current_task_description or "Pomodoro Sprint"
        debug_print(f"Task description for sprint save: '{task_desc}'")

        sprint = Sprint(
            project_id=self.current_project_id,
            task_category_id=self.current_task_category_id,
            task_description=task_desc,
            start_time=start_time,
            end_time=end_time,
            completed=True,
            interrupted=False,
            duration_minutes=int(actual_duration / 60),
            planned_duration=int(self.pomodoro_timer.sprint_duration / 60)
        )
        debug_print(f"Created sprint object: {sprint.task_description}, duration: {actual_duration}s")

        # Save to database
        debug_print("Calling db_manager.add_sprint()...")
        self.db_manager.add_sprint(sprint)
        debug_print("Sprint saved to database successfully")

        # Update consecutive sprint tracking for hyperfocus prevention
        self._update_consecutive_sprint_tracking(
            self.current_project_id,
            self.current_task_category_id,
            task_desc
        )

        # Update statistics
        if hasattr(self, 'update_stats'):
            self.update_stats()

    def _save_sprint_with_data(self, sprint_data):
        """
        Save sprint using captured data to avoid race conditions.

        Args:
            sprint_data: Dict with 'project_id', 'task_category_id', 'task_description', 'start_time'
        """
        start_time = sprint_data['start_time']
        end_time = datetime.now()

        if start_time is None:
            error_print("Sprint start time is None in captured data, cannot save sprint")
            return

        actual_duration = (end_time - start_time).total_seconds()
        debug_print(f"Saving sprint with captured data: start={start_time}, duration={actual_duration}s")

        # Ensure task description is not None
        task_desc = sprint_data['task_description'] or "Pomodoro Sprint"
        debug_print(f"Task description for sprint save: '{task_desc}'")

        sprint = Sprint(
            project_id=sprint_data['project_id'],
            task_category_id=sprint_data['task_category_id'],
            task_description=task_desc,
            start_time=start_time,
            end_time=end_time,
            completed=True,
            interrupted=False,
            duration_minutes=int(actual_duration / 60),
            planned_duration=int(self.pomodoro_timer.sprint_duration / 60)
        )
        debug_print(f"Created sprint object with captured data: {sprint.task_description}, duration: {actual_duration}s")

        # Save to database
        debug_print("Calling db_manager.add_sprint()...")
        self.db_manager.add_sprint(sprint)
        debug_print("Sprint saved to database successfully with captured data")

        # Update consecutive sprint tracking for hyperfocus prevention
        self._update_consecutive_sprint_tracking(
            sprint_data['project_id'],
            sprint_data['task_category_id'],
            task_desc
        )

        # Update statistics
        if hasattr(self, 'update_stats'):
            self.update_stats()

        debug_print("Sprint save with captured data completed successfully")
