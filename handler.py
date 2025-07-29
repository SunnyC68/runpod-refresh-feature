import os
import json
import uuid
import base64
import time
import subprocess
import socket
import traceback
from io import BytesIO
from PIL import Image

try:
    import runpod
    import requests
    import websocket
    print("✅ All imports successful")
except Exception as e:
    print(f"❌ Import error: {e}")
    exit(1)

# Configuration with environment variable support (like official handler)
COMFYUI_HOST = "127.0.0.1:8188"
COMFYUI_URL = f"http://{COMFYUI_HOST}"

# Timeouts and retry configuration (inspired by official handler)
SERVER_CHECK_TIMEOUT = 3
WEBSOCKET_TIMEOUT = 10
MAX_EXECUTION_TIME = 120
COMFYUI_STARTUP_TIMEOUT = 1000 # Increased timeout to 3 minutes

# WebSocket reconnection settings (from official handler)
WEBSOCKET_RECONNECT_ATTEMPTS = int(os.environ.get("WEBSOCKET_RECONNECT_ATTEMPTS", 5))
WEBSOCKET_RECONNECT_DELAY_S = int(os.environ.get("WEBSOCKET_RECONNECT_DELAY_S", 3))

# Enable websocket trace logs for debugging (from official handler)
if os.environ.get("WEBSOCKET_TRACE", "false").lower() == "true":
    websocket.enableTrace(True)

# Worker refresh setting (from official handler)
REFRESH_WORKER = os.environ.get("REFRESH_WORKER", "false").lower() == "true"

# Global variables for ComfyUI process management
comfyui_process = None
comfyui_ready = False

print(f"handler-saas - Serverless Config: ComfyUI at {COMFYUI_URL}")
print(f"handler-saas - WebSocket reconnect attempts: {WEBSOCKET_RECONNECT_ATTEMPTS}")
print(f"handler-saas - Worker refresh enabled: {REFRESH_WORKER}")

def _comfy_server_status():
    """Return detailed server health info (from official handler)"""
    try:
        resp = requests.get(f"{COMFYUI_URL}/", timeout=5)
        return {
            "reachable": resp.status_code == 200,
            "status_code": resp.status_code,
        }
    except Exception as exc:
        return {"reachable": False, "error": str(exc)}

def _attempt_websocket_reconnect(ws_url, max_attempts, delay_s, initial_error):
    """
    Advanced websocket reconnection logic (adapted from official handler)
    """
    print(f"handler-saas - WebSocket connection closed: {initial_error}. Attempting to reconnect...")
    
    last_reconnect_error = initial_error
    for attempt in range(max_attempts):
        # Check ComfyUI server health before reconnect attempt
        srv_status = _comfy_server_status()
        if not srv_status["reachable"]:
            print(f"handler-saas - ComfyUI HTTP unreachable – aborting websocket reconnect: {srv_status.get('error', 'status '+str(srv_status.get('status_code')))}")
            raise websocket.WebSocketConnectionClosedException("ComfyUI HTTP unreachable during websocket reconnect")

        print(f"handler-saas - Reconnect attempt {attempt + 1}/{max_attempts}... (ComfyUI HTTP reachable, status {srv_status.get('status_code')})")
        
        try:
            new_ws = websocket.WebSocket()
            new_ws.connect(ws_url, timeout=10)
            print(f"handler-saas - WebSocket reconnected successfully")
            return new_ws
        except (websocket.WebSocketException, ConnectionRefusedError, socket.timeout, OSError) as reconn_err:
            last_reconnect_error = reconn_err
            print(f"handler-saas - Reconnect attempt {attempt + 1} failed: {reconn_err}")
            if attempt < max_attempts - 1:
                print(f"handler-saas - Waiting {delay_s} seconds before next attempt...")
                time.sleep(delay_s)
            else:
                print(f"handler-saas - Max reconnection attempts reached")

    print("handler-saas - Failed to reconnect websocket after connection closed")
    raise websocket.WebSocketConnectionClosedException(f"Connection closed and failed to reconnect. Last error: {last_reconnect_error}")

