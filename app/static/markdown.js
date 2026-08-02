function escapeHtml(text) {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function inline(text) {
  return text
    .replace(/`([^`\n]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*\n]+)\*/g, "<em>$1</em>");
}

function renderMarkdown(text) {
  const escaped = escapeHtml(text);

  const codeBlocks = [];
  const withPlaceholders = escaped.replace(/```([\s\S]*?)```/g, (_, code) => {
    codeBlocks.push(`<pre><code>${code.trim()}</code></pre>`);
    return ` CODEBLOCK${codeBlocks.length - 1} `;
  });

  const lines = withPlaceholders.split("\n");
  const blockLines = [];
  let listItems = null;
  let listTag = null;

  const flushList = () => {
    if (listItems) {
      blockLines.push({ block: true, html: `<${listTag}>${listItems.join("")}</${listTag}>` });
      listItems = null;
      listTag = null;
    }
  };

  for (const line of lines) {
    const placeholderMatch = line.match(/^ CODEBLOCK(\d+) $/);
    const headerMatch = line.match(/^(#{1,3})\s+(.*)$/);
    const orderedMatch = line.match(/^\d+\.\s+(.*)$/);
    const unorderedMatch = line.match(/^[-*]\s+(.*)$/);

    if (placeholderMatch) {
      flushList();
      blockLines.push({ block: true, html: codeBlocks[Number(placeholderMatch[1])] });
    } else if (headerMatch) {
      flushList();
      const level = headerMatch[1].length;
      blockLines.push({ block: true, html: `<h${level}>${inline(headerMatch[2])}</h${level}>` });
    } else if (orderedMatch) {
      if (listTag !== "ol") {
        flushList();
        listTag = "ol";
        listItems = [];
      }
      listItems.push(`<li>${inline(orderedMatch[1])}</li>`);
    } else if (unorderedMatch) {
      if (listTag !== "ul") {
        flushList();
        listTag = "ul";
        listItems = [];
      }
      listItems.push(`<li>${inline(unorderedMatch[1])}</li>`);
    } else if (line.trim() === "") {
      flushList();
      blockLines.push({ block: true, html: "" });
    } else {
      flushList();
      blockLines.push({ block: false, html: inline(line) });
    }
  }
  flushList();

  const output = [];
  let paragraph = [];
  const flushParagraph = () => {
    if (paragraph.length) {
      output.push(`<p>${paragraph.join("<br>")}</p>`);
      paragraph = [];
    }
  };
  for (const entry of blockLines) {
    if (entry.block) {
      flushParagraph();
      if (entry.html !== "") output.push(entry.html);
    } else {
      paragraph.push(entry.html);
    }
  }
  flushParagraph();

  return output.join("\n");
}

if (typeof module !== "undefined") {
  module.exports = { renderMarkdown, escapeHtml, inline };
}
