# pytest-gitscope

**Smart test filtering based on Git revisions**

A pytest plugin that intelligently filters and runs only the tests affected by changes in a specific Git revision or commit range. Instead of running your entire test suite, pytest-gitscope analyzes your Git history to determine which tests are relevant to your recent changes.

## Features

- 🎯 **Targeted Testing** - Run only tests related to modified files
- ⚡ **Fast Execution** - Dramatically reduce test execution time
- 🔍 **Git Integration** - Seamlessly works with your Git workflow
- 📊 **Smart Detection** - Automatically detects affected test files and dependencies
- 🛠️ **Flexible Filtering** - Support for commit ranges, branches, and specific revisions

## Quick Start

```bash
pip install pytest-gitscope

# Run tests affected by changes in the last commit
pytest --gitscope HEAD~1

# Run tests affected by changes between two commits
pytest --gitscope main..feature-branch
```

Perfect for CI/CD pipelines and local development to focus on what matters most.


## Understanding pytest-gitscope with a Complete Example

Let's walk through a real-world example to see exactly how `pytest-gitscope` works.

### Initial Project Structure

```
myproject/
├── src/
│   ├── calculator.py
│   ├── user_manager.py
│   └── utils.py
├── tests/
│   ├── test_calculator.py
│   ├── test_user_manager.py
│   ├── test_utils.py
│   └── test_integration.py
└── docs/
    └── README.md
```

### Step 1: Initial State

Your project has 15 tests total:
```bash
$ pytest --collect-only -q
15 tests collected
```

Running all tests takes 45 seconds:
```bash
$ pytest
================ 15 passed in 45.23s ================
```

### Step 2: Making Changes

You're working on a new feature and modify two files:

**Changes to `src/calculator.py`:**
```python
def add(a, b):
    return a + b

def multiply(a, b):  # ← NEW FUNCTION
    return a * b
```

**Changes to `docs/README.md`:**
```markdown
# MyProject
Updated documentation with new examples...
```

### Step 3: See What Git Detects

```bash
$ git diff --name-only HEAD~1
src/calculator.py
docs/README.md
```

### Step 4: Run pytest-gitscope

Instead of running all 15 tests, use pytest-gitscope:

```bash
$ pytest --gitscope HEAD~1
```

**What happens internally:**

1. **File Analysis**: pytest-gitscope runs `git diff --name-only HEAD~1`
   ```
   Changed files: ['src/calculator.py', 'docs/README.md']
   ```

2. **Test Mapping**: It identifies which tests are affected:
   ```
   src/calculator.py → tests/test_calculator.py
   docs/README.md → (no tests affected)
   ```

3. **Dependency Detection**: It scans for imports and finds:
   ```
   tests/test_integration.py imports calculator.py
   ```

4. **Final Test Selection**:
   ```
   Selected tests:
   ✓ tests/test_calculator.py (directly affected)
   ✓ tests/test_integration.py (imports calculator.py)
   ✗ tests/test_user_manager.py (not affected)
   ✗ tests/test_utils.py (not affected)
   ```

**Output:**
```bash
$ pytest --gitscope HEAD~1
========================== test session starts ==========================
gitscope: Analyzing changes from HEAD~1
gitscope: Found 2 changed files
gitscope: Selected 8 tests from 2 test files (7 tests skipped)

tests/test_calculator.py ✓✓✓✓✓
tests/test_integration.py ✓✓✓

=================== 8 passed, 7 skipped in 12.34s ===================
```

### Step 5: Compare the Results

| Method | Tests Run | Time |
|--------|-----------|------|
| Regular pytest | 15 tests | 45.23s |
| pytest --gitscope | 8 tests | 12.34s |
| **Savings** | **7 tests skipped** | **73% faster** |

### Real-World Scenarios

#### Scenario 1: Feature Branch
```bash
# Test only changes in your feature branch
$ pytest --gitscope main..feature/new-auth
gitscope: Selected 12 tests from 4 test files (28 tests skipped)
```

#### Scenario 2: Last 3 Commits
```bash
# Test changes from last 3 commits
$ pytest --gitscope HEAD~3
gitscope: Selected 6 tests from 2 test files (34 tests skipped)
```

#### Scenario 3: Specific Files Only
```bash
# Test only your calculator changes
$ pytest --gitscope HEAD~1 tests/test_calculator.py
gitscope: Selected 5 tests from 1 test file (35 tests skipped)
```

### What Gets Detected

✅ **Direct matches**: `src/calculator.py` → `tests/test_calculator.py`\
✅ **Import dependencies**: Files that import changed modules\
✅ **Test utilities**: Shared test fixtures and utilities\
✅ **Configuration changes**: `pytest.ini`, `conftest.py`

❌ **Documentation only**: `README.md`, `*.md` files (configurable)\
❌ **Unrelated modules**: Files with no test connections




### Important Note: Dependency Management

⚠️ **pytest-gitscope works best with projects using package managers like Poetry or uv.**

Without a proper dependency manager, pytest-gitscope might miss some test dependencies. Here's why:

**With Poetry/uv (Recommended):**
```python
# pytest-gitscope can analyze pyproject.toml and lock files
# to understand the full dependency graph
src/calculator.py → tests/test_calculator.py ✓
src/calculator.py → tests/test_math_integration.py ✓ (detected via deps)
```

**Without package manager:**
```python
# pytest-gitscope relies only on direct imports scanning
src/calculator.py → tests/test_calculator.py ✓
src/calculator.py → tests/test_math_integration.py ? (might be missed)
```

**Recommendation**: For best results, use pytest-gitscope in projects with:
- `pyproject.toml` (Poetry, uv, setuptools)
- `requirements.txt` with proper dependency tracking
- Clear import patterns


### Integration with CI/CD

Perfect for speeding up your CI pipeline:

```yaml
# .github/workflows/test.yml
- name: Run targeted tests
  run: pytest --gitscope origin/main..HEAD
```

This way, pull requests only run tests affected by the changes, dramatically reducing build times while maintaining confidence in your code quality.
