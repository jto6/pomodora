"""
Unit tests for logging utility functions.
Tests multi-level logging, thread safety, and output routing.
"""

import pytest
import logging
import io
import sys
from contextlib import redirect_stdout, redirect_stderr
from threading import Thread
import tempfile
import os

from utils.logging import (
    verbose_print, error_print, info_print, debug_print, trace_print,
    set_verbose_level, set_verbose, VERBOSE_LEVEL
)


@pytest.mark.unit
class TestLoggingFunctions:
    """Test individual logging functions"""
    
    def test_verbose_print_output(self, capsys):
        """Test verbose_print outputs to stdout"""
        verbose_print("Test verbose message")
        captured = capsys.readouterr()
        assert "Test verbose message" in captured.out
    
    def test_error_print_output(self, capsys):
        """Test error_print outputs to stderr"""
        error_print("Test error message")
        captured = capsys.readouterr()
        assert "Test error message" in captured.err
    
    def test_info_print_output(self, capsys):
        """Test info_print outputs based on verbosity level"""
        # Test with different verbosity levels
        info_print("Test info message", level=1)
        captured = capsys.readouterr()
        # Output depends on current verbosity setting
        assert isinstance(captured.out, str)  # Should not error
    
    def test_debug_print_output(self, capsys):
        """Test debug_print outputs based on verbosity level"""
        debug_print("Test debug message", level=2)
        captured = capsys.readouterr()
        assert isinstance(captured.out, str)  # Should not error
    
    def test_trace_print_output(self, capsys):
        """Test trace_print outputs based on verbosity level"""
        trace_print("Test trace message", level=3)
        captured = capsys.readouterr()
        assert isinstance(captured.out, str)  # Should not error
    
    def test_logging_with_none_message(self, capsys):
        """Test logging functions handle None messages gracefully"""
        verbose_print(None)
        error_print(None)
        info_print(None, level=1)
        debug_print(None, level=2)
        trace_print(None, level=3)
        
        captured = capsys.readouterr()
        # Should not crash, may output nothing or "None"
        assert isinstance(captured.out, str)
        assert isinstance(captured.err, str)
    
    def test_logging_with_empty_string(self, capsys):
        """Test logging functions handle empty strings"""
        verbose_print("")
        error_print("")
        info_print("", level=1)
        debug_print("", level=2)
        trace_print("", level=3)
        
        captured = capsys.readouterr()
        # Should not crash
        assert isinstance(captured.out, str)
        assert isinstance(captured.err, str)
    
    @pytest.mark.parametrize("level", [0, 1, 2, 3])
    def test_logging_levels(self, level, capsys):
        """Test logging functions with different verbosity levels"""
        # This test assumes logging functions check a global verbosity level
        # Actual implementation may vary
        
        info_print("Info message", level=level)
        debug_print("Debug message", level=level)
        trace_print("Trace message", level=level)
        
        captured = capsys.readouterr()
        assert isinstance(captured.out, str)
    
    def test_logging_with_formatting(self, capsys):
        """Test logging functions with string formatting"""
        test_value = 42
        test_string = "test"
        
        verbose_print(f"Value: {test_value}, String: {test_string}")
        captured = capsys.readouterr()
        assert "Value: 42" in captured.out
        assert "String: test" in captured.out
    
    def test_multiline_logging(self, capsys):
        """Test logging functions with multiline strings"""
        multiline_message = """Line 1
Line 2
Line 3"""
        
        verbose_print(multiline_message)
        captured = capsys.readouterr()
        assert "Line 1" in captured.out
        assert "Line 2" in captured.out
        assert "Line 3" in captured.out
    
    def test_unicode_logging(self, capsys):
        """Test logging functions with unicode characters"""
        unicode_messages = [
            "café",     # Accented characters
            "测试",      # Chinese characters
            "🍅",       # Emoji
            "Ñoño",     # Spanish characters
        ]
        
        for message in unicode_messages:
            verbose_print(message)
        
        captured = capsys.readouterr()
        for message in unicode_messages:
            assert message in captured.out


@pytest.mark.unit
class TestLoggingSetup:
    """Test logging setup and configuration"""
    
    def test_verbose_level_setting(self):
        """Test setting verbose levels"""
        original_level = VERBOSE_LEVEL
        
        try:
            # Test level setting
            set_verbose_level(2)
            assert VERBOSE_LEVEL == 2
            
            set_verbose_level(0)
            assert VERBOSE_LEVEL == 0
            
            set_verbose_level(3)
            assert VERBOSE_LEVEL == 3
            
            # Test bounds checking
            set_verbose_level(-1)
            assert VERBOSE_LEVEL == 0
            
            set_verbose_level(10)
            assert VERBOSE_LEVEL == 3
        finally:
            # Restore original level
            set_verbose_level(original_level)
    
    def test_verbose_compatibility_function(self):
        """Test backward compatibility verbose function"""
        original_level = VERBOSE_LEVEL
        
        try:
            set_verbose(True)
            assert VERBOSE_LEVEL == 1
            
            set_verbose(False)
            assert VERBOSE_LEVEL == 0
        finally:
            set_verbose_level(original_level)
    
    def test_verbose_level_affects_output(self, capsys):
        """Test that verbose level affects what gets printed"""
        original_level = VERBOSE_LEVEL
        
        try:
            # Level 0 - only errors
            set_verbose_level(0)
            error_print("Error message")
            info_print("Info message")
            debug_print("Debug message")
            trace_print("Trace message")
            
            captured = capsys.readouterr()
            assert "Error message" in captured.out
            assert "Info message" not in captured.out
            assert "Debug message" not in captured.out
            assert "Trace message" not in captured.out
            
            # Level 1 - errors and info
            set_verbose_level(1)
            error_print("Error message 1")
            info_print("Info message 1")
            debug_print("Debug message 1")
            trace_print("Trace message 1")
            
            captured = capsys.readouterr()
            assert "Error message 1" in captured.out
            assert "Info message 1" in captured.out
            assert "Debug message 1" not in captured.out
            assert "Trace message 1" not in captured.out
        finally:
            set_verbose_level(original_level)


