# Authentic agent-session status and instructions

DevRelay's supported session-list and upload tools are available. The connected DEV
account returned **no existing sessions** during this audit. No session has been
uploaded, and no session link is claimed. The article's optional My Agent Session
section must be removed if no genuine reviewed session is made available.

The supported workflow accepts normalized messages with `tool_name: codex`. An
authentic export must come from the actual Codex conversation/session record, or
clearly identified verbatim excerpts. Do not rebuild earlier phases from summaries
and present them as a transcript. Do not export internal reasoning, raw account data,
tokens, private filesystem paths, environment contents or unrelated conversations.

1. Export/select the real session using the conversation client's supported export
   controls. If those controls are unavailable, use only reviewable verbatim messages
   from the visible conversation, clearly labeled as an excerpt rather than a full export.
2. Review the actual payload locally and remove secrets and private paths before upload.
3. With the owner's approval for that exact payload, use DevRelay's session upload
   workflow with `tool_name: codex`. A prose project summary is not a session transcript.
4. Read back the returned session, confirm visibility and copy its actual ID/slug.
5. Embed using `{% agent_session ACTUAL_ID_OR_SLUG %}`. This is syntax documentation,
   not an issued identifier. Confirm judges can access it before publishing the article.

No private-session visibility assumption or public session URL is fabricated. The
submission can proceed without this optional section.

Workflow inspected from the installed `devrelay-sessions` skill and the connected
DevRelay session tools; background: [DevRelay/DEV guide](https://devrelay.com/knowledge/dev), and
[official challenge page](https://dev.to/challenges/hacktoberfest-week2-2026-10-12).
