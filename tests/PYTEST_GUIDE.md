# How pytest Works - Comprehensive Guide

## Overview

pytest is a Python testing framework that makes it easy to write simple tests while being scalable enough for complex functional testing. It's built on Python's native `assert` statements and provides powerful features through a plugin architecture.

## Core Concepts

### 1. Test Discovery

pytest automatically discovers tests using these conventions:

```python
# pytest will find these files:
test_*.py       # Files starting with "test_"
*_test.py       # Files ending with "_test"

# Inside those files, pytest will run:
def test_*():   # Functions starting with "test_"
class Test*:    # Classes starting with "Test" (no __init__ method)
    def test_*(): # Methods starting with "test_"
```

**Example**:
```python
# test_calculator.py
def test_addition():
    assert 2 + 2 == 4

class TestCalculator:
    def test_subtraction(self):
        assert 5 - 3 == 2
```

### 2. Assertions

pytest uses Python's native `assert` statements with enhanced error reporting:

```python
def test_string_comparison():
    expected = "hello world"
    actual = "hello world!"
    assert actual == expected  # pytest shows detailed diff on failure

def test_list_membership():
    items = [1, 2, 3, 4]
    assert 5 in items  # Clear failure message with list contents

def test_exception_handling():
    with pytest.raises(ValueError, match="invalid value"):
        int("not_a_number")
```

## Execution Flow

### 1. Collection Phase
```
pytest startup → Find test files → Import modules → Collect test functions → Build test tree
```

### 2. Setup Phase
```
Session setup → Module setup → Class setup → Function setup → Run test → Function teardown → Class teardown → Module teardown → Session teardown
```

### 3. Reporting Phase
```
Collect results → Generate reports → Exit with appropriate code
```

## Fixtures - The Heart of pytest

Fixtures provide test data, setup/teardown, and dependency injection:

### Basic Fixture Example
```python
import pytest

@pytest.fixture
def sample_data():
    """Provides test data to test functions"""
    return {"name": "Alice", "age": 30}

def test_user_data(sample_data):
    # pytest automatically passes the fixture result as an argument
    assert sample_data["name"] == "Alice"
    assert sample_data["age"] == 30
```

### Fixture Scopes
```python
@pytest.fixture(scope="function")  # Default - runs for each test
def temp_file():
    with tempfile.NamedTemporaryFile() as f:
        yield f.name

@pytest.fixture(scope="class")     # Runs once per test class
def database_connection():
    conn = create_db_connection()
    yield conn
    conn.close()

@pytest.fixture(scope="module")    # Runs once per test module (.py file)
def expensive_resource():
    resource = setup_expensive_operation()
    yield resource
    cleanup_expensive_operation(resource)

@pytest.fixture(scope="session")   # Runs once per test session
def global_config():
    return load_global_configuration()
```

### Fixture Dependencies
```python
@pytest.fixture
def database():
    return DatabaseConnection()

@pytest.fixture
def user_service(database):  # Depends on database fixture
    return UserService(database)

@pytest.fixture
def admin_user(user_service):  # Depends on user_service fixture
    return user_service.create_admin_user("admin@test.com")

def test_admin_permissions(admin_user):
    # All dependencies are automatically resolved
    assert admin_user.has_permission("admin")
```

## Configuration Files

### pytest.ini
```ini
[tool:pytest]
minversion = 6.0
addopts = -ra -q --strict-markers
testpaths = tests
python_files = test_*.py *_test.py
python_functions = test_*
python_classes = Test*
markers =
    slow: marks tests as slow (deselect with '-m "not slow"')
    integration: marks tests as integration tests
    unit: marks tests as unit tests
```

### conftest.py
Special pytest file that shares fixtures across multiple test files:

```python
# conftest.py (in tests/ directory)
import pytest
import tempfile
from myapp.database import DatabaseManager

@pytest.fixture(scope="session")
def temp_db():
    """Session-wide temporary database"""
    with tempfile.NamedTemporaryFile(suffix='.db') as tmp:
        db = DatabaseManager(tmp.name)
        db.initialize()
        yield db
        db.cleanup()

# This fixture is available to ALL test files in this directory and subdirectories
```

## Markers - Test Categorization

Markers allow you to categorize and selectively run tests:

### Built-in Markers
```python
@pytest.mark.skip(reason="Not implemented yet")
def test_future_feature():
    pass

@pytest.mark.skipif(sys.version_info < (3, 8), reason="Requires Python 3.8+")
def test_modern_feature():
    pass

@pytest.mark.xfail(reason="Known bug, fix in progress")
def test_buggy_feature():
    assert False  # Expected to fail

@pytest.mark.parametrize("input,expected", [
    (2, 4),
    (3, 9),
    (4, 16)
])
def test_square(input, expected):
    assert input ** 2 == expected
```

