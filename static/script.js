// Function to load and display journal entries
async function loadJournalEntries() {
  try {
    const response = await fetch("/api/journal-entries");
    const entries = await response.json();
    const entryList = document.getElementById("entry-list");

    // Clear existing entries
    entryList.innerHTML = "";

    entries.forEach((entry) => {
      const li = document.createElement("li");
      li.className = "entry-item";
      li.innerHTML = `
        <div class="entry-title" title="${entry.title}">${entry.title}</div>
        <div class="entry-preview">
          <span class="entry-date">${entry.date}</span>
          ${entry.preview}
        </div>
      `;
      li.addEventListener("click", () => loadEntry(entry.filename));
      entryList.appendChild(li);
    });
  } catch (error) {
    console.error("Error loading journal entries:", error);
  }
}

// Function to load a specific entry
async function loadEntry(filename) {
  try {
    const editorContent = document.getElementById("editor-content");
    editorContent.dataset.currentFilename = filename;

    await reloadCurrentJournalEntry();

    // Focus on the editor content
    editorContent.focus();

    // Move the cursor to the end of the content
    const range = document.createRange();
    const sel = window.getSelection();
    range.selectNodeContents(editorContent);
    range.collapse(false);
    sel.removeAllRanges();
    sel.addRange(range);

    // Send the current filename to Chainlit copilot
    sendCurrentFilenameToChainlit(filename);
  } catch (error) {
    console.error("Error loading entry:", error);
  }
}