def start_comfyui():
    """Start ComfyUI with better error handling and a more patient wait."""
    global comfyui_process, comfyui_ready
    
    if comfyui_process and comfyui_process.poll() is None:
        print("handler-saas - ComfyUI already running")
        return True
    
    print("handler-saas - Starting ComfyUI for serverless...")
    
    try:
        cmd = [
            "python", "/app/ComfyUI/main.py",
            "--port", "8188",
            "--listen", "0.0.0.0",
            "--dont-print-server",
            "--disable-auto-launch",
            "--cpu-vae",
            "--normalvram"
        ]
        
        comfyui_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True, # Use text mode for easier log handling
            cwd="/app/ComfyUI"
        )
        
        print(f"handler-saas - ComfyUI started with PID: {comfyui_process.pid}")
        
        # Patiently wait for ComfyUI to be ready
        start_time = time.time()
        while time.time() - start_time < COMFYUI_STARTUP_TIMEOUT:
            if comfyui_process.poll() is not None:
                # Process has terminated, read logs to find out why
                stdout, stderr = comfyui_process.communicate()
                print(f"handler-saas - ComfyUI process terminated unexpectedly.")
                print(f"handler-saas - STDOUT: {stdout}")
                print(f"handler-saas - STDERR: {stderr}")
                return False
            
            srv_status = _comfy_server_status()
            if srv_status["reachable"]:
                comfyui_ready = True
                print(f"handler-saas - ComfyUI is ready! (took {time.time() - start_time:.2f} seconds)")
                return True
            
            # Print a waiting message every 10 seconds
            if int(time.time() - start_time) % 10 == 0:
                 print(f"handler-saas - Waiting for ComfyUI to be ready... ({int(time.time() - start_time)}s elapsed)")

            time.sleep(1)
        
        # If loop finishes, it's a timeout
        print(f"handler-saas - ComfyUI failed to start within the {COMFYUI_STARTUP_TIMEOUT} second timeout.")
        comfyui_process.terminate() # Ensure the zombie process is killed
        stdout, stderr = comfyui_process.communicate()
        print(f"handler-saas - ComfyUI process terminated.")
        print(f"handler-saas - STDOUT on timeout: {stdout}")
        print(f"handler-saas - STDERR on timeout: {stderr}")
        return False
        
    except Exception as e:
        print(f"handler-saas - Failed to start ComfyUI: {e}")
        print(traceback.format_exc())
        return False

def check_comfyui_ready():
    """Enhanced health check with server diagnostics"""
    global comfyui_ready
    
    if not comfyui_ready:
        return start_comfyui()
    
    srv_status = _comfy_server_status()
    if srv_status["reachable"]:
        return True
    else:
        print(f"handler-saas - ComfyUI health check failed: {srv_status}")
        comfyui_ready = False
        return start_comfyui()

def validate_saas_input(job_input):
    """Input validation with better error messages"""
    if not job_input:
        return None, "Missing input data"
    
    if "input_image" not in job_input:
        return None, "Missing required 'input_image' field"
    
    if "prompt" not in job_input or not job_input["prompt"].strip():
        return None, "Missing required 'prompt' text or prompt is empty"
    
    # Validate image data format (like official handler)
    input_image = job_input["input_image"]
    if isinstance(input_image, str):
        # Handle data URI prefix (like official handler)
        if "," in input_image:
            try:
                base64_data = input_image.split(",", 1)[1]
                base64.b64decode(base64_data)  # Validate base64
            except Exception as e:
                return None, f"Invalid base64 image data: {e}"
        else:
            try:
                base64.b64decode(input_image)  # Validate base64
            except Exception as e:
                return None, f"Invalid base64 image data: {e}"
    else:
        return None, "input_image must be a base64 string"
    
    seed = job_input.get("seed", int(time.time()) % 1000000)
    
    return {
        "input_image": job_input["input_image"],
        "prompt": job_input["prompt"],
        "seed": seed
    }, None

