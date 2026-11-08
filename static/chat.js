const form = document.querySelector("#chat-form");
const input = document.querySelector("#message-input");
const sendButton = document.querySelector("#send-button");
const count = document.querySelector("#character-count");
const messages = document.querySelector("#messages");
const status = document.querySelector("#assistant-state");
const resetButton = document.querySelector("#new-chat");
const welcome = messages.querySelector("[data-welcome]").cloneNode(true);
const history = [];

function setStatus(label, state = "") {
  status.className = `status-pill ${state}`.trim();
  status.lastElementChild.textContent = label;
}

function scrollLatest() {
  messages.scrollTop = messages.scrollHeight;
}

function createMessage(text, isUser) {
  const row = document.createElement("article");
  row.className = `message-row ${isUser ? "user-message" : "assistant-message"}`;
  const avatar = document.createElement("div");
  avatar.className = "message-avatar";
  avatar.setAttribute("aria-hidden", "true");
  avatar.textContent = isUser ? "YOU" : "N";
  const stack = document.createElement("div");
  stack.className = "message-stack";
  const sender = document.createElement("span");
  sender.className = "message-sender";
  sender.textContent = isUser ? "You" : "NurtureNest · companion";
  const bubble = document.createElement("div");
  bubble.className = "message-bubble";
  bubble.textContent = text;
  const time = document.createElement("span");
  time.className = "message-time";
  time.textContent = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(new Date());
  stack.append(sender, bubble, time);
  row.append(avatar, stack);
  messages.append(row);
  scrollLatest();
  return { bubble, stack };
}

function appendSources(stack, sources) {
  if (!sources?.length) return;
  const list = document.createElement("div");
  list.className = "source-list";
  for (const source of sources) {
    const link = document.createElement("a");
    link.textContent = source.topic || source.label;
    if (source.url) {
      link.href = source.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
    } else {
      link.href = "#";
      link.addEventListener("click", (event) => event.preventDefault());
      link.title = source.label || source.topic;
    }
    list.append(link);
  }
  stack.append(list);
}

function applyEvent(event, reply) {
  if (event.token) {
    reply.bubble.classList.remove("is-streaming");
    reply.bubble.textContent += event.token;
    reply.content += event.token;
    scrollLatest();
  }
  if (event.done) {
    reply.complete = true;
    appendSources(reply.stack, event.sources);
    setStatus(event.emergency ? "Urgent guidance" : "Listening", event.emergency ? "is-alert" : "");
  }
  if (event.error) {
    reply.failed = true;
    reply.bubble.textContent = event.error;
    setStatus("Connection issue", "is-alert");
  }
}

async function consumeStream(response, reply) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const dispatch = (block) => {
    const line = block.split(/\r?\n/).find((item) => item.startsWith("data: "));
    if (line) applyEvent(JSON.parse(line.slice(6)), reply);
  };
  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      dispatch(buffer.slice(0, boundary));
      buffer = buffer.slice(boundary + 2);
      boundary = buffer.indexOf("\n\n");
    }
    if (done) break;
  }
  if (buffer.trim()) dispatch(buffer);
}

async function sendMessage(message) {
  createMessage(message, true);
  const reply = createMessage("", false);
  Object.assign(reply, { content: "", complete: false, failed: false });
  reply.bubble.classList.add("is-streaming");
  setStatus("Writing back", "is-busy");
  input.disabled = true;
  sendButton.disabled = true;
  resetButton.disabled = true;
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, history: history.slice(-8) }),
    });
    if (!response.ok) {
      const payload = await response.json();
      throw new Error(payload.error || "Your message could not be sent.");
    }
    await consumeStream(response, reply);
    reply.bubble.classList.remove("is-streaming");
    if (reply.complete && !reply.failed) {
      history.push({ role: "user", content: message }, { role: "assistant", content: reply.content });
      history.splice(0, Math.max(0, history.length - 8));
    }
  } catch (error) {
    reply.bubble.classList.remove("is-streaming");
    reply.bubble.textContent = error.message || "I couldn't connect. Please try again.";
    setStatus("Connection issue", "is-alert");
  } finally {
    input.disabled = false;
    resetButton.disabled = false;
    input.focus();
    updateComposer();
  }
}

function updateComposer() {
  count.textContent = `${input.value.length} / 2000`;
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 128)}px`;
  sendButton.disabled = input.disabled || !input.value.trim();
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const message = input.value.trim();
  if (!message || input.disabled) return;
  input.value = "";
  updateComposer();
  sendMessage(message);
});
input.addEventListener("input", updateComposer);
input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});
document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => {
    if (input.disabled) return;
    input.value = button.dataset.prompt;
    updateComposer();
    form.requestSubmit();
  });
});
resetButton.addEventListener("click", async () => {
  if (resetButton.disabled) return;
  resetButton.disabled = true;
  try {
    const response = await fetch("/api/clear", { method: "POST" });
    if (!response.ok) throw new Error("Could not start a new chat.");
    history.length = 0;
    messages.replaceChildren(welcome.cloneNode(true));
    setStatus("Listening");
    input.value = "";
    updateComposer();
    input.focus();
  } catch (error) {
    setStatus(error.message, "is-alert");
  } finally {
    resetButton.disabled = false;
  }
});
updateComposer();
