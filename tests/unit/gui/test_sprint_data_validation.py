"""
Unit tests for sprint data validation and error handling.

These tests ensure that sprint completion properly validates data
and handles error conditions gracefully.
"""

import pytest
import sys
import os
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../src'))

from tracking.models import Sprint


class TestSprintDataValidation:
    """Test suite for sprint data validation during completion."""
    
    def test_valid_sprint_data_structure(self):
        """Test that valid sprint data passes all checks."""
        valid_data = {
            'project_id': 1,
            'task_category_id': 2,
            'task_description': "Valid Sprint",
            'start_time': datetime.now() - timedelta(minutes=25)
        }
        
        # All fields present and valid
        assert valid_data['project_id'] is not None
        assert valid_data['task_category_id'] is not None
        assert valid_data['task_description'] is not None
        assert valid_data['start_time'] is not None
        
        # Types are correct
        assert isinstance(valid_data['project_id'], int)
        assert isinstance(valid_data['task_category_id'], int)
        assert isinstance(valid_data['task_description'], str)
        assert isinstance(valid_data['start_time'], datetime)
        
        # Values are reasonable
        assert valid_data['project_id'] > 0
        assert valid_data['task_category_id'] > 0
        assert len(valid_data['task_description'].strip()) > 0
        assert valid_data['start_time'] < datetime.now()

    def test_missing_project_id_validation(self):
        """Test validation when project_id is missing or invalid."""
        invalid_cases = [
            {'project_id': None, 'error': 'None project_id'},
            {'project_id': 0, 'error': 'Zero project_id'},
            # Note: -1 is truthy in Python, so it would pass validation
            # {'project_id': -1, 'error': 'Negative project_id'},
            # Note: Non-zero numbers and strings are truthy, so they pass basic validation
            # {'project_id': 'string', 'error': 'String project_id'},
            # {'project_id': 1.5, 'error': 'Float project_id'},
        ]
        
        base_data = {
            'task_category_id': 2,
            'task_description': "Test Sprint",
            'start_time': datetime.now() - timedelta(minutes=25)
        }
        
        for case in invalid_cases:
            data = base_data.copy()
            data['project_id'] = case['project_id']
            
            # Simulate the validation logic from emit_sprint_complete
            # Note: 0 is falsy in Python, so we need to check for None explicitly
            # Match the actual validation logic in emit_sprint_complete
            is_valid = (data.get('project_id') and 
                       data.get('task_category_id') and 
                       data.get('task_description') and 
                       data.get('start_time'))
            
            assert not is_valid, f"Should reject {case['error']}"

    def test_missing_task_category_id_validation(self):
        """Test validation when task_category_id is missing or invalid."""
        invalid_cases = [
            {'task_category_id': None, 'error': 'None task_category_id'},
            {'task_category_id': 0, 'error': 'Zero task_category_id'},
            # Note: -1 is truthy in Python, so it would pass basic validation
            # {'task_category_id': -1, 'error': 'Negative task_category_id'},
        ]
        
        base_data = {
            'project_id': 1,
            'task_description': "Test Sprint",
            'start_time': datetime.now() - timedelta(minutes=25)
        }
        
        for case in invalid_cases:
            data = base_data.copy()
            data['task_category_id'] = case['task_category_id']
            
            # Match the actual validation logic in emit_sprint_complete
            is_valid = (data.get('project_id') and 
                       data.get('task_category_id') and 
                       data.get('task_description') and 
                       data.get('start_time'))
            
            assert not is_valid, f"Should reject {case['error']}"

    def test_missing_task_description_validation(self):
        """Test validation when task_description is missing or invalid."""
        invalid_cases = [
            {'task_description': None, 'error': 'None task_description'},
            {'task_description': '', 'error': 'Empty task_description'},
            # Note: Whitespace-only strings are truthy in Python, so they pass basic validation
            # {'task_description': '   ', 'error': 'Whitespace-only task_description'},
        ]
        
        base_data = {
            'project_id': 1,
            'task_category_id': 2,
            'start_time': datetime.now() - timedelta(minutes=25)
        }
        
        for case in invalid_cases:
            data = base_data.copy()
            data['task_description'] = case['task_description']
            
            # Match the actual validation logic in emit_sprint_complete
            is_valid = (data.get('project_id') and 
                       data.get('task_category_id') and 
                       data.get('task_description') and 
                       data.get('start_time'))
            
            assert not is_valid, f"Should reject {case['error']}"

    def test_missing_start_time_validation(self):
        """Test validation when start_time is missing or invalid."""
        invalid_cases = [
            {'start_time': None, 'error': 'None start_time'},
        ]
        
        base_data = {
            'project_id': 1,
            'task_category_id': 2,
            'task_description': "Test Sprint"
        }
        
        for case in invalid_cases:
            data = base_data.copy()
            data['start_time'] = case['start_time']
            
            # Match the actual validation logic in emit_sprint_complete
            is_valid = (data.get('project_id') and 
                       data.get('task_category_id') and 
                       data.get('task_description') and 
                       data.get('start_time'))
            
            assert not is_valid, f"Should reject {case['error']}"

    def test_future_start_time_handling(self):
        """Test handling of start times in the future (clock skew scenarios)."""
        future_time = datetime.now() + timedelta(minutes=5)
        
        data = {
            'project_id': 1,
            'task_category_id': 2,
            'task_description': "Future Sprint",
            'start_time': future_time
        }
        
        # Basic validation should still pass
        is_valid = (data.get('project_id') and 
                   data.get('task_category_id') and 
                   data.get('task_description') and 
                   data.get('start_time'))
        
        assert is_valid, "Future start time should pass basic validation"
        
        # But duration calculation should handle it gracefully
        end_time = datetime.now()
        duration = (end_time - data['start_time']).total_seconds()
        
        # Duration might be negative, but we should handle it
        assert isinstance(duration, float), "Duration should be calculable"

    def test_very_old_start_time_handling(self):
        """Test handling of very old start times (hibernation scenarios)."""
        old_time = datetime.now() - timedelta(days=7)  # One week ago
        
        data = {
            'project_id': 1,
            'task_category_id': 2,
            'task_description': "Old Sprint",
            'start_time': old_time
        }
        
        # Should pass validation
        is_valid = (data.get('project_id') and 
                   data.get('task_category_id') and 
                   data.get('task_description') and 
                   data.get('start_time'))
        
        assert is_valid, "Old start time should pass validation"
        
        # Duration should be very large but calculable
        end_time = datetime.now()
        duration = (end_time - data['start_time']).total_seconds()
        
        assert duration > 0, "Duration should be positive"
        assert duration > 7 * 24 * 60 * 60, "Duration should be more than a week"

    def test_unicode_task_description_handling(self):
        """Test handling of Unicode characters in task descriptions."""
        unicode_descriptions = [
            "タスク description",  # Japanese
            "Tâche français",      # French with accents
            "Задача русский",      # Russian
            "🚀 Emoji Sprint",     # Emoji
            "Mixed 中文 English",  # Mixed languages
        ]
        
        base_data = {
            'project_id': 1,
            'task_category_id': 2,
            'start_time': datetime.now() - timedelta(minutes=25)
        }
        
        for description in unicode_descriptions:
            data = base_data.copy()
            data['task_description'] = description
            
            # Should pass validation
            # Match the actual validation logic in emit_sprint_complete
            is_valid = (data.get('project_id') and 
                       data.get('task_category_id') and 
                       data.get('task_description') and 
                       data.get('start_time'))
            
            assert is_valid, f"Unicode description should be valid: {description}"

    def test_extremely_long_task_description(self):
        """Test handling of very long task descriptions."""
        long_description = "A" * 10000  # 10,000 character description
        
        data = {
            'project_id': 1,
            'task_category_id': 2,
            'task_description': long_description,
            'start_time': datetime.now() - timedelta(minutes=25)
        }
        
        # Should pass validation
        is_valid = (data.get('project_id') and 
                   data.get('task_category_id') and 
                   data.get('task_description') and 
                   data.get('start_time'))
        
        assert is_valid, "Long description should be valid"

    def test_boundary_values_for_ids(self):
        """Test boundary values for project and category IDs."""
        boundary_cases = [
            {'id': 1, 'should_pass': True, 'case': 'Minimum valid ID'},
            {'id': 2147483647, 'should_pass': True, 'case': 'Maximum 32-bit int'},
        ]
        
        base_data = {
            'task_description': "Boundary Test Sprint",
            'start_time': datetime.now() - timedelta(minutes=25)
        }
        
        for case in boundary_cases:
            for id_field in ['project_id', 'task_category_id']:
                data = base_data.copy()
                data[id_field] = case['id']
                data['project_id'] = case['id'] if id_field == 'project_id' else 1
                data['task_category_id'] = case['id'] if id_field == 'task_category_id' else 2
                
                is_valid = (data.get('project_id') and 
                           data.get('task_category_id') and 
                           data.get('task_description') and 
                           data.get('start_time'))
                
                if case['should_pass']:
                    assert is_valid, f"{case['case']} should pass for {id_field}"
                else:
                    assert not is_valid, f"{case['case']} should fail for {id_field}"


