#!/usr/bin/env bash
# install.sh - install the Java replication skills (and rules) into a project or your user profile.
#
#   ./install.sh --project /path/to/java-app      # .cursor/skills + .cursor/rules in that project
#   ./install.sh --global                         # ~/.cursor/skills (rules are project-only in Cursor)
#   options: --no-rules  --link (symlink instead of copy, for skill development)  --force  --dry-run
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.cursor"
SKILLS=(java-replicate java-app-analyzer jira-requirement-mapper java-app-replicator java-parity-verifier)
RULES=(replication-guardrails.mdc java-code-conventions.mdc spring-batch-conventions.mdc)

target="" rules=1 link=0 force=0 dry=0
while [ $# -gt 0 ]; do
  case "$1" in
    --project) target="${2:?--project needs a directory}"; shift 2 ;;
    --global)  target="$HOME"; rules=0; shift ;;
    --no-rules) rules=0; shift ;;
    --link)    link=1; shift ;;
    --force)   force=1; shift ;;
    --dry-run) dry=1; shift ;;
    -h|--help) sed -n '2,7p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done
[ -n "$target" ] || { sed -n '2,7p' "$0"; exit 2; }
[ -d "$target" ] || { echo "error: not a directory: $target" >&2; exit 2; }

run() { if [ "$dry" = 1 ]; then echo "+ $*"; else "$@"; fi; }

place() { # place <src> <dest>
  local src="$1" dest="$2"
  if [ -e "$dest" ] || [ -L "$dest" ]; then
    if [ "$force" != 1 ]; then
      if [ "$link" = 0 ] && diff -rq "$src" "$dest" >/dev/null 2>&1; then
        echo "unchanged  $dest"; return
      fi
      echo "exists     $dest (use --force to replace)"; return
    fi
    run rm -rf "$dest"
  fi
  if [ "$link" = 1 ]; then run ln -s "$src" "$dest"; else run cp -R "$src" "$dest"; fi
  echo "installed  $dest"
}

run mkdir -p "$target/.cursor/skills"
for s in "${SKILLS[@]}"; do place "$SRC/skills/$s" "$target/.cursor/skills/$s"; done

if [ "$rules" = 1 ]; then
  run mkdir -p "$target/.cursor/rules"
  for r in "${RULES[@]}"; do place "$SRC/rules/$r" "$target/.cursor/rules/$r"; done
fi

cat <<EOF

Done. In Cursor Agent chat type /java-replicate (or /java-app-analyzer, /jira-requirement-mapper, ...).
Optional: connect Jira via the Atlassian MCP server (see mcp.json.example), or set JIRA_* env vars.
Suggested .gitignore line for large parity outputs:  .replication/parity/**/output*
EOF
