#!/usr/bin/env python3
"""
Test runner for sprint completion race condition fix verification.

This script runs all tests related to the race condition fix and provides
a comprehensive summary of test coverage.
"""

import subprocess
import sys
import os

def run_command(command, description):
    """Run a command and return the result."""
    print(f"\n🔧 {description}")
    print(f"Command: {command}")
    print("-" * 60)
    
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, cwd="/home/jon/dev/pomodora", executable="/bin/bash")
        
        if result.returncode == 0:
            print("✅ PASSED")
            if result.stdout:
                # Extract test summary
                lines = result.stdout.split('\n')
                for line in lines:
                    if 'passed' in line and ('failed' in line or 'error' in line or '=' in line):
                        print(f"   {line.strip()}")
                        break
            return True
        else:
            print("❌ FAILED")
            if result.stdout:
                print("STDOUT:")
                print(result.stdout)
            if result.stderr:
                print("STDERR:")
                print(result.stderr)
            return False
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

def main():
    print("🎯 Sprint Completion Race Condition Fix - Test Suite")
    print("=" * 60)
    
    # Ensure we're in the right directory and have the virtual environment
    os.chdir("/home/jon/dev/pomodora")
    
    test_results = []
    
    # 1. Unit tests for race condition fix
    success = run_command(
        "source venv/bin/activate && /home/jon/.local/bin/pytest tests/unit/gui/test_sprint_completion_race_condition.py -v --tb=no",
        "Unit Tests: Sprint Completion Race Condition Fix"
    )
    test_results.append(("Unit Tests - Race Condition", success))
    
    # 2. Unit tests for data validation
    success = run_command(
        "source venv/bin/activate && /home/jon/.local/bin/pytest tests/unit/gui/test_sprint_data_validation.py -v --tb=no",
        "Unit Tests: Sprint Data Validation"
    )
    test_results.append(("Unit Tests - Data Validation", success))
    
    # 3. Basic functionality tests (regression check)
    success = run_command(
        "source venv/bin/activate && /home/jon/.local/bin/pytest tests/test_basic.py -v --tb=no",
        "Basic Functionality Tests (Regression Check)"
    )
    test_results.append(("Basic Functionality", success))
    
    # 4. Try to run a subset of existing tests to ensure no regressions
    success = run_command(
        "source venv/bin/activate && /home/jon/.local/bin/pytest tests/unit/timer/ -v --tb=no",
        "Timer Unit Tests (Regression Check)"
    )
    test_results.append(("Timer Unit Tests", success))
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    
    total_tests = len(test_results)
    passed_tests = sum(1 for _, success in test_results if success)
    
    for test_name, success in test_results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    print(f"\nOverall: {passed_tests}/{total_tests} test suites passed")
    
    if passed_tests == total_tests:
        print("🎉 All tests passed! The race condition fix is working correctly.")
        return 0
    else:
        print("⚠️  Some tests failed. Review the output above for details.")
        return 1

def print_test_documentation():
    """Print documentation about the test coverage."""
    print("\n" + "=" * 60)
    print("📋 TEST COVERAGE DOCUMENTATION")
    print("=" * 60)
    
    print("""
🎯 RACE CONDITION FIX TESTS

1. Unit Tests: Sprint Completion Race Condition Fix
   File: tests/unit/gui/test_sprint_completion_race_condition.py
   
   Tests Covered:
   ✓ Normal sprint completion flow
   ✓ Race condition handling (state cleared before save)
   ✓ Invalid data rejection
   ✓ Missing data handling
   ✓ Multiple rapid completions
   ✓ Thread safety simulation
   ✓ Data type preservation
   ✓ Duration calculation accuracy
   
2. Unit Tests: Sprint Data Validation
   File: tests/unit/gui/test_sprint_data_validation.py
   
   Tests Covered:
   ✓ Valid data structure verification
   ✓ Missing field validation (project_id, task_category_id, etc.)
   ✓ Boundary value testing
   ✓ Unicode text handling
   ✓ Timezone handling
   ✓ Error condition handling
   ✓ Data corruption recovery
   
3. Integration Considerations:
   - The race condition fix ensures sprint data is captured atomically
   - Database operations are protected from threading issues
   - Multi-workstation sync integrity is maintained
   
🔧 TECHNICAL DETAILS

The race condition fix implements:

1. Immediate Data Capture:
   - Sprint data captured in timer thread immediately
   - Stored in _pending_sprint_data attribute
   - Protected from UI state clearing

2. Safe Signal Handling:
   - Qt signals carry captured data
   - No dependency on instance variables during save
   - Validation occurs before capture

3. Robust Error Handling:
   - Invalid data rejected early
   - Graceful degradation on errors
   - Clear logging for debugging

🎯 ISSUE RESOLVED

Original Problem:
- Timer completion in background thread
- UI state cleared by main thread (race condition)
- Sprint saved with incomplete data (end_time=NULL, completed=False)
- Hibernation recovery incorrectly triggered on other workstations

Solution Applied:
- Atomic data capture at timer completion
- Thread-safe data passing via Qt signals
- Validation before capture
- Robust error handling

This ensures sprints are always saved with correct completion data
regardless of threading timing or UI state changes.
""")

if __name__ == "__main__":
    exit_code = main()
    print_test_documentation()
    sys.exit(exit_code)