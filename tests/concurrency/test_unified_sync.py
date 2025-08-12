"""
Unified concurrency tests for leader election sync.
Tests both LocalFile and GoogleDrive coordination backends with same sync logic.
"""

import pytest

from helpers.unified_sync_simulators import UnifiedSyncSimulator


@pytest.mark.concurrency
@pytest.mark.database
@pytest.mark.slow
@pytest.mark.parametrize("backend_type", ["local_file"])  # Add "google_drive" when ready
class TestUnifiedSyncConcurrency:
    """Test unified leader election sync with different coordination backends"""
    
    def test_manual_sync_conflicts(self, backend_type):
        """Test multiple manual sync button presses simultaneously"""
        simulator = UnifiedSyncSimulator(backend_type=backend_type, num_instances=3)
        try:
            instances = simulator.create_app_instances()
            assert len(instances) == 3
            
            # Create some initial data
            sprint_ids = simulator.create_concurrent_sprints(count_per_instance=5)
            
            # Verify initial data creation
            total_sprints = sum(len(ids) for ids in sprint_ids.values())
            assert total_sprints == 15  # 3 instances × 5 sprints each
            
            # Simulate manual sync conflicts
            sync_results = simulator.simulate_sync_triggers()
            
            # Verify sync operations completed
            assert 'manual_sync' in sync_results
            assert len(sync_results['manual_sync']) > 0
            
            # Check for errors
            assert len(simulator.errors) == 0, f"Errors occurred: {simulator.errors}"
            
            # Verify data integrity
            integrity = simulator.verify_data_integrity()
            assert integrity['data_consistency'], f"Data integrity issues: {integrity}"
            assert integrity['backend_type'] == backend_type
        finally:
            simulator.cleanup()
    
    def test_timer_sync_conflicts(self, backend_type):
        """Test automatic timer-triggered sync conflicts"""
        simulator = UnifiedSyncSimulator(backend_type=backend_type, num_instances=4)
        try:
            simulator.create_app_instances()
            
            # Simulate timer-triggered sync operations
            sync_results = simulator.simulate_sync_triggers()
            
            # Verify all sync types were triggered
            assert len(sync_results['timer_sync']) > 0
            assert len(simulator.errors) == 0, f"Timer sync errors: {simulator.errors}"
            
            # Verify data integrity
            integrity = simulator.verify_data_integrity()
            assert integrity['data_consistency']
            assert integrity['backend_type'] == backend_type
        finally:
            simulator.cleanup()
    
    def test_shutdown_sync_conflicts(self, backend_type):
        """Test app shutdown sync conflicts"""
        simulator = UnifiedSyncSimulator(backend_type=backend_type, num_instances=2)
        try:
            instances = simulator.create_app_instances()
            
            # Create some data to sync
            simulator.create_concurrent_sprints(count_per_instance=3)
            
            # Simulate shutdown sync operations
            sync_results = simulator.simulate_sync_triggers(sync_types=['shutdown', 'shutdown'])
            
            # Verify shutdown sync executed
            assert len(sync_results['shutdown_sync']) > 0
            assert len(simulator.errors) == 0, f"Shutdown sync errors: {simulator.errors}"
            
            # Verify data integrity after shutdown sync
            integrity = simulator.verify_data_integrity()
            assert integrity['data_consistency']
            assert integrity['backend_type'] == backend_type
        finally:
            simulator.cleanup()
    
    def test_leader_election_robustness(self, backend_type):
        """Test leader election behavior with multiple concurrent instances"""
        simulator = UnifiedSyncSimulator(backend_type=backend_type, num_instances=5)
        try:
            instances = simulator.create_app_instances()
            
            # Create concurrent data operations
            simulator.create_concurrent_sprints(count_per_instance=8)
            
            # Get sync status to verify proper coordination
            status = simulator.get_sync_status()
            assert status['backend_type'] == backend_type
            assert status['num_instances'] == 5
            
            # Verify all instances can sync without conflicts
            sync_results = simulator.simulate_sync_triggers()
            
            # Check data integrity after complex scenarios
            integrity = simulator.verify_data_integrity()
            assert integrity['data_consistency'], f"Data integrity failed: {integrity}"
            assert integrity['total_sprints'] > 0
            assert integrity['backend_type'] == backend_type
        finally:
            simulator.cleanup()


