import os
import subprocess
import threading
import time
import json
import uuid
import base64
import sys
from io import BytesIO
from PIL import Image

try:
    import runpod
    import requests
    import websocket
    print("✅ All imports successful")
except Exception as e:
    print(f"❌ Import error: {e}")
    import traceback
    traceback.print_exc()

# --- Configuration ---
COMFYUI_PORT = 8188
COMFYUI_URL = f"http://127.0.0.1:{COMFYUI_PORT}"
CLIENT_ID = str(uuid.uuid4())

print(f"🔧 Configuration: ComfyUI URL = {COMFYUI_URL}, Client ID = {CLIENT_ID}")
print(f"🐍 Python executable: {sys.executable}")

# --- Global variable to hold the ComfyUI server process ---
comfyui_process = None
comfyui_ready = False

# --- Function to start the ComfyUI server ---
def start_comfyui():
    global comfyui_process, comfyui_ready
    try:
        print("🚀 Starting ComfyUI server...")
        comfyui_path = "/app/ComfyUI/main.py"
        
        # Check if ComfyUI exists
        if not os.path.exists(comfyui_path):
            print(f"❌ ComfyUI not found at {comfyui_path}")
            print("📁 Contents of /app:")
            try:
                print(os.listdir("/app"))
            except:
                print("❌ Cannot list /app directory")
            return
            
        print(f"✅ Found ComfyUI at {comfyui_path}")
        
        # Use the same Python interpreter that's running this script
        args = [
            sys.executable, "-u", comfyui_path,
            "--port", str(COMFYUI_PORT),
            "--listen", "0.0.0.0",
            "--dont-print-server"
        ]
        
        print(f"🔧 ComfyUI command: {' '.join(args)}")
        comfyui_process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        print("🏁 ComfyUI process started, waiting for server...")
        
        # Wait until the server is ready
        max_attempts = 60  # 60 seconds timeout
        for attempt in range(max_attempts):
            try:
                if comfyui_process.poll() is not None:
                    stdout, stderr = comfyui_process.communicate()
                    print(f"❌ ComfyUI process exited early!")
                    print(f"📤 STDOUT: {stdout}")
                    print(f"📤 STDERR: {stderr}")
                    return
                
                response = requests.get(f"{COMFYUI_URL}/history/{CLIENT_ID}", timeout=5)
                if response.status_code == 200:
                    print("✅ ComfyUI server is ready!")
                    comfyui_ready = True
                    return
            except requests.exceptions.RequestException as e:
                print(f"⏳ Waiting for ComfyUI server... attempt {attempt + 1}/{max_attempts} ({e})")
                time.sleep(1)
        
        print("❌ ComfyUI server failed to start within 60 seconds")
        if comfyui_process.poll() is None:
            print("🔍 ComfyUI process still running but not responding")
        
    except Exception as e:
        print(f"❌ Error starting ComfyUI: {e}")
        import traceback
        traceback.print_exc()

# Start ComfyUI in a background thread
try:
    print("🧵 Starting ComfyUI thread...")
    threading.Thread(target=start_comfyui, daemon=True).start()
    print("✅ ComfyUI thread started")
except Exception as e:
    print(f"❌ Error starting ComfyUI thread: {e}")
    import traceback
    traceback.print_exc()

def get_image_data(filename, subfolder, folder_type):
    try:
        response = requests.get(f"{COMFYUI_URL}/view?{requests.compat.urlencode({'filename': filename, 'subfolder': subfolder, 'type': folder_type})}")
        return response.content
    except Exception as e:
        print(f"❌ Error getting image data: {e}")
        raise

def queue_prompt(prompt, client_id):
    try:
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
    except Exception as e:
        print(f"❌ Error in queue_prompt: {e}")
        raise

