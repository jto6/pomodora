"""
Timer control mixin for ModernPomodoroWindow.

Provides functionality for timer start/stop/pause, sprint/break handling,
work block mode, and hyperfocus prevention.
"""

import threading

from PySide6.QtWidgets import QMessageBox

from timer.pomodoro import TimerState
from utils.logging import debug_print, info_print, error_print


class TimerControlMixin:
    """Mixin providing timer control functionality."""

    def toggle_timer(self):
        """Start or pause the timer"""
        debug_print(f"Toggle timer called, current state: {self.pomodoro_timer.state}")

        if self.pomodoro_timer.state == TimerState.STOPPED:
            # Validate task description before starting
            task_description = self.task_input.text().strip()
            if not task_description:
                debug_print("Cannot start sprint: Task description is required")
                return

            # Stop work block reminder if active (user started new sprint)
            self.stop_work_block_reminder()

            # Get sprint parameters
            project_id = self.project_combo.currentData()
            task_category_id = self.task_category_combo.currentData()

            # Check for hyperfocus (3+ consecutive identical sprints)
            self._check_hyperfocus_warning(project_id, task_category_id, task_description)

            # Start new sprint
            self.current_project_id = project_id
            self.current_task_category_id = task_category_id
            self.current_task_description = task_description

            self.pomodoro_timer.start_sprint()
            self.sprint_start_time = self.pomodoro_timer.start_time  # Preserve for completion
            debug_print(f"Sprint started - Project ID: {self.current_project_id}, Task Category ID: {self.current_task_category_id}, Task: '{self.current_task_description}', Start time: {self.sprint_start_time}")
            self.qt_timer.start(1000)  # Update every second
            self.start_button.setText("Pause")
            self.stop_button.setEnabled(True)
            self.complete_button.setEnabled(True)  # Enable complete button during timer
            self.sync_compact_buttons()  # Sync compact button states
            self.state_label.setText("Focus Time! 🎯")

            # Auto-enter compact mode if enabled
            if self.auto_compact_mode and not self.compact_mode:
                self.toggle_compact_mode()

        elif self.pomodoro_timer.state == TimerState.RUNNING:
            # Pause
            debug_print("Pausing timer")
            remaining_before = self.pomodoro_timer.get_time_remaining()
            debug_print(f"Time remaining before pause: {remaining_before}")
            self.pomodoro_timer.pause()
            self.qt_timer.stop()
            self.start_button.setText("Resume")
            self.sync_compact_buttons()  # Sync compact button states
            self.state_label.setText("Paused ⏸️")

        elif self.pomodoro_timer.state == TimerState.PAUSED:
            # Resume
            debug_print("Resuming timer")
            remaining_before = self.pomodoro_timer.get_time_remaining()
            debug_print(f"Time remaining before resume: {remaining_before}")
            self.pomodoro_timer.resume()
            self.qt_timer.start(1000)
            self.start_button.setText("Pause")
            self.complete_button.setEnabled(True)  # Keep complete button enabled
            self.sync_compact_buttons()  # Sync compact button states
            self.state_label.setText("Focus Time! 🎯")
            remaining_after = self.pomodoro_timer.get_time_remaining()
            debug_print(f"Time remaining after resume: {remaining_after}")

            # Auto-enter compact mode if enabled
            if self.auto_compact_mode and not self.compact_mode:
                self.toggle_compact_mode()

        elif self.pomodoro_timer.state == TimerState.BREAK:
            # During break - complete current sprint first, then start new sprint
            debug_print("Ending break early - completing current sprint and starting new one")

            # Stop work block reminder if active
            self.stop_work_block_reminder()

            # Save the previous sprint parameters before completing
            prev_project_id = self.current_project_id
            prev_task_category_id = self.current_task_category_id
            prev_task_description = self.current_task_description

            # Complete the current sprint first (uses the original sprint parameters)
            self.complete_sprint()

            # Now start new sprint with the SAME parameters as the just-completed sprint
            self.current_project_id = prev_project_id
            self.current_task_category_id = prev_task_category_id
            self.current_task_description = prev_task_description

            # Update UI field to show the task description
            self.task_input.setText(prev_task_description)

            debug_print(f"New sprint started with same parameters - Project ID: {self.current_project_id}, Task Category ID: {self.current_task_category_id}, Task: '{self.current_task_description}'")
            self.pomodoro_timer.start_sprint()
            self.sprint_start_time = self.pomodoro_timer.start_time  # Preserve for completion
            self.qt_timer.start(1000)
            self.start_button.setText("Pause")
            self.stop_button.setEnabled(True)
            self.complete_button.setEnabled(True)
            self.sync_compact_buttons()  # Sync compact button states
            self.state_label.setText("Focus Time! 🎯")

            # Auto-enter compact mode if enabled
            if self.auto_compact_mode and not self.compact_mode:
                self.toggle_compact_mode()

    def stop_timer(self):
        """Stop the current timer"""
        # If stopping during break, complete the sprint first
        if self.pomodoro_timer.get_state() == TimerState.BREAK:
            debug_print("Stopping during break - completing sprint first")
            self.complete_sprint()

        self.pomodoro_timer.stop()
        self.qt_timer.stop()
        self.reset_ui()

        # Exit compact mode when stopping timer
        if self.compact_mode:
            self.toggle_compact_mode()

    def emit_sprint_complete(self):
        """Thread-safe method called from background timer thread"""
        # Capture critical sprint data immediately to avoid race conditions
        sprint_data = {
            'project_id': self.current_project_id,
            'task_category_id': self.current_task_category_id,
            'task_description': self.current_task_description,
            'start_time': self.sprint_start_time
        }

        # Only emit signal if we have valid sprint data
        if (sprint_data['project_id'] and sprint_data['task_category_id'] and
            sprint_data['task_description'] and sprint_data['start_time']):
            # Store the captured data temporarily
            self._pending_sprint_data = sprint_data
            self.sprint_completed.emit()
        else:
            debug_print(f"Sprint completion skipped - invalid data: {sprint_data}")

    def handle_sprint_complete(self):
        """Main thread handler for sprint completion"""
        info_print("Sprint completed - playing alarm and starting break")

        # Auto-save sprint to database when timer completes
        # This ensures sprints are saved even after hibernation resume
        # Use captured sprint data to avoid race conditions
        if hasattr(self, '_pending_sprint_data') and self._pending_sprint_data:
            try:
                debug_print("Auto-saving sprint on timer completion using captured data")
                self._save_sprint_with_data(self._pending_sprint_data)
                info_print("Sprint auto-saved on timer completion")
                # Clear the pending data
                delattr(self, '_pending_sprint_data')
            except Exception as e:
                error_print(f"Failed to auto-save sprint on timer completion: {e}")
        else:
            error_print("No pending sprint data available for auto-save")

        # Get alarm settings
        from tracking.local_settings import get_local_settings
        settings = get_local_settings()
        volume = settings.get("alarm_volume", 0.7)
        sprint_alarm = settings.get("sprint_alarm", "gentle_chime")

        # Play sprint completion alarm
        from audio.alarm import play_alarm_sound

        def play_alarm():
            try:
                play_alarm_sound(sprint_alarm, volume)
            except Exception as e:
                print(f"Sprint alarm error: {e}")

        # Play in separate thread to avoid blocking UI
        thread = threading.Thread(target=play_alarm, daemon=True)
        thread.start()

        # Update UI to show break state - need to refresh button states
        self.refresh_ui_state()
        self.sync_compact_buttons()  # Ensure compact buttons match main window state

    def emit_break_complete(self):
        """Thread-safe method called from background timer thread"""
        self.break_completed.emit()

    def handle_break_complete(self):
        """Main thread handler for break completion"""
        info_print("Break completed - playing alarm and auto-completing sprint")

        # Get alarm settings
        from tracking.local_settings import get_local_settings
        settings = get_local_settings()
        volume = settings.get("alarm_volume", 0.7)
        break_alarm = settings.get("break_alarm", "urgent_alert")

        # Play break completion alarm
        from audio.alarm import play_alarm_sound

        def play_alarm():
            try:
                play_alarm_sound(break_alarm, volume)
            except Exception as e:
                print(f"Break alarm error: {e}")

        # Play in separate thread to avoid blocking UI
        thread = threading.Thread(target=play_alarm, daemon=True)
        thread.start()

        # Sprint was already saved during timer completion, just reset UI
        self.pomodoro_timer.stop()
        self.qt_timer.stop()
        self.reset_ui()
        self.state_label.setText("Sprint Completed! 🎉")
        self.refresh_data_dependent_ui()

        # Clear preserved sprint start time after successful completion
        self.sprint_start_time = None
        debug_print("Break completed - sprint already saved, UI reset")

        # Start work block reminder timer if work block mode is enabled
        if self.work_block_mode:
            self.start_work_block_reminder()

    def toggle_work_block_mode(self, state):
        """Toggle work block mode on/off"""
        self.work_block_mode = bool(state)
        debug_print(f"Work block mode {'enabled' if self.work_block_mode else 'disabled'}")

        # Save the setting
        from tracking.local_settings import get_local_settings
        settings = get_local_settings()
        settings.set("work_block_mode", self.work_block_mode)

        if self.work_block_mode:
            # If enabling and timer is stopped (after a sprint), start reminder
            if self.pomodoro_timer.get_state() == TimerState.STOPPED:
                # Only start reminder if there was a recent sprint (not on fresh app start)
                if hasattr(self, '_had_recent_sprint') and self._had_recent_sprint:
                    self.start_work_block_reminder()
        else:
            # If disabling, stop any active reminder
            self.stop_work_block_reminder()

    def start_work_block_reminder(self):
        """Start the work block reminder timer"""
        self.work_block_reminder_timer.stop()  # Stop any existing timer
        self.work_block_reminder_timer.start(self.work_block_reminder_interval)
        debug_print(f"Work block reminder started: will fire in {self.work_block_reminder_interval / 1000 / 60:.1f} minutes")
        self._had_recent_sprint = True  # Track that we had a sprint

    def stop_work_block_reminder(self):
        """Stop the work block reminder timer"""
        if self.work_block_reminder_timer.isActive():
            self.work_block_reminder_timer.stop()
            debug_print("Work block reminder stopped")

    def on_work_block_reminder(self):
        """Handler for work block reminder timeout - play alarm and restart timer"""
        debug_print("Work block reminder fired - playing alarm")

        # Play reminder alarm
        from tracking.local_settings import get_local_settings
        settings = get_local_settings()
        volume = settings.get("alarm_volume", 0.7)
        reminder_alarm = settings.get("work_block_reminder_alarm", "gentle_chime")

        from audio.alarm import play_alarm_sound

        def play_alarm():
            try:
                play_alarm_sound(reminder_alarm, volume)
            except Exception as e:
                error_print(f"Work block reminder alarm error: {e}")

        # Play in separate thread to avoid blocking UI
        thread = threading.Thread(target=play_alarm, daemon=True)
        thread.start()

        # Restart timer for next reminder (only if still in work block mode and timer stopped)
        if self.work_block_mode and self.pomodoro_timer.get_state() == TimerState.STOPPED:
            self.work_block_reminder_timer.start(self.work_block_reminder_interval)
            debug_print(f"Work block reminder restarted: will fire again in {self.work_block_reminder_interval / 1000 / 60:.1f} minutes")

    def _update_consecutive_sprint_tracking(self, project_id, task_category_id, task_description):
        """Update tracking for consecutive identical sprints (hyperfocus prevention)"""
        current_sprint = {
            'project_id': project_id,
            'task_category_id': task_category_id,
            'task_description': task_description
        }

        if (self._last_completed_sprint and
            self._last_completed_sprint['project_id'] == project_id and
            self._last_completed_sprint['task_category_id'] == task_category_id and
            self._last_completed_sprint['task_description'] == task_description):
            # Same sprint repeated
            self._consecutive_sprint_count += 1
            debug_print(f"Consecutive sprint count: {self._consecutive_sprint_count}")
        else:
            # Different sprint, reset counter
            self._consecutive_sprint_count = 1
            debug_print(f"New sprint type, reset consecutive count to 1")

        self._last_completed_sprint = current_sprint

    def _check_hyperfocus_warning(self, project_id, task_category_id, task_description):
        """Check if hyperfocus warning should be shown before starting a sprint.
        Returns True if warning was shown and acknowledged, False if no warning needed."""
        # Check if this would be the 3rd+ consecutive identical sprint
        if (self._last_completed_sprint and
            self._consecutive_sprint_count >= 2 and
            self._last_completed_sprint['project_id'] == project_id and
            self._last_completed_sprint['task_category_id'] == task_category_id and
            self._last_completed_sprint['task_description'] == task_description):

            debug_print(f"Hyperfocus warning triggered: {self._consecutive_sprint_count + 1} consecutive sprints")
            self._show_hyperfocus_warning()
            return True
        return False

    def _show_hyperfocus_warning(self):
        """Show the hyperfocus prevention reminder popup"""
        msg = QMessageBox(self)
        msg.setWindowTitle("Hyperfocus Check")
        msg.setIcon(QMessageBox.Information)
        msg.setText("You've been working on the same task for multiple sprints.")
        msg.setInformativeText(
            "To continue with this sprint:\n\n"
            "1. Take a 2 minute walk\n"
            "2. Ask yourself: \"What would you tell a mentee to do next?\""
        )
        msg.setStandardButtons(QMessageBox.Ok)
        msg.setDefaultButton(QMessageBox.Ok)

        # Apply current theme styling
        self.apply_dialog_styling(msg)

        msg.exec()
