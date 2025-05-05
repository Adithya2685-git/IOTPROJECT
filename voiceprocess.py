import requests
import base64
import json
import os
import time
import torch # For device check and Sentence Transformers
import hashlib  # Added for data comparison
from faster_whisper import WhisperModel # Import here for type hints or general visibility
from sentence_transformers import SentenceTransformer, util # Import here

# --- Configuration ---
# OM2M server config
SERVER_URL = "http://192.168.158.66:8080/~/in-cse/in-name/voice_command/audio_upload?rcn=4"
AUTH_CREDENTIALS = ("admin", "admin")
HEADERS = {
    "X-M2M-Origin": "admin:admin", # Include originator for OM2M requests
    "Content-Type": "application/json",
    "Accept": "application/json"
}
OUTPUT_WAV_FILENAME = "output_latest_command.wav" # Changed filename
POLLING_INTERVAL = 4  # Fetch every 4 seconds
REQUIRE_COMPLETE_SESSIONS = True  # Only process complete sessions

# AI Model Config
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
COMPUTE_TYPE = "float16" if DEVICE == "cuda" else "int8" # Use float16 on GPU, int8 on CPU for performance
WHISPER_MODEL_SIZE = "large-v3"
SENTENCE_TRANSFORMER_MODEL = 'all-mpnet-base-v2'
SIMILARITY_THRESHOLD = 0.2 # Adjust this threshold based on testing (0.0 to 1.0)

# Command Mapping Config
# Define the canonical commands and their corresponding structured action
COMMAND_MAP = {
    "activate lights":          {'device': 'led', 'action': 'activate'},
    "deactivate lights":        {'device': 'led', 'action': 'deactivate'},
    "lights on":          {'device': 'led', 'action': 'activate'},
    "lights off":       {'device': 'led', 'action': 'deactivate'},
    "turn on lights":           {'device': 'led', 'action': 'activate'}, # Alias
    "turn off lights":          {'device': 'led', 'action': 'deactivate'}, # Alias
    "activate lock":    {'device': 'solenoid', 'action': 'activate'},
    "deactivate lock":  {'device': 'solenoid', 'action': 'deactivate'},
    "turn on lock":     {'device': 'solenoid', 'action': 'activate'}, # Alias
    "turn off lock":    {'device': 'solenoid', 'action': 'deactivate'}, # Alias
    "fan speed to minimum":  {'device': 'fan', 'action': 'set_speed', 'value': 1},
    "fan speed to medium":  {'device': 'fan', 'action': 'set_speed', 'value': 2},
    "fan speed to max":  {'device': 'fan', 'action': 'set_speed', 'value': 3},
    "fan speed to one":          {'device': 'fan', 'action': 'set_speed', 'value': 1}, # Alias
    "fan speed to two":          {'device': 'fan', 'action': 'set_speed', 'value': 2}, # Alias
    "fan speed to three":          {'device': 'fan', 'action': 'set_speed', 'value': 3}, # Alias
    "set to one":          {'device': 'fan', 'action': 'set_speed', 'value': 1}, # Alias
    "set to two":          {'device': 'fan', 'action': 'set_speed', 'value': 2}, # Alias
    "set to three":          {'device': 'fan', 'action': 'set_speed', 'value': 3}, # Alias
    "deactivate fan":        {'device': 'fan', 'action': 'deactivate'},
    "fan off":       {'device': 'fan', 'action': 'deactivate'},
    "switch off fan":        {'device': 'fan', 'action': 'deactivate'},
    "turn off fan":         {'device': 'fan', 'action': 'deactivate'}, # Alias
    "set fan off":         {'device': 'fan', 'action': 'deactivate'} # Alias
}
# Get the list of canonical command phrases for embedding
CANONICAL_COMMANDS = list(COMMAND_MAP.keys())

# --- Global Variables for Models (Load Once) ---
whisper_model: WhisperModel = None
st_model: SentenceTransformer = None
known_command_embeddings: torch.Tensor = None
last_processed_hash = None  # Track the hash of previously processed data
last_processed_session_id = None  # Track the last processed session ID