def prepare_fixed_workflow(input_image_filename, prompt_text, seed):
    """Generate your fixed workflow with user inputs injected"""
    
    workflow = {
        "1": {
            "inputs": {"image": input_image_filename},
            "class_type": "LoadImage"
        },
        "2": {
            "inputs": {
                "preprocessor": "TilePreprocessor",
                "resolution": 512,
                "image": ["68", 0]
            },
            "class_type": "AIO_Preprocessor"
        },
        "3": {
            "inputs": {
                "strength": 0.4,
                "start_percent": 0.01,
                "end_percent": 0.5,
                "positive": ["14", 0],
                "negative": ["9", 0],
                "control_net": ["4", 0],
                "image": ["2", 0],
                "vae": ["23", 0]
            },
            "class_type": "ControlNetApplyAdvanced"
        },
        "4": {
            "inputs": {"control_net_name": "FLUX.1-dev-ControlNet-Union-Pro-Shakker-Labs.safetensors"},
            "class_type": "ControlNetLoader"
        },
        "9": {
            "inputs": {
                "clip_l": "",
                "t5xxl": "",
                "guidance": 3.5,
                "clip": ["76", 0]
            },
            "class_type": "CLIPTextEncodeFlux"
        },
        "13": {
            "inputs": {
                "width": ["31", 0],
                "height": ["31", 1],
                "batch_size": 1
            },
            "class_type": "EmptySD3LatentImage"
        },
        "14": {
            "inputs": {
                "guidance": 3.5,
                "conditioning": ["30", 0]
            },
            "class_type": "FluxGuidance"
        },
        "23": {
            "inputs": {"vae_name": "ae.safetensors"},
            "class_type": "VAELoader"
        },
        "30": {
            "inputs": {
                "text": ["56", 0],
                "clip": ["76", 0]
            },
            "class_type": "CLIPTextEncode"
        },
        "31": {
            "inputs": {"image": ["68", 0]},
            "class_type": "GetImageSize+"
        },
        "35": {
            "inputs": {"sampler_name": "euler"},
            "class_type": "KSamplerSelect"
        },
        "37": {
            "inputs": {
                "samples": ["43", 0],
                "vae": ["23", 0]
            },
            "class_type": "VAEDecode"
        },
        "38": {
            "inputs": {
                "threshold": 1,
                "cfg": 1,
                "uncond_zero_scale": 0,
                "cfg_start_pct": 0,
                "model": ["63", 0],
                "positive": ["3", 0],
                "negative": ["3", 1]
            },
            "class_type": "AdaptiveGuidance"
        },
        "39": {
            "inputs": {"noise_seed": seed},
            "class_type": "RandomNoise"
        },
        "42": {
            "inputs": {
                "scheduler": "normal",
                "steps": 40,
                "denoise": 1,
                "model": ["63", 0]
            },
            "class_type": "BasicScheduler"
        },
        "43": {
            "inputs": {
                "noise": ["39", 0],
                "guider": ["38", 0],
                "sampler": ["35", 0],
                "sigmas": ["42", 0],
                "latent_image": ["13", 0]
            },
            "class_type": "SamplerCustomAdvanced"
        },
        "51": {
            "inputs": {
                "method": "mkl",
                "strength": 0.8,
                "image_ref": ["68", 0],
                "image_target": ["37", 0]
            },
            "class_type": "ColorMatch"
        },
        "56": {
            "inputs": {"text": prompt_text},
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
                "image": ["1", 0]
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
            "inputs": {"model_name": "RealESRGAN_x8.pth"},
            "class_type": "UpscaleModelLoader"
        },
        "84": {
            "inputs": {
                "upscale_by": 1.0,
                "rescale_method": "lanczos",
                "upscale_model": ["81", 0],
                "image": ["51", 0]
            },
            "class_type": "UpscaleImageByUsingModel"
        },
        "95": {
            "inputs": {
                "filename_prefix": "saas_output",
                "file_type": "WEBP (lossless)",
                "remove_metadata": True,
                "images": ["84", 0]
            },
            "class_type": "SaveImagePlus"
        }
    }
    
    return workflow

