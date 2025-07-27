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

    # --- Load your workflow directly from this string (THE FIX) ---
    workflow_json_string = """
    {
      "1": {
        "inputs": {
          "image": "input_image.png"
        },
        "class_type": "LoadImage"
      },
      "2": {
        "inputs": {
          "preprocessor": "TilePreprocessor",
          "resolution": 512,
          "image": [
            "68",
            0
          ]
        },
        "class_type": "AIO_Preprocessor"
      },
      "3": {
        "inputs": {
          "strength": 0.4000000000000001,
          "start_percent": 0.010000000000000002,
          "end_percent": 0.5000000000000001,
          "positive": [
            "14",
            0
          ],
          "negative": [
            "9",
            0
          ],
          "control_net": [
            "4",
            0
          ],
          "image": [
            "2",
            0
          ],
          "vae": [
            "23",
            0
          ]
        },
        "class_type": "ControlNetApplyAdvanced"
      },
      "4": {
        "inputs": {
          "control_net_name": "FLUX.1-dev-ControlNet-Union-Pro-Shakker-Labs.safetensors"
        },
        "class_type": "ControlNetLoader"
      },
      "9": {
        "inputs": {
          "clip_l": "",
          "t5xxl": "",
          "guidance": 3.5,
          "clip": [
            "76",
            0
          ]
        },
        "class_type": "CLIPTextEncodeFlux"
      },
      "13": {
        "inputs": {
          "width": [
            "31",
            0
          ],
          "height": [
            "31",
            1
          ],
          "batch_size": 1
        },
        "class_type": "EmptySD3LatentImage"
      },
      "14": {
        "inputs": {
          "guidance": 3.5,
          "conditioning": [
            "30",
            0
          ]
        },
        "class_type": "FluxGuidance"
      },
      "23": {
        "inputs": {
          "vae_name": "ae.safetensors"
        },
        "class_type": "VAELoader"
      },
      "30": {
        "inputs": {
          "text": [
            "56",
            0
          ],
          "clip": [
            "76",
            0
          ]
        },
        "class_type": "CLIPTextEncode"
      },
      "31": {
        "inputs": {
          "image": [
            "68",
            0
          ]
        },
        "class_type": "GetImageSize+"
      },
      "35": {
        "inputs": {
          "sampler_name": "euler"
        },
        "class_type": "KSamplerSelect"
      },
      "37": {
        "inputs": {
          "samples": [
            "43",
            0
          ],
          "vae": [
            "23",
            0
          ]
        },
        "class_type": "VAEDecode"
      },
      "38": {
        "inputs": {
          "threshold": 1,
          "cfg": 1,
          "uncond_zero_scale": 0,
          "cfg_start_pct": 0,
          "model": [
            "63",
            0
          ],
          "positive": [
            "3",
            0
          ],
          "negative": [
            "3",
            1
          ]
        },
        "class_type": "AdaptiveGuidance"
      },
      "39": {
        "inputs": {
          "noise_seed": 46
        },
        "class_type": "RandomNoise"
      },
      "42": {
        "inputs": {
          "scheduler": "normal",
          "steps": 40,
          "denoise": 1,
          "model": [
            "63",
            0
          ]
        },
        "class_type": "BasicScheduler"
      },
      "43": {
        "inputs": {
          "noise": [
            "39",
            0
          ],
          "guider": [
            "38",
            0
          ],
          "sampler": [
            "35",
            0
          ],
          "sigmas": [
            "42",
            0
          ],
          "latent_image": [
            "13",
            0
          ]
        },
        "class_type": "SamplerCustomAdvanced"
      },
      "51": {
        "inputs": {
          "method": "mkl",
          "strength": 0.8000000000000002,
          "image_ref": [
            "68",
            0
          ],
          "image_target": [
            "37",
            0
          ]
        },
        "class_type": "ColorMatch"
      },
      "56": {
        "inputs": {
          "text": "A man with a thick beard, wearing a backward cap, open flannel shirt, and white tank top, stands next to a flip chart. The chart has bold black text reading "IT'S NOT," followed by "REAL ESTATE" in white letters on a red background. Below the text is a hand-drawn house, crossed out with a large red X, and a dashed arrow pointing away from it. His expression is mid-explanation, suggesting he's debunking the idea that real estate is the best investment. The background is a clean blue gradient, giving it a sharp, attention-grabbing look typical of YouTube thumbnails."
        },
        "class_type": "Textbox"
      },
      "63": {
        "inputs": {
          "model_path": "svdq-int4-flux.1-dev",
          "cache_threshold": 0,
          "attention": "nunchaku-fp16",
          "cpu_offload": "auto",
          "device_id": 0,
          "data_type": "bfloat16",
          "i2f_mode": "enabled"
        },
        "class_type": "NunchakuFluxDiTLoader"
      },
      "68": {
        "inputs": {
          "width": 1280,
          "height": 720,
          "upscale_method": "nearest-exact",
          "keep_proportion": "stretch",
          "pad_color": "0, 0, 0",
          "crop_position": "top",
          "divisible_by": 2,
          "device": "cpu",
          "image": [
            "1",
            0
          ]
        },
        "class_type": "ImageResizeKJv2"
      },
      "76": {
        "inputs": {
          "model_type": "flux.1",
          "text_encoder1": "clip_l.safetensors",
          "text_encoder2": "t5xxl_fp8_e4m3fn.safetensors",
          "t5_min_length": 512
        },
        "class_type": "NunchakuTextEncoderLoaderV2"
      },
      "81": {
        "inputs": {
          "model_name": "RealESRGAN_x8.pth"
        },
        "class_type": "UpscaleModelLoader"
      },
      "84": {
        "inputs": {
          "upscale_by": 1.0000000000000002,
          "rescale_method": "lanczos",
          "upscale_model": [
            "81",
            0
          ],
          "image": [
            "51",
            0
          ]
        },
        "class_type": "UpscaleImageByUsingModel"
      },
      "95": {
        "inputs": {
          "filename_prefix": "FormDez",
          "file_type": "WEBP (lossless)",
          "remove_metadata": true,
          "images": [
            "84",
            0
          ]
        },
        "class_type": "SaveImagePlus"
      }
    }
    """
    prompt = json.loads(workflow_json_string)

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
