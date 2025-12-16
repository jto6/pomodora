"""
Mixin classes for ModernPomodoroWindow.

These mixins split the main window functionality into logical, cohesive modules.
"""

from gui.mixins.compact_mode_mixin import CompactModeMixin
from gui.mixins.sync_mixin import SyncMixin
from gui.mixins.sprint_mixin import SprintMixin
from gui.mixins.timer_control_mixin import TimerControlMixin
from gui.mixins.task_input_mixin import TaskInputMixin

__all__ = [
    'CompactModeMixin',
    'SyncMixin',
    'SprintMixin',
    'TimerControlMixin',
    'TaskInputMixin',
]