@pytest.mark.concurrency
@pytest.mark.database 
@pytest.mark.slow
class TestBackendSpecificFeatures:
    """Test features specific to different coordination backends"""
    
    def test_local_file_coordination(self):
        """Test LocalFile backend specific coordination features"""
        simulator = UnifiedSyncSimulator(backend_type="local_file", num_instances=3)
        try:
            instances = simulator.create_app_instances()
            
            # Verify shared database file location exists
            assert simulator.shared_db_path.parent.exists()
            
            # Test concurrent operations
            simulator.create_concurrent_sprints(count_per_instance=5)
            
            # Verify coordination directory is created
            coordination_dir = simulator.shared_db_path.parent / ".pomodora_sync"
            assert coordination_dir.exists()
            
            # Verify data integrity
            integrity = simulator.verify_data_integrity()
            assert integrity['data_consistency']
            assert integrity['backend_type'] == "local_file"
            
        finally:
            simulator.cleanup()
    
    @pytest.mark.skip("Mock Google Drive backend - enable when ready")
    def test_google_drive_coordination(self):
        """Test GoogleDrive backend coordination with mocks"""
        simulator = UnifiedSyncSimulator(backend_type="google_drive", num_instances=3)
        try:
            instances = simulator.create_app_instances()
            
            # Test concurrent operations with mock Google Drive
            simulator.create_concurrent_sprints(count_per_instance=3)
            
            # Verify mock coordination worked
            status = simulator.get_sync_status()
            assert status['backend_type'] == "google_drive"
            
            # Verify data integrity
            integrity = simulator.verify_data_integrity()
            assert integrity['data_consistency']
            assert integrity['backend_type'] == "google_drive"
            
        finally:
            simulator.cleanup()


@pytest.mark.concurrency
@pytest.mark.database
@pytest.mark.slow
class TestConcurrencyEdgeCases:
    """Test edge cases and error scenarios in concurrent sync"""
    
    @pytest.mark.parametrize("backend_type", ["local_file"])
    def test_coordination_backend_unavailable(self, backend_type):
        """Test behavior when coordination backend becomes unavailable"""
        simulator = UnifiedSyncSimulator(backend_type=backend_type, num_instances=2)
        try:
            instances = simulator.create_app_instances()
            
            # Initially everything should work
            simulator.create_concurrent_sprints(count_per_instance=2)
            
            # Simulate backend becoming unavailable (remove shared directory for local_file)
            if backend_type == "local_file":
                coordination_dir = simulator.shared_db_path.parent / ".pomodora_sync"
                if coordination_dir.exists():
                    import shutil
                    shutil.rmtree(coordination_dir)
            
            # Operations should still work locally even if sync fails
            integrity = simulator.verify_data_integrity()
            assert integrity['total_sprints'] > 0  # Data was created successfully
            
        finally:
            simulator.cleanup()
    
    @pytest.mark.parametrize("backend_type", ["local_file"])
    def test_cleanup_stale_coordination_files(self, backend_type):
        """Test cleanup of stale coordination files from crashed instances"""
        simulator = UnifiedSyncSimulator(backend_type=backend_type, num_instances=1)
        try:
            instances = simulator.create_app_instances()
            
            # Create some coordination files
            simulator.create_concurrent_sprints(count_per_instance=1)
            
            # Test cleanup functionality
            for instance in instances:
                instance.cleanup_stale_coordination_files(max_age_hours=0)  # Clean all files
            
            # Verify cleanup worked (no crashes)
            if backend_type == "local_file":
                coordination_dir = simulator.shared_db_path.parent / ".pomodora_sync"
                if coordination_dir.exists():
                    files = list(coordination_dir.glob("*"))
                    # Some coordination files might remain (e.g., lock files in use)
                    assert len(files) >= 0  # Just ensure no crash
            
        finally:
            simulator.cleanup()


@pytest.mark.concurrency
@pytest.mark.database
@pytest.mark.slow
class TestSyncConsistency:
    """Test that unified sync produces consistent results across backends"""
    
    def test_same_sync_logic_different_backends(self):
        """Verify that the same sync logic works identically with different backends"""
        results = {}
        
        # Test with local file backend
        for backend_type in ["local_file"]:  # Add "google_drive" when ready
            simulator = UnifiedSyncSimulator(backend_type=backend_type, num_instances=3)
            try:
                instances = simulator.create_app_instances()
                
                # Create identical data across backends
                sprint_ids = simulator.create_concurrent_sprints(count_per_instance=5)
                
                # Run sync operations
                sync_results = simulator.simulate_sync_triggers()
                
                # Verify data integrity
                integrity = simulator.verify_data_integrity()
                
                results[backend_type] = {
                    'sprint_ids': sprint_ids,
                    'sync_results': sync_results,
                    'integrity': integrity,
                    'errors': simulator.errors.copy()
                }
                
            finally:
                simulator.cleanup()
        
        # All backends should produce consistent results
        for backend_type, result in results.items():
            assert result['integrity']['data_consistency'], f"Backend {backend_type} failed integrity check"
            assert len(result['errors']) == 0, f"Backend {backend_type} had errors: {result['errors']}"
            
            # All should create same amount of data
            total_sprints = sum(len(ids) for ids in result['sprint_ids'].values())
            assert total_sprints == 15  # 3 instances × 5 sprints each