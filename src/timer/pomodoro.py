import threading
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, Optional

class TimerState(Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    BREAK = "break"
    PAUSED = "paused"

class PomodoroTimer:
    def __init__(self, sprint_duration: int = 25, break_duration: int = 5):
        self.sprint_duration = sprint_duration * 60  # Convert to seconds
        self.break_duration = break_duration * 60    # Convert to seconds

        self.state = TimerState.STOPPED
        self.current_time = 0
        self.start_time = None
        self.break_start_time = None
        self.pause_time = 0

        # Callbacks
        self.on_tick: Optional[Callable[[int, TimerState], None]] = None
        self.on_sprint_complete: Optional[Callable[[], None]] = None
        self.on_break_complete: Optional[Callable[[], None]] = None
        self.on_state_change: Optional[Callable[[TimerState], None]] = None

        # Threading
        self._timer_thread = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    def set_durations(self, sprint_minutes: int, break_minutes: int):
        """Update timer durations (only when stopped)"""
        with self._lock:
            if self.state == TimerState.STOPPED:
                self.sprint_duration = sprint_minutes * 60
                self.break_duration = break_minutes * 60

    def start_sprint(self):
        """Start a new sprint timer"""
        with self._lock:
            if self.state in [TimerState.STOPPED, TimerState.BREAK]:
                self.state = TimerState.RUNNING
                self.current_time = self.sprint_duration
                self.start_time = datetime.now()
                self.pause_time = 0
                self._start_timer_thread()

                if self.on_state_change:
                    self.on_state_change(self.state)

    def start_break(self):
        """Start break timer"""
        with self._lock:
            if self.state == TimerState.RUNNING:
                self.state = TimerState.BREAK
                self.current_time = self.break_duration
                self.start_time = datetime.now()
                self.pause_time = 0

                if self.on_state_change:
                    self.on_state_change(self.state)

    def pause(self):
        """Pause the current timer"""
        with self._lock:
            if self.state in [TimerState.RUNNING, TimerState.BREAK]:
                self.state = TimerState.PAUSED
                self.pause_time = time.time()

                if self.on_state_change:
                    self.on_state_change(self.state)

    def resume(self):
        """Resume from pause"""
        with self._lock:
            if self.state == TimerState.PAUSED:
                if self.pause_time > 0:
                    # Adjust start time to account for pause duration
                    pause_duration = time.time() - self.pause_time
                    # Move start time forward by the pause duration to maintain remaining time
                    self.start_time = self.start_time + timedelta(seconds=pause_duration)

                # Determine previous state based on current_time
                if self.current_time <= self.break_duration:
                    self.state = TimerState.BREAK
                else:
                    self.state = TimerState.RUNNING

                self.pause_time = 0

                if self.on_state_change:
                    self.on_state_change(self.state)

    def stop(self):
        """Stop the timer completely"""
        with self._lock:
            self.state = TimerState.STOPPED
            self.current_time = 0
            self.start_time = None
            self.break_start_time = None
            self.pause_time = 0
            self._stop_event.set()

            if self.on_state_change:
                self.on_state_change(self.state)

    def _start_timer_thread(self):
        """Start the timer thread"""
        self._stop_event.clear()
        if self._timer_thread and self._timer_thread.is_alive():
            return

        self._timer_thread = threading.Thread(target=self._timer_loop, daemon=True)
        self._timer_thread.start()

    def _timer_loop(self):
        """Main timer loop running in separate thread"""
        while not self._stop_event.is_set():
            with self._lock:
                if self.state in [TimerState.RUNNING, TimerState.BREAK] and self.start_time:
                    elapsed = (datetime.now() - self.start_time).total_seconds()

                    if self.state == TimerState.RUNNING:
                        self.current_time = max(0, self.sprint_duration - elapsed)

                        if self.current_time <= 0:
                            # Sprint completed
                            self.state = TimerState.BREAK
                            self.current_time = self.break_duration
                            self.break_start_time = datetime.now()  # Preserve original start_time for sprint duration

                            if self.on_sprint_complete:
                                threading.Thread(target=self.on_sprint_complete, daemon=True).start()
                            if self.on_state_change:
                                threading.Thread(target=lambda: self.on_state_change(self.state), daemon=True).start()

                    elif self.state == TimerState.BREAK:
                        # Use break_start_time for break duration calculation
                        break_elapsed = (datetime.now() - self.break_start_time).total_seconds() if self.break_start_time else 0
                        self.current_time = max(0, self.break_duration - break_elapsed)

                        if self.current_time <= 0:
                            # Break completed
                            self.state = TimerState.STOPPED
                            self.current_time = 0
                            self.start_time = None
                            self.break_start_time = None

                            if self.on_break_complete:
                                threading.Thread(target=self.on_break_complete, daemon=True).start()
                            if self.on_state_change:
                                threading.Thread(target=lambda: self.on_state_change(self.state), daemon=True).start()

                    # Trigger tick callback
                    if self.on_tick:
                        threading.Thread(target=lambda: self.on_tick(int(self.current_time), self.state), daemon=True).start()

            time.sleep(0.1)  # Update every 100ms for smooth display

    def get_time_remaining(self) -> int:
        """Get remaining time in seconds"""
        with self._lock:
            return int(self.current_time)

    def get_state(self) -> TimerState:
        """Get current timer state"""
        with self._lock:
            return self.state

    def get_progress_percentage(self) -> float:
        """Get progress as percentage (0-100)"""
        with self._lock:
            if self.state == TimerState.RUNNING:
                total = self.sprint_duration
                remaining = self.current_time
            elif self.state == TimerState.BREAK:
                total = self.break_duration
                remaining = self.current_time
            else:
                return 0.0

            if total > 0:
                return ((total - remaining) / total) * 100
            return 0.0

    def format_time(self, seconds: int) -> str:
        """Format seconds as MM:SS"""
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes:02d}:{seconds:02d}"

    def get_sprint_start_time(self) -> Optional[datetime]:
        """Get the start time of current sprint"""
        with self._lock:
            return self.start_time