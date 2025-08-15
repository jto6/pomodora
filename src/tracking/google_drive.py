import os
import json
import pickle
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import io
from utils.logging import verbose_print, error_print, info_print, debug_print

# Required scopes for Google Drive access
# Using drive scope to access existing folders and files
SCOPES = ['https://www.googleapis.com/auth/drive']

class GoogleDriveSync:
    def __init__(self, credentials_path: str = "credentials.json", token_path: str = "token.pickle"):
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.service = None
        self.folder_id = None
        self.db_file_id = None

    def authenticate(self) -> bool:
        """Authenticate with Google Drive API"""
        creds = None

        # Load existing token
        if os.path.exists(self.token_path):
            with open(self.token_path, 'rb') as token:
                creds = pickle.load(token)

        # If there are no valid credentials, request authorization
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    error_print(f"Failed to refresh credentials: {e}")
                    return False
            else:
                if not os.path.exists(self.credentials_path):
                    error_print(f"Google Drive credentials file not found: {self.credentials_path}")
                    error_print("Please download credentials.json from Google Cloud Console")
                    return False

                try:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.credentials_path, SCOPES)
                    creds = flow.run_local_server(port=0)
                except Exception as e:
                    error_print(f"Failed to authenticate: {e}")
                    return False

            # Save credentials for next run
            with open(self.token_path, 'wb') as token:
                pickle.dump(creds, token)

        try:
            self.service = build('drive', 'v3', credentials=creds)
            return True
        except Exception as e:
            error_print(f"Failed to build Google Drive service: {e}")
            return False

    def setup_drive_folder(self, folder_name: str = "TimeTracking") -> bool:
        """Create or find the Pomodora data folder in Google Drive"""
        if not self.service:
            return False

        try:
            # Search for existing folder
            results = self.service.files().list(
                q=f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
                fields="files(id, name, parents)"
            ).execute()

            folders = results.get('files', [])

            if folders:
                # If multiple folders exist, warn and use the first one
                if len(folders) > 1:
                    error_print(f"Warning: Found {len(folders)} folders named '{folder_name}'. Using the first one.")
                    error_print("Consider removing duplicate folders from Google Drive.")

                self.folder_id = folders[0]['id']
                info_print(f"Found existing folder: {folder_name}")
                return True

            # No folders found, create new one
            folder_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': ['root']
            }

            folder = self.service.files().create(
                body=folder_metadata,
                fields='id'
            ).execute()

            self.folder_id = folder.get('id')
            info_print(f"Created new folder: {folder_name}")

            return True

        except Exception as e:
            error_print(f"Failed to setup drive folder: {e}")
            return False

    def upload_database(self, local_db_path: str) -> bool:
        """Upload local database to Google Drive"""
        if not self.service or not self.folder_id:
            return False

        if not os.path.exists(local_db_path):
            error_print(f"Local database file not found: {local_db_path}")
            return False

        try:
            db_filename = os.path.basename(local_db_path)

            # Safety check: only upload files named 'pomodora.db'
            if db_filename != 'pomodora.db':
                error_print(f"Refusing to upload non-standard database file: {db_filename}")
                return False

            # Check if database already exists in Drive
            results = self.service.files().list(
                q=f"name='{db_filename}' and parents in '{self.folder_id}' and trashed=false",
                fields="files(id, name, modifiedTime)"
            ).execute()

            files = results.get('files', [])
            debug_print(f"Found {len(files)} database files named '{db_filename}' in Google Drive")
            
            # If multiple files exist, warn and pick the most recently modified one
            if len(files) > 1:
                error_print(f"Warning: Found {len(files)} database files named '{db_filename}' in Google Drive")
                error_print("Using the most recently modified file. Consider removing duplicates.")
                # Sort by modifiedTime descending to get the most recent first
                files.sort(key=lambda f: f['modifiedTime'], reverse=True)
                debug_print(f"Selected most recent file: ID={files[0]['id']}, modified={files[0]['modifiedTime']}")

            # Prepare file metadata and media
            file_metadata = {
                'name': db_filename,
                'parents': [self.folder_id]
            }

            media = MediaFileUpload(local_db_path, resumable=True)

            if files:
                # Update existing file (most recently modified if there are duplicates)
                self.db_file_id = files[0]['id']
                debug_print(f"Attempting to update existing file with ID: {self.db_file_id}")
                
                # Clean up duplicate files before updating
                if len(files) > 1:
                    debug_print(f"Cleaning up {len(files) - 1} duplicate database files")
                    for duplicate_file in files[1:]:
                        try:
                            self.service.files().delete(fileId=duplicate_file['id']).execute()
                            debug_print(f"Deleted duplicate file: {duplicate_file['id']}")
                        except Exception as e:
                            error_print(f"Failed to delete duplicate file {duplicate_file['id']}: {e}")
                
                # Update the remaining file
                try:
                    updated_file = self.service.files().update(
                        fileId=self.db_file_id,
                        media_body=media,
                        fields='id, modifiedTime'
                    ).execute()
                    info_print(f"Updated existing database in Google Drive (ID: {self.db_file_id})")
                except Exception as e:
                    error_print(f"Failed to update existing file {self.db_file_id}: {e}")
                    return False  # Don't create duplicates, fail instead
            else:
                # Create new file
                debug_print("No existing database files found, creating new file")
                uploaded_file = self.service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id, modifiedTime'
                ).execute()
                self.db_file_id = uploaded_file.get('id')
                info_print(f"Created new database in Google Drive (ID: {self.db_file_id})")

            return True

        except Exception as e:
            error_print(f"Failed to upload database: {e}")
            return False

    def download_database(self, local_db_path: str) -> bool:
        """Download database from Google Drive"""
        if not self.service or not self.folder_id:
            return False

        try:
            db_filename = os.path.basename(local_db_path)

            # Find database file in Drive
            results = self.service.files().list(
                q=f"name='{db_filename}' and parents in '{self.folder_id}' and trashed=false",
                fields="files(id, name, modifiedTime)"
            ).execute()

            files = results.get('files', [])

            if not files:
                error_print(f"Database file not found in Google Drive: {db_filename}")
                return False

            # If multiple files exist, warn and pick the most recently modified one
            if len(files) > 1:
                error_print(f"Warning: Found {len(files)} database files named '{db_filename}' in Google Drive")
                error_print("Using the most recently modified file. Consider removing duplicates.")
                # Sort by modifiedTime descending to get the most recent first
                files.sort(key=lambda f: f['modifiedTime'], reverse=True)

            self.db_file_id = files[0]['id']

            # Download file
            request = self.service.files().get_media(fileId=self.db_file_id)
            file_io = io.BytesIO()
            downloader = MediaIoBaseDownload(file_io, request)

            done = False
            while done is False:
                status, done = downloader.next_chunk()

            # Write to local file
            with open(local_db_path, 'wb') as f:
                f.write(file_io.getvalue())

            # Fix auto-increment sequences to prevent ID collisions
            self._fix_autoincrement_sequences(local_db_path)

            info_print(f"Downloaded database from Google Drive")
            return True

        except Exception as e:
            error_print(f"Failed to download database: {e}")
            return False

    def sync_database(self, local_db_path: str) -> bool:
        """Sync database with Google Drive (bidirectional)"""
        if not self.service or not self.folder_id:
            return False

        try:
            db_filename = os.path.basename(local_db_path)
            local_exists = os.path.exists(local_db_path)

            # Find remote database
            results = self.service.files().list(
                q=f"name='{db_filename}' and parents in '{self.folder_id}' and trashed=false",
                fields="files(id, name, modifiedTime)"
            ).execute()

            files = results.get('files', [])
            remote_exists = len(files) > 0

            if not local_exists and not remote_exists:
                info_print("No database file found locally or remotely")
                return True  # Nothing to sync

            if local_exists and not remote_exists:
                # Upload local to remote
                return self.upload_database(local_db_path)

            if not local_exists and remote_exists:
                # Download remote to local
                return self.download_database(local_db_path)

            # Both exist - check modification times
            self.db_file_id = files[0]['id']
            remote_modified = datetime.fromisoformat(files[0]['modifiedTime'].replace('Z', '+00:00'))
            local_modified = datetime.fromtimestamp(os.path.getmtime(local_db_path))

            # Convert to UTC for comparison
            local_modified = local_modified.replace(tzinfo=remote_modified.tzinfo)

            if remote_modified > local_modified:
                info_print("Remote database is newer, downloading...")
                return self.download_database(local_db_path)
            elif local_modified > remote_modified:
                info_print("Local database is newer, uploading...")
                return self.upload_database(local_db_path)
            else:
                debug_print("Databases are in sync")
                return True

        except Exception as e:
            error_print(f"Failed to sync database: {e}")
            return False

    def get_database_info(self, db_filename: str = "pomodora.db") -> Optional[Dict[str, Any]]:
        """Get information about the database file in Google Drive"""
        if not self.service or not self.folder_id:
            return None

        try:
            results = self.service.files().list(
                q=f"name='{db_filename}' and parents in '{self.folder_id}' and trashed=false",
                fields="files(id, name, modifiedTime, size)"
            ).execute()

            files = results.get('files', [])

            if files:
                file_info = files[0]
                return {
                    'id': file_info['id'],
                    'name': file_info['name'],
                    'modified_time': file_info['modifiedTime'],
                    'size': int(file_info.get('size', 0))
                }

            return None

        except Exception as e:
            error_print(f"Failed to get database info: {e}")
            return None

    def upload_file(self, local_file_path: str, filename: str) -> bool:
        """Upload a file to Google Drive folder"""
        if not self.service or not self.folder_id:
            return False

        try:
            media = MediaFileUpload(local_file_path)

            # Check if file already exists
            results = self.service.files().list(
                q=f"name='{filename}' and parents in '{self.folder_id}' and trashed=false",
                fields="files(id, name)"
            ).execute()

            files = results.get('files', [])

            if files:
                # If multiple files exist with the same name, delete all but the first and update the first
                if len(files) > 1:
                    error_print(f"⚠️  DUPLICATE CLEANUP: Found {len(files)} files named '{filename}' during upload!")
                    for i, duplicate_file in enumerate(files[1:], 1):  # Delete all but the first
                        try:
                            self.service.files().delete(fileId=duplicate_file['id']).execute()
                            error_print(f"🗑️  DUPLICATE CLEANUP: Deleted duplicate #{i}: {duplicate_file['id']}")
                        except Exception as delete_error:
                            error_print(f"❌ DUPLICATE CLEANUP: Failed to delete duplicate {duplicate_file['id']}: {delete_error}")
                    error_print(f"✅ DUPLICATE CLEANUP: Cleaned up {len(files) - 1} duplicate files, keeping {files[0]['id']}")
                
                # Update the remaining file (files[0])
                file_id = files[0]['id']
                self.service.files().update(
                    fileId=file_id,
                    media_body=media
                ).execute()
                debug_print(f"Updated existing file: {filename}")
            else:
                # Create new file
                file_metadata = {
                    'name': filename,
                    'parents': [self.folder_id]
                }
                self.service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id'
                ).execute()
                debug_print(f"Created new file: {filename}")

            return True

        except Exception as e:
            error_print(f"Failed to upload file {filename}: {e}")
            return False

    def delete_file_by_name(self, filename: str) -> bool:
        """Delete a file by name from Google Drive folder"""
        if not self.service or not self.folder_id:
            return False

        try:
            # Find the file
            results = self.service.files().list(
                q=f"name='{filename}' and parents in '{self.folder_id}' and trashed=false",
                fields="files(id, name)"
            ).execute()

            files = results.get('files', [])

            if not files:
                debug_print(f"File not found for deletion: {filename}")
                return True  # File doesn't exist, consider it deleted

            # Delete the file
            file_id = files[0]['id']
            self.service.files().delete(fileId=file_id).execute()
            debug_print(f"Deleted file: {filename}")
            return True

        except Exception as e:
            error_print(f"Failed to delete file {filename}: {e}")
            return False

    def list_files_by_pattern(self, pattern: str) -> list:
        """List files matching a pattern in Google Drive folder"""
        if not self.service or not self.folder_id:
            return []

        try:
            # Convert shell pattern to Google Drive query
            # For now, handle simple prefix matching
            if pattern.endswith('*.json'):
                prefix = pattern[:-6]  # Remove '*.json'
                query = f"name contains '{prefix}' and name contains '.json' and parents in '{self.folder_id}' and trashed=false"
            else:
                query = f"name contains '{pattern}' and parents in '{self.folder_id}' and trashed=false"

            results = self.service.files().list(
                q=query,
                fields="files(id, name, modifiedTime)"
            ).execute()

            files = results.get('files', [])
            debug_print(f"Found {len(files)} files matching pattern: {pattern}")
            return files

        except Exception as e:
            error_print(f"Failed to list files with pattern {pattern}: {e}")
            return []

    def download_json_file(self, filename: str) -> Optional[dict]:
        """Download and parse JSON file from Google Drive"""
        if not self.service or not self.folder_id:
            return None

        try:
            # Find the file
            results = self.service.files().list(
                q=f"name='{filename}' and parents in '{self.folder_id}' and trashed=false",
                fields="files(id, name)"
            ).execute()

            files = results.get('files', [])

            if not files:
                debug_print(f"JSON file not found: {filename}")
                return None

            file_id = files[0]['id']
            return self.download_json_file_by_id(file_id)

        except Exception as e:
            error_print(f"Failed to download JSON file {filename}: {e}")
            return None

    def download_json_file_by_id(self, file_id: str) -> Optional[dict]:
        """Download and parse JSON file by ID from Google Drive"""
        if not self.service:
            return None

        try:
            import json

            request = self.service.files().get_media(fileId=file_id)
            downloaded = io.BytesIO()
            downloader = MediaIoBaseDownload(downloaded, request)

            done = False
            while done is False:
                status, done = downloader.next_chunk()

            # Parse JSON
            downloaded.seek(0)
            content = downloaded.read().decode('utf-8')
            return json.loads(content)

        except Exception as e:
            error_print(f"Failed to download JSON file by ID {file_id}: {e}")
            return None

    def _fix_autoincrement_sequences(self, db_path: str):
        """Fix SQLite auto-increment sequences to prevent ID collisions after database replacement"""
        try:
            import sqlite3
            
            # Connect to the database
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Get list of tables that have auto-increment primary keys
            tables_to_fix = ['sprints', 'projects', 'task_categories']
            
            for table_name in tables_to_fix:
                try:
                    # Get the maximum ID for this table
                    cursor.execute(f"SELECT MAX(id) FROM {table_name}")
                    max_id = cursor.fetchone()[0]
                    
                    if max_id is not None:
                        # For INTEGER PRIMARY KEY (without AUTOINCREMENT), we need to prime the sequence
                        # by inserting a dummy record with max_id+1, then deleting it
                        next_id = max_id + 1
                        
                        if table_name == 'sprints':
                            # Insert dummy sprint record
                            cursor.execute(f"INSERT INTO {table_name} (id, project_id, task_category_id, task_description, start_time, completed) VALUES (?, 1, 1, 'DUMMY_RECORD', datetime('now'), 0)", (next_id,))
                        elif table_name == 'projects':
                            # Insert dummy project record  
                            cursor.execute(f"INSERT INTO {table_name} (id, name, active) VALUES (?, 'DUMMY_PROJECT', 0)", (next_id,))
                        elif table_name == 'task_categories':
                            # Insert dummy task category record
                            cursor.execute(f"INSERT INTO {table_name} (id, name, active) VALUES (?, 'DUMMY_CATEGORY', 0)", (next_id,))
                        
                        # Delete the dummy record - this primes the auto-increment
                        cursor.execute(f"DELETE FROM {table_name} WHERE id = ?", (next_id,))
                        debug_print(f"Fixed auto-increment sequence for {table_name}: primed to start from {next_id}")
                    else:
                        debug_print(f"No records in {table_name}, skipping sequence fix")
                        
                except sqlite3.Error as e:
                    error_print(f"Failed to fix sequence for table {table_name}: {e}")
                    continue
            
            conn.commit()
            conn.close()
            debug_print("Auto-increment sequences fixed successfully")
            
        except Exception as e:
            error_print(f"Failed to fix auto-increment sequences: {e}")

    def list_files_by_pattern(self, pattern: str) -> list:
        """List files matching a pattern in the configured folder"""
        try:
            if not self.service or not self.folder_id:
                return []
            
            # Convert simple pattern to Google Drive query
            # For now, handle basic patterns like "sync_intent_*.json"
            if '*' in pattern:
                base_pattern = pattern.replace('*', '')
                query = f"parents in '{self.folder_id}' and trashed=false and name contains '{base_pattern}'"
            else:
                query = f"parents in '{self.folder_id}' and trashed=false and name='{pattern}'"
            
            results = self.service.files().list(
                q=query,
                fields="files(id, name, createdTime, modifiedTime, size)"
            ).execute()
            
            return results.get('files', [])
            
        except Exception as e:
            error_print(f"Failed to list files by pattern '{pattern}': {e}")
            return []

    def list_files_by_name(self, filename: str) -> list:
        """List files with exact name match in the configured folder"""
        try:
            if not self.service or not self.folder_id:
                return []
            
            query = f"name='{filename}' and parents in '{self.folder_id}' and trashed=false"
            results = self.service.files().list(
                q=query,
                fields="files(id, name, createdTime, modifiedTime, size)"
            ).execute()
            
            return results.get('files', [])
            
        except Exception as e:
            error_print(f"Failed to list files by name '{filename}': {e}")
            return []

    def delete_file_by_name(self, filename: str) -> bool:
        """Delete file by name from the configured folder"""
        try:
            files = self.list_files_by_name(filename)
            if not files:
                debug_print(f"File not found for deletion: {filename}")
                return True  # Not an error if file doesn't exist
            
            for file in files:
                self.service.files().delete(fileId=file['id']).execute()
                debug_print(f"Deleted file: {filename}")
            
            return True
            
        except Exception as e:
            error_print(f"Failed to delete file '{filename}': {e}")
            return False

    def download_file(self, file_id: str, local_path: str) -> bool:
        """Download a file by ID from Google Drive"""
        try:
            if not self.service:
                error_print("Google Drive service not initialized")
                return False

            # Download file content
            request = self.service.files().get_media(fileId=file_id)
            file_io = io.BytesIO()
            downloader = MediaIoBaseDownload(file_io, request)

            done = False
            while done is False:
                status, done = downloader.next_chunk()

            # Write to local file
            local_file_path = Path(local_path)
            local_file_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(local_path, 'wb') as f:
                f.write(file_io.getvalue())

            debug_print(f"Downloaded file {file_id} to {local_path}")
            return True

        except Exception as e:
            error_print(f"Failed to download file {file_id}: {e}")
            return False

    def copy_file(self, file_id: str, new_name: str) -> bool:
        """Copy a file to a new name"""
        try:
            if not self.service or not self.folder_id:
                return False
            
            body = {
                'name': new_name,
                'parents': [self.folder_id]
            }
            
            self.service.files().copy(fileId=file_id, body=body).execute()
            debug_print(f"Copied file to: {new_name}")
            return True
            
        except Exception as e:
            error_print(f"Failed to copy file to '{new_name}': {e}")
            return False

    def rename_file(self, file_id: str, new_name: str) -> bool:
        """Rename a file"""
        try:
            if not self.service:
                return False
            
            body = {'name': new_name}
            self.service.files().update(fileId=file_id, body=body).execute()
            debug_print(f"Renamed file to: {new_name}")
            return True
            
        except Exception as e:
            error_print(f"Failed to rename file to '{new_name}': {e}")
            return False

    def ensure_folder_exists(self, folder_name: str) -> bool:
        """Ensure folder exists and set folder_id"""
        return self.setup_drive_folder(folder_name)

