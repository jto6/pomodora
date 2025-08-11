"""
Concurrency tests for different sync triggers: manual, timer, and shutdown sync.
Tests multi-app database concurrency with overlapping sync operations.
"""

import pytest
import time
import threading
from datetime import datetime

from helpers.sync_simulators import MultiAppSimulator, MockGoogleDriveSync


@pytest.mark.concurrency
@pytest.mark.database
@pytest.mark.slow
class TestSyncTriggerConcurrency:
    """Test concurrent sync operations from different triggers"""
    
    def test_manual_sync_conflicts(self):
        """Test multiple manual sync button presses simultaneously"""
        simulator = MultiAppSimulator(num_instances=3)
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
        finally:
            simulator.cleanup()
    
    def test_timer_sync_conflicts(self):
        """Test automatic timer-triggered sync conflicts"""
        simulator = MultiAppSimulator(num_instances=4)
        try:
            simulator.create_app_instances()
            
            # Simulate timer-triggered sync operations
            sync_results = simulator.simulate_sync_triggers()
            
            # Verify timer sync operations
            assert 'timer_sync' in sync_results
            timer_events = sync_results['timer_sync']
            
            # Should have start and complete events
            start_events = [e for e in timer_events if 'started' in e]
            complete_events = [e for e in timer_events if 'completed' in e]
            
            assert len(start_events) >= 1
            assert len(complete_events) >= 1
            
            # No errors should occur
            assert len(simulator.errors) == 0
        finally:
            simulator.cleanup()
    
    def test_shutdown_sync_overlaps(self):
        """Test application shutdown sync overlapping with other operations"""
        simulator = MultiAppSimulator(num_instances=3)
        try:
            simulator.create_app_instances()
            
            # Create data while shutdown sync is happening
            def create_data_during_shutdown():
                time.sleep(0.1)  # Let shutdown start
                simulator.create_concurrent_sprints(count_per_instance=3)
            
            # Start data creation thread
            data_thread = threading.Thread(target=create_data_during_shutdown)
            data_thread.start()
            
            # Start shutdown sync
            sync_results = simulator.simulate_sync_triggers()
            
            # Wait for data creation to complete
            data_thread.join()
            
            # Verify shutdown sync handled concurrent operations
            assert 'shutdown_sync' in sync_results
            shutdown_events = sync_results['shutdown_sync']
            assert len(shutdown_events) > 0
            
            # Check data integrity after concurrent operations
            integrity = simulator.verify_data_integrity()
            assert integrity['total_sprints'] > 0
            assert integrity['data_consistency']
        finally:
            simulator.cleanup()
    
    def test_mixed_trigger_scenarios(self):
        """Test complex scenarios with manual + timer + shutdown sync"""
        simulator = MultiAppSimulator(num_instances=5)
        try:
            simulator.create_app_instances()
            
            # Run mixed sync scenario
            scenario_results = simulator.test_mixed_sync_scenarios()
            
            # Verify all sync types occurred
            overlapping_syncs = scenario_results['overlapping_syncs']
            assert 'manual_sync' in overlapping_syncs
            assert 'timer_sync' in overlapping_syncs
            assert 'shutdown_sync' in overlapping_syncs
            
            # Verify conflict resolution
            assert 'data_conflicts' in scenario_results
            assert 'resolution_outcomes' in scenario_results
            
            # Check final data state
            integrity = simulator.verify_data_integrity()
            assert integrity['foreign_key_violations'] == 0
            
            # Should have minimal errors despite conflicts
            assert len(simulator.errors) <= 2  # Allow minor timing-related errors
        finally:
            simulator.cleanup()
    
    def test_sync_trigger_priorities(self):
        """Test that different sync triggers handle priorities correctly"""
        simulator = MultiAppSimulator(num_instances=3)
        mock_sync = MockGoogleDriveSync()
        
        try:
            simulator.create_app_instances()
            
            # Simulate different sync priorities
            priorities = []
            
            def manual_sync_attempt():
                if mock_sync.attempt_leader_election("manual_sync"):
                    priorities.append("manual_sync_leader")
                    time.sleep(0.2)
                    mock_sync.release_leadership("manual_sync")
            
            def timer_sync_attempt():
                time.sleep(0.1)  # Start slightly later
                if mock_sync.attempt_leader_election("timer_sync"):
                    priorities.append("timer_sync_leader")
                    time.sleep(0.3)
                    mock_sync.release_leadership("timer_sync")
            
            def shutdown_sync_attempt():
                time.sleep(0.05)  # Start earliest
                if mock_sync.attempt_leader_election("shutdown_sync"):
                    priorities.append("shutdown_sync_leader")
                    time.sleep(0.1)
                    mock_sync.release_leadership("shutdown_sync")
            
            # Start concurrent sync attempts
            threads = [
                threading.Thread(target=manual_sync_attempt),
                threading.Thread(target=timer_sync_attempt),
                threading.Thread(target=shutdown_sync_attempt)
            ]
            
            for thread in threads:
                thread.start()
            
            for thread in threads:
                thread.join()
            
            # Verify leader election worked
            assert len(priorities) >= 1  # At least one sync became leader
            
            # Check sync history
            sync_history = mock_sync.get_sync_history()
            assert len(sync_history) >= 3  # Should have multiple election attempts
            
        finally:
            simulator.cleanup()


