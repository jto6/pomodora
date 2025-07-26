import tkinter as tk
from tkinter import ttk, messagebox
import threading
from datetime import datetime
from typing import Optional

from ..timer.pomodoro import PomodoroTimer, TimerState
from ..tracking.models import DatabaseManager, Project, Sprint, Settings
from .project_manager import ProjectManagerDialog
from .data_viewer import DataViewerWindow
from .settings_dialog import SettingsDialog
from .alarm import AlarmManager

class MainWindow:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Pomodora - Sprint Tracker")
        self.root.geometry("400x500")
        self.root.resizable(True, True)
        
        # Initialize components
        self.db_manager = DatabaseManager()
        self.db_manager.initialize_default_projects()
        self.db_manager.initialize_default_settings()
        
        self.timer = None
        self.alarm_manager = AlarmManager()
        self.current_sprint = None
        self.compact_mode = False
        
        # Load settings
        self.load_settings()
        
        # Setup timer
        self.setup_timer()
        
        # Create GUI
        self.create_widgets()
        self.update_display()
        
        # Bind window events
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Start GUI update loop
        self.update_gui()
    
    def load_settings(self):
        """Load settings from database"""
        session = self.db_manager.get_session()
        try:
            self.sprint_duration = Settings.get_setting(session, "sprint_duration", 25)
            self.break_duration = Settings.get_setting(session, "break_duration", 5)
            self.alarm_volume = Settings.get_setting(session, "alarm_volume", 0.7)
        finally:
            session.close()
        
        self.alarm_manager.set_volume(self.alarm_volume)
    
    def setup_timer(self):
        """Initialize the Pomodoro timer"""
        self.timer = PomodoroTimer(self.sprint_duration, self.break_duration)
        self.timer.on_sprint_complete = self.on_sprint_complete
        self.timer.on_break_complete = self.on_break_complete
        self.timer.on_state_change = self.on_timer_state_change
    
    def create_widgets(self):
        """Create the main GUI widgets"""
        # Main container
        self.main_frame = ttk.Frame(self.root, padding="10")
        self.main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        self.main_frame.columnconfigure(1, weight=1)
        
        # Timer display
        self.create_timer_display()
        
        # Project selection
        self.create_project_section()
        
        # Task description
        self.create_task_section()
        
        # Control buttons
        self.create_control_buttons()
        
        # Menu bar
        self.create_menu()
        
        # Status bar
        self.create_status_bar()
    
    def create_timer_display(self):
        """Create the timer display section"""
        timer_frame = ttk.LabelFrame(self.main_frame, text="Timer", padding="10")
        timer_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        timer_frame.columnconfigure(0, weight=1)
        
        # Time display
        self.time_var = tk.StringVar(value="25:00")
        self.time_label = tk.Label(timer_frame, textvariable=self.time_var, 
                                  font=("Arial", 36, "bold"), fg="#2c3e50")
        self.time_label.grid(row=0, column=0, pady=(0, 10))
        
        # Progress bar
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(timer_frame, variable=self.progress_var, 
                                          maximum=100, length=300)
        self.progress_bar.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # State label
        self.state_var = tk.StringVar(value="Ready to start")
        self.state_label = tk.Label(timer_frame, textvariable=self.state_var, 
                                   font=("Arial", 12), fg="#7f8c8d")
        self.state_label.grid(row=2, column=0)
    
    def create_project_section(self):
        """Create project selection section"""
        project_frame = ttk.LabelFrame(self.main_frame, text="Project", padding="10")
        project_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        project_frame.columnconfigure(1, weight=1)
        
        ttk.Label(project_frame, text="Project:").grid(row=0, column=0, sticky=tk.W, padx=(0, 10))
        
        self.project_var = tk.StringVar()
        self.project_combo = ttk.Combobox(project_frame, textvariable=self.project_var, 
                                         state="readonly", width=30)
        self.project_combo.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(0, 10))
        
        self.manage_projects_btn = ttk.Button(project_frame, text="Manage", 
                                            command=self.show_project_manager)
        self.manage_projects_btn.grid(row=0, column=2)
        
        self.load_projects()
    
    def create_task_section(self):
        """Create task description section"""
        task_frame = ttk.LabelFrame(self.main_frame, text="Task Description", padding="10")
        task_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        task_frame.columnconfigure(0, weight=1)
        task_frame.rowconfigure(1, weight=1)
        
        ttk.Label(task_frame, text="What are you working on?").grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
        
        self.task_text = tk.Text(task_frame, height=4, wrap=tk.WORD)
        self.task_text.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Scrollbar for text
        task_scrollbar = ttk.Scrollbar(task_frame, orient=tk.VERTICAL, command=self.task_text.yview)
        task_scrollbar.grid(row=1, column=1, sticky=(tk.N, tk.S))
        self.task_text.config(yscrollcommand=task_scrollbar.set)
    
    def create_control_buttons(self):
        """Create control buttons"""
        control_frame = ttk.Frame(self.main_frame)
        control_frame.grid(row=3, column=0, columnspan=2, pady=(0, 10))
        
        self.start_btn = ttk.Button(control_frame, text="Start Sprint", 
                                   command=self.start_sprint, style="Accent.TButton")
        self.start_btn.grid(row=0, column=0, padx=(0, 10))
        
        self.pause_btn = ttk.Button(control_frame, text="Pause", 
                                   command=self.pause_resume, state=tk.DISABLED)
        self.pause_btn.grid(row=0, column=1, padx=(0, 10))
        
        self.stop_btn = ttk.Button(control_frame, text="Stop", 
                                  command=self.stop_sprint, state=tk.DISABLED)
        self.stop_btn.grid(row=0, column=2, padx=(0, 10))
        
        self.complete_btn = ttk.Button(control_frame, text="Complete Sprint", 
                                      command=self.complete_sprint, state=tk.DISABLED)
        self.complete_btn.grid(row=0, column=3)
    
    def create_menu(self):
        """Create menu bar"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="View Data", command=self.show_data_viewer)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_closing)
        
        # View menu
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="View", menu=view_menu)
        view_menu.add_command(label="Toggle Compact Mode", command=self.toggle_compact_mode)
        
        # Tools menu
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        tools_menu.add_command(label="Manage Projects", command=self.show_project_manager)
        tools_menu.add_command(label="Settings", command=self.show_settings)
    
    def create_status_bar(self):
        """Create status bar"""
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(self.main_frame, textvariable=self.status_var, 
                              relief=tk.SUNKEN, anchor=tk.W)
        status_bar.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E))
    
    def load_projects(self):
        """Load projects into combo box"""
        session = self.db_manager.get_session()
        try:
            projects = session.query(Project).filter(Project.active == True).all()
            project_names = [p.name for p in projects]
            self.project_combo['values'] = project_names
            
            if project_names and not self.project_var.get():
                self.project_combo.current(0)
        finally:
            session.close()
    
    def start_sprint(self):
        """Start a new sprint"""
        project = self.project_var.get()
        task = self.task_text.get("1.0", tk.END).strip()
        
        if not project:
            messagebox.showwarning("Warning", "Please select a project")
            return
        
        if not task:
            messagebox.showwarning("Warning", "Please enter a task description")
            return
        
        # Create new sprint record
        session = self.db_manager.get_session()
        try:
            self.current_sprint = Sprint(
                project_name=project,
                task_description=task,
                start_time=datetime.now(),
                planned_duration=self.sprint_duration
            )
            session.add(self.current_sprint)
            session.commit()
            
            # Start timer
            self.timer.start_sprint()
            self.update_button_states()
            self.status_var.set(f"Sprint started: {project}")
            
        except Exception as e:
            session.rollback()
            messagebox.showerror("Error", f"Failed to start sprint: {str(e)}")
        finally:
            session.close()
    
    def pause_resume(self):
        """Pause or resume the timer"""
        if self.timer.get_state() == TimerState.PAUSED:
            self.timer.resume()
        else:
            self.timer.pause()
        
        self.update_button_states()
    
    def stop_sprint(self):
        """Stop the current sprint"""
        if messagebox.askyesno("Confirm", "Are you sure you want to stop the current sprint?"):
            self.timer.stop()
            self.save_current_sprint(interrupted=True)
            self.current_sprint = None
            self.update_button_states()
            self.status_var.set("Sprint stopped")
    
    def complete_sprint(self):
        """Complete the current sprint"""
        self.timer.stop()
        self.save_current_sprint(completed=True)
        self.current_sprint = None
        self.update_button_states()
        self.status_var.set("Sprint completed")
        
        # Clear task description for next sprint
        self.task_text.delete("1.0", tk.END)
    
    def save_current_sprint(self, completed=False, interrupted=False):
        """Save the current sprint to database"""
        if not self.current_sprint:
            return
        
        session = self.db_manager.get_session()
        try:
            # Refresh the sprint object
            sprint = session.merge(self.current_sprint)
            sprint.end_time = datetime.now()
            sprint.completed = completed
            sprint.interrupted = interrupted
            
            if sprint.start_time and sprint.end_time:
                duration = (sprint.end_time - sprint.start_time).total_seconds() / 60
                sprint.duration_minutes = int(duration)
            
            session.commit()
        except Exception as e:
            session.rollback()
            print(f"Error saving sprint: {e}")
        finally:
            session.close()
    
    def on_sprint_complete(self):
        """Called when sprint timer completes"""
        self.alarm_manager.play_sprint_complete_alarm()
        self.root.after(0, lambda: self.status_var.set("Sprint complete! Take a break."))
    
    def on_break_complete(self):
        """Called when break timer completes"""
        self.alarm_manager.play_break_complete_alarm()
        self.root.after(0, lambda: self.status_var.set("Break complete! Ready for next sprint."))
        
        # Complete current sprint if it exists
        if self.current_sprint:
            self.root.after(0, self.complete_sprint)
    
    def on_timer_state_change(self, state: TimerState):
        """Called when timer state changes"""
        self.root.after(0, self.update_button_states)
    
    def update_button_states(self):
        """Update button states based on timer state"""
        state = self.timer.get_state()
        
        if state == TimerState.STOPPED:
            self.start_btn.config(state=tk.NORMAL, text="Start Sprint")
            self.pause_btn.config(state=tk.DISABLED, text="Pause")
            self.stop_btn.config(state=tk.DISABLED)
            self.complete_btn.config(state=tk.DISABLED)
        
        elif state == TimerState.RUNNING:
            self.start_btn.config(state=tk.DISABLED, text="Start Sprint")
            self.pause_btn.config(state=tk.NORMAL, text="Pause")
            self.stop_btn.config(state=tk.NORMAL)
            self.complete_btn.config(state=tk.NORMAL)
        
        elif state == TimerState.PAUSED:
            self.start_btn.config(state=tk.DISABLED, text="Start Sprint")
            self.pause_btn.config(state=tk.NORMAL, text="Resume")
            self.stop_btn.config(state=tk.NORMAL)
            self.complete_btn.config(state=tk.NORMAL)
        
        elif state == TimerState.BREAK:
            self.start_btn.config(state=tk.NORMAL, text="Start New Sprint")
            self.pause_btn.config(state=tk.DISABLED, text="Pause")
            self.stop_btn.config(state=tk.DISABLED)
            self.complete_btn.config(state=tk.NORMAL)
    
    def update_display(self):
        """Update timer display"""
        if self.timer:
            remaining = self.timer.get_time_remaining()
            self.time_var.set(self.timer.format_time(remaining))
            self.progress_var.set(self.timer.get_progress_percentage())
            
            state = self.timer.get_state()
            state_text = {
                TimerState.STOPPED: "Ready to start",
                TimerState.RUNNING: "Sprint in progress",
                TimerState.BREAK: "Break time",
                TimerState.PAUSED: "Paused"
            }
            self.state_var.set(state_text.get(state, "Unknown"))
            
            # Update time label color based on state
            colors = {
                TimerState.STOPPED: "#2c3e50",
                TimerState.RUNNING: "#27ae60",
                TimerState.BREAK: "#f39c12",
                TimerState.PAUSED: "#e74c3c"
            }
            self.time_label.config(fg=colors.get(state, "#2c3e50"))
    
    def update_gui(self):
        """Update GUI periodically"""
        self.update_display()
        self.root.after(100, self.update_gui)  # Update every 100ms
    
    def toggle_compact_mode(self):
        """Toggle between normal and compact view"""
        self.compact_mode = not self.compact_mode
        
        if self.compact_mode:
            # Hide most widgets, show only timer
            self.main_frame.grid_forget()
            
            # Create compact frame
            self.compact_frame = ttk.Frame(self.root, padding="5")
            self.compact_frame.grid(row=0, column=0, sticky=(tk.W, tk.E))
            
            # Compact timer display
            compact_time = tk.Label(self.compact_frame, textvariable=self.time_var, 
                                   font=("Arial", 20, "bold"), fg="#2c3e50")
            compact_time.grid(row=0, column=0, padx=(0, 10))
            
            compact_state = tk.Label(self.compact_frame, textvariable=self.state_var, 
                                    font=("Arial", 10), fg="#7f8c8d")
            compact_state.grid(row=0, column=1)
            
            # Resize window
            self.root.geometry("200x50")
            self.root.resizable(False, False)
        else:
            # Restore normal view
            if hasattr(self, 'compact_frame'):
                self.compact_frame.destroy()
            
            self.main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
            self.root.geometry("400x500")
            self.root.resizable(True, True)
    
    def show_project_manager(self):
        """Show project manager dialog"""
        dialog = ProjectManagerDialog(self.root, self.db_manager)
        self.root.wait_window(dialog.dialog)
        self.load_projects()  # Refresh project list
    
    def show_data_viewer(self):
        """Show data viewer window"""
        DataViewerWindow(self.root, self.db_manager)
    
    def show_settings(self):
        """Show settings dialog"""
        dialog = SettingsDialog(self.root, self.db_manager)
        self.root.wait_window(dialog.dialog)
        
        # Reload settings and update timer
        self.load_settings()
        if self.timer.get_state() == TimerState.STOPPED:
            self.timer.set_durations(self.sprint_duration, self.break_duration)
    
    def on_closing(self):
        """Handle window closing"""
        if self.timer.get_state() != TimerState.STOPPED:
            if messagebox.askyesno("Confirm Exit", 
                                 "Timer is running. Do you want to save and exit?"):
                self.save_current_sprint(interrupted=True)
                self.timer.stop()
            else:
                return
        
        self.root.quit()
        self.root.destroy()
    
    def run(self):
        """Start the application"""
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.on_closing()