# --- The RunPod Handler ---
def handler(event):
    try:
        print("=== 🎯 Handler started ===")
        print(f"📨 Event received: {event}")
        
        # Check if ComfyUI is ready
        if not comfyui_ready:
            error_msg = "ComfyUI server is not ready. Please wait for initialization to complete."
            print(f"❌ {error_msg}")
            return {"error": error_msg}
        
        job_input = event.get("input", {})
        print(f"📋 Job input: {job_input}")

        # --- Load your workflow directly from this string ---
        print("📜 Loading workflow JSON...")
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
              "text": "A man with a thick beard, wearing a backward cap, open flannel shirt, and white tank top, stands next to a flip chart. The chart has bold black text reading IT'S NOT, followed by REAL ESTATE in white letters on a red background. Below the text is a hand-drawn house, crossed out with a large red X, and a dashed arrow pointing away from it. His expression is mid-explanation, suggesting he's debunking the idea that real estate is the best investment. The background is a clean blue gradient, giving it a sharp, attention-grabbing look typical of YouTube thumbnails."
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
        
        print("🔍 Parsing workflow JSON...")
        prompt = json.loads(workflow_json_string)
        print("✅ Workflow JSON parsed successfully")

        # --- Inject user inputs into the workflow ---
        # Update the prompt text in node 56
        prompt["56"]["inputs"]["text"] = job_input.get("prompt", "a default prompt")
        print(f"📝 Updated prompt: {prompt['56']['inputs']['text']}")
        
        # Update the seed in node 39
        prompt["39"]["inputs"]["noise_seed"] = job_input.get("seed", 12345)
        print(f"🎲 Updated seed: {prompt['39']['inputs']['noise_seed']}")
        
        # Handle the input image (sent as base64)
        if 'input_image' in job_input:
            print("🖼️ Processing input image...")
            try:
                image_data = base64.b64decode(job_input['input_image'])
                image = Image.open(BytesIO(image_data))
                
                # Ensure the input directory exists
                os.makedirs("/app/ComfyUI/input", exist_ok=True)
                
                # Save the image to the ComfyUI input directory
                input_path = "/app/ComfyUI/input/input_image.png"
                image.save(input_path)
                print(f"💾 Image saved to: {input_path}")
                
                # Update the LoadImage node (node 1) to use this file
                prompt["1"]["inputs"]["image"] = "input_image.png"
            except Exception as e:
                print(f"❌ Error processing input image: {e}")
                raise

        print("⏳ Waiting for ComfyUI to be ready...")
        # Wait a bit more for ComfyUI to be fully ready
        time.sleep(5)
        
        print("📤 Queueing prompt...")
        # --- Queue the job and get the prompt ID ---
        prompt_id = queue_prompt(prompt, CLIENT_ID)
        print(f"🆔 Prompt queued with ID: {prompt_id}")
        
        print("🔍 Fetching results...")
        # --- Fetch the final output image ---
        max_wait = 300  # 5 minutes timeout
        wait_time = 0
        while wait_time < max_wait:
            try:
                history_response = requests.get(f"{COMFYUI_URL}/history/{prompt_id}")
                if history_response.status_code == 200:
                    history_data = history_response.json()
                    if prompt_id in history_data:
                        history = history_data[prompt_id]
                        break
                print(f"⏳ Waiting for job completion... {wait_time}s")
                time.sleep(5)
                wait_time += 5
            except Exception as e:
                print(f"❌ Error checking history: {e}")
                time.sleep(5)
                wait_time += 5
        else:
            raise Exception(f"⏰ Job timed out after {max_wait} seconds")
        
        output_images = []
        for node_id, node_output in history['outputs'].items():
            if 'images' in node_output:
                for image in node_output['images']:
                    try:
                        image_data = get_image_data(image['filename'], image['subfolder'], image['type'])
                        encoded_image = base64.b64encode(image_data).decode('utf-8')
                        output_images.append(f"data:image/png;base64,{encoded_image}")
                    except Exception as e:
                        print(f"❌ Error processing output image: {e}")
                        continue
        
        print(f"✅ Generated {len(output_images)} output images")
        return {"images": output_images}
        
    except Exception as e:
        print(f"💥 === ERROR in handler ===")
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"error": str(e), "traceback": traceback.format_exc()}

# Test locally if run directly
if __name__ == "__main__":
    print("🧪 === Testing handler locally ===")
    test_event = {"input": {"prompt": "test prompt", "seed": 12345}}
    result = handler(test_event)
    print(f"📊 Result: {result}")
else:
    print("🚀 Starting RunPod serverless...")
    try:
        runpod.serverless.start({"handler": handler})
    except Exception as e:
        print(f"💥 CRITICAL ERROR starting RunPod serverless: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
