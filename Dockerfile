# Start from a verified RunPod image with Python and GPU drivers
FROM runpod/pytorch:2.2.0-py3.10-cuda12.1.1-devel-ubuntu22.04

# Set the working directory
WORKDIR /app

# Install essential tools and clear the cache
RUN apt-get update && apt-get install -y git && apt-get clean && rm -rf /var/lib/apt/lists/*

# Clone the ComfyUI repository
RUN git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git

# Set the working directory to ComfyUI
WORKDIR /app/ComfyUI

# Install ComfyUI's Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# --- Install ALL 8 Custom Nodes (with corrected link and --depth 1 for speed) ---
RUN git clone --depth 1 https://github.com/Fannovel16/comfyui_controlnet_aux.git ./custom_nodes/comfyui_controlnet_aux
RUN git clone --depth 1 https://github.com/asagi4/comfyui-adaptive-guidance.git ./custom_nodes/comfyui-adaptive-guidance
RUN git clone --depth 1 https://github.com/cubiq/ComfyUI_essentials.git ./custom_nodes/ComfyUI_essentials
RUN git clone --depth 1 https://github.com/kijai/ComfyUI-KJNodes.git ./custom_nodes/ComfyUI-KJNodes
RUN git clone --depth 1 https://github.com/chibiace/ComfyUI-Chibi-Nodes.git ./custom_nodes/ComfyUI-Chibi-Nodes
RUN git clone --depth 1 https://github.com/TheBill2001/comfyui-upscale-by-model.git ./custom_nodes/comfyui-upscale-by-model
# --- THIS IS THE FINAL CORRECTED LINE ---
RUN git clone --depth 1 https://github.com/Goktug/comfyui-saveimage-plus.git ./custom_nodes/Save-Image-Plus
RUN git clone --depth 1 https://github.com/ltamann/TBG_Enhanced_Tiled_Upscaler_and_Refiner.git ./custom_nodes/TBG_Enhanced_Tiled_Upscaler_and_Refiner

# Go back to the root directory for the handler
WORKDIR /app

# Install the Python libraries needed for our handler.py script
COPY handler_requirements.txt .
RUN pip install --no-cache-dir -r handler_requirements.txt

# Copy the handler script into the container
COPY handler.py .

# Set the command to run the handler when the worker starts
CMD ["python", "-u", "/app/handler.py"]
