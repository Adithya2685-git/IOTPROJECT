import requests
import base64
import json

# OM2M server configuration (adjust as needed)
# For a container with child content instances, you often need to include ?rcn=4.
SERVER_URL = "http://192.168.158.66:8080/~/in-cse/in-name/voice_command/audio_upload?rcn=4"
AUTH_CREDENTIALS = ("admin", "admin")
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json"
}

def fetch_om2m_audio_entries():
    """
    Fetches the audio entries from the OM2M server and prints the raw JSON.
    Returns the JSON data as a dictionary.
    """
    try:
        response = requests.get(SERVER_URL, auth=AUTH_CREDENTIALS, headers=HEADERS)
        response.raise_for_status()  # Raise an error for HTTP error codes
        data = response.json()
        print("=== FULL JSON RESPONSE ===")
        print(json.dumps(data, indent=2))
        return data
    except Exception as e:
        print("Error fetching audio data:", e)
        return {}

def extract_entries_from_container(data):
    """
    Extracts audio entries when the JSON response has a container response.
    Typically, OM2M returns the container as a key 'm2m:cnt' and the audio
    content instances under the key 'm2m:cin'.
    """
    if "m2m:cnt" in data:
        container = data["m2m:cnt"]
        if "m2m:cin" in container:
            entries = container["m2m:cin"]
            if isinstance(entries, dict):
                entries = [entries]  # Single instance is returned as a dict
            return entries
    print("Expected keys not found in container response.")
    return []

def extract_entries_from_results(data):
    """
    Extracts audio entries when the JSON response holds a list under 'results'.
    Each element in the list should have an 'm2m:cin' key.
    """
    if "results" in data:
        results = data["results"]
        entries = []
        for item in results:
            if "m2m:cin" in item:
                entries.append(item["m2m:cin"])
        return entries
    print("Expected 'results' key not found in JSON.")
    return []

def parse_entries(data):
    """
    Attempts to parse the raw JSON data and extract audio entries.
    First, it tries the container approach; if that fails, it then checks for a direct list.
    """
    entries = extract_entries_from_container(data)
    if entries:
        return entries

    # Fall back to results parsing
    entries = extract_entries_from_results(data)
    if entries:
        return entries

    print("No audio entries found in the response.")
    return []

def assemble_wav_file(session_data):
    """
    Assemble a WAV file using a session's header and audio chunks.
    The session_data is expected to have:
      - header: Base64 encoded WAV header string
      - chunks: A dictionary with chunk indices as keys and Base64 encoded chunk data as values
    Returns:
      - wav_bytes: A bytes object containing the complete WAV file data,
                   or None on error.
    """
    if session_data.get("header") is None:
        print("No WAV header found in session data.")
        return None

    try:
        header_bytes = base64.b64decode(session_data["header"])
    except Exception as e:
        print("Error decoding header:", e)
        return None

    wav_data = bytearray(header_bytes)
    chunks = session_data.get("chunks", {})

    for idx in sorted(chunks.keys()):
        try:
            chunk_bytes = base64.b64decode(chunks[idx])
        except Exception as e:
            print(f"Error decoding chunk {idx}:", e)
            return None
        wav_data.extend(chunk_bytes)

    return wav_data

def group_audio_session(entries):
    """
    Groups individual audio messages (AUDIO_START, AUDIO_CHUNK, AUDIO_END) by session.
    Returns:
        sessions: A dict mapping session IDs to their respective data.
                  Example:
                  {
                      "session_id": {
                          "header": "<Base64 WAV header>",
                          "total_chunks": <int>,
                          "chunks": {0: "<Base64 data>", 1: "<Base64 data>", ...},
                          "end": True/False
                      },
                      ...
                  }
    """
    sessions = {}
    for entry in entries:
        message = entry.get("con", "")
        if message.startswith("AUDIO_START:"):
            parts = message.split(":")
            if len(parts) >= 4:
                session_id = parts[1]
                try:
                    total_chunks = int(parts[2])
                except ValueError:
                    total_chunks = 0
                header_encoded = parts[3]
                sessions[session_id] = {
                    "header": header_encoded,
                    "total_chunks": total_chunks,
                    "chunks": {},
                    "end": False
                }
        elif message.startswith("AUDIO_CHUNK:"):
            parts = message.split(":")
            if len(parts) >= 4:
                session_id = parts[1]
                try:
                    chunk_index = int(parts[2])
                except ValueError:
                    continue
                chunk_encoded = parts[3]
                if session_id in sessions:
                    sessions[session_id]["chunks"][chunk_index] = chunk_encoded
                else:
                    sessions[session_id] = {
                        "header": None,
                        "total_chunks": 0,
                        "chunks": {chunk_index: chunk_encoded},
                        "end": False
                    }
        elif message.startswith("AUDIO_END:"):
            parts = message.split(":")
            if len(parts) >= 2:
                session_id = parts[1]
                if session_id in sessions:
                    sessions[session_id]["end"] = True
                else:
                    sessions[session_id] = {
                        "header": None,
                        "total_chunks": 0,
                        "chunks": {},
                        "end": True
                    }
    return sessions

def main():
    # Fetch and print the raw JSON from the OM2M server.
    raw_data = fetch_om2m_audio_entries()
    if not raw_data:
        print("No data returned from OM2M.")
        return

    # Extract audio entries from the JSON (adjust based on your OM2M structure).
    entries = parse_entries(raw_data)
    if not entries:
        print("No audio entries found after parsing.")
        return

    print("Found %d audio entries." % len(entries))
    for i, entry in enumerate(entries):
        print(f"Entry {i+1} content:", entry.get("con", "No content"))

    # Group the entries by audio session
    sessions = group_audio_session(entries)
    if not sessions:
        print("No audio session found.")
        return

    # Select the latest session based on the session id (assumed to be numeric string)
    latest_session_id = max(sessions.keys(), key=lambda sid: int(sid) if sid.isdigit() else 0)
    session_data = sessions[latest_session_id]

    # Optionally, validate the session contains an AUDIO_END marker and the expected number of chunks
    expected_chunks = session_data.get("total_chunks", 0)
    if not session_data.get("end", False):
        print("Warning: AUDIO_END marker not received for session", latest_session_id)
    if expected_chunks and len(session_data["chunks"]) != expected_chunks:
        print(f"Warning: Expected {expected_chunks} chunks but received {len(session_data['chunks'])}.")

    # Assemble the WAV file from the session data
    wav_bytes = assemble_wav_file(session_data)
    if wav_bytes is None:
        print("Failed to assemble WAV file.")
        return

    output_filename = "output.wav"
    try:
        with open(output_filename, "wb") as f:
            f.write(wav_bytes)
        print(f"WAV file successfully saved as '{output_filename}'.")
    except Exception as e:
        print("Error writing WAV file:", e)

if __name__ == "__main__":
    main()
