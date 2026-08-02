# Web UI restyle

## Goal

The web interface (`app/templates/`, `app/static/style.css`, `app/static/app.js`) is currently unstyled beyond a handful of layout rules. This is a full visual overhaul: consistent typography, spacing, and color across all four pages, plus a chat experience that renders assistant replies as formatted text instead of raw markdown.

## Non-goals

- No manual light/dark toggle — theme follows `prefers-color-scheme` only.
- No fantasy/TTRPG theming (parchment, serif display fonts, etc.) — clean modern app aesthetic instead.
- No new build tooling, package manager, or CDN dependency. The project has no frontend build step today and this work should not introduce one.
- No changes to backend routes, streaming protocol, or data model.

## Visual system

`app/static/style.css` gains a `:root` block of CSS custom properties, overridden under `@media (prefers-color-scheme: dark)`:

- `--bg` — page background
- `--surface` — card/panel background (list items, bubbles, form containers)
- `--text` — primary text
- `--text-muted` — secondary text (labels, captions, timestamps)
- `--border` — hairline borders
- `--accent` / `--accent-text` — links, buttons, focus rings, user chat bubbles

Light theme: off-white background, dark slate text, single blue-ish accent.
Dark theme: near-black background, light gray text, same accent hue lightened for contrast.

Typography: system font stack (`-apple-system, "Segoe UI", sans-serif`), a small type scale for h1/h2/body/small text, `line-height: 1.5+`.

Layout: centered column widens from 720px to ~760px. Header gets vertical padding and a bottom border. Buttons and inputs get consistent padding, border-radius, and `:focus-visible` outlines (native controls are currently unstyled).

## Per-page changes

- **`systems.html`** — system list items become cards. The delete button is visually de-emphasized (small, muted, right-aligned) relative to the "Chat" link.
- **`system_detail.html`** — upload form and documents list get card treatment. Document status (`pending` / `ready` / `failed`) renders as a colored badge instead of plain `<strong>` text.
- **`chat.html`** — see Chat UI below.
- **`base.html`** — header restyled per Layout above; no structural change.

## Chat UI

`#chat-log` becomes a flex column with consistent gap between messages (replacing stacked `<p>` tags).

Each message is a bubble:
- User: right-aligned, `--accent` background, `--accent-text` color.
- Assistant: left-aligned, `--surface` background, `--text` color, subtle `--border`.
- Speaker label ("You" / "Assistant") renders as a small muted caption above the bubble rather than inline bold text inside it.

No typing-cursor affordance during streaming for v1 — out of scope, can be a follow-up.

## Markdown rendering

Assistant replies are LLM output and commonly contain markdown syntax (lists, bold, headers) that today renders as literal asterisks/dashes via `entry.textContent`. User-typed questions are never parsed as markdown — only assistant messages.

`app/static/app.js` gains a `renderMarkdown(text)` function:

1. Escape `<`, `>`, `&` in the raw text first.
2. Apply regex passes, in order, for: fenced code blocks, inline code spans, `#`/`##` headers, `**bold**`, `*italic*`, list items (`-`/`*`/`1.`) grouped into `<ul>`/`<ol>`, paragraph breaks on blank lines.
3. Return an HTML string.

Because escaping happens before any markdown pass runs, the output is safe to assign via `.innerHTML` even though the source text is model-generated — no user- or model-controlled string can inject a tag, since `<`/`>` are neutralized up front and every subsequent pass only ever wraps already-escaped text in known-safe tags.

### Streaming integration

Today `streamChatResponse` appends each chunk directly to `entry.textContent` as it arrives. That must change since partial markdown can't be safely re-parsed on every token (e.g. an unclosed `**` mid-stream).

New approach: accumulate the raw chunks into a local string as before, but on each chunk set `entry.innerHTML = renderMarkdown(accumulated)` instead of appending to `textContent`. This re-parses the full accumulated text on every chunk — acceptable given typical reply lengths and chunk counts for this app. The function's return value (used for `chatHistory` and localStorage) stays the accumulated raw markdown string, not the rendered HTML — history replay on page load re-renders from raw markdown the same way.

## Testing

No existing automated tests cover templates, CSS, or `app.js`; none are added here since this is a pure presentation-layer change with no new backend behavior. Verification is manual:

- Load each page in both light and dark OS theme settings, confirm the CSS variables apply correctly.
- Send a chat question that provokes a markdown-heavy reply (e.g. one likely to produce a list) and confirm it renders as real HTML, not literal `*`/`-`/`#` characters.
- Confirm chat history reload (via localStorage) still renders correctly after a page refresh.
- Confirm streaming still displays progressively (no long delay before any text appears).