class GoogleDriveManager:
    """High-level manager for Google Drive database synchronization"""

    def __init__(self, db_path: str = "pomodora.db"):
        self.db_path = db_path
        self.drive_sync = GoogleDriveSync()
        self.sync_interval = timedelta(minutes=5)  # Sync every 5 minutes
        self.last_sync = None
        self.folder_name = "TimeTracking"  # Default folder name

    def initialize(self) -> bool:
        """Initialize Google Drive integration"""
        try:
            if not self.drive_sync.authenticate():
                return False

            if not self.drive_sync.setup_drive_folder(self.folder_name):
                return False

            # Initial sync
            return self.sync_now()

        except Exception as e:
            error_print(f"Failed to initialize Google Drive: {e}")
            return False

    def sync_now(self) -> bool:
        """Force immediate synchronization"""
        try:
            result = self.drive_sync.sync_database(self.db_path)
            if result:
                self.last_sync = datetime.now()
            return result
        except Exception as e:
            error_print(f"Sync failed: {e}")
            return False

    def auto_sync(self) -> bool:
        """Automatic sync based on time interval"""
        if not self.last_sync or (datetime.now() - self.last_sync) >= self.sync_interval:
            return self.sync_now()
        return True

    def is_enabled(self) -> bool:
        """Check if Google Drive sync is properly configured"""
        return (self.drive_sync.service is not None and
                self.drive_sync.folder_id is not None)

    def get_status(self) -> Dict[str, Any]:
        """Get current sync status"""
        return {
            'enabled': self.is_enabled(),
            'last_sync': self.last_sync,
            'credentials_exist': os.path.exists(self.drive_sync.credentials_path),
            'token_exist': os.path.exists(self.drive_sync.token_path)
        }