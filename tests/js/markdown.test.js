const test = require("node:test");
const assert = require("node:assert/strict");
const { renderMarkdown } = require("../../app/static/markdown.js");

test("wraps plain text in a paragraph", () => {
  assert.equal(renderMarkdown("Hello world"), "<p>Hello world</p>");
});

test("renders bold and italic text", () => {
  assert.equal(
    renderMarkdown("This is **bold** and *italic*."),
    "<p>This is <strong>bold</strong> and <em>italic</em>.</p>"
  );
});

test("renders an unordered list", () => {
  assert.equal(
    renderMarkdown("- one\n- two"),
    "<ul><li>one</li><li>two</li></ul>"
  );
});

test("renders an ordered list", () => {
  assert.equal(
    renderMarkdown("1. first\n2. second"),
    "<ol><li>first</li><li>second</li></ol>"
  );
});

test("renders headers", () => {
  assert.equal(renderMarkdown("## Section"), "<h2>Section</h2>");
});

test("renders inline code", () => {
  assert.equal(
    renderMarkdown("Use `renderMarkdown()` here."),
    "<p>Use <code>renderMarkdown()</code> here.</p>"
  );
});

test("renders fenced code blocks", () => {
  assert.equal(
    renderMarkdown("```\nconst x = 1;\n```"),
    "<pre><code>const x = 1;</code></pre>"
  );
});

test("escapes raw HTML before applying markdown", () => {
  assert.equal(
    renderMarkdown("<script>alert(1)</script> and **bold**"),
    "<p>&lt;script&gt;alert(1)&lt;/script&gt; and <strong>bold</strong></p>"
  );
});

test("returns an empty string for empty input", () => {
  assert.equal(renderMarkdown(""), "");
});
