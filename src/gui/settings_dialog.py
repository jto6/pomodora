import tkinter as tk
from tkinter import ttk, messagebox
from ..tracking.models import DatabaseManager, Settings

class SettingsDialog:
    def __init__(self, parent, db_manager: DatabaseManager):
        self.parent = parent
        self.db_manager = db_manager
        
        # Create dialog window
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Settings")
        self.dialog.geometry("400x300")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        # Center the dialog
        self.dialog.geometry("+%d+%d" % (parent.winfo_rootx() + 50, parent.winfo_rooty() + 50))
        
        self.create_widgets()
        self.load_settings()
    
    def create_widgets(self):
        """Create dialog widgets"""
        main_frame = ttk.Frame(self.dialog, padding="20")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.dialog.columnconfigure(0, weight=1)
        self.dialog.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        # Title
        title_label = ttk.Label(main_frame, text="Settings", font=("Arial", 14, "bold"))
        title_label.grid(row=0, column=0, columnspan=2, pady=(0, 20))
        
        # Timer settings
        timer_frame = ttk.LabelFrame(main_frame, text="Timer Settings", padding="10")
        timer_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 15))
        timer_frame.columnconfigure(1, weight=1)
        
        # Sprint duration
        ttk.Label(timer_frame, text="Sprint Duration (minutes):").grid(row=0, column=0, sticky=tk.W, pady=(0, 10))
        self.sprint_duration_var = tk.IntVar()
        sprint_spinbox = ttk.Spinbox(timer_frame, from_=1, to=60, width=10, 
                                    textvariable=self.sprint_duration_var)
        sprint_spinbox.grid(row=0, column=1, sticky=tk.W, pady=(0, 10))
        
        # Break duration
        ttk.Label(timer_frame, text="Break Duration (minutes):").grid(row=1, column=0, sticky=tk.W, pady=(0, 10))
        self.break_duration_var = tk.IntVar()
        break_spinbox = ttk.Spinbox(timer_frame, from_=1, to=30, width=10, 
                                   textvariable=self.break_duration_var)
        break_spinbox.grid(row=1, column=1, sticky=tk.W, pady=(0, 10))
        
        # Audio settings
        audio_frame = ttk.LabelFrame(main_frame, text="Audio Settings", padding="10")
        audio_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 15))
        audio_frame.columnconfigure(1, weight=1)
        
        # Alarm volume
        ttk.Label(audio_frame, text="Alarm Volume:").grid(row=0, column=0, sticky=tk.W, pady=(0, 10))
        self.volume_var = tk.DoubleVar()
        volume_scale = ttk.Scale(audio_frame, from_=0.0, to=1.0, orient=tk.HORIZONTAL,
                                variable=self.volume_var, length=200)
        volume_scale.grid(row=0, column=1, sticky=(tk.W, tk.E), pady=(0, 10), padx=(10, 0))
        
        # Volume label
        self.volume_label = ttk.Label(audio_frame, text="70%")
        self.volume_label.grid(row=0, column=2, pady=(0, 10), padx=(10, 0))
        
        # Update volume label when scale changes
        volume_scale.configure(command=self.update_volume_label)
        
        # Cloud settings
        cloud_frame = ttk.LabelFrame(main_frame, text="Cloud Storage", padding="10")
        cloud_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 15))
        
        self.google_drive_var = tk.BooleanVar()
        google_drive_check = ttk.Checkbutton(cloud_frame, text="Enable Google Drive sync (requires setup)", 
                                           variable=self.google_drive_var)
        google_drive_check.grid(row=0, column=0, sticky=tk.W)
        
        # Note about Google Drive
        note_label = ttk.Label(cloud_frame, text="Note: Google Drive sync requires API credentials", 
                              font=("Arial", 9), foreground="gray")
        note_label.grid(row=1, column=0, sticky=tk.W, pady=(5, 0))
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=4, column=0, columnspan=2, pady=(10, 0))
        
        ttk.Button(button_frame, text="Save", command=self.save_settings).grid(row=0, column=0, padx=(0, 10))
        ttk.Button(button_frame, text="Cancel", command=self.dialog.destroy).grid(row=0, column=1, padx=(0, 10))
        ttk.Button(button_frame, text="Reset to Defaults", command=self.reset_defaults).grid(row=0, column=2)
    
    def load_settings(self):
        """Load current settings"""
        session = self.db_manager.get_session()
        try:
            sprint_duration = Settings.get_setting(session, "sprint_duration", 25)
            break_duration = Settings.get_setting(session, "break_duration", 5)
            alarm_volume = Settings.get_setting(session, "alarm_volume", 0.7)
            google_drive_enabled = Settings.get_setting(session, "google_drive_enabled", False)
            
            self.sprint_duration_var.set(sprint_duration)
            self.break_duration_var.set(break_duration)
            self.volume_var.set(alarm_volume)
            self.google_drive_var.set(google_drive_enabled)
            
            self.update_volume_label(alarm_volume)
            
        finally:
            session.close()
    
    def update_volume_label(self, value=None):
        """Update volume percentage label"""
        if value is None:
            value = self.volume_var.get()
        else:
            value = float(value)
        
        percentage = int(value * 100)
        self.volume_label.config(text=f"{percentage}%")
    
    def save_settings(self):
        """Save settings to database"""
        session = self.db_manager.get_session()
        try:
            Settings.set_setting(session, "sprint_duration", self.sprint_duration_var.get())
            Settings.set_setting(session, "break_duration", self.break_duration_var.get())
            Settings.set_setting(session, "alarm_volume", self.volume_var.get())
            Settings.set_setting(session, "google_drive_enabled", self.google_drive_var.get())
            
            messagebox.showinfo("Success", "Settings saved successfully")
            self.dialog.destroy()
            
        except Exception as e:
            session.rollback()
            messagebox.showerror("Error", f"Failed to save settings: {str(e)}")
        finally:
            session.close()
    
    def reset_defaults(self):
        """Reset settings to defaults"""
        if messagebox.askyesno("Confirm Reset", "Reset all settings to default values?"):
            self.sprint_duration_var.set(25)
            self.break_duration_var.set(5)
            self.volume_var.set(0.7)
            self.google_drive_var.set(False)
            self.update_volume_label(0.7)