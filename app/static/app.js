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
    const chatHistory = [];
    chatForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const systemId = chatForm.dataset.systemId;
      const question = new FormData(chatForm).get("question");
      appendChatEntry("You", question);
      chatForm.reset();
      const answer = await streamChatResponse(systemId, question, chatHistory);
      chatHistory.push({ role: "user", content: question });
      chatHistory.push({ role: "assistant", content: answer });
    });
  }
});

async function refreshDocuments(systemId) {
  const documentsList = document.getElementById("documents-list");
  const response = await fetch(`/systems/${systemId}/documents`);
  const documents = await response.json();
  documentsList.innerHTML = "";
  for (const doc of documents) {
    const li = document.createElement("li");
    li.append(`${doc.filename} — `);
    const strong = document.createElement("strong");
    strong.textContent = doc.status;
    li.append(strong);
    if (doc.error_message) {
      li.append(` (${doc.error_message})`);
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
  const entry = appendChatEntry("Assistant", "");
  if (!response.ok) {
    entry.textContent = `[error: ${response.status} ${await response.text()}]`;
    return entry.textContent;
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
      if (payload.content) entry.textContent += payload.content;
      if (payload.error) entry.textContent += `[error: ${payload.error}]`;
    }
  }
  return entry.textContent;
}

function appendChatEntry(speaker, text) {
  const log = document.getElementById("chat-log");
  const entry = document.createElement("p");
  entry.innerHTML = `<strong>${speaker}:</strong> `;
  const span = document.createElement("span");
  span.textContent = text;
  entry.appendChild(span);
  log.appendChild(entry);
  return span;
}
