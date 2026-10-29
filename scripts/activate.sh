# source scripts/activate.sh
_project301_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
source "${_project301_root}/.venv/bin/activate"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONNOUSERSITE=1
export PYTHONPATH="${_project301_root}/src:${_project301_root}/pulse/python:${_project301_root}/pulse/bin"
# Optional worktree-local dependency overlay; never write through a shared .venv.
if [ -d "${_project301_root}/runs/standard_answer/_deps" ]; then
    export PYTHONPATH="${PYTHONPATH}:${_project301_root}/runs/standard_answer/_deps"
fi
unset _project301_root
