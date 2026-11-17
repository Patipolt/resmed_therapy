#!/bin/sh
task_project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -x "$task_project_dir/.venv/bin/python" ]; then
    exec "$task_project_dir/.venv/bin/python" "$task_project_dir/main.py"
fi
printf '%s\n' 'Create the .venv and install requirements.txt first. See README.md.'
exit 1
