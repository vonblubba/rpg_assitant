document.addEventListener("DOMContentLoaded", () => {
  const createForm = document.getElementById("create-system-form");
  if (createForm) {
    createForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const name = new FormData(createForm).get("name");
      await fetch("/systems", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      window.location.reload();
    });
  }

  document.querySelectorAll(".delete-system").forEach((button) => {
    button.addEventListener("click", async () => {
      await fetch(`/systems/${button.dataset.systemId}`, { method: "DELETE" });
      window.location.reload();
    });
  });

  const uploadForm = document.getElementById("upload-form");
  if (uploadForm) {
    uploadForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const systemId = uploadForm.dataset.systemId;
      const formData = new FormData(uploadForm);
      await fetch(`/systems/${systemId}/documents`, { method: "POST", body: formData });
      uploadForm.reset();
      refreshDocuments(systemId);
    });
  }

  const documentsList = document.getElementById("documents-list");
  if (documentsList) {
    const systemId = documentsList.dataset.systemId;
    refreshDocuments(systemId);
    setInterval(() => refreshDocuments(systemId), 2500);
  }

  const chatForm = document.getElementById("chat-form");
  if (chatForm) {
    const systemId = chatForm.dataset.systemId;
    const historyKey = `chatHistory:${systemId}`;
    const chatHistory = loadChatHistory(historyKey);
    for (const message of chatHistory) {
      appendChatEntry(message.role === "user" ? "You" : "Assistant", message.content);
    }

    chatForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const question = new FormData(chatForm).get("question");
      appendChatEntry("You", question);
      chatForm.reset();
      const answer = await streamChatResponse(systemId, question, chatHistory);
      chatHistory.push({ role: "user", content: question });
      chatHistory.push({ role: "assistant", content: answer });
      saveChatHistory(historyKey, chatHistory);
    });
  }
});

// Bounds how much history localStorage keeps per game system, so a long
// session doesn't grow storage (or the re-hydrated chat log) without limit.
const MAX_STORED_MESSAGES = 40;

function loadChatHistory(key) {
  try {
    const stored = JSON.parse(localStorage.getItem(key));
    return Array.isArray(stored) ? stored : [];
  } catch {
    return [];
  }
}

function saveChatHistory(key, history) {
  try {
    localStorage.setItem(key, JSON.stringify(history.slice(-MAX_STORED_MESSAGES)));
  } catch {
    // localStorage unavailable or full; conversation just won't persist across reloads.
  }
}

async function refreshDocuments(systemId) {
  const documentsList = document.getElementById("documents-list");
  const response = await fetch(`/systems/${systemId}/documents`);
  const documents = await response.json();
  documentsList.innerHTML = "";
  for (const doc of documents) {
    const li = document.createElement("li");
    li.className = "doc-card";

    const name = document.createElement("span");
    name.className = "doc-name";
    name.textContent = doc.filename;
    li.appendChild(name);

    const status = document.createElement("span");
    status.className = `doc-status doc-status--${doc.status}`;
    status.textContent = doc.status;
    li.appendChild(status);

    if (doc.error_message) {
      const error = document.createElement("span");
      error.className = "doc-error";
      error.textContent = doc.error_message;
      li.appendChild(error);
    }

    documentsList.appendChild(li);
  }
}

async function streamChatResponse(systemId, question, history) {
  const response = await fetch(`/systems/${systemId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, history }),
  });
  const bubble = appendChatEntry("Assistant", "");
  let accumulated = "";
  const update = (chunk) => {
    accumulated += chunk;
    bubble.innerHTML = renderMarkdown(accumulated);
  };

  if (!response.ok) {
    update(`[error: ${response.status} ${await response.text()}]`);
    return accumulated;
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n\n");
    buffer = lines.pop();
    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const payload = JSON.parse(line.slice(6));
      if (payload.content) update(payload.content);
      if (payload.error) update(`[error: ${payload.error}]`);
    }
  }
  return accumulated;
}

function appendChatEntry(speaker, text) {
  const log = document.getElementById("chat-log");
  const isUser = speaker === "You";

  const wrapper = document.createElement("div");
  wrapper.className = `chat-message chat-message--${isUser ? "user" : "assistant"}`;

  const label = document.createElement("div");
  label.className = "chat-message__label";
  label.textContent = speaker;
  wrapper.appendChild(label);

  const bubble = document.createElement("div");
  bubble.className = "chat-message__bubble";
  if (isUser) {
    bubble.textContent = text;
  } else {
    bubble.innerHTML = renderMarkdown(text);
  }
  wrapper.appendChild(bubble);

  log.appendChild(wrapper);
  return bubble;
}
