# Start from a RunPod image with the necessary GPU drivers (CUDA 12)
FROM runpod/pytorch:2.3.0-py3.11-cuda12.1.1-devel-ubuntu22.04

# Set the working directory
WORKDIR /app

# Install essential tools and clear the cache
RUN apt-get update && apt-get install -y git && apt-get clean && rm -rf /var/lib/apt/lists/*

# Clone the ComfyUI repository
RUN git clone https://github.com/comfyanonymous/ComfyUI.git

# Set the working directory to ComfyUI
WORKDIR /app/ComfyUI

# Install ComfyUI's Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# --- Install ALL 8 Custom Nodes from Your Screenshot ---
RUN git clone https://github.com/Fannovel16/comfyui_controlnet_aux.git ./custom_nodes/comfyui_controlnet_aux
RUN git clone https://github.com/asagi4/comfyui-adaptive-guidance.git ./custom_nodes/comfyui-adaptive-guidance
RUN git clone https://github.com/cubiq/ComfyUI_essentials.git ./custom_nodes/ComfyUI_essentials
RUN git clone https://github.com/kijai/ComfyUI-KJNodes.git ./custom_nodes/ComfyUI-KJNodes
RUN git clone https://github.com/chibiace/ComfyUI-Chibi-Nodes.git ./custom_nodes/ComfyUI-Chibi-Nodes
RUN git clone https://github.com/TheBill2001/comfyui-upscale-by-model.git ./custom_nodes/comfyui-upscale-by-model
RUN git clone https://github.com/goktug99/ComfyUI-SaveImage-Plus.git ./custom_nodes/ComfyUI-SaveImage-Plus
RUN git clone https://github.com/ltamann/TBG_Enhanced_Tiled_Upscaler_and_Refiner.git ./custom_nodes/TBG_Enhanced_Tiled_Upscaler_and_Refiner

# Go back to the root directory for the handler
WORKDIR /app

# Install the Python libraries needed for our handler.py script
COPY handler_requirements.txt .
RUN pip install --no-cache-dir -r handler_requirements.txt

# Copy the handler script into the container
COPY handler.py .

# Set the command to run the handler when the worker starts
CMD ["python", "-u", "/app/handler.py"]
