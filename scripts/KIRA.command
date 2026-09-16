#!/bin/bash
# Double-clickable macOS launcher. Users can drop a symlink to this on
# their Desktop; double-clicking opens Terminal, boots services, then
# starts the menu-bar app.
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"
exec bash scripts/kira.sh