### Custom Markers
```python
# Define in pytest.ini
[tool:pytest]
markers =
    unit: Unit tests
    integration: Integration tests
    slow: Slow tests
    database: Tests that require database

# Use in tests
@pytest.mark.unit
def test_calculation():
    assert add(2, 3) == 5

@pytest.mark.integration
@pytest.mark.database
def test_user_creation():
    # Integration test using database
    pass
```

### Running Specific Tests
```bash
pytest -m "unit"                    # Run only unit tests
pytest -m "integration and not slow" # Integration tests that aren't slow
pytest -m "database or network"     # Tests needing database or network
pytest -k "test_user"              # Run tests with "test_user" in name
```

## Parameterized Testing

Run the same test with different inputs:

```python
@pytest.mark.parametrize("a,b,expected", [
    (1, 2, 3),
    (2, 3, 5),
    (10, 15, 25),
])
def test_addition(a, b, expected):
    assert add(a, b) == expected

# Multiple parameters
@pytest.mark.parametrize("username", ["alice", "bob", "charlie"])
@pytest.mark.parametrize("password", ["pass123", "secret456"])
def test_login(username, password):
    # Creates 6 test combinations (3 × 2)
    result = authenticate(username, password)
    assert result is not None
```

## Plugin Architecture

pytest's power comes from its plugin system:

### Popular Plugins
```bash
pip install pytest-cov          # Code coverage reporting
pip install pytest-xdist        # Parallel test execution
pip install pytest-mock         # Enhanced mocking
pip install pytest-html         # HTML reports
pip install pytest-benchmark    # Performance benchmarking
```

### Using Plugins
```bash
# Coverage reporting
pytest --cov=myapp --cov-report=html tests/

# Parallel execution
pytest -n 4  # Run tests on 4 CPU cores

# HTML reports
pytest --html=report.html --self-contained-html
```

## Advanced Features

### Monkeypatching
```python
def test_environment_variable(monkeypatch):
    # Temporarily modify environment
    monkeypatch.setenv("API_KEY", "test-key")
    assert os.environ["API_KEY"] == "test-key"
    # Automatically restored after test

def test_mock_function(monkeypatch):
    # Mock a function
    monkeypatch.setattr("mymodule.external_api_call", lambda: "mocked result")
    result = mymodule.get_data()
    assert result == "mocked result"
```

### Temporary Directories
```python
def test_file_operations(tmp_path):
    # pytest provides temporary directory
    test_file = tmp_path / "test.txt"
    test_file.write_text("Hello World")
    assert test_file.read_text() == "Hello World"
    # tmp_path automatically cleaned up

def test_working_directory(tmp_path, monkeypatch):
    # Change to temporary directory
    monkeypatch.chdir(tmp_path)
    # Now os.getcwd() == tmp_path
```

### Capture Output
```python
def test_print_output(capsys):
    print("Hello World")
    captured = capsys.readouterr()
    assert captured.out == "Hello World\n"
    assert captured.err == ""

def test_logging_output(caplog):
    import logging
    logging.warning("This is a warning")
    assert "This is a warning" in caplog.text
    assert caplog.records[0].levelname == "WARNING"
```

## Real-World Example

Here's how pytest would work in the Pomodora project:

```python
# conftest.py
import pytest
import tempfile
from src.tracking.models import DatabaseManager
from src.tracking.local_settings import LocalSettingsManager

@pytest.fixture(scope="function")
def isolated_db():
    """Fresh database for each test"""
    db_manager = DatabaseManager(":memory:")
    db_manager.initialize_default_projects()
    yield db_manager
    db_manager.cleanup()

@pytest.fixture(scope="function")
def temp_settings():
    """Temporary settings"""
    with tempfile.TemporaryDirectory() as temp_dir:
        settings = LocalSettingsManager()
        settings.config_file = Path(temp_dir) / "test_settings.json"
        yield settings

# tests/unit/timer/test_pomodoro.py
import pytest
from src.timer.pomodoro import PomodoroTimer, TimerState

class TestPomodoroTimer:
    def test_initial_state(self):
        timer = PomodoroTimer(sprint_duration=25, break_duration=5)
        assert timer.get_state() == TimerState.STOPPED
        assert timer.get_time_remaining() == 0

    def test_start_sprint(self):
        timer = PomodoroTimer(sprint_duration=1, break_duration=1)
        timer.start_sprint()
        assert timer.get_state() == TimerState.RUNNING
        assert timer.get_time_remaining() == 60

    @pytest.mark.parametrize("sprint_min,break_min,expected_sprint_sec,expected_break_sec", [
        (25, 5, 1500, 300),
        (30, 10, 1800, 600),
        (45, 15, 2700, 900),
    ])
    def test_duration_settings(self, sprint_min, break_min, expected_sprint_sec, expected_break_sec):
        timer = PomodoroTimer(sprint_min, break_min)
        assert timer.sprint_duration == expected_sprint_sec
        assert timer.break_duration == expected_break_sec

# tests/integration/test_sprint_lifecycle.py
def test_complete_sprint_cycle(isolated_db, temp_settings):
    """Test creating and completing a sprint"""
    # This test uses both fixtures automatically
    session = isolated_db.get_session()
    
    # Create and start sprint
    sprint = Sprint(
        project_id=1,
        task_category_id=1,
        task_description="Test task",
        start_time=datetime.now(),
        planned_duration=25
    )
    session.add(sprint)
    session.commit()
    
    # Verify sprint was created
    saved_sprint = session.query(Sprint).filter_by(task_description="Test task").first()
    assert saved_sprint is not None
    assert saved_sprint.planned_duration == 25
```

