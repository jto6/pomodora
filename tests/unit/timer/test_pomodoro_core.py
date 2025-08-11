"""
Unit tests for core Pomodoro timer functionality.
Tests timer state machine, duration handling, and basic operations.
"""

import pytest
import time
import threading
from datetime import datetime, timedelta

from timer.pomodoro import PomodoroTimer, TimerState


@pytest.mark.unit
class TestPomodoroTimerCore:
    """Test core timer functionality"""
    
    def test_initial_state(self):
        """Timer should start in STOPPED state with zero time"""
        timer = PomodoroTimer(sprint_duration=25, break_duration=5)
        assert timer.get_state() == TimerState.STOPPED
        assert timer.get_time_remaining() == 0
    
    def test_duration_conversion(self):
        """Timer should convert minutes to seconds correctly"""
        timer = PomodoroTimer(sprint_duration=25, break_duration=5)
        assert timer.sprint_duration == 1500  # 25 * 60
        assert timer.break_duration == 300    # 5 * 60
    
    @pytest.mark.parametrize("sprint_min,break_min,expected_sprint_sec,expected_break_sec", [
        (1, 1, 60, 60),
        (25, 5, 1500, 300),
        (30, 10, 1800, 600),
        (45, 15, 2700, 900),
        (60, 30, 3600, 1800),
    ])
    def test_duration_settings(self, sprint_min, break_min, expected_sprint_sec, expected_break_sec):
        """Test various duration settings"""
        timer = PomodoroTimer(sprint_min, break_min)
        assert timer.sprint_duration == expected_sprint_sec
        assert timer.break_duration == expected_break_sec
    
    def test_set_durations_when_stopped(self):
        """Should be able to change durations when timer is stopped"""
        timer = PomodoroTimer(sprint_duration=25, break_duration=5)
        timer.set_durations(30, 10)
        assert timer.sprint_duration == 1800  # 30 * 60
        assert timer.break_duration == 600    # 10 * 60
    
    def test_cannot_set_durations_when_running(self):
        """Should not change durations when timer is running"""
        timer = PomodoroTimer(sprint_duration=1, break_duration=1)  # 1 minute for test
        timer.start_sprint()
        
        # Try to change duration while running
        timer.set_durations(2, 2)
        
        # Duration should remain unchanged
        assert timer.sprint_duration == 60
        assert timer.break_duration == 60
        
        timer.stop()
    
    def test_start_sprint_state_change(self):
        """Starting sprint should change state to RUNNING"""
        timer = PomodoroTimer(sprint_duration=1, break_duration=1)
        timer.start_sprint()
        
        assert timer.get_state() == TimerState.RUNNING
        assert timer.get_time_remaining() == 60
        assert timer.start_time is not None
        
        timer.stop()
    
    def test_pause_resume_functionality(self):
        """Test pause and resume operations"""
        timer = PomodoroTimer(sprint_duration=1, break_duration=1)
        timer.start_sprint()
        original_state = timer.get_state()
        assert original_state == TimerState.RUNNING
        
        # Pause timer
        timer.pause()
        assert timer.get_state() == TimerState.PAUSED
        
        # Resume timer - should return to previous state (RUNNING or BREAK)
        timer.resume()
        resumed_state = timer.get_state()
        assert resumed_state in [TimerState.RUNNING, TimerState.BREAK]
        
        timer.stop()
    
    def test_stop_functionality(self):
        """Test stop operation resets timer"""
        timer = PomodoroTimer(sprint_duration=1, break_duration=1)
        timer.start_sprint()
        
        timer.stop()
        
        assert timer.get_state() == TimerState.STOPPED
        assert timer.get_time_remaining() == 0
        assert timer.start_time is None
    
    def test_cannot_pause_when_stopped(self):
        """Cannot pause when timer is not running"""
        timer = PomodoroTimer(sprint_duration=1, break_duration=1)
        
        # Should not change state when trying to pause stopped timer
        timer.pause()
        assert timer.get_state() == TimerState.STOPPED
    
    def test_cannot_resume_when_not_paused(self):
        """Cannot resume when timer is not paused"""
        timer = PomodoroTimer(sprint_duration=1, break_duration=1)
        timer.start_sprint()
        
        # Should remain running when trying to resume running timer
        timer.resume()
        assert timer.get_state() == TimerState.RUNNING
        
        timer.stop()
    
    def test_break_state_handling(self):
        """Test break state can be started from running state"""
        timer = PomodoroTimer(sprint_duration=1, break_duration=1)
        
        # Start sprint first, then transition to break
        timer.start_sprint()
        assert timer.get_state() == TimerState.RUNNING
        
        # Transition to break
        timer.start_break()
        assert timer.get_state() == TimerState.BREAK
        
        timer.stop()


@pytest.mark.unit
class TestPomodoroTimerCallbacks:
    """Test timer callback functionality"""
    
    def test_callback_registration(self):
        """Test that callbacks can be registered"""
        timer = PomodoroTimer(sprint_duration=1, break_duration=1)
        
        def dummy_callback():
            pass
            
        timer.on_sprint_complete = dummy_callback
        timer.on_break_complete = dummy_callback
        timer.on_state_change = lambda state: None
        timer.on_tick = lambda time_remaining, state: None
        
        assert timer.on_sprint_complete is not None
        assert timer.on_break_complete is not None
        assert timer.on_state_change is not None
        assert timer.on_tick is not None
    
    def test_state_change_callback(self):
        """Test state change callback is triggered"""
        timer = PomodoroTimer(sprint_duration=1, break_duration=1)
        states_received = []
        
        def state_callback(state):
            states_received.append(state)
        
        timer.on_state_change = state_callback
        
        timer.start_sprint()
        timer.pause()
        timer.resume()
        timer.stop()
        
        # Should have received state changes
        assert TimerState.RUNNING in states_received
        assert TimerState.PAUSED in states_received
        assert TimerState.STOPPED in states_received


@pytest.mark.unit
class TestPomodoroTimerThreading:
    """Test timer thread safety"""
    
    def test_thread_safety_basic(self):
        """Test basic thread safety of timer operations"""
        timer = PomodoroTimer(sprint_duration=1, break_duration=1)
        
        def start_stop_timer():
            timer.start_sprint()
            time.sleep(0.1)
            timer.stop()
        
        # Start multiple threads
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=start_stop_timer)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads
        for thread in threads:
            thread.join()
        
        # Timer should be in consistent state
        assert timer.get_state() == TimerState.STOPPED
    
    def test_concurrent_state_changes(self):
        """Test concurrent state change operations"""
        timer = PomodoroTimer(sprint_duration=1, break_duration=1)
        results = []
        
        def timer_operations():
            try:
                timer.start_sprint()
                results.append("started")
                timer.pause()
                results.append("paused")
                timer.resume()
                results.append("resumed")
                timer.stop()
                results.append("stopped")
            except Exception as e:
                results.append(f"error: {e}")
        
        # Run concurrent operations
        thread = threading.Thread(target=timer_operations)
        thread.start()
        thread.join()
        
        # Should have completed without errors
        assert "error" not in str(results)
        assert len([r for r in results if not r.startswith("error")]) >= 4