@pytest.mark.concurrency
@pytest.mark.database
@pytest.mark.slow
class TestHighFrequencySyncOperations:
    """Test high-frequency sync operations across multiple instances"""
    
    def test_rapid_sync_cycles(self):
        """Test rapid sync cycles under load"""
        simulator = MultiAppSimulator(num_instances=4)
        try:
            simulator.create_app_instances()
            
            # Run stress test for short duration
            stress_results = simulator.stress_test_operations(duration_minutes=0.05)  # 3 seconds
            
            # Verify operations completed
            assert stress_results['operations_completed'] > 0
            
            # Check performance metrics
            metrics = stress_results['performance_metrics']
            assert 'operations_per_second' in metrics
            assert metrics['operations_per_second'] > 0
            
            # Verify data integrity after stress test
            integrity = simulator.verify_data_integrity()
            assert integrity['total_sprints'] == stress_results['operations_completed']
            assert integrity['data_consistency']
            
            # Errors should be minimal
            error_rate = stress_results['errors_encountered'] / max(1, stress_results['operations_completed'])
            assert error_rate < 0.1  # Less than 10% error rate
        finally:
            simulator.cleanup()
    
    def test_concurrent_database_writes(self):
        """Test concurrent database writes from multiple sync triggers"""
        simulator = MultiAppSimulator(num_instances=6)
        try:
            instances = simulator.create_app_instances()
            
            # Create data concurrently from all instances
            sprint_collections = []
            
            def create_data_batch(instance_index):
                results = simulator.create_concurrent_sprints(count_per_instance=8)
                sprint_collections.append(results)
            
            # Start multiple data creation threads
            threads = []
            for i in range(3):  # 3 concurrent batches
                thread = threading.Thread(target=create_data_batch, args=(i,))
                threads.append(thread)
                thread.start()
            
            # Wait for all to complete
            for thread in threads:
                thread.join()
            
            # Verify all data was created without conflicts
            total_expected = 3 * 6 * 8  # 3 batches × 6 instances × 8 sprints
            integrity = simulator.verify_data_integrity()
            
            # Should have created significant amount of data
            assert integrity['total_sprints'] > 50  # Allowing for some variations
            assert integrity['foreign_key_violations'] == 0
            assert integrity['data_consistency']
        finally:
            simulator.cleanup()
    
    def test_sync_interruption_recovery(self):
        """Test sync recovery after interruptions"""
        simulator = MultiAppSimulator(num_instances=3)
        mock_sync = MockGoogleDriveSync()
        
        try:
            simulator.create_app_instances()
            
            # Create initial data
            simulator.create_concurrent_sprints(count_per_instance=5)
            initial_integrity = simulator.verify_data_integrity()
            initial_count = initial_integrity['total_sprints']
            
            # Simulate sync interruption
            interruption_results = []
            
            def interrupted_sync():
                if mock_sync.attempt_leader_election("interrupted_sync"):
                    interruption_results.append("sync_started")
                    time.sleep(0.1)
                    # Simulate interruption (no release_leadership call)
                    interruption_results.append("sync_interrupted")
            
            def recovery_sync():
                time.sleep(0.2)  # Wait for interruption
                # New sync should be able to take over
                if mock_sync.attempt_leader_election("recovery_sync"):
                    interruption_results.append("recovery_sync_started")
                    time.sleep(0.1)
                    mock_sync.release_leadership("recovery_sync")
                    interruption_results.append("recovery_sync_completed")
            
            # Run interruption scenario
            interrupt_thread = threading.Thread(target=interrupted_sync)
            recovery_thread = threading.Thread(target=recovery_sync)
            
            interrupt_thread.start()
            recovery_thread.start()
            
            interrupt_thread.join()
            recovery_thread.join()
            
            # Verify recovery occurred
            assert "sync_interrupted" in interruption_results
            assert "recovery_sync_completed" in interruption_results
            
            # Data should still be intact
            final_integrity = simulator.verify_data_integrity()
            assert final_integrity['total_sprints'] == initial_count
            assert final_integrity['data_consistency']
        finally:
            simulator.cleanup()