// Function to auto-save the entry
async function autoSaveEntry() {
  const editorContent = document.getElementById("editor-content");
  const currentFilename = editorContent.dataset.currentFilename;

  if (!currentFilename) {
    console.error("No current filename found for auto-save");
    return;
  }

  try {
    // Convert HTML to Markdown
    const markdownContent = htmlToMarkdown(editorContent.innerHTML);

    const response = await fetch(`/api/update-entry/${currentFilename}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ content: markdownContent }),
    });

    if (!response.ok) {
      throw new Error("Failed to auto-save entry");
    }

    console.log("Entry auto-saved successfully");

    // Refresh the entry list on the sidebar
    await loadJournalEntries();
  } catch (error) {
    console.error("Error auto-saving entry:", error);
  }
}

// Function to convert HTML to Markdown
function htmlToMarkdown(html) {
  // Extract the title (first h1 element)
  const titleMatch = html.match(/<h1>(.*?)<\/h1>/i);
  const title = titleMatch ? titleMatch[1] : "Untitled";

  // Remove the title from the HTML content
  let content = html.replace(/<h1>.*?<\/h1>/i, "");

  // Convert the rest of the content
  let markdown = content
    .replace(/<h2>(.*?)<\/h2>/gi, "## $1\n\n")
    .replace(/<h3>(.*?)<\/h3>/gi, "### $1\n\n")
    .replace(/<strong>(.*?)<\/strong>/gi, "**$1**")
    .replace(/<em>(.*?)<\/em>/gi, "*$1*")
    .replace(/<p>(.*?)<\/p>/gi, "$1\n\n")
    .replace(/<br>/gi, "\n")
    .replace(/<ul>(.*?)<\/ul>/gi, "$1\n")
    .replace(/<li>(.*?)<\/li>/gi, "- $1\n")
    .replace(/<ol>(.*?)<\/ol>/gi, "$1\n")
    .replace(/<li>(.*?)<\/li>/gi, "1. $1\n");

  // Remove any remaining HTML tags
  markdown = markdown.replace(/<[^>]+>/g, "");

  // Combine the title and content
  return `# ${title}\n\n${markdown.trim()}`;
}

// Debounce function to limit the frequency of auto-saves
function debounce(func, delay) {
  let timeoutId;
  return function (...args) {
    clearTimeout(timeoutId);
    timeoutId = setTimeout(() => func.apply(this, args), delay);
  };
}

// Load entries when the page loads
window.addEventListener("load", async () => {
  loadJournalEntries();

  // Fetch and display calendar events
  const calendarEvents = await fetchCalendarEvents();
  updateCalendarSidebar(calendarEvents.todays_events);

  // Add event listener for the new entry button
  const newEntryBtn = document.getElementById("new-entry-btn");
  newEntryBtn.addEventListener("click", createNewEntry);

  // Add event listener for the editor content
  const editorContent = document.getElementById("editor-content");
  editorContent.addEventListener("focus", handleEditorFocus);

  // Mount Chainlit widget with updated configuration
  window.mountChainlitWidget({
    chainlitServer: "http://localhost:8000",
    button: {
      style: {
        bgcolor: "#ffffff",
        color: "#000000",
        borderColor: "#e0e0e0",
      },
    },
  });

  // Send the current filename to Chainlit when the widget is ready
  window.addEventListener("chainlit-widget-ready", () => {
    const currentFilename = editorContent.dataset.currentFilename;
    if (currentFilename) {
      sendCurrentFilenameToChainlit(currentFilename);
    }
  });
});

// Function to send the current filename to Chainlit
function sendCurrentFilenameToChainlit(filename) {
  window.sendChainlitMessage({
    type: "system_message",
    output: JSON.stringify({ action: "load_entry", filename: filename }),
  });
}

// Modify the handleEditorFocus function
async function handleEditorFocus() {
  const editorContent = document.getElementById("editor-content");
  if (
    !editorContent.dataset.currentFilename &&
    editorContent.textContent.trim() === ""
  ) {
    await createNewEntry();
  }
}

// Event listener for Chainlit calls
window.addEventListener("chainlit-call-fn", (e) => {
  const { name, args, callback } = e.detail;
  if (name === "update_journal") {
    console.log("Updating journal entry:", args.filename);
    reloadCurrentJournalEntry();
    callback("Journal entry updated successfully");
  }
});

// Remove the old chainlit-message event listener as it's no longer needed

// Function to create a new entry
async function createNewEntry() {
  try {
    const response = await fetch("/api/new-entry", { method: "POST" });
    const newEntry = await response.json();

    const editorContent = document.getElementById("editor-content");
    editorContent.innerHTML = `<h1>${newEntry.title}</h1><p></p>`;
    editorContent.dataset.currentFilename = newEntry.filename;

    // Remove the 'placeholder' class if it exists
    editorContent.classList.remove("placeholder");

    // Add event listener for auto-save
    editorContent.addEventListener("input", debounce(autoSaveEntry, 1000));

    // Focus the editor and place cursor after the title
    editorContent.focus();
    const range = document.createRange();
    const sel = window.getSelection();
    range.setStartAfter(editorContent.querySelector("h1"));
    range.collapse(true);
    sel.removeAllRanges();
    sel.addRange(range);

    await loadJournalEntries(); // Reload the entry list
  } catch (error) {
    console.error("Error creating new entry:", error);
  }
}

// Function to reload the current journal entry in the editor
async function reloadCurrentJournalEntry() {
  const editorContent = document.getElementById("editor-content");
  const currentFilename = editorContent.dataset.currentFilename;
  if (currentFilename) {
    try {
      const response = await fetch(`/api/journal-entry/${currentFilename}`);
      if (response.ok) {
        const content = await response.text();
        editorContent.innerHTML = content;
        console.log("Journal entry reloaded successfully");

        // Refresh the entry list on the sidebar
        await loadJournalEntries();
      } else {
        console.error("Failed to reload journal entry");
      }
    } catch (error) {
      console.error("Error reloading journal entry:", error);
    }
  }
}

// Function to fetch calendar events
async function fetchCalendarEvents() {
  try {
    const response = await fetch("/api/calendar-events");
    const data = await response.json();
    return data;
  } catch (error) {
    console.error("Error fetching calendar events:", error);
    return { all_events: [], todays_events: [] };
  }
}

// Function to update the sidebar with calendar events
function updateCalendarSidebar(events) {
  const eventList = document.getElementById("event-list");
  eventList.innerHTML = ""; // Clear existing events

  events.forEach((event) => {
    const li = document.createElement("li");
    li.textContent = event;
    eventList.appendChild(li);
  });
}