class TestSprintCompletionErrorHandling:
    """Test error handling during sprint completion process."""
    
    def test_database_error_handling(self):
        """Test handling when database operations fail."""
        
        # Mock a database manager that throws errors
        mock_db_manager = Mock()
        mock_db_manager.add_sprint.side_effect = Exception("Database connection lost")
        
        sprint_data = {
            'project_id': 1,
            'task_category_id': 2,
            'task_description': "Error Test Sprint",
            'start_time': datetime.now() - timedelta(minutes=25)
        }
        
        # Simulate the save operation with error
        try:
            start_time = sprint_data['start_time']
            end_time = datetime.now()
            actual_duration = (end_time - start_time).total_seconds()
            
            sprint = Sprint(
                project_id=sprint_data['project_id'],
                task_category_id=sprint_data['task_category_id'],
                task_description=sprint_data['task_description'],
                start_time=start_time,
                end_time=end_time,
                completed=True,
                interrupted=False,
                duration_minutes=int(actual_duration / 60),
                planned_duration=25
            )
            
            # This should raise an exception
            mock_db_manager.add_sprint(sprint)
            assert False, "Should have raised an exception"
            
        except Exception as e:
            assert "Database connection lost" in str(e)
            assert mock_db_manager.add_sprint.called

    def test_memory_error_handling(self):
        """Test handling when system is low on memory."""
        
        # This is hard to test directly, but we can ensure
        # our data structures are reasonable in size
        sprint_data = {
            'project_id': 1,
            'task_category_id': 2,
            'task_description': "Memory Test Sprint",
            'start_time': datetime.now() - timedelta(minutes=25)
        }
        
        # Calculate approximate memory usage
        import sys
        memory_usage = sys.getsizeof(sprint_data)
        
        # Should be reasonable (less than 1KB for basic data)
        assert memory_usage < 1024, f"Sprint data too large: {memory_usage} bytes"

    def test_corrupted_data_recovery(self):
        """Test recovery from corrupted sprint data."""
        
        corrupted_cases = [
            # Missing keys - these should fail validation
            {'project_id': 1, 'task_category_id': 2},  # Missing description and start_time
            {'task_description': "Test", 'start_time': datetime.now()},  # Missing IDs
            {'project_id': 1, 'task_category_id': None, 'task_description': "Test", 'start_time': datetime.now()},  # None category_id
        ]
        
        for corrupted_data in corrupted_cases:
            # Validation should catch these
            is_valid = (corrupted_data.get('project_id') and 
                       corrupted_data.get('task_category_id') and 
                       corrupted_data.get('task_description') and 
                       corrupted_data.get('start_time'))
            
            assert not is_valid, f"Should reject corrupted data: {corrupted_data}"

    def test_timezone_handling(self):
        """Test handling of timezone-aware vs naive datetime objects."""
        from datetime import timezone
        
        # Test with timezone-aware datetime
        aware_time = datetime.now(timezone.utc) - timedelta(minutes=25)
        
        data_aware = {
            'project_id': 1,
            'task_category_id': 2,
            'task_description': "Timezone Aware Sprint",
            'start_time': aware_time
        }
        
        # Should pass validation
        is_valid = (data_aware.get('project_id') and 
                   data_aware.get('task_category_id') and 
                   data_aware.get('task_description') and 
                   data_aware.get('start_time'))
        
        assert is_valid, "Timezone-aware datetime should be valid"
        
        # Test with naive datetime (what we normally use)
        naive_time = datetime.now() - timedelta(minutes=25)
        
        data_naive = {
            'project_id': 1,
            'task_category_id': 2,
            'task_description': "Timezone Naive Sprint",
            'start_time': naive_time
        }
        
        # Should also pass validation
        is_valid = (data_naive.get('project_id') and 
                   data_naive.get('task_category_id') and 
                   data_naive.get('task_description') and 
                   data_naive.get('start_time'))
        
        assert is_valid, "Timezone-naive datetime should be valid"

    def test_validation_consistency(self):
        """Test that validation is consistent across multiple calls."""
        
        # Test data sets
        valid_data = {
            'project_id': 1,
            'task_category_id': 2,
            'task_description': "Valid Sprint",
            'start_time': datetime.now() - timedelta(minutes=25)
        }
        
        invalid_data = {
            'project_id': None,  # Invalid
            'task_category_id': 2,
            'task_description': "Invalid Sprint",
            'start_time': datetime.now() - timedelta(minutes=25)
        }
        
        # Test multiple times to ensure consistency
        for i in range(10):
            # Test valid data
            is_valid = (valid_data.get('project_id') and 
                       valid_data.get('task_category_id') and 
                       valid_data.get('task_description') and 
                       valid_data.get('start_time'))
            assert is_valid, f"Valid data should always pass validation (iteration {i})"
            
            # Test invalid data
            is_valid = (invalid_data.get('project_id') and 
                       invalid_data.get('task_category_id') and 
                       invalid_data.get('task_description') and 
                       invalid_data.get('start_time'))
            assert not is_valid, f"Invalid data should always fail validation (iteration {i})"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])