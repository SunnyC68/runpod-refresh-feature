import os
import subprocess
import threading
import time
import json
import uuid
import base64
from io import BytesIO
from PIL import Image

import runpod
import requests
import websocket

# --- Configuration ---
COMFYUI_PORT = 8188
COMFYUI_URL = f"http://127.0.0.1:{COMFYUI_PORT}"
CLIENT_ID = str(uuid.uuid4())

# --- Global variable to hold the ComfyUI server process ---
comfyui_process = None

# --- Function to start the ComfyUI server ---
def start_comfyui():
    global comfyui_process
    comfyui_path = "/app/ComfyUI/main.py"
    
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
    
    comfyui_process = subprocess.Popen(args)
    print("ComfyUI server starting...")
    
    # Wait until the server is ready
    while True:
        try:
            requests.get(f"{COMFYUI_URL}/history/{CLIENT_ID}", timeout=5)
            print("ComfyUI server is ready.")
            break
        except requests.exceptions.RequestException:
            time.sleep(1)

# Start ComfyUI in a background thread
threading.Thread(target=start_comfyui, daemon=True).start()

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


# --- The RunPod Handler ---
def handler(event):
    job_input = event.get("input", {})

    # --- Load your workflow ---
    with open("FluxControlNetTileSame_api (1).json", 'r') as f:
        prompt = json.load(f)

    # --- Inject user inputs into the workflow ---
    # Update the prompt text in node 56
    prompt["56"]["inputs"]["text"] = job_input.get("prompt", "a default prompt")
    
    # Update the seed in node 39
    prompt["39"]["inputs"]["noise_seed"] = job_input.get("seed", 12345)
    
    # Handle the input image (sent as base64)
    if 'input_image' in job_input:
        image_data = base64.b64decode(job_input['input_image'])
        image = Image.open(BytesIO(image_data))
        
        # Save the image to the ComfyUI input directory
        input_path = "/app/ComfyUI/input/input_image.png"
        image.save(input_path)
        
        # Update the LoadImage node (node 1) to use this file
        prompt["1"]["inputs"]["image"] = "input_image.png"

    # --- Queue the job and get the prompt ID ---
    prompt_id = queue_prompt(prompt, CLIENT_ID)
    
    # --- Fetch the final output image ---
    history = requests.get(f"{COMFYUI_URL}/history/{prompt_id}").json()[prompt_id]
    
    output_images = []
    for node_id, node_output in history['outputs'].items():
        if 'images' in node_output:
            for image in node_output['images']:
                image_data = get_image_data(image['filename'], image['subfolder'], image['type'])
                encoded_image = base64.b64encode(image_data).decode('utf-8')
                output_images.append(f"data:image/png;base64,{encoded_image}")
                
    return {"images": output_images}

runpod.serverless.start({"handler": handler})
