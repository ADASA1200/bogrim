# Token-saving rules

Keep context small. Prefer the cheapest action that answers the question.

## Reading
- Search before reading: use Grep/Glob to locate code, then Read only the relevant range (`offset`/`limit`), not whole files.
- Never re-read a file already in context or one you just edited.
- In this repo many files are identical: run `md5sum *.js` first and read each distinct hash once.
- Do not scan the whole filesystem (`find /`, `ls -R`); stay inside the repo.
- Cap long command output with `head`, `tail`, `wc -l` or `grep`; never dump large logs or JSON into context.

## Working
- Do not spawn subagents unless asked; do the work inline.
- Batch independent tool calls in one turn.
- Make targeted Edits instead of rewriting whole files.
- Do not run builds/tests that cannot work here (no `package.json` yet).
- Ask one short question when a request is ambiguous rather than exploring every option.

## Answering
- Reply short and to the point: no restating the request, no recap of steps already shown, no lists of options you will not pursue.
- Show only the changed lines or a file path, not full file contents, unless asked.
- The user reads Hebrew: answer in concise Hebrew; keep code, commands and these instruction files in English (fewer tokens).

## Maintaining context files
- Keep `CLAUDE.md` and this file short; add a rule only after a repeated mistake, and delete rules that no longer apply.