def save_input_image(image_b64, filename="input_image.jpg"):
    """Save input image with better error handling"""
    try:
        # Handle data URI prefix (like official handler)
        if "," in image_b64:
            image_b64 = image_b64.split(",", 1)[1]
        
        image_data = base64.b64decode(image_b64)
        image = Image.open(BytesIO(image_data))
        
        os.makedirs("/app/ComfyUI/input", exist_ok=True)
        
        input_path = f"/app/ComfyUI/input/{filename}"
        image.save(input_path, optimize=True)
        print(f"handler-saas - Input image saved: {filename}")
        
        return filename
    except base64.binascii.Error as e:
        raise ValueError(f"Invalid base64 image data: {e}")
    except Exception as e:
        raise ValueError(f"Failed to process input image: {e}")

def execute_workflow_fast_fail(workflow, max_wait_time=MAX_EXECUTION_TIME):
    """Execute workflow with advanced websocket handling"""
    client_id = str(uuid.uuid4())
    ws = None
    
    try:
        ws_url = f"ws://{COMFYUI_HOST}/ws?clientId={client_id}"
        ws = websocket.WebSocket()
        ws.settimeout(WEBSOCKET_TIMEOUT)
        ws.connect(ws_url)
        print(f"handler-saas - WebSocket connected: {client_id}")
        
        payload = {"prompt": workflow, "client_id": client_id}
        response = requests.post(f"{COMFYUI_URL}/prompt", json=payload, timeout=SERVER_CHECK_TIMEOUT)
        
        if response.status_code != 200:
            raise ValueError(f"Failed to queue workflow: {response.text}")
        
        result = response.json()
        prompt_id = result.get("prompt_id")
        if not prompt_id:
            raise ValueError("No prompt_id returned from ComfyUI")
        
        print(f"handler-saas - Workflow queued: {prompt_id}")
        
        start_time = time.time()
        execution_complete = False
        
        while time.time() - start_time < max_wait_time:
            try:
                message = ws.recv()
                if isinstance(message, str):
                    data = json.loads(message)
                    
                    if (data.get("type") == "executing" and 
                        data.get("data", {}).get("node") is None and
                        data.get("data", {}).get("prompt_id") == prompt_id):
                        execution_complete = True
                        print(f"handler-saas - Execution complete: {prompt_id}")
                        break
                    
                    elif (data.get("type") == "execution_error" and 
                          data.get("data", {}).get("prompt_id") == prompt_id):
                        error_data = data.get("data", {})
                        raise ValueError(
                            f"Workflow failed at node {error_data.get('node_id')}: "
                            f"{error_data.get('exception_message', 'Unknown error')}"
                        )
                        
            except websocket.WebSocketTimeoutException:
                continue
            except websocket.WebSocketConnectionClosedException as closed_err:
                # Use advanced reconnection logic (from official handler)
                ws = _attempt_websocket_reconnect(
                    ws_url, WEBSOCKET_RECONNECT_ATTEMPTS, 
                    WEBSOCKET_RECONNECT_DELAY_S, closed_err
                )
                continue
            except json.JSONDecodeError:
                print(f"handler-saas - Received invalid JSON message")
                continue
        
        if not execution_complete:
            raise ValueError(f"Workflow timed out after {max_wait_time} seconds")
        
        return prompt_id
    
    finally:
        # Proper cleanup (like official handler)
        if ws and ws.connected:
            try:
                print(f"handler-saas - Closing websocket connection")
                ws.close()
            except:
                pass

