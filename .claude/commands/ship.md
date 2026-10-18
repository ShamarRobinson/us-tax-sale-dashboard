---
description: Rebuild the data files, commit the current work as Shamar, push, and confirm the GitHub Pages deploy
argument-hint: short commit subject
---

Publish the current working tree. Follow the standing rules in CLAUDE.md (author Shamar Robinson
<shamarrobinson31@gmail.com>, Title Case headings, no em dashes, links included).

1. If any Python, source adapter or county file changed, run `python3 fetch_all.py --offline` so
   `data/registry.json`, `data/index.json`, the master CSVs, `data/changes.json` and `data/upcoming.ics` match.
2. Run a quick check: `python3 -m py_compile *.py sources/*.py tools/*.py` and `node --check app.js county.js
   common.js analyzer.js` (skip node if it is not installed).
3. Review `git status --short` and `git diff --stat`. Do not commit scratch files or anything under `scratch/`.
4. Commit with the subject `$ARGUMENTS` (or write one if empty) and a short body that says what changed and why.
   Verify `git log -1 --format='%an <%ae>'` shows Shamar; amend with
   `git -c user.name="Shamar Robinson" -c user.email="shamarrobinson31@gmail.com" commit --amend --no-edit --reset-author`
   if it does not.
5. `git fetch origin && git rebase origin/main && git push origin HEAD`.
6. Wait for `gh run list --workflow=pages-build-deployment --limit 1 --json status,conclusion,headSha -q '.[0]'` to
   show `completed` and `success` for the pushed SHA, then give the live link with a cache-busting query, for
   example `https://shamarrobinson.github.io/us-tax-sale-dashboard/?v=<unix time>`.
