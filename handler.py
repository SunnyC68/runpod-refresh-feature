import os
import subprocess
import threading
import time
import json
import uuid
import base64
from io import BytesIO
from PIL import Image

print("Starting handler.py - imports successful")

try:
    import runpod
    print("RunPod import successful")
except Exception as e:
    print(f"RunPod import failed: {e}")

try:
    import requests
    print("Requests import successful")
except Exception as e:
    print(f"Requests import failed: {e}")

try:
    import websocket
    print("Websocket import successful")
except Exception as e:
    print(f"Websocket import failed: {e}")

# --- Configuration ---
COMFYUI_PORT = 8188
COMFYUI_URL = f"http://127.0.0.1:{COMFYUI_PORT}"
CLIENT_ID = str(uuid.uuid4())

print(f"Configuration set - ComfyUI URL: {COMFYUI_URL}, Client ID: {CLIENT_ID}")

# --- Global variable to hold the ComfyUI server process ---
comfyui_process = None

# --- Function to start the ComfyUI server ---
def start_comfyui():
    print("start_comfyui function called")
    global comfyui_process
    comfyui_path = "/app/ComfyUI/main.py"
    
    print(f"Checking if ComfyUI path exists: {comfyui_path}")
    if not os.path.exists(comfyui_path):
        print(f"ERROR: ComfyUI path does not exist: {comfyui_path}")
        return
    
    # IMPORTANT: These paths now point to /workspace to match the volume mount path.
    args = [
        "python", "-u", comfyui_path,
        "--port", str(COMFYUI_PORT),
        "--listen", "0.0.0.0",
        "--dont-print-server",
        "--checkpoints-dir", "/workspace/ComfyUI/models/checkpoints",
        "--controlnet-dir", "/workspace/ComfyUI/models/controlnet",
        "--vae-dir", "/workspace/ComfyUI/models/vae",
        "--lora-dir", "/workspace/ComfyUI/models/loras",
        "--upscale-models-dir", "/workspace/ComfyUI/models/upscale_models"
    ]
    
    print(f"Starting ComfyUI with args: {args}")
    try:
        comfyui_process = subprocess.Popen(args)
        print("ComfyUI process started successfully")
    except Exception as e:
        print(f"ERROR starting ComfyUI process: {e}")
        return
    
    print("ComfyUI server starting...")
    
    # Wait until the server is ready
    max_attempts = 30
    attempts = 0
    while attempts < max_attempts:
        try:
            print(f"Attempt {attempts + 1}: Checking if ComfyUI is ready...")
            response = requests.get(f"{COMFYUI_URL}/history/{CLIENT_ID}", timeout=5)
            print(f"ComfyUI responded with status: {response.status_code}")
            print("ComfyUI server is ready.")
            break
        except requests.exceptions.RequestException as e:
            print(f"ComfyUI not ready yet: {e}")
            attempts += 1
            time.sleep(2)
    
    if attempts >= max_attempts:
        print("ERROR: ComfyUI failed to start within timeout period")

print("About to start ComfyUI in background thread...")
# Start ComfyUI in a background thread
try:
    threading.Thread(target=start_comfyui, daemon=True).start()
    print("ComfyUI thread started successfully")
except Exception as e:
    print(f"ERROR starting ComfyUI thread: {e}")

def get_image_data(filename, subfolder, folder_type):
    response = requests.get(f"{COMFYUI_URL}/view?{requests.compat.urlencode({'filename': filename, 'subfolder': subfolder, 'type': folder_type})}")
    return response.content

def queue_prompt(prompt, client_id):
    ws = websocket.WebSocket()
    ws.connect(f"ws://{COMFYUI_URL.split('//')[1]}/ws?clientId={client_id}")
    
    prompt_id = str(uuid.uuid4())
    prompt["prompt_id"] = prompt_id
    
    ws.send(json.dumps({"prompt": prompt, "client_id": client_id}))
    
    while True:
        out = ws.recv()
        if isinstance(out, str):
            message = json.loads(out)
            if message['type'] == 'executing' and message['data']['node'] is None and message['data']['prompt_id'] == prompt_id:
                ws.close()
                return prompt_id # Execution is done
        else: # Handle binary data (less common for this part)
            continue


# --- SIMPLIFIED TEST HANDLER ---
def handler(event):
    print("=== HANDLER CALLED ===")
    print(f"Event received: {event}")
    
    # Just return a simple test response for now
    return {
        "status": "success", 
        "message": "Handler is working!", 
        "event": event,
        "comfyui_process_running": comfyui_process is not None and comfyui_process.poll() is None
    }

print("About to start RunPod serverless...")
try:
    runpod.serverless.start({"handler": handler})
    print("RunPod serverless started successfully")
except Exception as e:
    print(f"ERROR starting RunPod serverless: {e}")
    import traceback
    print(f"Full traceback: {traceback.format_exc()}")
