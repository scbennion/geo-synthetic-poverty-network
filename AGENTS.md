# Working agreement

## Git approval

- Do not create commits or push changes without the user's explicit approval for the specific prepared changes and action. Approval to edit files or create a branch is not approval to commit or push. Approval to commit alone is not approval to push.
- Before requesting approval, complete authorized edits and appropriate checks, then show the affected files and explain the proposed commit boundaries.
- Read-only Git inspection and staging changes for review are allowed. Do not merge, force-push, rewrite published history, or modify `main` without explicit authorization.
- Preserve existing user changes. Use the existing checkout; do not create a worktree unless requested.
- Avoid modifying existing files without user approval

## Scope and documentation

- Explain scientific assumptions and unfamiliar terms in plain language. Distinguish implemented behavior, intended behavior, and independently verified evidence.
- Inspect source before documenting algorithms. Do not invent dataset provenance or citations; identify missing preparation steps and unsupported assumptions.
- Cite assumptions with links to the original paper or code behavior
- Do not change application behavior to make it match the documentation without a separate implementation request.
- Avoid addressing problems beyond the original scope of the request

## Coding Conventions

- Follow the conventions from "The Zen of Python"
  - Beautiful is better than ugly.
  - Explicit is better than implicit.
  - Simple is better than complex.
  - Complex is better than complicated.
  - Flat is better than nested.
  - Sparse is better than dense.
  - Readability counts.
  - Special cases aren't special enough to break the rules.
  - Although practicality beats purity.
  - Errors should never pass silently.
  - Unless explicitly silenced.
  - In the face of ambiguity, refuse the temptation to guess.
  - There should be one-- and preferably only one --obvious way to do it.
  - If the implementation is hard to explain, it's a bad idea.
  - If the implementation is easy to explain, it may be a good idea.
- Create simple to complex tests for each part of your code that thoroughly test intended behavior
