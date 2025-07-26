import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime, timedelta
import calendar
from sqlalchemy import func, and_
from ..tracking.models import DatabaseManager, Sprint, Project
from ..tracking.excel_export import ExcelExporter

class DataViewerWindow:
    def __init__(self, parent, db_manager: DatabaseManager):
        self.parent = parent
        self.db_manager = db_manager
        
        # Create window
        self.window = tk.Toplevel(parent)
        self.window.title("Sprint Data Viewer")
        self.window.geometry("800x600")
        self.window.resizable(True, True)
        
        self.create_widgets()
        self.load_data()
    
    def create_widgets(self):
        """Create window widgets"""
        main_frame = ttk.Frame(self.window, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(2, weight=1)
        
        # Controls frame
        controls_frame = ttk.Frame(main_frame)
        controls_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        controls_frame.columnconfigure(2, weight=1)
        
        # View selector
        ttk.Label(controls_frame, text="View:").grid(row=0, column=0, padx=(0, 10))
        self.view_var = tk.StringVar(value="today")
        view_combo = ttk.Combobox(controls_frame, textvariable=self.view_var, 
                                 values=["today", "week", "month"], state="readonly", width=10)
        view_combo.grid(row=0, column=1, padx=(0, 20))
        view_combo.bind("<<ComboboxSelected>>", self.on_view_change)
        
        # Date selector (for month view)
        self.date_frame = ttk.Frame(controls_frame)
        self.date_frame.grid(row=0, column=2, sticky=tk.W)
        
        self.year_var = tk.IntVar(value=datetime.now().year)
        self.month_var = tk.IntVar(value=datetime.now().month)
        
        ttk.Label(self.date_frame, text="Year:").grid(row=0, column=0, padx=(0, 5))
        year_spinbox = ttk.Spinbox(self.date_frame, from_=2020, to=2030, width=8,
                                  textvariable=self.year_var, command=self.load_data)
        year_spinbox.grid(row=0, column=1, padx=(0, 20))
        
        ttk.Label(self.date_frame, text="Month:").grid(row=0, column=2, padx=(0, 5))
        month_spinbox = ttk.Spinbox(self.date_frame, from_=1, to=12, width=8,
                                   textvariable=self.month_var, command=self.load_data)
        month_spinbox.grid(row=0, column=3, padx=(0, 20))
        
        # Export button
        export_btn = ttk.Button(controls_frame, text="Export to Excel", command=self.export_excel)
        export_btn.grid(row=0, column=3, padx=(20, 0))
        
        # Summary frame
        summary_frame = ttk.LabelFrame(main_frame, text="Summary", padding="10")
        summary_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        summary_frame.columnconfigure(1, weight=1)
        summary_frame.columnconfigure(3, weight=1)
        
        # Summary labels
        ttk.Label(summary_frame, text="Total Sprints:").grid(row=0, column=0, sticky=tk.W)
        self.total_sprints_var = tk.StringVar(value="0")
        ttk.Label(summary_frame, textvariable=self.total_sprints_var, font=("Arial", 10, "bold")).grid(row=0, column=1, sticky=tk.W, padx=(10, 20))
        
        ttk.Label(summary_frame, text="Completed:").grid(row=0, column=2, sticky=tk.W)
        self.completed_sprints_var = tk.StringVar(value="0")
        ttk.Label(summary_frame, textvariable=self.completed_sprints_var, font=("Arial", 10, "bold")).grid(row=0, column=3, sticky=tk.W, padx=(10, 20))
        
        ttk.Label(summary_frame, text="Total Time:").grid(row=1, column=0, sticky=tk.W)
        self.total_time_var = tk.StringVar(value="0h 0m")
        ttk.Label(summary_frame, textvariable=self.total_time_var, font=("Arial", 10, "bold")).grid(row=1, column=1, sticky=tk.W, padx=(10, 20))
        
        ttk.Label(summary_frame, text="Avg per Sprint:").grid(row=1, column=2, sticky=tk.W)
        self.avg_time_var = tk.StringVar(value="0m")
        ttk.Label(summary_frame, textvariable=self.avg_time_var, font=("Arial", 10, "bold")).grid(row=1, column=3, sticky=tk.W, padx=(10, 0))
        
        # Data table
        table_frame = ttk.LabelFrame(main_frame, text="Sprint Data", padding="5")
        table_frame.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        
        # Treeview
        columns = ("date", "time", "project", "task", "duration", "status")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=15)
        
        self.tree.heading("date", text="Date")
        self.tree.heading("time", text="Time")
        self.tree.heading("project", text="Project")
        self.tree.heading("task", text="Task")
        self.tree.heading("duration", text="Duration")
        self.tree.heading("status", text="Status")
        
        self.tree.column("date", width=100)
        self.tree.column("time", width=80)
        self.tree.column("project", width=120)
        self.tree.column("task", width=250)
        self.tree.column("duration", width=80)
        self.tree.column("status", width=80)
        
        self.tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Scrollbars
        v_scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        v_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.tree.config(yscrollcommand=v_scrollbar.set)
        
        h_scrollbar = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        h_scrollbar.grid(row=1, column=0, sticky=(tk.W, tk.E))
        self.tree.config(xscrollcommand=h_scrollbar.set)
        
        # Hide date selector initially (only show for month view)
        self.toggle_date_selector()
    
    def toggle_date_selector(self):
        """Show/hide date selector based on view"""
        if self.view_var.get() == "month":
            self.date_frame.grid()
        else:
            self.date_frame.grid_remove()
    
    def on_view_change(self, event=None):
        """Handle view change"""
        self.toggle_date_selector()
        self.load_data()
    
    def get_date_range(self):
        """Get date range based on current view"""
        now = datetime.now()
        
        if self.view_var.get() == "today":
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = start_date + timedelta(days=1)
        
        elif self.view_var.get() == "week":
            # Get current week (Monday to Sunday)
            days_since_monday = now.weekday()
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_since_monday)
            end_date = start_date + timedelta(days=7)
        
        else:  # month
            year = self.year_var.get()
            month = self.month_var.get()
            start_date = datetime(year, month, 1)
            
            # Get last day of month
            last_day = calendar.monthrange(year, month)[1]
            end_date = datetime(year, month, last_day, 23, 59, 59)
        
        return start_date, end_date
    
    def load_data(self):
        """Load sprint data for current view"""
        start_date, end_date = self.get_date_range()
        
        session = self.db_manager.get_session()
        try:
            # Query sprints in date range
            sprints = session.query(Sprint).filter(
                and_(
                    Sprint.start_time >= start_date,
                    Sprint.start_time < end_date
                )
            ).order_by(Sprint.start_time.desc()).all()
            
            # Clear existing data
            for item in self.tree.get_children():
                self.tree.delete(item)
            
            # Calculate summary statistics
            total_sprints = len(sprints)
            completed_sprints = sum(1 for s in sprints if s.completed)
            total_minutes = sum(s.duration_minutes or 0 for s in sprints)
            avg_minutes = total_minutes / total_sprints if total_sprints > 0 else 0
            
            # Update summary
            self.total_sprints_var.set(str(total_sprints))
            self.completed_sprints_var.set(str(completed_sprints))
            self.total_time_var.set(f"{total_minutes // 60}h {total_minutes % 60}m")
            self.avg_time_var.set(f"{avg_minutes:.1f}m")
            
            # Get project colors
            projects = session.query(Project).all()
            project_colors = {p.name: p.color for p in projects}
            
            # Populate tree
            for sprint in sprints:
                date_str = sprint.start_time.strftime("%Y-%m-%d")
                time_str = sprint.start_time.strftime("%H:%M")
                
                status = "Completed" if sprint.completed else ("Interrupted" if sprint.interrupted else "In Progress")
                duration_str = f"{sprint.duration_minutes}m" if sprint.duration_minutes else "0m"
                
                # Truncate long task descriptions
                task = sprint.task_description
                if len(task) > 50:
                    task = task[:47] + "..."
                
                item_id = self.tree.insert("", tk.END, values=(
                    date_str, time_str, sprint.project_name, task, duration_str, status
                ))
                
                # Color code by project
                if sprint.project_name in project_colors:
                    # This is a simple approach - tkinter treeview doesn't easily support row colors
                    # For a more advanced implementation, you might use tags
                    pass
        
        finally:
            session.close()
    
    def export_excel(self):
        """Export current data to Excel"""
        try:
            # Get file path
            filename = filedialog.asksaveasfilename(
                defaultextension=".xlsx",
                filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
                title="Save Excel Export"
            )
            
            if not filename:
                return
            
            # Create exporter
            exporter = ExcelExporter(self.db_manager)
            
            # Export based on current view
            view = self.view_var.get()
            if view == "month":
                year = self.year_var.get()
                month = self.month_var.get()
                exporter.export_month(year, month, filename)
            else:
                start_date, end_date = self.get_date_range()
                exporter.export_date_range(start_date, end_date, filename)
            
            messagebox.showinfo("Success", f"Data exported to {filename}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export data: {str(e)}")