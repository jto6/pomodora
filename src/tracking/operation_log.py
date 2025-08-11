"""
Operation logging system for database change tracking and merge operations
Tracks all local database changes to enable proper multi-workstation synchronization
"""

import json
from datetime import datetime
from enum import Enum
from typing import Optional
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
try:
    from utils.logging import debug_print, info_print, error_print
except ImportError:
    # Fallback for testing
    def debug_print(msg): print(f"DEBUG: {msg}")
    def info_print(msg): print(f"INFO: {msg}")
    def error_print(msg): print(f"ERROR: {msg}")

class OperationType(Enum):
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"

class OperationTracker:
    """Tracks and manages database operations for merge synchronization using in-memory storage"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        # Use in-memory list instead of database table
        self.pending_operations = []
        debug_print("In-memory operation tracker initialized")

    def log_insert(self, table_name: str, record_id: int, record_data: dict):
        """Log an INSERT operation"""
        self._log_operation(OperationType.INSERT, table_name, record_id, record_data)

    def log_update(self, table_name: str, record_id: int, old_data: dict, new_data: dict):
        """Log an UPDATE operation"""
        self._log_operation(OperationType.UPDATE, table_name, record_id, new_data, old_data)

    def log_delete(self, table_name: str, record_id: int, record_data: dict):
        """Log a DELETE operation"""
        self._log_operation(OperationType.DELETE, table_name, record_id, old_data=record_data)

    def _log_operation(self, op_type: OperationType, table_name: str, record_id: int,
                      record_data: dict = None, old_data: dict = None):
        """Internal method to log an operation in memory"""
        try:
            # Create in-memory operation record
            operation = {
                'id': len(self.pending_operations) + 1,  # Simple ID
                'operation_type': op_type.value,
                'table_name': table_name,
                'record_id': record_id,
                'record_data': json.dumps(record_data) if record_data else None,
                'old_data': json.dumps(old_data) if old_data else None,
                'timestamp': datetime.utcnow()
            }

            self.pending_operations.append(operation)
            debug_print(f"Logged {op_type.value} on {table_name}[{record_id}] (in-memory)")

        except Exception as e:
            error_print(f"Failed to log operation {op_type.value} on {table_name}[{record_id}]: {e}")

    def get_unsynced_operations(self):
        """Get all pending operations, ordered by timestamp"""
        try:
            # Sort by timestamp (all operations are unsynced in memory)
            sorted_ops = sorted(self.pending_operations, key=lambda x: x['timestamp'])
            debug_print(f"Found {len(sorted_ops)} pending operations")
            return sorted_ops
        except Exception as e:
            error_print(f"Failed to get pending operations: {e}")
            return []

    def track_operation(self, operation_type: str, table_name: str, data: dict):
        """Generic operation tracking method for compatibility"""
        try:
            # Extract record ID if present
            record_id = data.get('id', 0)  # Default ID for new records
            
            if operation_type.lower() == 'insert':
                self.log_insert(table_name, record_id, data)
            elif operation_type.lower() == 'update':
                self.log_update(table_name, record_id, {}, data)  # No old_data available
            elif operation_type.lower() == 'delete':
                self.log_delete(table_name, record_id, data)
            else:
                error_print(f"Unknown operation type: {operation_type}")
        except Exception as e:
            error_print(f"Failed to track operation {operation_type} on {table_name}: {e}")

    def get_pending_operations(self):
        """Alias for get_unsynced_operations() for compatibility"""
        return self.get_unsynced_operations()

    def mark_operations_synced(self, operation_ids: list):
        """Mark operations as synced (remove from memory)"""
        try:
            # Remove synced operations from memory
            initial_count = len(self.pending_operations)
            self.pending_operations = [op for op in self.pending_operations if op['id'] not in operation_ids]
            synced_count = initial_count - len(self.pending_operations)
            info_print(f"Cleared {synced_count} synced operations from memory")
        except Exception as e:
            error_print(f"Failed to clear synced operations: {e}")

    def clear_operations(self):
        """Clear all pending operations (after successful sync)"""
        try:
            count = len(self.pending_operations)
            self.pending_operations.clear()
            debug_print(f"Cleared {count} pending operations")
        except Exception as e:
            error_print(f"Failed to clear operations: {e}")

    def cleanup_old_operations(self, days_to_keep: int = 30):
        """No-op: in-memory operations are automatically cleaned up when synced"""
        pass


class DatabaseMerger:
    """Handles merging local operations with remote database"""

    def __init__(self, local_db_path: str, remote_db_path: str, local_tracker: OperationTracker = None):
        self.local_db_path = local_db_path
        self.remote_db_path = remote_db_path
        # Use existing tracker if provided, otherwise create new one
        self.local_tracker = local_tracker or OperationTracker(local_db_path)

    def merge_databases(self) -> bool:
        """
        Merge local operations into remote database
        Returns True if merge was successful
        """
        try:
            info_print("Starting database merge operation")

            # Get all unsynced local operations
            unsynced_ops = self.local_tracker.get_unsynced_operations()
            if not unsynced_ops:
                info_print("No local operations to merge")
                return True

            info_print(f"Merging {len(unsynced_ops)} local operations into remote database")

            # Note: Remote database should already have the correct foreign key schema
            # The local and remote databases now both use the same modern schema

            # Apply operations to remote database
            remote_engine = create_engine(f'sqlite:///{self.remote_db_path}')
            RemoteSession = sessionmaker(bind=remote_engine)
            remote_session = RemoteSession()

            try:
                applied_ops = []
                for op in unsynced_ops:
                    if self._apply_operation_to_remote(remote_session, op):
                        applied_ops.append(op['id'])
                    else:
                        error_print(f"Failed to apply operation {op['id']}, stopping merge")
                        remote_session.rollback()
                        return False

                # Commit all changes to remote database
                remote_session.commit()
                info_print(f"Successfully applied {len(applied_ops)} operations to remote database")

                # Mark operations as synced in local database
                if applied_ops:
                    self.local_tracker.mark_operations_synced(applied_ops)

                return True

            except Exception as e:
                remote_session.rollback()
                error_print(f"Error during merge operation: {e}")
                return False
            finally:
                remote_session.close()

        except Exception as e:
            error_print(f"Failed to merge databases: {e}")
            return False

    def merge_operations(self, target_db_path: str, operations: list) -> Optional[str]:
        """
        Apply operations to target database and return path to modified database.
        This method is used by LeaderElectionSyncManager for database sync.
        
        Args:
            target_db_path: Path to database to apply operations to
            operations: List of operations to apply
            
        Returns:
            Path to modified database (same as input if successful), None if failed
        """
        try:
            if not operations:
                debug_print("No operations to apply - returning original database path")
                return target_db_path
                
            info_print(f"Applying {len(operations)} operations to database: {target_db_path}")
            
            # Apply operations to the target database
            target_engine = create_engine(f'sqlite:///{target_db_path}')
            TargetSession = sessionmaker(bind=target_engine)
            target_session = TargetSession()
            
            try:
                applied_count = 0
                for op in operations:
                    if self._apply_operation_to_remote(target_session, op):
                        applied_count += 1
                    else:
                        error_print(f"Failed to apply operation {op['id']}, stopping merge")
                        target_session.rollback()
                        return None
                
                # Commit all changes
                target_session.commit()
                info_print(f"Successfully applied {applied_count} operations to target database")
                
                return target_db_path
                
            except Exception as e:
                target_session.rollback()
                error_print(f"Error applying operations to target database: {e}")
                return None
            finally:
                target_session.close()
                
        except Exception as e:
            error_print(f"Failed to merge operations into target database: {e}")
            return None

    def _apply_operation_to_remote(self, remote_session, operation: dict) -> bool:
        """Apply a single operation to the remote database"""
        try:
            table_name = operation['table_name']
            record_id = operation['record_id']
            op_type = operation['operation_type']

            debug_print(f"Applying {op_type} operation on {table_name}[{record_id}]")

            if op_type == OperationType.INSERT.value:
                return self._apply_insert(remote_session, table_name, record_id, operation['record_data'])
            elif op_type == OperationType.UPDATE.value:
                return self._apply_update(remote_session, table_name, record_id, operation['record_data'])
            elif op_type == OperationType.DELETE.value:
                return self._apply_delete(remote_session, table_name, record_id)
            else:
                error_print(f"Unknown operation type: {op_type}")
                return False

        except Exception as e:
            error_print(f"Failed to apply operation {operation['id']}: {e}")
            return False

    def _apply_insert(self, remote_session, table_name: str, record_id: int, record_data_json: str) -> bool:
        """Apply INSERT operation to remote database"""
        try:
            record_data = json.loads(record_data_json)

            # Always let database auto-assign IDs for INSERT operations
            # This prevents all ID conflicts and follows database best practices
            processed_data = record_data.copy()
            processed_data.pop('id', None)  # Always remove ID to force auto-assignment
            
            debug_print(f"Inserting {table_name} record with auto-assigned ID (original local ID was {record_id})")

            # Handle datetime conversion for SQLite
            for key, value in processed_data.items():
                if isinstance(value, str) and key.endswith('_at'):
                    # Keep ISO format datetime strings as-is for SQLite
                    pass
                elif key.endswith('_time') and isinstance(value, str):
                    # Keep ISO format datetime strings as-is for SQLite
                    pass

            # Build INSERT query without ID column
            columns = list(processed_data.keys())
            placeholders = [f":{col}" for col in columns]
            query = text(f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({', '.join(placeholders)})")

            remote_session.execute(query, processed_data)
            debug_print(f"Successfully inserted {table_name} record with auto-assigned ID")
            return True

        except Exception as e:
            error_print(f"Failed to apply INSERT for {table_name}[{record_id}]: {e}")
            return False

    def _apply_update(self, remote_session, table_name: str, record_id: int, record_data_json: str) -> bool:
        """Apply UPDATE operation to remote database"""
        try:
            record_data = json.loads(record_data_json)

            # Check if record exists
            existing = remote_session.execute(
                text(f"SELECT id FROM {table_name} WHERE id = :id"),
                {"id": record_id}
            ).fetchone()

            if not existing:
                debug_print(f"Record {table_name}[{record_id}] doesn't exist in remote, skipping UPDATE")
                return True

            # Build UPDATE query
            set_clauses = [f"{col} = :{col}" for col in record_data.keys() if col != 'id']
            query = text(f"UPDATE {table_name} SET {', '.join(set_clauses)} WHERE id = :id")

            # Add id to record_data for WHERE clause
            update_data = record_data.copy()
            update_data['id'] = record_id

            remote_session.execute(query, update_data)
            debug_print(f"Successfully updated {table_name}[{record_id}] in remote")
            return True

        except Exception as e:
            error_print(f"Failed to apply UPDATE for {table_name}[{record_id}]: {e}")
            return False

    def _apply_delete(self, remote_session, table_name: str, record_id: int) -> bool:
        """Apply DELETE operation to remote database"""
        try:
            # For sprints, always apply DELETE (we want to preserve deletions)
            if table_name == 'sprints':
                remote_session.execute(
                    text(f"DELETE FROM {table_name} WHERE id = :id"),
                    {"id": record_id}
                )
                debug_print(f"Successfully deleted {table_name}[{record_id}] from remote")
                return True

            # For projects and task_categories, be more careful about deletes
            # Check if the record is referenced by any sprints
            if table_name in ['projects', 'task_categories']:
                foreign_key_col = 'project_id' if table_name == 'projects' else 'task_category_id'
                references = remote_session.execute(
                    text(f"SELECT COUNT(*) FROM sprints WHERE {foreign_key_col} = :id"),
                    {"id": record_id}
                ).fetchone()[0]

                if references > 0:
                    debug_print(f"Skipping DELETE of {table_name}[{record_id}] - still referenced by {references} sprints")
                    return True

                remote_session.execute(
                    text(f"DELETE FROM {table_name} WHERE id = :id"),
                    {"id": record_id}
                )
                debug_print(f"Successfully deleted {table_name}[{record_id}] from remote")
                return True

            return True

        except Exception as e:
            error_print(f"Failed to apply DELETE for {table_name}[{record_id}]: {e}")
            return False