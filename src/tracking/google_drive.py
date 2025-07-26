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

# Required scopes for Google Drive access
SCOPES = ['https://www.googleapis.com/auth/drive.file']

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
                    print(f"Failed to refresh credentials: {e}")
                    return False
            else:
                if not os.path.exists(self.credentials_path):
                    print(f"Google Drive credentials file not found: {self.credentials_path}")
                    print("Please download credentials.json from Google Cloud Console")
                    return False
                
                try:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.credentials_path, SCOPES)
                    creds = flow.run_local_server(port=0)
                except Exception as e:
                    print(f"Failed to authenticate: {e}")
                    return False
            
            # Save credentials for next run
            with open(self.token_path, 'wb') as token:
                pickle.dump(creds, token)
        
        try:
            self.service = build('drive', 'v3', credentials=creds)
            return True
        except Exception as e:
            print(f"Failed to build Google Drive service: {e}")
            return False
    
    def setup_drive_folder(self, folder_name: str = "Pomodora Data") -> bool:
        """Create or find the Pomodora data folder in Google Drive"""
        if not self.service:
            return False
        
        try:
            # Search for existing folder
            results = self.service.files().list(
                q=f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
                fields="files(id, name)"
            ).execute()
            
            folders = results.get('files', [])
            
            if folders:
                self.folder_id = folders[0]['id']
                print(f"Found existing folder: {folder_name}")
            else:
                # Create new folder
                folder_metadata = {
                    'name': folder_name,
                    'mimeType': 'application/vnd.google-apps.folder'
                }
                
                folder = self.service.files().create(
                    body=folder_metadata,
                    fields='id'
                ).execute()
                
                self.folder_id = folder.get('id')
                print(f"Created new folder: {folder_name}")
            
            return True
            
        except Exception as e:
            print(f"Failed to setup drive folder: {e}")
            return False
    
    def upload_database(self, local_db_path: str) -> bool:
        """Upload local database to Google Drive"""
        if not self.service or not self.folder_id:
            return False
        
        if not os.path.exists(local_db_path):
            print(f"Local database file not found: {local_db_path}")
            return False
        
        try:
            db_filename = os.path.basename(local_db_path)
            
            # Check if database already exists in Drive
            results = self.service.files().list(
                q=f"name='{db_filename}' and parents in '{self.folder_id}' and trashed=false",
                fields="files(id, name, modifiedTime)"
            ).execute()
            
            files = results.get('files', [])
            
            # Prepare file metadata and media
            file_metadata = {
                'name': db_filename,
                'parents': [self.folder_id]
            }
            
            media = MediaFileUpload(local_db_path, resumable=True)
            
            if files:
                # Update existing file
                self.db_file_id = files[0]['id']
                updated_file = self.service.files().update(
                    fileId=self.db_file_id,
                    media_body=media,
                    fields='id, modifiedTime'
                ).execute()
                print(f"Updated database in Google Drive")
            else:
                # Create new file
                uploaded_file = self.service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id, modifiedTime'
                ).execute()
                self.db_file_id = uploaded_file.get('id')
                print(f"Uploaded new database to Google Drive")
            
            return True
            
        except Exception as e:
            print(f"Failed to upload database: {e}")
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
                print(f"Database file not found in Google Drive: {db_filename}")
                return False
            
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
            
            print(f"Downloaded database from Google Drive")
            return True
            
        except Exception as e:
            print(f"Failed to download database: {e}")
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
                print("No database file found locally or remotely")
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
                print("Remote database is newer, downloading...")
                return self.download_database(local_db_path)
            elif local_modified > remote_modified:
                print("Local database is newer, uploading...")
                return self.upload_database(local_db_path)
            else:
                print("Databases are in sync")
                return True
            
        except Exception as e:
            print(f"Failed to sync database: {e}")
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
            print(f"Failed to get database info: {e}")
            return None

class GoogleDriveManager:
    """High-level manager for Google Drive database synchronization"""
    
    def __init__(self, db_path: str = "pomodora.db"):
        self.db_path = db_path
        self.drive_sync = GoogleDriveSync()
        self.sync_interval = timedelta(minutes=5)  # Sync every 5 minutes
        self.last_sync = None
        
    def initialize(self) -> bool:
        """Initialize Google Drive integration"""
        try:
            if not self.drive_sync.authenticate():
                return False
            
            if not self.drive_sync.setup_drive_folder():
                return False
            
            # Initial sync
            return self.sync_now()
            
        except Exception as e:
            print(f"Failed to initialize Google Drive: {e}")
            return False
    
    def sync_now(self) -> bool:
        """Force immediate synchronization"""
        try:
            result = self.drive_sync.sync_database(self.db_path)
            if result:
                self.last_sync = datetime.now()
            return result
        except Exception as e:
            print(f"Sync failed: {e}")
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