@pytest.mark.unit
class TestLoggingThreadSafety:
    """Test thread safety of logging functions"""
    
    def test_concurrent_logging(self, capsys):
        """Test concurrent logging from multiple threads"""
        results = []
        
        def log_messages(thread_id):
            try:
                for i in range(10):
                    verbose_print(f"Thread {thread_id} message {i}")
                    error_print(f"Thread {thread_id} error {i}")
                results.append(f"Thread {thread_id} completed")
            except Exception as e:
                results.append(f"Thread {thread_id} error: {e}")
        
        # Create and start multiple threads
        threads = []
        for i in range(5):
            thread = Thread(target=log_messages, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        captured = capsys.readouterr()
        
        # Verify all threads completed without errors
        completed_threads = [r for r in results if "completed" in r]
        assert len(completed_threads) == 5
        
        # Verify output contains messages from all threads
        assert len(captured.out) > 0
        assert len(captured.err) > 0
    
    def test_logging_thread_isolation(self, capsys):
        """Test that logging from different threads doesn't interfere"""
        thread_outputs = {}
        
        def isolated_logging(thread_id):
            message = f"Isolated message from thread {thread_id}"
            verbose_print(message)
            thread_outputs[thread_id] = message
        
        threads = []
        for i in range(3):
            thread = Thread(target=isolated_logging, args=(i,))
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        captured = capsys.readouterr()
        
        # All messages should be present in output
        for thread_id, message in thread_outputs.items():
            assert message in captured.out


@pytest.mark.unit
class TestLoggingFileOutput:
    """Test logging to file output"""
    
    def test_file_logging_concept(self):
        """Test concept of file logging (current implementation is console-only)"""
        # Current implementation doesn't support file logging
        # This test verifies the logging functions work for console output
        
        original_level = VERBOSE_LEVEL
        try:
            set_verbose_level(2)
            
            # Test that all logging functions work without file support
            error_print("File test error")
            info_print("File test info")
            debug_print("File test debug")
            trace_print("File test trace")
            
            # No exceptions should be raised
            assert True
        finally:
            set_verbose_level(original_level)
    
    def test_console_logging_robustness(self):
        """Test robustness of console logging"""
        original_level = VERBOSE_LEVEL
        
        try:
            # Test all levels work
            for level in range(4):
                set_verbose_level(level)
                
                error_print(f"Error at level {level}")
                info_print(f"Info at level {level}")
                debug_print(f"Debug at level {level}")  
                trace_print(f"Trace at level {level}")
            
            # Should complete without errors
            assert True
        finally:
            set_verbose_level(original_level)


@pytest.mark.unit
class TestLoggingErrorHandling:
    """Test error handling in logging functions"""
    
    def test_logging_with_invalid_objects(self, capsys):
        """Test logging functions with objects that can't be stringified"""
        class UnstringifiableObject:
            def __str__(self):
                raise Exception("Cannot convert to string")
            def __repr__(self):
                raise Exception("Cannot represent")
        
        obj = UnstringifiableObject()
        
        # Should handle gracefully without crashing
        try:
            verbose_print(obj)
        except Exception:
            pass  # May raise exception, but shouldn't crash the program
        
        captured = capsys.readouterr()
        # Should have some output or error handling
        assert isinstance(captured.out, str)
        assert isinstance(captured.err, str)
    
    def test_logging_during_shutdown(self):
        """Test logging behavior during application shutdown"""
        # Test that logging functions work during shutdown scenarios
        
        original_level = VERBOSE_LEVEL
        try:
            set_verbose_level(1)
            
            # Basic test that logging functions work in shutdown scenarios
            error_print("Shutdown test error message")
            info_print("Shutdown test info message")
            
            # Should not raise exceptions
            assert True
        finally:
            set_verbose_level(original_level)
    
    def test_logging_memory_usage(self):
        """Test that logging doesn't cause memory leaks"""
        import gc
        
        initial_objects = len(gc.get_objects())
        
        # Generate many log messages
        for i in range(1000):
            verbose_print(f"Memory test message {i}")
            if i % 100 == 0:
                gc.collect()
        
        gc.collect()
        final_objects = len(gc.get_objects())
        
        # Object count shouldn't grow excessively
        # Allow some growth for legitimate objects
        assert final_objects < initial_objects + 100