#!/bin/bash
set -e
REPO="$(cd "$(dirname "$0")/.." && pwd)"
SKILLS_SRC="$REPO/.claude/skills"
SKILLS_DST="$HOME/.claude/skills"

mkdir -p "$SKILLS_DST"

for skill_dir in "$SKILLS_SRC"/blog-*/; do
  name="$(basename "$skill_dir")"
  target="$SKILLS_DST/$name"
  if [ -L "$target" ]; then
    echo "Updating symlink: $name"
    ln -sf "$skill_dir" "$target"
  elif [ -e "$target" ]; then
    echo "WARNING: $target exists and is not a symlink — skipping $name"
  else
    echo "Creating symlink: $name"
    ln -s "$skill_dir" "$target"
  fi
done

echo "Done. Skills linked:"
ls -la "$SKILLS_DST" | grep blog-
