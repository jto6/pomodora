from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
                             QLabel, QListWidget, QMessageBox, QGroupBox, QGridLayout,
                             QListWidgetItem, QColorDialog, QTabWidget, QWidget, QFrame,
                             QCheckBox, QSplitter, QComboBox)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette, QFont, QFontMetrics
from utils.logging import debug_print, error_print, trace_print


class ActivityClassificationsDialog(QDialog):
    """Comprehensive activity classifications management dialog"""

    def __init__(self, parent=None, db_manager=None):
        super().__init__(parent)
        self.parent_window = parent
        self.db_manager = db_manager
        self.selected_project = None
        self.selected_category = None

        self.setWindowTitle("Activity Classifications")
        self.setFixedSize(800, 600)

        # Apply current theme styling to dialog
        if parent:
            parent.apply_dialog_styling(self)

        self.init_ui()

    def init_ui(self):
        """Initialize the activity classifications dialog UI"""
        main_layout = QVBoxLayout(self)

        # Create tab widget for Task Categories and Projects
        tab_widget = QTabWidget()

        # Task Categories Tab
        task_categories_tab = QWidget()
        task_categories_layout = QHBoxLayout(task_categories_tab)

        # Task Categories - Left panel (list)
        cat_left_widget = QWidget()
        cat_left_layout = QVBoxLayout(cat_left_widget)
        cat_left_layout.addWidget(QLabel("Current Task Categories:"))

        self.category_list = QListWidget()
        self.category_list.itemClicked.connect(self.on_category_selected)
        self.refresh_category_list()
        cat_left_layout.addWidget(self.category_list)

        # Category actions
        cat_actions = QHBoxLayout()
        cat_edit_button = QPushButton("Edit")
        cat_edit_button.clicked.connect(self.edit_selected_category)
        cat_toggle_button = QPushButton("Toggle Active")
        cat_toggle_button.clicked.connect(self.toggle_category_active)
        cat_delete_button = QPushButton("Delete")
        cat_delete_button.clicked.connect(self.delete_selected_category)

        cat_actions.addWidget(cat_edit_button)
        cat_actions.addWidget(cat_toggle_button)
        cat_actions.addWidget(cat_delete_button)
        cat_left_layout.addLayout(cat_actions)

        task_categories_layout.addWidget(cat_left_widget)

        # Task Categories - Right panel (add new)
        cat_right_widget = self.create_add_task_category_panel()
        task_categories_layout.addWidget(cat_right_widget)

        tab_widget.addTab(task_categories_tab, "Task Categories")

        # Projects Tab
        projects_tab = QWidget()
        projects_layout = QHBoxLayout(projects_tab)

        # Projects - Left panel (list)
        proj_left_widget = QWidget()
        proj_left_layout = QVBoxLayout(proj_left_widget)
        proj_left_layout.addWidget(QLabel("Current Projects:"))

        self.project_list = QListWidget()
        self.project_list.itemClicked.connect(self.on_project_selected)
        self.refresh_project_list()
        proj_left_layout.addWidget(self.project_list)

        # Project actions
        proj_actions = QHBoxLayout()
        proj_edit_button = QPushButton("Edit")
        proj_edit_button.clicked.connect(self.edit_selected_project)
        proj_toggle_button = QPushButton("Toggle Active")
        proj_toggle_button.clicked.connect(self.toggle_project_active)
        proj_delete_button = QPushButton("Delete")
        proj_delete_button.clicked.connect(self.delete_selected_project)

        proj_actions.addWidget(proj_edit_button)
        proj_actions.addWidget(proj_toggle_button)
        proj_actions.addWidget(proj_delete_button)
        proj_left_layout.addLayout(proj_actions)

        projects_layout.addWidget(proj_left_widget)

        # Projects - Right panel (add new) - now independent of categories
        proj_right_widget = self.create_add_project_panel()
        projects_layout.addWidget(proj_right_widget)

        tab_widget.addTab(projects_tab, "Projects")

        main_layout.addWidget(tab_widget)

        # Close button
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        main_layout.addWidget(close_button)

    def refresh_project_list(self):
        """Refresh the project list with visual color indicators"""
        self.project_list.clear()
        try:
            projects = self.db_manager.get_all_projects()
            debug_print(f"Found {len(projects)} projects")
            for project in projects:
                debug_print(f"Project: {project['name']}, Color: {project['color']}, Active: {project['active']}")

                # Create custom widget for each project with prominent color indicator
                widget = QWidget()
                layout = QHBoxLayout(widget)
                layout.setContentsMargins(5, 6, 5, 6)  # Increased vertical margins

                # Color indicator (larger square)
                color_label = QLabel()
                color_label.setFixedSize(16, 16)
                if project['active']:
                    color_label.setStyleSheet(f"background-color: {project['color']}; border: 1px solid #333; border-radius: 2px;")
                    text_label = QLabel(project['name'])
                else:
                    color_label.setStyleSheet(f"background-color: {project['color']}; border: 1px solid #333; border-radius: 2px; opacity: 0.5;")
                    text_label = QLabel(f"{project['name']} (inactive)")
                    text_label.setStyleSheet("color: #888;")

                # Project name (normal text color) - fix clipping by removing height constraints
                font = QFont()
                font.setPointSize(10)  # Slightly larger point size
                text_label.setFont(font)
                text_label.setStyleSheet(text_label.styleSheet())  # Keep color styling only

                # Set text eliding to clip long text with ellipsis
                text_label.setWordWrap(False)
                text_label.setTextInteractionFlags(Qt.NoTextInteraction)
                text_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)  # Center vertically
                # Remove fixed height - let the label size itself

                # Calculate available width and elide text if needed
                available_width = 200  # Approximate available width in the list
                font_metrics = text_label.fontMetrics()
                elided_text = font_metrics.elidedText(text_label.text(), Qt.ElideRight, available_width)
                text_label.setText(elided_text)

                layout.addWidget(color_label)
                layout.addWidget(text_label, 1)  # Give text label stretch factor to take available space

                # Create list item and set custom widget
                item = QListWidgetItem()
                item.setData(Qt.UserRole, project)
                # Set explicit size hint to ensure enough vertical space
                from PySide6.QtCore import QSize
                item.setSizeHint(QSize(widget.sizeHint().width(), 32))

                self.project_list.addItem(item)
                self.project_list.setItemWidget(item, widget)

        except Exception as e:
            error_print(f"Error loading projects: {e}")
            import traceback
            traceback.print_exc()

    def on_project_selected(self, item):
        """Handle project selection"""
        project = item.data(Qt.UserRole)
        if project:
            self.selected_project = project

    def edit_selected_project(self):
        """Edit the selected project"""
        if not hasattr(self, 'selected_project') or not self.selected_project:
            QMessageBox.warning(self, "Error", "Please select a project to edit.")
            return

        # TODO: Implement project editing dialog
        QMessageBox.information(self, "Info", "Project editing will be implemented in a future update.")

    def toggle_project_active(self):
        """Toggle active status of selected project"""
        if not hasattr(self, 'selected_project') or not self.selected_project:
            QMessageBox.warning(self, "Error", "Please select a project to toggle.")
            return

        try:
            project = self.selected_project
            new_status = self.db_manager.toggle_project_active(project['id'])

            if new_status is not None:
                self.refresh_project_list()  # Refresh the activity classifications display
                if self.parent_window:
                    self.parent_window.load_projects()  # Refresh the main window dropdown
            else:
                QMessageBox.warning(self, "Error", "Failed to toggle project status.")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to toggle project: {str(e)}")

    def delete_selected_project(self):
        """Delete the selected project"""
        if not hasattr(self, 'selected_project') or not self.selected_project:
            QMessageBox.warning(self, "Error", "Please select a project to delete.")
            return

        try:
            project = self.selected_project

            # Confirm deletion
            reply = QMessageBox.question(
                self,
                "Confirm Deletion",
                f"Are you sure you want to delete project '{project['name']}'?\n\nThis action cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                success, message = self.db_manager.delete_project(project['id'])

                if success:
                    self.refresh_project_list()  # Refresh the activity classifications display
                    if self.parent_window:
                        self.parent_window.load_projects()  # Refresh the main window dropdown
                    # Clear selection since project is deleted
                    self.selected_project = None
                else:
                    QMessageBox.warning(self, "Cannot Delete", message)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to delete project: {str(e)}")

    # Category management methods
    def refresh_category_list(self):
        """Refresh the task category list with visual color indicators"""
        self.category_list.clear()
        try:
            task_categories = self.db_manager.get_all_task_categories()
            debug_print(f"Found {len(task_categories)} task categories")
            for task_category in task_categories:
                debug_print(f"Task Category: {task_category['name']}, Color: {task_category['color']}, Active: {task_category['active']}")

                # Create custom widget for each task category with prominent color indicator
                widget = QWidget()
                layout = QHBoxLayout(widget)
                layout.setContentsMargins(5, 6, 5, 6)  # Increased vertical margins

                # Color indicator (larger square)
                color_label = QLabel()
                color_label.setFixedSize(16, 16)
                if task_category['active']:
                    color_label.setStyleSheet(f"background-color: {task_category['color']}; border: 1px solid #333; border-radius: 2px;")
                    text_label = QLabel(task_category['name'])
                else:
                    color_label.setStyleSheet(f"background-color: {task_category['color']}; border: 1px solid #333; border-radius: 2px; opacity: 0.5;")
                    text_label = QLabel(f"{task_category['name']} (inactive)")
                    text_label.setStyleSheet("color: #888;")

                # Task category name (normal text color) - fix clipping by removing height constraints
                font = QFont()
                font.setPointSize(10)  # Slightly larger point size
                text_label.setFont(font)
                text_label.setStyleSheet(text_label.styleSheet())  # Keep color styling only

                # Set text eliding to clip long text with ellipsis
                text_label.setWordWrap(False)
                text_label.setTextInteractionFlags(Qt.NoTextInteraction)
                text_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)  # Center vertically
                # Remove fixed height - let the label size itself

                # Calculate available width and elide text if needed
                available_width = 200  # Approximate available width in the list
                font_metrics = text_label.fontMetrics()
                elided_text = font_metrics.elidedText(text_label.text(), Qt.ElideRight, available_width)
                text_label.setText(elided_text)

                layout.addWidget(color_label)
                layout.addWidget(text_label, 1)  # Give text label stretch factor to take available space

                # Create list item and set custom widget
                item = QListWidgetItem()
                item.setData(Qt.UserRole, task_category)
                # Set explicit size hint to ensure enough vertical space
                from PySide6.QtCore import QSize
                item.setSizeHint(QSize(widget.sizeHint().width(), 32))

                self.category_list.addItem(item)
                self.category_list.setItemWidget(item, widget)

        except Exception as e:
            error_print(f"Error loading task categories: {e}")
            import traceback
            traceback.print_exc()

    def on_category_selected(self, item):
        """Handle task category selection"""
        task_category = item.data(Qt.UserRole)
        if task_category:
            self.selected_category = task_category

    def edit_selected_category(self):
        """Edit the selected task category"""
        if not hasattr(self, 'selected_category') or not self.selected_category:
            QMessageBox.warning(self, "Error", "Please select a task category to edit.")
            return

        # TODO: Implement task category editing dialog
        QMessageBox.information(self, "Info", "Task category editing will be implemented in a future update.")

    def toggle_category_active(self):
        """Toggle active status of selected task category"""
        if not hasattr(self, 'selected_category') or not self.selected_category:
            QMessageBox.warning(self, "Error", "Please select a task category to toggle.")
            return

        try:
            task_category = self.selected_category
            new_status = self.db_manager.toggle_task_category_active(task_category['id'])

            if new_status is not None:
                self.refresh_category_list()  # Refresh the task category display
                if self.parent_window:
                    self.parent_window.load_task_categories()  # Refresh the main window dropdown
            else:
                QMessageBox.warning(self, "Error", "Failed to toggle task category status.")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to toggle task category: {str(e)}")

    def delete_selected_category(self):
        """Delete the selected task category"""
        if not hasattr(self, 'selected_category') or not self.selected_category:
            QMessageBox.warning(self, "Error", "Please select a task category to delete.")
            return

        try:
            task_category = self.selected_category

            # Confirm deletion
            reply = QMessageBox.question(
                self,
                "Confirm Deletion",
                f"Are you sure you want to delete task category '{task_category['name']}'?\n\nThis action cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                success, message = self.db_manager.delete_task_category(task_category['id'])

                if success:
                    self.refresh_category_list()  # Refresh the task category display
                    if self.parent_window:
                        self.parent_window.load_task_categories()  # Refresh the main window dropdown
                    # Clear selection since task category is deleted
                    self.selected_category = None
                else:
                    QMessageBox.warning(self, "Cannot Delete", message)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to delete task category: {str(e)}")

    def create_add_task_category_panel(self):
        """Create the add task category panel"""
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        # Add new task category section
        add_group = QGroupBox("Add New Task Category")
        add_layout = QVBoxLayout(add_group)

        # Task category name
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Name:"))
        self.new_task_category_input = QLineEdit()
        name_layout.addWidget(self.new_task_category_input)
        add_layout.addLayout(name_layout)

        # Color selection (reuse the color palette)
        color_section = self.create_color_selector("task_category")
        add_layout.addWidget(color_section)

        # Add button
        add_button = QPushButton("Add Task Category")
        add_button.clicked.connect(self.add_new_task_category)
        add_layout.addWidget(add_button)

        right_layout.addWidget(add_group)
        right_layout.addStretch()

        return right_widget

    def create_add_project_panel(self):
        """Create the add project panel"""
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        # Add new project section
        add_group = QGroupBox("Add New Project")
        add_layout = QVBoxLayout(add_group)

        # Project name
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Name:"))
        self.new_project_input = QLineEdit()
        name_layout.addWidget(self.new_project_input)
        add_layout.addLayout(name_layout)

        # Projects are now independent of categories - no category selection needed

        # Color selection (reuse the color palette)
        color_section = self.create_color_selector("project")
        add_layout.addWidget(color_section)

        # Add button
        add_button = QPushButton("Add Project")
        add_button.clicked.connect(self.add_new_project)
        add_layout.addWidget(add_button)

        right_layout.addWidget(add_group)
        right_layout.addStretch()

        return right_widget

    def create_color_selector(self, prefix):
        """Create the color selection widget"""
        color_widget = QWidget()
        color_layout = QVBoxLayout(color_widget)

        # Color selection label
        color_label = QLabel("Choose Color:")
        color_layout.addWidget(color_label)

        # Color palette grid
        palette_layout = QGridLayout()
        setattr(self, f"{prefix}_selected_color", "#3498db")  # Default blue
        setattr(self, f"{prefix}_color_buttons", [])

        # Primary colors and distinct grays with yellow variations
        colors = [
            "#e74c3c", "#3498db", "#2ecc71", "#f39c12", "#9b59b6", "#1abc9c",  # Primary colors
            "#e67e22", "#34495e", "#95a5a6", "#16a085", "#f1c40f", "#27ae60",  # More colors with yellow
            "#2c3e50", "#7f8c8d", "#bdc3c7", "#ecf0f1", "#454545", "#f7dc6f"   # Grays with light yellow
        ]

        for i, color in enumerate(colors):
            row, col = divmod(i, 6)
            color_btn = QPushButton()
            color_btn.setFixedSize(20, 20)
            color_btn.setMinimumSize(20, 20)
            color_btn.setMaximumSize(20, 20)
            color_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color};
                    border: 1px solid #333;
                    border-radius: 2px;
                    min-height: 20px;
                    max-height: 20px;
                    height: 20px;
                    min-width: 20px;
                    max-width: 20px;
                    width: 20px;
                    margin: 0px;
                    padding: 0px;
                }}
            """)
            color_btn.clicked.connect(lambda checked, c=color, p=prefix: self.select_color_for_type(c, p))
            getattr(self, f"{prefix}_color_buttons").append(color_btn)
            palette_layout.addWidget(color_btn, row, col)

        palette_layout.setSpacing(2)
        palette_layout.setContentsMargins(0, 0, 0, 0)

        palette_widget = QWidget()
        palette_widget.setLayout(palette_layout)
        color_layout.addWidget(palette_widget)

        # Color preview section
        preview_layout = QHBoxLayout()
        preview_layout.addWidget(QLabel("Selected:"))

        color_preview = QFrame()
        color_preview.setFixedSize(40, 30)
        color_preview.setStyleSheet(f"background-color: #3498db; border: 1px solid #333;")
        setattr(self, f"{prefix}_color_preview", color_preview)
        preview_layout.addWidget(color_preview)

        custom_color_btn = QPushButton("Custom...")
        custom_color_btn.clicked.connect(lambda: self.open_color_dialog_for_type(prefix))
        preview_layout.addWidget(custom_color_btn)
        preview_layout.addStretch()

        color_layout.addWidget(QWidget())  # Spacer
        color_layout.addLayout(preview_layout)

        return color_widget

    def select_color_for_type(self, color, prefix):
        """Select a color for a specific type (category or project)"""
        setattr(self, f"{prefix}_selected_color", color)
        color_preview = getattr(self, f"{prefix}_color_preview")
        color_preview.setStyleSheet(f"background-color: {color}; border: 1px solid #333;")

    def open_color_dialog_for_type(self, prefix):
        """Open Qt color picker dialog for a specific type"""
        current_color = getattr(self, f"{prefix}_selected_color")
        color = QColorDialog.getColor(QColor(current_color), self, "Choose Color")
        if color.isValid():
            hex_color = color.name()
            self.select_color_for_type(hex_color, prefix)


    def add_new_task_category(self):
        """Add a new task category"""
        name = self.new_task_category_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "Please enter a task category name.")
            return

        try:
            selected_color = getattr(self, "task_category_selected_color", "#3498db")
            self.db_manager.create_task_category(name, selected_color)
            self.refresh_category_list()
            self.refresh_project_list()  # Refresh projects since new auto-project was created
            if self.parent_window:
                self.parent_window.load_projects()  # Refresh main window dropdown
                self.parent_window.load_task_categories()  # Refresh task category dropdown
            self.new_task_category_input.clear()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to add task category: {str(e)}")

    def add_new_project(self):
        """Add a new project (independent of categories now)"""
        name = self.new_project_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "Please enter a project name.")
            return

        try:
            selected_color = getattr(self, "project_selected_color", "#3498db")
            self.db_manager.create_project(name, selected_color)
            self.refresh_project_list()
            if self.parent_window:
                self.parent_window.load_projects()  # Refresh main window dropdown
            self.new_project_input.clear()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to add project: {str(e)}")