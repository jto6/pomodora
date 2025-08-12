"""
Multi-level logging utility for Pomodora application.
Provides error, info, debug, and trace logging with global control.
"""

# Global verbose level - can be set from main.py
VERBOSE_LEVEL = 0  # 0=errors only, 1=info, 2=debug, 3=trace

def set_verbose_level(level: int):
    """Set global verbose level (0-3)"""
    global VERBOSE_LEVEL
    VERBOSE_LEVEL = max(0, min(3, level))

def get_verbose_level() -> int:
    """Get current verbose level"""
    return VERBOSE_LEVEL

def set_verbose(enabled: bool):
    """Set verbose mode (for backward compatibility)"""
    set_verbose_level(1 if enabled else 0)

def error_print(*args, **kwargs):
    """Always print errors to stderr regardless of verbose level"""
    import sys
    print(*args, file=sys.stderr, **kwargs)

def info_print(*args, **kwargs):
    """Print informational messages at verbose level 1+"""
    if VERBOSE_LEVEL >= 1:
        print(*args, **kwargs)

def debug_print(*args, **kwargs):
    """Print debug messages at verbose level 2+"""
    if VERBOSE_LEVEL >= 2:
        print("[DEBUG]", *args, **kwargs)

def trace_print(*args, **kwargs):
    """Print trace messages at verbose level 3+"""
    if VERBOSE_LEVEL >= 3:
        print("[TRACE]", *args, **kwargs)

def verbose_print(*args, **kwargs):
    """Legacy function - always prints for backward compatibility"""
    print(*args, **kwargs)