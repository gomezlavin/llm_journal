from flask import Flask, jsonify, send_file, send_from_directory, request
import os
import markdown
from datetime import datetime
import re

app = Flask(__name__, static_folder="static")


def generate_unique_filename():
    today = datetime.now().strftime("%Y-%m-%d")
    timestamp = datetime.now().strftime("%H%M%S")
    return f"{today}-{timestamp}-entry.md"


@app.route("/api/journal-entries")
def get_journal_entries():
    entries = []
    for filename in os.listdir("data"):
        if filename.endswith(".md"):
            file_path = os.path.join("data", filename)
            with open(file_path, "r") as f:
                content = f.read().split("\n")
                title = content[0].strip("# ")  # Remove Markdown heading syntax
                body = content[1] if len(content) > 1 else ""
                date_str = filename.split("-")[:3]
                date = "-".join(date_str[:3])  # Keep as YYYY-MM-DD
                preview = body[:100] + "..." if len(body) > 100 else body
                entries.append(
                    {
                        "date": date,
                        "title": title,
                        "preview": preview,
                        "filename": filename,
                    }
                )
    return jsonify(sorted(entries, key=lambda x: x["filename"], reverse=True))


@app.route("/api/journal-entry/<filename>")
def get_journal_entry(filename):
    file_path = os.path.join("data", filename)
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            content = f.read()
            html_content = markdown.markdown(content)
            return html_content
    return "Entry not found", 404


@app.route("/")
def serve_journal():
    return send_file("journal.html")


@app.route("/static/<path:path>")
def serve_static(path):
    return send_from_directory("static", path)


@app.route("/api/new-entry", methods=["POST"])
def create_new_entry():
    filename = generate_unique_filename()
    title = f"Today, ..."
    file_path = os.path.join("data", filename)

    # Create a new entry file
    with open(file_path, "w") as f:
        f.write(f"# {title}\n\n")

    return jsonify(
        {
            "filename": filename,
            "title": title,
            "date": filename.split("-")[0],
            "preview": "",
        }
    )


if __name__ == "__main__":
    app.run(debug=True)
