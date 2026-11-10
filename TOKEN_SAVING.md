# Token-saving rules

Goal: spend tokens on thinking and verification, not on re-reading, re-explaining or dumping output.
Correctness always wins: if a rule here would make a result less reliable, break the rule.

## 1. Depth mode (overrides everything below)
Switch to full depth when debugging, reviewing code, the change touches several files, or the user says "check thoroughly" / "לעומק":
- Read whole files and their callers, not just the matching lines.
- Explore freely; use subagents for wide searches or parallel review.
- Verify the result (run it, test it, look at it) before reporting it as done.
Return to the rules below for routine work.

## 2. Context files (CLAUDE.md, skills, memory)
- These files load in every session, so every line costs tokens every time. Keep them short and without duplicate instructions.
- When the user says "add this to CLAUDE.md" / "remember this", add one concise line in the right section, not a paragraph.
- Add a rule only after a repeated mistake; delete rules that no longer apply.
- A task the user repeats (same format, same steps) should become a skill: offer "build a skill from this" instead of re-explaining it each session. When a skill produced a wrong result and was corrected, update the skill.

## 3. Connections (MCP servers and tools)
- Every enabled MCP connection loads its tool definitions into every session, often more than all context files combined.
- If an enabled connection is not needed for the current task, say so once and suggest disabling it; suggest enabling a connection only when the task needs it.

## 4. Reading
- Locate first, then read: Grep/Glob to find the place, then Read the relevant range (`offset`/`limit`). In depth mode, read the whole file.
- Never re-read a file already in context or one you just edited.
- In this repo many files are identical: run `md5sum *.js` first and read each distinct hash once.
- Stay inside the repo; no `find /` or `ls -R`.
- Cap long command output with `head`, `tail`, `wc -l` or `grep`.
- If the user gives an exact location (file, component, line, a bug-report page entry), go straight there instead of searching.

## 5. Offloading large reads to Gemini (only if a Gemini helper is configured)
Applies only when a helper such as `gemini_task.py` and a Gemini API key exist in this environment. If they do not, skip this section.
- "Big? Gemini first": before reading something larger than ~300 lines or ~20k characters (long logs, PDFs, documents, web pages), send it to Gemini with one focused question ("what is the error and on which line?", "what does it say about X? give the page"), then read yourself only the part it points to.
- Screenshots that only need information extracted (text, error message, table, numbers): send to Gemini. Screenshots that check the result of your own change: look yourself; never delegate verifying your own work.
- Never send to Gemini: code you are about to edit (you need the exact text), code-writing tasks (checking and fixing cancels the savings), or personal/sensitive content (emails, private documents, passwords, keys; the free tier may use submitted content).
- If Gemini fails or is overloaded, continue on your own; do not retry repeatedly.

## 6. Working
- Do the work yourself instead of sending the user to read docs or do manual steps; ask only for what only the user can provide (approval, credentials, a decision).
- Ask one short question when a request is genuinely ambiguous; otherwise pick the sensible default and say so.
- Batch independent tool calls in one turn.
- Make targeted Edits instead of rewriting whole files.
- Do not run builds/tests that cannot work here (no `package.json` yet).
- In long sessions, suggest `/compact` at a natural break rather than carrying stale context.

## 7. Answering
- The user reads Hebrew: answer in concise Hebrew. Keep code, commands and these instruction files in English (fewer tokens).
- No restating the request, no recap of steps already shown, no lists of options you will not pursue.
- Show only changed lines or a file path, not full file contents, unless asked.
- Keep caveats and risks even when answering briefly; brevity must not hide a problem.