# --- Model Loading Function ---
def load_models():
    global whisper_model, st_model, known_command_embeddings
    if whisper_model is not None and st_model is not None:
        print("Models already loaded.")
        return True

    print(f"Attempting to load models on device: {DEVICE}")
    try:
        # Load Whisper model (using faster-whisper)
        print(f"Loading Whisper model: {WHISPER_MODEL_SIZE}...")
        st_whisper = time.time()
        # Lazy loading, will download model on first use if not cached
        whisper_model = WhisperModel(WHISPER_MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
        print(f"Whisper model loaded in {time.time() - st_whisper:.2f} seconds.")

        # Load Sentence Transformer model
        print(f"Loading Sentence Transformer model: {SENTENCE_TRANSFORMER_MODEL}...")
        st_st = time.time()
        # Model will be downloaded if not cached
        st_model = SentenceTransformer(SENTENCE_TRANSFORMER_MODEL, device=DEVICE)
        print(f"Sentence Transformer model loaded in {time.time() - st_st:.2f} seconds.")

        # Pre-compute embeddings for known commands
        print("Computing known command embeddings...")
        st_emb = time.time()
        known_command_embeddings = st_model.encode(CANONICAL_COMMANDS, convert_to_tensor=True, device=DEVICE)
        print(f"Command embeddings computed in {time.time() - st_emb:.2f} seconds.")
        print("--- Models loaded successfully ---")
        return True

    except ImportError as e:
        print(f"Error importing model libraries: {e}")
        print("Please ensure faster-whisper and sentence-transformers are installed.")
        return False
    except Exception as e:
        print(f"Error loading models: {e}")
        # Specific check for CUDA issues
        if "cuda" in str(e).lower():
            print("This might be a CUDA setup issue. Ensure PyTorch was installed with the correct CUDA version for your GPU.")
        return False

# --- OM2M Fetching and Audio Assembly Functions (User Provided) ---

def fetch_om2m_audio_entries():
    """ Fetches audio entries from OM2M. """
    print(f"Fetching audio entries from: {SERVER_URL}")
    try:
        response = requests.get(SERVER_URL, auth=AUTH_CREDENTIALS, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        # print("=== FULL JSON RESPONSE ===") # Optional: uncomment for debugging
        # print(json.dumps(data, indent=2))
        return data
    except requests.exceptions.RequestException as e:
        print(f"Error fetching audio data from OM2M: {e}")
        return {}
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON response from OM2M: {e}")
        print(f"Response text: {response.text[:500]}...") # Log part of the response
        return {}
    except Exception as e:
        print(f"An unexpected error occurred during fetching: {e}")
        return {}

def calculate_data_hash(data):
    """Calculate a hash representing the data content."""
    if not data:
        return "empty_data"
    # Convert data to a consistent string representation and hash it
    data_str = json.dumps(data, sort_keys=True)
    return hashlib.md5(data_str.encode()).hexdigest()

def extract_entries_from_container(data):
    """ Extracts entries from typical OM2M container response. """
    if "m2m:cnt" in data:
        container = data["m2m:cnt"]
        if "m2m:cin" in container:
            entries = container["m2m:cin"]
            # Handle single instance vs list
            if isinstance(entries, dict):
                return [entries]
            elif isinstance(entries, list):
                return entries
            else:
                print(f"Warning: Unexpected type for 'm2m:cin': {type(entries)}")
                return []
    return [] # Return empty list if keys not found


def parse_entries(data):
    """ Parses raw JSON data to extract audio content instances ('m2m:cin'). """
    # Prioritize 'm2m:cnt' structure
    entries = extract_entries_from_container(data)
    if entries:
        print(f"Found {len(entries)} entries under 'm2m:cnt'.")
        return entries

    # Fallback: Check if data itself is a list of CINs (less common)
    if isinstance(data, list):
          # Check if elements look like CINs
          if data and isinstance(data[0], dict) and data[0].get('ty') == 4:
              print(f"Found {len(data)} entries directly in list.")
              return data

    # Fallback: Check if it's a response with a list under 'm2m:rsp' -> 'pc' -> 'm2m:cnt' -> 'm2m:cin'
    # This structure can appear in some responses depending on request parameters
    if isinstance(data, dict) and 'm2m:rsp' in data:
        rsp = data['m2m:rsp']
        if isinstance(rsp, dict) and 'pc' in rsp:
            pc = rsp['pc']
            # Now check if 'pc' contains the container structure
            pc_entries = extract_entries_from_container(pc)
            if pc_entries:
                print(f"Found {len(pc_entries)} entries under 'm2m:rsp/pc/m2m:cnt'.")
                return pc_entries

    print("Could not find 'm2m:cin' entries in the expected structures.")
    return []


def group_audio_session(entries):
    """ Groups audio messages by session ID. """
    sessions = {}
    print(f"Grouping {len(entries)} entries into sessions...")
    for entry in entries:
        # Check if entry is a dictionary and has 'con' key
        if not isinstance(entry, dict) or "con" not in entry:
            print(f"Skipping invalid entry: {entry}")
            continue

        message = entry["con"]
        if not isinstance(message, str):
            print(f"Skipping entry with non-string content: {message}")
            continue

        try:
            if message.startswith("AUDIO_START:"):
                parts = message.split(":", 3) # Split max 3 times
                if len(parts) == 4:
                    session_id, total_chunks_str, header_encoded = parts[1], parts[2], parts[3]
                    total_chunks = int(total_chunks_str)
                    sessions[session_id] = {
                        "header": header_encoded, "total_chunks": total_chunks,
                        "chunks": {}, "end": False
                    }
                else: print(f"Malformed AUDIO_START: {message}")
            elif message.startswith("AUDIO_CHUNK:"):
                parts = message.split(":", 3) # Split max 3 times
                if len(parts) == 4:
                    session_id, chunk_index_str, chunk_encoded = parts[1], parts[2], parts[3]
                    chunk_index = int(chunk_index_str)
                    if session_id not in sessions: # Handle chunk before start (unlikely but possible)
                        sessions[session_id] = {"header": None, "total_chunks": 0, "chunks": {}, "end": False}
                    sessions[session_id]["chunks"][chunk_index] = chunk_encoded
                else: print(f"Malformed AUDIO_CHUNK: {message}")
            elif message.startswith("AUDIO_END:"):
                parts = message.split(":", 1) # Split max 1 time
                if len(parts) == 2:
                    session_id = parts[1]
                    if session_id in sessions:
                        sessions[session_id]["end"] = True
                    else: # Handle end before start/chunk (unlikely)
                        sessions[session_id] = {"header": None, "total_chunks": 0, "chunks": {}, "end": True}
                else: print(f"Malformed AUDIO_END: {message}")
        except ValueError:
             print(f"Error parsing numeric part in message: {message}")
        except Exception as e:
             print(f"Unexpected error processing message '{message}': {e}")

    print(f"Found {len(sessions)} unique session IDs.")
    return sessions

def is_session_complete(session_data):
    """Check if a session is complete (has all chunks and end marker)."""
    # Verify we have header, all chunks, and end marker
    if not session_data or session_data.get("header") is None:
        # print("Session incomplete: Missing header") # Too noisy if always incomplete
        return False

    expected_chunks = session_data.get("total_chunks", 0)
    received_chunks = len(session_data.get("chunks", {}))

    if expected_chunks <= 0:
        # print("Session incomplete: Invalid expected chunk count") # Too noisy
        return False

    if received_chunks != expected_chunks:
        # print(f"Session incomplete: Missing chunks (expected {expected_chunks}, got {received_chunks})") # Too noisy
        return False

    if not session_data.get("end", False):
        # print("Session incomplete: Missing end marker") # Too noisy
        return False

    # All checks passed
    return True

def assemble_wav_file(session_data):
    """ Assembles WAV bytes from session header and chunks. """
    if not session_data or session_data.get("header") is None:
        print("Error: No header found in session data for assembly.")
        return None

    try:
        header_bytes = base64.b64decode(session_data["header"])
    except Exception as e:
        print(f"Error decoding base64 header: {e}")
        return None

    wav_data = bytearray(header_bytes)
    chunks = session_data.get("chunks", {})
    received_indices = sorted(chunks.keys())

    # Check for missing chunks if total_chunks is reliable
    expected_chunks = session_data.get("total_chunks", 0)
    if expected_chunks > 0 and len(received_indices) != expected_chunks:
        print(f"Warning: Mismatch! Expected {expected_chunks}, Got {len(received_indices)} chunks.")
        # Optional: Check for sequence gaps
        expected_indices = set(range(expected_chunks))
        missing = expected_indices - set(received_indices)
        if missing:
            print(f"Missing chunk indices: {sorted(list(missing))}")
            # Decide if you want to proceed despite missing chunks
            # return None # Uncomment to fail if chunks are missing

    print(f"Assembling WAV from {len(received_indices)} received chunks.")
    for idx in received_indices:
        try:
            chunk_bytes = base64.b64decode(chunks[idx])
            wav_data.extend(chunk_bytes)
        except Exception as e:
            print(f"Error decoding base64 for chunk {idx}: {e}")
            return None # Fail assembly if a chunk is corrupt

    return bytes(wav_data) # Return immutable bytes

# --- AI Processing Function ---
def process_audio_command(audio_path):
    """
    Transcribes audio using Whisper (English only) and maps recognized text to a command
    using Sentence Transformers and cosine similarity.
    """
    global whisper_model, st_model, known_command_embeddings # Use global models

    if whisper_model is None or st_model is None:
        print("Error: Models not loaded. Cannot process audio.")
        return None

    if not os.path.exists(audio_path):
        print(f"Error: Audio file not found at {audio_path}")
        return None

    try:
        # 1. Transcribe Audio using faster-whisper
        print(f"Transcribing '{audio_path}' with {WHISPER_MODEL_SIZE} (English only)...")
        st_transcribe = time.time()
        # Transcribe returns an iterator -> convert to list
        # *** MODIFICATION HERE: Specify language="en" ***
        segments, info = whisper_model.transcribe(audio_path, beam_size=5, language="en")
        # *********************************************
        recognized_text = " ".join([segment.text for segment in segments]).strip()
        duration = time.time() - st_transcribe
        print(f"Whisper recognized: '{recognized_text}' (in {duration:.2f}s)")
        # The language detection info might still be available but less relevant as we forced English
        # print(f"Detected language (Note: Forced English): {info.language} (probability {info.language_probability:.2f})")


        if not recognized_text:
            print("Whisper recognized empty text.")
            return None

        # 2. NLU: Find most similar command using Sentence Transformers
        st_nlu = time.time()
        recognized_embedding = st_model.encode(recognized_text, convert_to_tensor=True, device=DEVICE)

        # Compute cosine similarities
        cosine_scores = util.cos_sim(recognized_embedding, known_command_embeddings)[0]

        # Find the best match
        best_match_idx = torch.argmax(cosine_scores).item()
        best_score = cosine_scores[best_match_idx].item()
        matched_command_phrase = CANONICAL_COMMANDS[best_match_idx]
        nlu_duration = time.time() - st_nlu
        print(f"NLU processed in {nlu_duration:.3f}s")
        print(f"Best command match: '{matched_command_phrase}' with score: {best_score:.4f}")

        # 3. Map to Action (Apply threshold)
        if best_score >= SIMILARITY_THRESHOLD:
            action_details = COMMAND_MAP[matched_command_phrase]
            print(f"Command accepted. Action: {action_details}")
            # Add confidence score to the action details
            action_details_with_score = action_details.copy()
            action_details_with_score['confidence'] = best_score
            action_details_with_score['recognized_text'] = recognized_text # Include original text
            return action_details_with_score
        else:
            print(f"Command similarity ({best_score:.4f}) below threshold ({SIMILARITY_THRESHOLD}). Ignoring.")
            return None

    except Exception as e:
        print(f"Error during AI processing: {e}")
        import traceback
        traceback.print_exc() # Print detailed traceback for debugging
        return None

# --- OM2M Interaction Function (Placeholder) ---
def execute_om2m_action(action_details):
    """
    Placeholder function to send commands back to OM2M based on action_details.
    Replace this with your actual OM2M client logic.
    """
    if not action_details:
        print("No action to execute.")
        return

    print(f"--- EXECUTING OM2M ACTION ---")
    print(f"  Action Details: {action_details}")

    device = action_details['device']
    action = action_details['action']
    value = action_details.get('value') # Might be None

    # Example: Construct target URI and payload based on action
    # YOU NEED TO DEFINE THESE URIS BASED ON YOUR OM2M RESOURCE STRUCTURE
    target_uri = None
    payload_con = None # Content for the content instance

    if device == 'led':
        target_uri = "/~/in-cse/in-name/led" # EXAMPLE URI
        payload_con = "ON" if action == 'activate' else "OFF"
    elif device == 'solenoid':
        target_uri = "/~/in-cse/in-name/solenoid" # EXAMPLE URI
        payload_con = "ON" if action == 'activate' else "OFF"
    elif device == 'fan':
        target_uri = "/~/in-cse/in-name/fan" # EXAMPLE URI
        if action == 'set_speed':
            payload_con = str(value) # Speed 1, 2, or 3
        elif action == 'deactivate':
            payload_con = "0" # Speed 0 for off

    if target_uri and payload_con is not None:
        print(f"  Target URI: {target_uri}")
        print(f"  Payload Content: {payload_con}")

        # Construct OM2M payload for creating a content instance
        om2m_payload = {
            "m2m:cin": {
                "con": payload_con
            }
        }
        om2m_headers = {
             "X-M2M-Origin": "admin:admin", # Or your application AE credentials
             "Content-Type": "application/json;ty=4" # ty=4 for content instance
        }
        # Build URL safely
        # Extract base URL from SERVER_URL
        base_url_parts = SERVER_URL.split('/')
        if len(base_url_parts) > 2:
             base_url = '/'.join(base_url_parts[:3])
        else:
             print(f"Error parsing SERVER_URL: {SERVER_URL}")
             base_url = "http://localhost:8080" # Fallback

        full_target_url = f"{base_url}{target_uri}"


        # Send POST request to OM2M
        try:
            print(f"  Sending POST to {full_target_url}")
            response = requests.post(full_target_url, auth=AUTH_CREDENTIALS, headers=om2m_headers, json=om2m_payload)
            print(f"  OM2M Response Status: {response.status_code} {'(Success)' if response.status_code in [200, 201] else ''}")
            print(f"  OM2M Response Body: {response.text[:200]}")  # Show first 200 chars of response

            # More detailed status reporting
            if response.status_code in [200, 201]:
                print(f"  ✅ OM2M Command Successful (Status {response.status_code})")
            else:
                print(f"  ⚠️ OM2M Command returned status {response.status_code}")

        except requests.exceptions.RequestException as e:
            print(f"  ❌ Error sending command to OM2M: {e}")
        except Exception as e:
            print(f"  ❌ Unexpected error during OM2M command execution: {e}")

    else:
        print("  Could not determine target URI or payload for the action.")

    print(f"--- END OM2M ACTION ---")
# --- Find and process only complete sessions ---
def find_complete_session(sessions):
    """Find the latest complete session that hasn't been processed yet."""
    global last_processed_session_id

    if not sessions:
        return None, None

    # Sort session IDs by numeric value (assuming session IDs are numeric)
    try:
        # Convert to int for sorting, handle potential non-numeric IDs gracefully
        sorted_session_ids = sorted(sessions.keys(), key=lambda sid: int(sid) if sid.isdigit() else float('-inf'), reverse=True)
    except ValueError:
        print("Warning: Non-numeric session IDs found during sorting attempt. Falling back to string sorting.")
        sorted_session_ids = sorted(sessions.keys(), reverse=True)


    # Find the first complete session that we haven't processed yet
    for session_id in sorted_session_ids:
        # Skip if we've already processed this session
        if session_id == last_processed_session_id:
            # print(f"Session {session_id} already processed. Skipping.") # Too noisy
            continue

        session_data = sessions[session_id]

        if is_session_complete(session_data):
            print(f"Found complete session: {session_id}")
            return session_id, session_data
        else:
            # print(f"Session {session_id} is incomplete. Skipping.") # Too noisy
            pass # Keep console cleaner

    return None, None

# --- Process data when it's new ---
def process_data_if_new(raw_data):
    """Process data only if it differs from the previously processed data and contains complete sessions."""
    global last_processed_hash, last_processed_session_id

    # Calculate hash of current data
    current_hash = calculate_data_hash(raw_data)

    # If this is the exact same data we processed last time, skip processing
    # Also skip if the last processed session ID matches the one that would be found now,
    # *unless* the data has changed but that specific session is still the latest complete one.
    # The hash check is the primary mechanism for detecting overall data change.
    if current_hash == last_processed_hash:
        # print("No new data detected (hash unchanged). Skipping processing.") # Too noisy
        return False

    print("New data detected. Processing...")
    # Extract audio entries from the JSON
    entries = parse_entries(raw_data)
    if not entries:
        print("No audio entries found after parsing.")
        # Update hash even if no entries, to avoid reprocessing the same empty/invalid response
        last_processed_hash = current_hash
        return False

    print(f"Found {len(entries)} audio entries.")

    # Group the entries by audio session
    sessions = group_audio_session(entries)
    if not sessions:
        print("No audio sessions found.")
        # Update hash even if no sessions, to avoid reprocessing the same response without sessions
        last_processed_hash = current_hash
        return False

    # Find a complete session to process
    session_id, session_data = find_complete_session(sessions)

    if not session_id or not session_data:
        # print("No new complete sessions found to process.") # Too noisy if polling incomplete data
        # Still update the hash to avoid reprocessing the same incomplete data state
        last_processed_hash = current_hash
        return False

    # Assemble the WAV file from the session data
    wav_bytes = assemble_wav_file(session_data)
    if wav_bytes is None:
        print(f"Failed to assemble WAV file from session {session_id} data.")
        # Do NOT update last_processed_hash or last_processed_session_id,
        # so we might try processing this session again if data changes slightly or becomes valid.
        return False

    # Save the assembled WAV file
    try:
        with open(OUTPUT_WAV_FILENAME, "wb") as f:
            f.write(wav_bytes)
        print(f"WAV file successfully saved as '{OUTPUT_WAV_FILENAME}' for session {session_id}. Size: {len(wav_bytes)} bytes.")
    except Exception as e:
        print(f"Error writing WAV file '{OUTPUT_WAV_FILENAME}': {e}")
         # Do NOT update last_processed_hash or last_processed_session_id
        return False

    # --- Process the saved WAV file for commands ---
    print(f"\n--- Starting AI Processing for Session {session_id} ---")
    action_to_execute = process_audio_command(OUTPUT_WAV_FILENAME)
    print("--- AI Processing Finished ---")

    # --- Execute OM2M Action ---
    if action_to_execute:
        execute_om2m_action(action_to_execute)
    else:
        print("No command recognized or action determined.")

    # Update the hash and session ID of the processed data ONLY if processing was successful
    last_processed_hash = current_hash
    last_processed_session_id = session_id
    print(f"Successfully processed session {session_id}")
    return True

# --- Main Execution ---
def main():
    # Load AI models once
    if not load_models():
        print("Exiting due to model loading failure.")
        return

    try:
        print(f"Starting polling loop. Will check for new data every {POLLING_INTERVAL} seconds.")
        print(f"Complete sessions only: {REQUIRE_COMPLETE_SESSIONS}")
        print(f"Using Whisper model '{WHISPER_MODEL_SIZE}' on {DEVICE}, forcing English transcription.")
        print(f"Using Sentence Transformer model '{SENTENCE_TRANSFORMER_MODEL}' for NLU with threshold {SIMILARITY_THRESHOLD}.")
        print("Press Ctrl+C to stop the script.")

        while True:
            print("\n" + "="*40)
            print(f"Polling at {time.strftime('%Y-%m-%d %H:%M:%S')}")

            # Fetch data from the OM2M server
            raw_data = fetch_om2m_audio_entries()
            # process_data_if_new handles checking if data is empty/same as last time
            process_data_if_new(raw_data)

            # Wait for the next polling interval
            # print(f"Waiting {POLLING_INTERVAL} seconds until next poll...") # Too noisy
            time.sleep(POLLING_INTERVAL)

    except KeyboardInterrupt:
        print("\nPolling loop stopped by user (Ctrl+C).")
    except Exception as e:
        print(f"Unexpected error in polling loop: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()