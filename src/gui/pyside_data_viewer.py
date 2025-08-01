from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QTableWidget, QTableWidgetItem,
                               QComboBox, QDateEdit, QTabWidget, QFrame,
                               QHeaderView, QMessageBox, QFileDialog)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QFont
from datetime import datetime, timedelta, date
import calendar

class PySideDataViewerWindow(QWidget):
    """Modern PySide6 data viewer for Pomodoro sprints"""

    def __init__(self, parent, db_manager):
        super().__init__()
        self.parent = parent
        self.db_manager = db_manager
        self.current_filter = "day"
        self.current_date = date.today()

        self.init_ui()
        self.apply_styling()
        self.load_data()

    def init_ui(self):
        """Initialize the data viewer UI"""
        self.setWindowTitle("Pomodora - Data Viewer")
        self.setFixedSize(900, 600)

        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header
        self.create_header(layout)

        # Filter controls
        self.create_filter_controls(layout)

        # Tabs for different views
        self.create_tabs(layout)

        # Action buttons
        self.create_action_buttons(layout)

    def create_header(self, layout):
        """Create header section"""
        header_frame = QFrame()
        header_frame.setObjectName("headerFrame")
        header_layout = QHBoxLayout(header_frame)

        title_label = QLabel("📊 Sprint Data Viewer")
        title_label.setObjectName("titleLabel")
        title_label.setAlignment(Qt.AlignCenter)

        header_layout.addWidget(title_label)
        layout.addWidget(header_frame)

    def create_filter_controls(self, layout):
        """Create filtering controls"""
        filter_frame = QFrame()
        filter_frame.setObjectName("filterFrame")
        filter_layout = QHBoxLayout(filter_frame)

        # View type selector
        filter_layout.addWidget(QLabel("View:"))
        self.view_combo = QComboBox()
        self.view_combo.addItems(["Day", "Week", "Month"])
        self.view_combo.currentTextChanged.connect(self.on_view_changed)
        filter_layout.addWidget(self.view_combo)

        # Date selector
        filter_layout.addWidget(QLabel("Date:"))
        self.date_edit = QDateEdit()
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.dateChanged.connect(self.on_date_changed)
        filter_layout.addWidget(self.date_edit)

        # Navigation buttons
        self.prev_button = QPushButton("◀ Previous")
        self.prev_button.clicked.connect(self.previous_period)
        filter_layout.addWidget(self.prev_button)

        self.next_button = QPushButton("Next ▶")
        self.next_button.clicked.connect(self.next_period)
        filter_layout.addWidget(self.next_button)

        # Today button
        today_button = QPushButton("Today")
        today_button.clicked.connect(self.go_to_today)
        filter_layout.addWidget(today_button)

        filter_layout.addStretch()

        # Summary stats
        self.stats_label = QLabel("Loading...")
        self.stats_label.setObjectName("statsLabel")
        filter_layout.addWidget(self.stats_label)

        layout.addWidget(filter_frame)

    def create_tabs(self, layout):
        """Create tabbed interface"""
        self.tab_widget = QTabWidget()

        # Sprint list tab
        self.create_sprint_list_tab()

        # Summary tab
        self.create_summary_tab()

        layout.addWidget(self.tab_widget)

    def create_sprint_list_tab(self):
        """Create the sprint list table"""
        sprint_widget = QWidget()
        sprint_layout = QVBoxLayout(sprint_widget)

        # Sprint table
        self.sprint_table = QTableWidget()
        self.sprint_table.setColumnCount(6)
        self.sprint_table.setHorizontalHeaderLabels([
            "Date", "Time", "Project", "Task", "Duration", "Status"
        ])

        # Configure table
        header = self.sprint_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # Date
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Time
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Project
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)           # Task
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Duration
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)  # Status

        self.sprint_table.setAlternatingRowColors(True)
        self.sprint_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        sprint_layout.addWidget(self.sprint_table)
        self.tab_widget.addTab(sprint_widget, "📋 Sprint List")

    def create_summary_tab(self):
        """Create summary statistics tab"""
        summary_widget = QWidget()
        summary_layout = QVBoxLayout(summary_widget)

        # Summary frame
        self.summary_frame = QFrame()
        self.summary_frame.setObjectName("summaryFrame")
        summary_frame_layout = QVBoxLayout(self.summary_frame)

        self.summary_label = QLabel("Loading summary...")
        self.summary_label.setObjectName("summaryText")
        self.summary_label.setAlignment(Qt.AlignTop)
        self.summary_label.setWordWrap(True)

        summary_frame_layout.addWidget(self.summary_label)
        summary_layout.addWidget(self.summary_frame)

        self.tab_widget.addTab(summary_widget, "📈 Summary")

    def create_action_buttons(self, layout):
        """Create action buttons"""
        button_layout = QHBoxLayout()

        refresh_button = QPushButton("🔄 Refresh")
        refresh_button.clicked.connect(self.load_data)
        button_layout.addWidget(refresh_button)

        export_button = QPushButton("📁 Export to Excel")
        export_button.clicked.connect(self.export_current_view)
        button_layout.addWidget(export_button)

        button_layout.addStretch()

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)
        button_layout.addWidget(close_button)

        layout.addLayout(button_layout)

    def apply_styling(self):
        """Apply modern styling"""
        style = """
        QWidget {
            background: #f8f9fa;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui;
        }

        #headerFrame {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #667eea, stop:1 #764ba2);
            border-radius: 15px;
            padding: 15px;
            margin-bottom: 10px;
        }

        #titleLabel {
            font-size: 20px;
            font-weight: bold;
            color: white;
        }

        #filterFrame {
            background: white;
            border-radius: 10px;
            padding: 15px;
            border: 2px solid #dee2e6;
        }

        #statsLabel {
            font-weight: bold;
            color: #495057;
            background: #e9ecef;
            padding: 8px 12px;
            border-radius: 8px;
        }

        #summaryFrame {
            background: white;
            border-radius: 10px;
            padding: 20px;
            border: 2px solid #dee2e6;
        }

        #summaryText {
            font-size: 14px;
            line-height: 1.6;
            color: #495057;
        }

        QTableWidget {
            background: white;
            border: 2px solid #dee2e6;
            border-radius: 10px;
            gridline-color: #e9ecef;
            font-size: 13px;
        }

        QTableWidget::item {
            padding: 8px;
            border-bottom: 1px solid #e9ecef;
        }

        QTableWidget::item:selected {
            background: #667eea;
            color: white;
        }

        QHeaderView::section {
            background: #f8f9fa;
            border: 1px solid #dee2e6;
            padding: 10px 8px;
            font-weight: bold;
            color: #495057;
        }

        QPushButton {
            background: #667eea;
            color: white;
            border: none;
            border-radius: 8px;
            padding: 8px 16px;
            font-weight: bold;
            font-size: 13px;
        }

        QPushButton:hover {
            background: #5a6fd8;
        }

        QPushButton:pressed {
            background: #4c63d2;
        }

        QComboBox, QDateEdit {
            background: white;
            border: 2px solid #dee2e6;
            border-radius: 6px;
            padding: 6px 10px;
            font-size: 13px;
        }

        QComboBox:focus, QDateEdit:focus {
            border-color: #667eea;
        }

        QTabWidget::pane {
            border: 2px solid #dee2e6;
            border-radius: 10px;
            background: white;
        }

        QTabBar::tab {
            background: #e9ecef;
            border: none;
            padding: 10px 20px;
            margin-right: 2px;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
            font-weight: bold;
        }

        QTabBar::tab:selected {
            background: white;
            color: #667eea;
        }

        QTabBar::tab:hover {
            background: #f8f9fa;
        }
        """

        self.setStyleSheet(style)

    def on_view_changed(self, view):
        """Handle view type change"""
        self.current_filter = view.lower()
        self.load_data()

    def on_date_changed(self, qdate):
        """Handle date change"""
        self.current_date = qdate.toPython()
        self.load_data()

    def previous_period(self):
        """Go to previous period"""
        if self.current_filter == "day":
            self.current_date -= timedelta(days=1)
        elif self.current_filter == "week":
            self.current_date -= timedelta(weeks=1)
        elif self.current_filter == "month":
            if self.current_date.month == 1:
                self.current_date = self.current_date.replace(year=self.current_date.year - 1, month=12)
            else:
                self.current_date = self.current_date.replace(month=self.current_date.month - 1)

        self.date_edit.setDate(QDate(self.current_date))
        self.load_data()

    def next_period(self):
        """Go to next period"""
        if self.current_filter == "day":
            self.current_date += timedelta(days=1)
        elif self.current_filter == "week":
            self.current_date += timedelta(weeks=1)
        elif self.current_filter == "month":
            if self.current_date.month == 12:
                self.current_date = self.current_date.replace(year=self.current_date.year + 1, month=1)
            else:
                self.current_date = self.current_date.replace(month=self.current_date.month + 1)

        self.date_edit.setDate(QDate(self.current_date))
        self.load_data()

    def go_to_today(self):
        """Go to today's date"""
        self.current_date = date.today()
        self.date_edit.setDate(QDate.currentDate())
        self.load_data()

    def load_data(self):
        """Load and display sprint data"""
        try:
            sprints = self.get_sprints_for_period()
            self.populate_sprint_table(sprints)
            self.update_summary(sprints)
            self.update_stats_label(sprints)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load data: {str(e)}")

    def get_sprints_for_period(self):
        """Get sprints for the current period"""
        session = self.db_manager.get_session()
        try:
            from tracking.models import Sprint, Project, TaskCategory
            from sqlalchemy.orm import joinedload

            if self.current_filter == "day":
                start_date = datetime.combine(self.current_date, datetime.min.time())
                end_date = start_date + timedelta(days=1)
            elif self.current_filter == "week":
                # Start of week (Monday)
                days_since_monday = self.current_date.weekday()
                start_of_week = self.current_date - timedelta(days=days_since_monday)
                start_date = datetime.combine(start_of_week, datetime.min.time())
                end_date = start_date + timedelta(days=7)
            elif self.current_filter == "month":
                start_date = datetime.combine(
                    self.current_date.replace(day=1), datetime.min.time()
                )
                if self.current_date.month == 12:
                    next_month = start_date.replace(year=start_date.year + 1, month=1)
                else:
                    next_month = start_date.replace(month=start_date.month + 1)
                end_date = next_month

            # Eager load related objects to avoid lazy loading issues
            sprints = session.query(Sprint).options(
                joinedload(Sprint.project),
                joinedload(Sprint.task_category)
            ).filter(
                Sprint.start_time >= start_date,
                Sprint.start_time < end_date
            ).order_by(Sprint.start_time.asc()).all()
            
            # Create detached objects with all data loaded
            detached_sprints = []
            for sprint in sprints:
                # Access all lazy-loaded attributes while session is active
                project_name = sprint.project.name if sprint.project else "Unknown Project"
                task_category_name = sprint.task_category.name if sprint.task_category else "Unknown Category"
                
                # Create a simple data object to avoid session dependency
                sprint_data = type('SprintData', (), {
                    'id': sprint.id,
                    'start_time': sprint.start_time,
                    'end_time': sprint.end_time,
                    'task_description': sprint.task_description,
                    'completed': sprint.completed,
                    'interrupted': sprint.interrupted,
                    'duration_minutes': sprint.duration_minutes,
                    'project_name': project_name,
                    'task_category_name': task_category_name
                })()
                
                detached_sprints.append(sprint_data)
            
            return detached_sprints

        finally:
            session.close()

    def populate_sprint_table(self, sprints):
        """Populate the sprint table with data"""
        self.sprint_table.setRowCount(len(sprints))

        for row, sprint in enumerate(sprints):
            # Date
            date_item = QTableWidgetItem(sprint.start_time.strftime("%Y-%m-%d"))
            self.sprint_table.setItem(row, 0, date_item)

            # Time
            time_item = QTableWidgetItem(sprint.start_time.strftime("%H:%M"))
            self.sprint_table.setItem(row, 1, time_item)

            # Project
            project_item = QTableWidgetItem(sprint.project_name)
            self.sprint_table.setItem(row, 2, project_item)

            # Task
            task_item = QTableWidgetItem(sprint.task_description)
            self.sprint_table.setItem(row, 3, task_item)

            # Duration
            if sprint.end_time and sprint.start_time:
                duration = sprint.end_time - sprint.start_time
                duration_mins = int(duration.total_seconds() / 60)
                duration_item = QTableWidgetItem(f"{duration_mins} min")
            else:
                duration_item = QTableWidgetItem("N/A")
            self.sprint_table.setItem(row, 4, duration_item)

            # Status
            status = "✅ Completed" if sprint.completed else ("❌ Interrupted" if sprint.interrupted else "⏸️ Incomplete")
            status_item = QTableWidgetItem(status)
            self.sprint_table.setItem(row, 5, status_item)

    def update_summary(self, sprints):
        """Update the summary tab"""
        total_sprints = len(sprints)
        completed_sprints = len([s for s in sprints if s.completed])
        interrupted_sprints = len([s for s in sprints if s.interrupted])

        total_time = 0
        projects = {}

        for sprint in sprints:
            if sprint.end_time and sprint.start_time:
                duration = sprint.end_time - sprint.start_time
                total_time += duration.total_seconds() / 60

            project = sprint.project_name
            if project not in projects:
                projects[project] = 0
            projects[project] += 1

        # Calculate completion rate
        completion_rate = (completed_sprints / total_sprints * 100) if total_sprints > 0 else 0

        # Format time
        hours = int(total_time / 60)
        minutes = int(total_time % 60)

        # Generate summary text
        period_name = self.current_filter.title()
        period_date = self.current_date.strftime("%Y-%m-%d")

        summary_text = f"""
<h2>📊 {period_name} Summary - {period_date}</h2>

<h3>🎯 Sprint Statistics</h3>
<ul>
<li><b>Total Sprints:</b> {total_sprints}</li>
<li><b>Completed:</b> {completed_sprints} ({completion_rate:.1f}%)</li>
<li><b>Interrupted:</b> {interrupted_sprints}</li>
<li><b>Total Focus Time:</b> {hours}h {minutes}m</li>
</ul>

<h3>📋 Projects Breakdown</h3>
<ul>
"""

        if projects:
            for project, count in sorted(projects.items(), key=lambda x: x[1], reverse=True):
                percentage = (count / total_sprints * 100) if total_sprints > 0 else 0
                summary_text += f"<li><b>{project}:</b> {count} sprints ({percentage:.1f}%)</li>\n"
        else:
            summary_text += "<li><i>No projects found</i></li>\n"

        summary_text += "</ul>"

        if total_sprints == 0:
            summary_text += "\n<p><i>No sprints found for this period.</i></p>"

        self.summary_label.setText(summary_text)

    def update_stats_label(self, sprints):
        """Update the stats label in the header"""
        total = len(sprints)
        completed = len([s for s in sprints if s.completed])

        if total > 0:
            total_time = sum(
                (s.end_time - s.start_time).total_seconds() / 60
                for s in sprints
                if s.end_time and s.start_time
            )
            hours = int(total_time / 60)
            minutes = int(total_time % 60)

            self.stats_label.setText(
                f"📊 {total} sprints • {completed} completed • {hours}h {minutes}m total"
            )
        else:
            self.stats_label.setText("📊 No data for this period")

    def export_current_view(self):
        """Export current view to Excel"""
        try:
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Current View",
                f"pomodora_{self.current_filter}_{self.current_date.strftime('%Y%m%d')}.xlsx",
                "Excel Files (*.xlsx)"
            )

            if file_path:
                sprints = self.get_sprints_for_period()
                self.export_sprints_to_excel(sprints, file_path)
                QMessageBox.information(self, "Export Complete",
                                      f"Data exported successfully to:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export data:\n{str(e)}")

    def export_sprints_to_excel(self, sprints, file_path):
        """Export sprints to Excel file"""
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment

            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = f"Sprints_{self.current_filter.title()}"

            # Headers
            headers = ["Date", "Time", "Project", "Task", "Duration (min)", "Status"]
            for col, header in enumerate(headers, 1):
                cell = ws.cell(row=1, column=col, value=header)
                cell.font = Font(bold=True)
                cell.fill = PatternFill(start_color="DDDDDD", end_color="DDDDDD", fill_type="solid")
                cell.alignment = Alignment(horizontal="center")

            # Data
            for row, sprint in enumerate(sprints, 2):
                ws.cell(row=row, column=1, value=sprint.start_time.strftime("%Y-%m-%d"))
                ws.cell(row=row, column=2, value=sprint.start_time.strftime("%H:%M"))
                ws.cell(row=row, column=3, value=sprint.project_name)
                ws.cell(row=row, column=4, value=sprint.task_description)

                if sprint.end_time and sprint.start_time:
                    duration = (sprint.end_time - sprint.start_time).total_seconds() / 60
                    ws.cell(row=row, column=5, value=f"{int(duration)}")
                else:
                    ws.cell(row=row, column=5, value="N/A")

                status = "Completed" if sprint.completed else ("Interrupted" if sprint.interrupted else "Incomplete")
                ws.cell(row=row, column=6, value=status)

            # Auto-adjust column widths
            for column in ws.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                ws.column_dimensions[column_letter].width = adjusted_width

            wb.save(file_path)

        except ImportError:
            raise Exception("openpyxl library not found. Please install it with: pip install openpyxl")