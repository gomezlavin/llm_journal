// Function to load and display journal entries
async function loadJournalEntries() {
  try {
    const response = await fetch("/api/journal-entries");
    const entries = await response.json();
    const entryList = document.getElementById("entry-list");
    const currentFilename =
      document.getElementById("editor-content").dataset.currentFilename;

    // Clear existing entries
    entryList.innerHTML = "";

    entries.forEach((entry) => {
      const li = document.createElement("li");
      li.className = "entry-item";
      li.dataset.filename = entry.filename;
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

    // Highlight the current entry
    highlightCurrentEntry(currentFilename);
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

    // Update URL parameter
    updateUrlParam("entry", filename);

    // Update the right sidebar with events for the current date
    if (filename) {
      await updateRightSidebarEvents(filename);
    } else {
      console.error("No filename available for loading events");
    }

    // Highlight the current entry in the sidebar
    highlightCurrentEntry(filename);
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
  await loadJournalEntries();

  // Fetch and display calendar events
  const calendarEvents = await fetchCalendarEvents();
  const today = new Date().toISOString().split("T")[0];
  updateCalendarSidebar(calendarEvents, today);

  // Add event listener for the new entry button
  const newEntryBtn = document.getElementById("new-entry-btn");
  newEntryBtn.addEventListener("click", createNewEntry);

  // Add event listener for the editor content
  const editorContent = document.getElementById("editor-content");
  editorContent.addEventListener("focus", handleEditorFocus);

  // Mount Chainlit widget with updated configuration
  window.mountChainlitWidget({
    containerId: "toggle-sidebar-btn",
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

  // Check for entry parameter in URL
  const entryParam = getUrlParam("entry");
  if (entryParam) {
    await loadEntry(entryParam);
  } else {
    await openTodaysLatestNote();
  }
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
    updateUrlParam("entry", newEntry.filename); // Update URL parameter

    // Update the right sidebar with events for the new entry's date
    await updateRightSidebarEvents(newEntry.filename);
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
async function fetchCalendarEvents(forceRefresh = false) {
  const url = forceRefresh
    ? "/api/calendar-events?refresh=true"
    : "/api/calendar-events";
  fetch(url)
    .then((response) => response.json())
    .then((data) => {
      updateEventList(data.todays_events);
    })
    .catch((error) => console.error("Error fetching calendar events:", error));
}

// Function to update the sidebar with calendar events
function updateCalendarSidebar(events, date) {
  const eventList = document.getElementById("event-list");
  eventList.innerHTML = ""; // Clear existing events

  console.log("Updating calendar sidebar with events:", events);
  console.log("Date:", date);

  // Update the sidebar title with the date
  const sidebarTitle = document.getElementById("sidebar-title");
  const dateObj = new Date(date);
  const options = {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  };
  sidebarTitle.textContent = dateObj.toLocaleDateString("en-US", options);

  if (!Array.isArray(events) || events.length === 0) {
    console.log("No events to display");
    eventList.innerHTML = "<li>No events for this date</li>";
    return;
  }

  events.forEach((event) => {
    if (!event || !event.title || !event.start_time || !event.end_time) {
      console.error("Invalid event data:", event);
      return;
    }

    const li = document.createElement("li");
    const startTime = new Date(event.start_time).toLocaleTimeString("en-US", {
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    });
    const endTime = new Date(event.end_time).toLocaleTimeString("en-US", {
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    });
    li.textContent = `${event.title}, ${startTime}-${endTime}`;
    eventList.appendChild(li);
  });
}

// Function to open today's latest note
async function openTodaysLatestNote() {
  try {
    const response = await fetch("/api/journal-entries");
    const entries = await response.json();

    const today = new Date().toISOString().split("T")[0];
    const todaysEntries = entries.filter((entry) => entry.date === today);

    if (todaysEntries.length > 0) {
      const latestEntry = todaysEntries[0]; // Entries are already sorted latest first
      await loadEntry(latestEntry.filename);
    } else {
      await createNewEntry();
    }
  } catch (error) {
    console.error("Error opening today's latest note:", error);
  }
}

// Function to update URL parameter
function updateUrlParam(key, value) {
  const url = new URL(window.location);
  url.searchParams.set(key, value);
  window.history.pushState({}, "", url);
}

// Function to get URL parameter
function getUrlParam(key) {
  const urlParams = new URLSearchParams(window.location.search);
  return urlParams.get(key);
}

// Add this new function to update the right sidebar events
async function updateRightSidebarEvents(filename) {
  try {
    const date = filename.split("-").slice(0, 3).join("-");
    console.log("Fetching events for date:", date);
    const response = await fetch(`/api/calendar-events/${date}`);
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    const events = await response.json();
    console.log("Received events:", events);
    if (Array.isArray(events) && events.length > 0) {
      updateCalendarSidebar(events, date);
    } else {
      console.log("No events found for the date");
      updateCalendarSidebar([], date);
    }
  } catch (error) {
    console.error("Error fetching events for the date:", error);
    updateCalendarSidebar([], filename.split("-").slice(0, 3).join("-"));
  }
}

// Add this function to highlight the current entry
function highlightCurrentEntry(filename) {
  const entryItems = document.querySelectorAll(".entry-item");
  entryItems.forEach((item) => {
    item.classList.remove("current-entry");
    if (item.dataset.filename === filename) {
      item.classList.add("current-entry");
    }
  });
}

document.addEventListener("DOMContentLoaded", function () {
  const toggleSidebarBtn = document.getElementById("toggle-sidebar-btn");
  const rightSidebar = document.getElementById("right-sidebar");

  toggleSidebarBtn.addEventListener("click", function () {
    rightSidebar.classList.toggle("hidden");
    toggleSidebarBtn.classList.toggle("sidebar-hidden");

    // Update the emoji based on the sidebar state
    if (rightSidebar.classList.contains("hidden")) {
      toggleSidebarBtn.textContent = "🗄️";
    } else {
      toggleSidebarBtn.textContent = "📁";
    }
  });

  const refreshEventsBtn = document.getElementById("refresh-events-btn");
  refreshEventsBtn.addEventListener("click", function () {
    fetchCalendarEvents(true);
  });
});
