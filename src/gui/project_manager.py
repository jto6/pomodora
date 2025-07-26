import tkinter as tk
from tkinter import ttk, messagebox, colorchooser
from ..tracking.models import DatabaseManager, Project

class ProjectManagerDialog:
    def __init__(self, parent, db_manager: DatabaseManager):
        self.parent = parent
        self.db_manager = db_manager
        
        # Create dialog window
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Manage Projects")
        self.dialog.geometry("500x400")
        self.dialog.resizable(True, True)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        # Center the dialog
        self.dialog.geometry("+%d+%d" % (parent.winfo_rootx() + 50, parent.winfo_rooty() + 50))
        
        self.create_widgets()
        self.load_projects()
    
    def create_widgets(self):
        """Create dialog widgets"""
        main_frame = ttk.Frame(self.dialog, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.dialog.columnconfigure(0, weight=1)
        self.dialog.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(1, weight=1)
        
        # Title
        title_label = ttk.Label(main_frame, text="Project Management", 
                               font=("Arial", 14, "bold"))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 10))
        
        # Project list
        list_frame = ttk.LabelFrame(main_frame, text="Projects", padding="5")
        list_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        
        # Treeview for projects
        columns = ("name", "color", "active")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=12)
        
        self.tree.heading("name", text="Project Name")
        self.tree.heading("color", text="Color")
        self.tree.heading("active", text="Active")
        
        self.tree.column("name", width=200)
        self.tree.column("color", width=100)
        self.tree.column("active", width=80)
        
        self.tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Scrollbar for treeview
        tree_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        tree_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.tree.config(yscrollcommand=tree_scrollbar.set)
        
        # Project entry form
        form_frame = ttk.LabelFrame(main_frame, text="Add/Edit Project", padding="5")
        form_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        form_frame.columnconfigure(1, weight=1)
        
        # Project name
        ttk.Label(form_frame, text="Name:").grid(row=0, column=0, sticky=tk.W, padx=(0, 10))
        self.name_var = tk.StringVar()
        self.name_entry = ttk.Entry(form_frame, textvariable=self.name_var, width=30)
        self.name_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(0, 10))
        
        # Color selection
        ttk.Label(form_frame, text="Color:").grid(row=0, column=2, sticky=tk.W, padx=(0, 10))
        self.color_var = tk.StringVar(value="#3498db")
        self.color_button = tk.Button(form_frame, text="Choose", command=self.choose_color,
                                     bg=self.color_var.get(), width=8)
        self.color_button.grid(row=0, column=3, padx=(0, 10))
        
        # Active checkbox
        self.active_var = tk.BooleanVar(value=True)
        self.active_check = ttk.Checkbutton(form_frame, text="Active", variable=self.active_var)
        self.active_check.grid(row=0, column=4)
        
        # Action buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=3, column=0, columnspan=3, pady=(0, 10))
        
        self.add_btn = ttk.Button(button_frame, text="Add Project", command=self.add_project)
        self.add_btn.grid(row=0, column=0, padx=(0, 10))
        
        self.update_btn = ttk.Button(button_frame, text="Update Project", 
                                    command=self.update_project, state=tk.DISABLED)
        self.update_btn.grid(row=0, column=1, padx=(0, 10))
        
        self.delete_btn = ttk.Button(button_frame, text="Delete Project", 
                                    command=self.delete_project, state=tk.DISABLED)
        self.delete_btn.grid(row=0, column=2, padx=(0, 10))
        
        # Close button
        close_frame = ttk.Frame(main_frame)
        close_frame.grid(row=4, column=0, columnspan=3)
        
        ttk.Button(close_frame, text="Close", command=self.dialog.destroy).grid(row=0, column=0)
        
        # Bind treeview selection
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        
        # Bind enter key to add/update
        self.name_entry.bind("<Return>", lambda e: self.add_project() if self.add_btn['state'] == 'normal' else self.update_project())
    
    def load_projects(self):
        """Load projects into treeview"""
        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        session = self.db_manager.get_session()
        try:
            projects = session.query(Project).order_by(Project.name).all()
            
            for project in projects:
                self.tree.insert("", tk.END, iid=project.id, values=(
                    project.name,
                    project.color,
                    "Yes" if project.active else "No"
                ))
                
                # Set background color for color column
                self.tree.set(project.id, "color", "●")  # Use bullet character
                
        finally:
            session.close()
    
    def on_tree_select(self, event):
        """Handle treeview selection"""
        selection = self.tree.selection()
        if selection:
            project_id = selection[0]
            
            session = self.db_manager.get_session()
            try:
                project = session.query(Project).filter(Project.id == project_id).first()
                if project:
                    self.name_var.set(project.name)
                    self.color_var.set(project.color)
                    self.active_var.set(project.active)
                    self.color_button.config(bg=project.color)
                    
                    # Enable update/delete buttons
                    self.update_btn.config(state=tk.NORMAL)
                    self.delete_btn.config(state=tk.NORMAL)
                    self.add_btn.config(state=tk.DISABLED)
                    
            finally:
                session.close()
        else:
            self.clear_form()
    
    def clear_form(self):
        """Clear the form"""
        self.name_var.set("")
        self.color_var.set("#3498db")
        self.active_var.set(True)
        self.color_button.config(bg="#3498db")
        
        self.add_btn.config(state=tk.NORMAL)
        self.update_btn.config(state=tk.DISABLED)
        self.delete_btn.config(state=tk.DISABLED)
    
    def choose_color(self):
        """Open color chooser dialog"""
        color = colorchooser.askcolor(initialcolor=self.color_var.get(), title="Choose Project Color")
        if color[1]:  # color[1] is the hex value
            self.color_var.set(color[1])
            self.color_button.config(bg=color[1])
    
    def add_project(self):
        """Add new project"""
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Warning", "Please enter a project name")
            return
        
        session = self.db_manager.get_session()
        try:
            # Check if project name already exists
            existing = session.query(Project).filter(Project.name == name).first()
            if existing:
                messagebox.showerror("Error", "Project name already exists")
                return
            
            # Create new project
            project = Project(
                name=name,
                color=self.color_var.get(),
                active=self.active_var.get()
            )
            session.add(project)
            session.commit()
            
            self.load_projects()
            self.clear_form()
            messagebox.showinfo("Success", "Project added successfully")
            
        except Exception as e:
            session.rollback()
            messagebox.showerror("Error", f"Failed to add project: {str(e)}")
        finally:
            session.close()
    
    def update_project(self):
        """Update selected project"""
        selection = self.tree.selection()
        if not selection:
            return
        
        project_id = selection[0]
        name = self.name_var.get().strip()
        
        if not name:
            messagebox.showwarning("Warning", "Please enter a project name")
            return
        
        session = self.db_manager.get_session()
        try:
            # Check if project name already exists (excluding current project)
            existing = session.query(Project).filter(
                Project.name == name,
                Project.id != project_id
            ).first()
            if existing:
                messagebox.showerror("Error", "Project name already exists")
                return
            
            # Update project
            project = session.query(Project).filter(Project.id == project_id).first()
            if project:
                project.name = name
                project.color = self.color_var.get()
                project.active = self.active_var.get()
                session.commit()
                
                self.load_projects()
                self.clear_form()
                messagebox.showinfo("Success", "Project updated successfully")
            
        except Exception as e:
            session.rollback()
            messagebox.showerror("Error", f"Failed to update project: {str(e)}")
        finally:
            session.close()
    
    def delete_project(self):
        """Delete selected project"""
        selection = self.tree.selection()
        if not selection:
            return
        
        project_id = selection[0]
        
        if not messagebox.askyesno("Confirm Delete", 
                                  "Are you sure you want to delete this project?\n"
                                  "This will not delete existing sprint records."):
            return
        
        session = self.db_manager.get_session()
        try:
            project = session.query(Project).filter(Project.id == project_id).first()
            if project:
                session.delete(project)
                session.commit()
                
                self.load_projects()
                self.clear_form()
                messagebox.showinfo("Success", "Project deleted successfully")
            
        except Exception as e:
            session.rollback()
            messagebox.showerror("Error", f"Failed to delete project: {str(e)}")
        finally:
            session.close()