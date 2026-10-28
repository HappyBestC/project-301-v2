# source scripts/activate.sh
_project301_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
source "${_project301_root}/.venv/bin/activate"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONNOUSERSITE=1
export PYTHONPATH="${_project301_root}/src:${_project301_root}/pulse/python:${_project301_root}/pulse/bin"
unset _project301_root
