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
        <div class="entry-title">${entry.title}</div>
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
    const response = await fetch(`/api/journal-entry/${filename}`);
    const content = await response.text();
    const editorContent = document.getElementById("editor-content");

    // Always set the entire content, including the new heading
    editorContent.innerHTML = content;

    editorContent.dataset.currentFilename = filename;
  } catch (error) {
    console.error("Error loading entry:", error);
  }
}

// Load entries when the page loads
window.addEventListener("load", () => {
  loadJournalEntries();

  // Add event listener for the new entry button
  const newEntryBtn = document.getElementById("new-entry-btn");
  newEntryBtn.addEventListener("click", createNewEntry);
});

// Function to reload the current journal entry in the editor
function reloadCurrentJournalEntry() {
  const editorContent = document.getElementById("editor-content");
  if (editorContent.dataset.currentFilename) {
    loadEntry(editorContent.dataset.currentFilename);
  }
}

// Event listener for Chainlit calls
window.addEventListener("chainlit-call-fn", (e) => {
  const { name, args, callback } = e.detail;
  if (name === "test") {
    console.log(name, args);
    callback("You sent: " + args.msg);
    reloadCurrentJournalEntry();
  }
});

// Mount Chainlit widget
window.mountChainlitWidget({
  chainlitServer: "http://localhost:8000",
});

// Function to create a new entry
async function createNewEntry() {
  try {
    const response = await fetch("/api/new-entry", { method: "POST" });
    const newEntry = await response.json();
    loadEntry(newEntry.filename);
    await loadJournalEntries(); // Reload the entry list
  } catch (error) {
    console.error("Error creating new entry:", error);
  }
}