def get_final_image(prompt_id):
    """Get final image with better error handling"""
    try:
        response = requests.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=SERVER_CHECK_TIMEOUT)
        response.raise_for_status()
        history = response.json()
        
        if prompt_id not in history:
            raise ValueError("Workflow results not found in history")
        
        outputs = history[prompt_id].get("outputs", {})
        if "95" not in outputs or "images" not in outputs["95"]:
            raise ValueError("Final upscaled image not found in outputs")
        
        image_info = outputs["95"]["images"][0]
        filename = image_info["filename"]
        subfolder = image_info.get("subfolder", "")
        
        params = {
            "filename": filename,
            "subfolder": subfolder,
            "type": image_info.get("type", "output")
        }
        
        response = requests.get(f"{COMFYUI_URL}/view", params=params, timeout=30)
        response.raise_for_status()
        
        print(f"handler-saas - Retrieved final image: {filename}")
        return response.content, filename
    
    except requests.RequestException as e:
        raise ValueError(f"HTTP error retrieving image: {e}")
    except Exception as e:
        raise ValueError(f"Failed to retrieve final image: {e}")

def handler(event):
    """Enhanced handler with comprehensive error handling (like official handler)"""
    job_start_time = time.time()
    
    try:
        print("=== handler-saas - Serverless ComfyUI Handler Started ===")
        
        # Enhanced input validation
        job_input = event.get("input", {})
        validated_data, error = validate_saas_input(job_input)
        if error:
            return {"error": error, "processing_time": 0}
        
        input_image_b64 = validated_data["input_image"]
        prompt_text = validated_data["prompt"]
        seed = validated_data["seed"]
        
        print(f"handler-saas - Processing: prompt='{prompt_text[:50]}...', seed={seed}")
        
        # Enhanced ComfyUI health check
        if not check_comfyui_ready():
            return {
                "error": "Service temporarily unavailable - please try again",
                "processing_time": time.time() - job_start_time
            }
        
        # Save input image
        input_filename = save_input_image(input_image_b64)
        
        # Generate workflow with user inputs
        workflow = prepare_fixed_workflow(input_filename, prompt_text, seed)
        
        # Execute workflow with advanced error handling
        prompt_id = execute_workflow_fast_fail(workflow)
        
        # Get final result
        image_bytes, output_filename = get_final_image(prompt_id)
        
        processing_time = time.time() - job_start_time
        
        # Return image data to your app
        image_b64 = base64.b64encode(image_bytes).decode('utf-8')
        
        print(f"handler-saas - Generated image in {processing_time:.1f}s, returning to your app")
        
        return {
            "success": True,
            "image_data": f"data:image/webp;base64,{image_b64}",
            "filename": output_filename,
            "processing_time": round(processing_time, 1),
            "seed_used": seed,
            "file_size_bytes": len(image_bytes),
            "format": "webp"
        }
    
    # Comprehensive error handling (like official handler)
    except websocket.WebSocketException as e:
        processing_time = time.time() - job_start_time
        print(f"handler-saas - WebSocket Error: {e}")
        print(traceback.format_exc())
        return {
            "error": f"WebSocket communication error: {e}",
            "processing_time": round(processing_time, 1)
        }
    except requests.RequestException as e:
        processing_time = time.time() - job_start_time
        print(f"handler-saas - HTTP Request Error: {e}")
        print(traceback.format_exc())
        return {
            "error": f"HTTP communication error with ComfyUI: {e}",
            "processing_time": round(processing_time, 1)
        }
    except ValueError as e:
        processing_time = time.time() - job_start_time
        print(f"handler-saas - Value Error: {e}")
        print(traceback.format_exc())
        return {
            "error": str(e),
            "processing_time": round(processing_time, 1)
        }
    except Exception as e:
        processing_time = time.time() - job_start_time
        print(f"handler-saas - Unexpected Handler Error: {e}")
        print(traceback.format_exc())
        return {
            "error": "An unexpected error occurred",
            "processing_time": round(processing_time, 1)
        }

if __name__ == "__main__":
    print("handler-saas - Starting serverless SaaS handler...")
    runpod.serverless.start({"handler": handler}) 