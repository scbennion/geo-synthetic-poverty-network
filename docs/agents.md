## Git approval

- Do not create commits or push changes without the user's explicit approval for the specific prepared changes and action. 
- Approval to edit files is not approval to commit or push. Approval to commit alone is not approval to push.
- Before requesting approval, complete authorized edits and appropriate checks, then show the affected files and explain the proposed commit boundaries.
- Do not merge or modify `main` without explicit authorization.
- Use the existing branch; do not create a new branch unless requested.
- Avoid modifying existing files without user approval

## Scope and documentation

- Explain scientific assumptions and unfamiliar terms in plain language. 
- Distinguish implemented behavior, intended behavior, and independently verified evidence.
- Inspect source before documenting algorithms. Do not invent dataset origin or citations; identify missing preparation steps and unsupported assumptions.
- Cite assumptions with links to the original paper or code behavior
- Do not change application behavior to make it match the documentation without a separate implementation request.
- Avoid addressing problems beyond the original scope of the request
- Use plain although accurate language when possible. For example, "dataset origin is better than "dataset provenance"
- Keep the README focused on purpose, current capabilities, a starting path, and navigation. Maintain one authoritative home for each topic and link to it instead of duplicating instructions.
- Keep execution instructions in `docs/pipeline.md`, intended MVP design in `docs/assumptions.md`, and research scope and questions in `README.md`.
- Keep observed relationships, modeled contacts, aggregate flows, proximity, and resource-access opportunities distinguishable in dataset documentation and code.
- Document selected dataset releases, provenance, access constraints, geographic/temporal coverage, and integration status. Mark unverified details explicitly.
- Update affected documentation when an interface or implementation changes. 

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

## Readability and responsibility

- Use descriptive domain names for packages, modules, functions, and variables. Avoid generic utility names, unexplained abbreviations, misspellings, and double-underscore names for ordinary functions.
- Keep functions focused. Group shared code by responsibility, such as input preparation, household assignment, geography, validation, or output handling.
- Keep command-line scripts thin: parse arguments and coordinate reusable functions. Avoid mixing downloads, scientific rules, validation, and file writing into one function.
- Prefer straightforward control flow and explicit inputs over speculative abstractions or configuration layers. Split modules when it makes responsibilities easier to find, not solely to meet a line-count target.
- Use explicitly named input fields rather than positional column slices. Document identifiers, required fields, units, coordinate systems, and missing-value meanings at data boundaries.
- Remove obsolete commented code and unused paths only after checking callers and relevant history. Preserve explanations of scientific choices and non-obvious constraints.

## Refactoring and behavior preservation

- Avoid modifying or rewording the text describing previous changes in `docs/changelog.md`
- Preserve seeded results, random-draw order, assignment order, shared capacity behavior, identifiers, file formats, and geographic selection during readability refactors. Include isolated people and missing-data cases where relevant.
- If a refactor cannot preserve behavior, identify the difference and treat it as a separate model or compatibility change. Do not silently change scientific assumptions while reorganizing code.
- Run relevant existing checks after changes and report what was verified and any limits. Documentation-only changes need link/content checks; code changes need the affected tests and appropriate broader checks.
