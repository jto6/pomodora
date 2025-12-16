"""
Compact mode mixin for ModernPomodoroWindow.

Provides functionality for toggling between normal and compact (minimal) view modes.
"""

from PySide6.QtWidgets import QFrame


class CompactModeMixin:
    """Mixin providing compact mode functionality."""

    def toggle_compact_mode(self):
        """Toggle between normal and compact view"""
        self.compact_mode = not self.compact_mode

        # Compact mode state is not saved - app always starts in normal mode

        if self.compact_mode:
            # Enter compact mode
            self.enter_compact_mode()
        else:
            # Exit compact mode
            self.exit_compact_mode()

    def enter_compact_mode(self):
        """Enter compact mode with minimal layout"""
        # Store current layout state for restoration
        timer_frame = self.centralWidget().findChild(QFrame, "timerFrame")
        if timer_frame and timer_frame.layout():
            self._stored_spacing = timer_frame.layout().spacing()
            self._stored_margins = timer_frame.layout().contentsMargins()

        # Hide everything except timer
        self.centralWidget().findChild(QFrame, "headerFrame").hide()
        self.centralWidget().findChild(QFrame, "inputFrame").hide()
        self.centralWidget().findChild(QFrame, "controlFrame").hide()
        self.centralWidget().findChild(QFrame, "statusFrame").hide()

        # Show compact controls and sync their state
        self.compact_controls_frame.show()
        self.sync_compact_buttons()  # Ensure buttons show correct state for current timer

        # Resize window first
        self.setFixedSize(*self.compact_size)
        self.compact_action.setText('Exit Compact Mode')

        # Apply compact styling based on current theme
        self.apply_compact_styling()

        # Adjust layout spacing for compact mode - minimize spacing for full-window blue area
        if timer_frame and timer_frame.layout():
            timer_frame.layout().setSpacing(1)  # Minimal spacing between elements
            timer_frame.layout().setContentsMargins(0, 0, 0, 0)  # No margins around content

        # Remove main layout margins to let timer frame fill entire window
        main_layout = self.centralWidget().layout()
        if main_layout:
            self._stored_main_margins = main_layout.contentsMargins()  # Store for restoration
            main_layout.setContentsMargins(0, 0, 0, 0)  # No margins around main layout
            main_layout.setSpacing(0)  # No spacing between main layout elements

    def exit_compact_mode(self):
        """Exit compact mode and restore normal layout"""
        # Hide compact controls
        self.compact_controls_frame.hide()

        # Restore window size first
        self.setFixedSize(*self.normal_size)
        self.compact_action.setText('Toggle Compact Mode')

        # Show all elements
        self.centralWidget().findChild(QFrame, "headerFrame").show()
        self.centralWidget().findChild(QFrame, "inputFrame").show()
        self.centralWidget().findChild(QFrame, "controlFrame").show()
        self.centralWidget().findChild(QFrame, "statusFrame").show()

        # Restore layout spacing to stored values or defaults
        timer_frame = self.centralWidget().findChild(QFrame, "timerFrame")
        if timer_frame and timer_frame.layout():
            # Use stored values if available, otherwise use defaults
            spacing = getattr(self, '_stored_spacing', 10)
            margins = getattr(self, '_stored_margins', None)

            timer_frame.layout().setSpacing(spacing)
            if margins:
                timer_frame.layout().setContentsMargins(margins)
            else:
                timer_frame.layout().setContentsMargins(11, 11, 11, 11)

        # Restore main layout margins
        main_layout = self.centralWidget().layout()
        if main_layout:
            stored_main_margins = getattr(self, '_stored_main_margins', None)
            if stored_main_margins:
                main_layout.setContentsMargins(stored_main_margins)
            else:
                main_layout.setContentsMargins(25, 25, 25, 25)  # Default margins
            main_layout.setSpacing(5)  # Default spacing

        # Reapply normal styling completely
        self.apply_modern_styling()

        # Force layout update to prevent corruption
        self.centralWidget().updateGeometry()
        self.update()
        self.repaint()
