import os
import runpy
import sys
from pathlib import Path

import pytest

# Get the project root directory (assuming tests are run from the root or one level down)
PROJECT_ROOT = Path(__file__).parent.parent
EXAMPLES_DIR = PROJECT_ROOT / "examples"

# Find all Python scripts in the examples directory
example_scripts = list(EXAMPLES_DIR.glob("*.py"))
example_script_ids = [f"example: {p.relative_to(PROJECT_ROOT)}" for p in example_scripts]


@pytest.mark.parametrize("example_path", example_scripts, ids=example_script_ids)
def test_run_example(example_path: Path):
    """Runs an example script and checks for exceptions."""
    print(f"\nRunning example: {example_path.relative_to(PROJECT_ROOT)}...")

    # Store original state
    original_cwd = os.getcwd()
    original_sys_argv = sys.argv
    original_sys_path = list(sys.path)

    try:
        # Change to examples directory so relative paths in examples work
        os.chdir(EXAMPLES_DIR)

        # Prepend the project root to sys.path to help with potential imports
        # within the example scripts if they rely on the local package
        sys.path.insert(0, str(PROJECT_ROOT))

        # Set sys.argv to prevent examples from processing pytest args
        # Set the first argument to the script path, like the python interpreter does
        sys.argv = [str(example_path)]

        # Run the script using runpy
        runpy.run_path(str(example_path), run_name="__main__")

        # If it completes without exception, the test passes implicitly
        print(f"Example {example_path.name} ran successfully.")

    except Exception as e:
        pytest.fail(f"Example script {example_path.name} failed with exception:\n{e}", pytrace=True)

    finally:
        # Restore original state
        os.chdir(original_cwd)
        sys.argv = original_sys_argv
        sys.path = original_sys_path