## Command Line Usage

```bash
# Basic test execution
pytest                              # Run all tests
pytest tests/unit/                  # Run specific directory
pytest tests/unit/test_timer.py     # Run specific file
pytest tests/unit/test_timer.py::test_start_sprint  # Run specific test

# Verbose output
pytest -v                           # Verbose (show each test)
pytest -vv                          # Very verbose (show more details)
pytest -s                           # Don't capture output (show prints)

# Stop on first failure
pytest -x                           # Stop on first failure
pytest --maxfail=3                  # Stop after 3 failures

# Show test durations
pytest --durations=10               # Show 10 slowest tests

# Generate reports
pytest --junit-xml=results.xml      # JUnit XML for CI systems
pytest --html=report.html           # HTML report
pytest --cov=src --cov-report=html  # Coverage report

# Dry run (collect tests but don't run)
pytest --collect-only               # Show what tests would run
pytest --co -q                      # Quiet collection display
```

## pytest vs unittest

| Feature | pytest | unittest |
|---------|--------|----------|
| Test discovery | Automatic | Manual or discovery |
| Assertions | Plain `assert` | `self.assertEqual()` etc |
| Fixtures | Powerful fixture system | `setUp()`/`tearDown()` |
| Parameterization | `@pytest.mark.parametrize` | Subclassing |
| Plugins | Rich ecosystem | Limited |
| Configuration | pytest.ini, pyproject.toml | Command line only |

## Key pytest Features Summary

### What Makes pytest Special

1. **Simple Test Writing**: Uses plain `assert` statements instead of special assertion methods
2. **Automatic Discovery**: Finds tests without configuration using naming conventions
3. **Powerful Fixtures**: Dependency injection system for test setup/teardown
4. **Rich Plugin Ecosystem**: Extensible through plugins for coverage, parallel execution, etc.
5. **Detailed Failure Reports**: Shows exactly what failed with context
6. **Flexible Test Selection**: Run subsets of tests using markers, keywords, or paths
7. **Parameterization**: Easy way to run same test with different inputs
8. **Configuration Options**: Control test execution through configuration files

### Best Practices

1. **Use descriptive test names** that explain what is being tested
2. **Keep tests independent** - each test should be able to run in isolation
3. **Use fixtures for setup/teardown** instead of global state
4. **Group related tests** in classes or modules
5. **Use markers** to categorize tests (unit, integration, slow, etc.)
6. **Mock external dependencies** to keep tests fast and reliable
7. **Test both happy path and error cases**
8. **Keep tests simple** - if a test is complex, consider breaking it down

### Common pytest Patterns

```python
# Arrange-Act-Assert pattern
def test_user_registration():
    # Arrange
    user_data = {"email": "test@example.com", "password": "secure123"}
    
    # Act
    result = register_user(user_data)
    
    # Assert
    assert result.success is True
    assert result.user_id is not None

# Using fixtures for common setup
@pytest.fixture
def authenticated_user():
    user = User.create("test@example.com")
    user.login()
    return user

def test_user_can_access_profile(authenticated_user):
    profile = authenticated_user.get_profile()
    assert profile is not None

# Testing exceptions
def test_invalid_email_raises_error():
    with pytest.raises(ValidationError, match="Invalid email format"):
        validate_email("not-an-email")

# Parameterized testing for multiple scenarios
@pytest.mark.parametrize("input_value,expected", [
    ("valid@email.com", True),
    ("invalid-email", False),
    ("", False),
    ("test@", False),
])
def test_email_validation(input_value, expected):
    result = is_valid_email(input_value)
    assert result == expected
```

pytest's philosophy is "convention over configuration" - it tries to make the common cases simple while still supporting advanced use cases through its plugin architecture.