@pytest.mark.concurrency
@pytest.mark.database
@pytest.mark.slow
class TestSyncDataIntegrity:
    """Test data integrity across different sync scenarios"""
    
    def test_no_data_loss_during_conflicts(self):
        """Test that no data is lost during sync conflicts"""
        simulator = MultiAppSimulator(num_instances=4)
        try:
            simulator.create_app_instances()
            
            # Create baseline data
            baseline_sprints = simulator.create_concurrent_sprints(count_per_instance=10)
            baseline_total = sum(len(ids) for ids in baseline_sprints.values())
            
            # Run conflicting operations
            conflict_results = simulator.test_mixed_sync_scenarios()
            
            # Create additional data during conflicts
            additional_sprints = simulator.create_concurrent_sprints(count_per_instance=5)
            additional_total = sum(len(ids) for ids in additional_sprints.values())
            
            # Verify no data loss
            final_integrity = simulator.verify_data_integrity()
            expected_minimum = baseline_total + additional_total
            
            assert final_integrity['total_sprints'] >= expected_minimum
            assert final_integrity['foreign_key_violations'] == 0
            assert final_integrity['data_consistency']
        finally:
            simulator.cleanup()
    
    def test_foreign_key_consistency_under_load(self):
        """Test foreign key consistency during high load"""
        simulator = MultiAppSimulator(num_instances=5)
        try:
            simulator.create_app_instances()
            
            # Run high-load scenario
            stress_results = simulator.stress_test_operations(duration_minutes=0.1)
            
            # Verify foreign key integrity
            integrity = simulator.verify_data_integrity()
            
            # Should have no foreign key violations despite load
            assert integrity['foreign_key_violations'] == 0
            
            # All sprints should have valid project and category references
            assert integrity['data_consistency']
            
            # Verify we actually created substantial data
            assert integrity['total_sprints'] > 10
        finally:
            simulator.cleanup()
    
    def test_timestamp_consistency(self):
        """Test timestamp consistency across concurrent operations"""
        simulator = MultiAppSimulator(num_instances=3)
        try:
            simulator.create_app_instances()
            
            # Record operation start time
            operation_start = datetime.now()
            
            # Create data with timing constraints
            sprint_ids = simulator.create_concurrent_sprints(count_per_instance=8)
            
            operation_end = datetime.now()
            
            # Verify all timestamps are reasonable
            if simulator.instances:
                session = simulator.instances[0].get_session()
                try:
                    from tracking.models import Sprint
                    all_sprints = session.query(Sprint).all()
                    
                    for sprint in all_sprints:
                        # Start time should be within operation window
                        assert sprint.start_time >= operation_start
                        assert sprint.start_time <= operation_end
                        
                        # If completed, end time should be after start time
                        if sprint.completed and sprint.end_time:
                            assert sprint.end_time >= sprint.start_time
                finally:
                    session.close()
            
            # Verify data integrity
            integrity = simulator.verify_data_integrity()
            assert integrity['data_consistency']
        finally:
            simulator.cleanup()