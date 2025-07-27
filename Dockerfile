# Start from a verified RunPod image with Python and GPU drivers
FROM runpod/pytorch:2.2.0-py3.10-cuda12.1.1-devel-ubuntu22.04

# Performance environment variables (from official ComfyUI Dockerfile)
ENV DEBIAN_FRONTEND=noninteractive
ENV PIP_PREFER_BINARY=1
ENV PYTHONUNBUFFERED=1
ENV CMAKE_BUILD_PARALLEL_LEVEL=8

# Set the working directory
WORKDIR /app

# Install essential tools and dependencies in one layer (better caching)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git \
        curl \
        wget \
        libgl1 \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender1 \
        ffmpeg \
        && apt-get autoremove -y \
        && apt-get clean -y \
        && rm -rf /var/lib/apt/lists/*

# Install uv for faster package management (from official ComfyUI Dockerfile)
RUN wget -qO- https://astral.sh/uv/install.sh | sh \
    && ln -s /root/.local/bin/uv /usr/local/bin/uv \
    && ln -s /root/.local/bin/uvx /usr/local/bin/uvx \
    && uv venv /opt/venv

# Use the virtual environment for all subsequent commands (like official)
ENV PATH="/opt/venv/bin:${PATH}"

# Clone the ComfyUI repository
RUN git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git

# Set the working directory to ComfyUI and install dependencies
WORKDIR /app/ComfyUI
RUN uv pip install --no-cache-dir -r requirements.txt

# Install ALL custom nodes in a single layer for better caching
RUN git clone --depth 1 https://github.com/Fannovel16/comfyui_controlnet_aux.git ./custom_nodes/comfyui_controlnet_aux && \
    git clone --depth 1 https://github.com/asagi4/comfyui-adaptive-guidance.git ./custom_nodes/comfyui-adaptive-guidance && \
    git clone --depth 1 https://github.com/cubiq/ComfyUI_essentials.git ./custom_nodes/ComfyUI_essentials && \
    git clone --depth 1 https://github.com/kijai/ComfyUI-KJNodes.git ./custom_nodes/ComfyUI-KJNodes && \
    git clone --depth 1 https://github.com/chibiace/ComfyUI-Chibi-Nodes.git ./custom_nodes/ComfyUI-Chibi-Nodes && \
    git clone --depth 1 https://github.com/TheBill2001/comfyui-upscale-by-model.git ./custom_nodes/comfyui-upscale-by-model && \
    git clone --depth 1 https://github.com/Goktug/comfyui-saveimage-plus.git ./custom_nodes/Save-Image-Plus && \
    git clone --depth 1 https://github.com/Ltamann/ComfyUI-TBG-ETUR.git ./custom_nodes/ComfyUI-TBG-ETUR

# Install dependencies for custom nodes with better error handling using uv
RUN find ./custom_nodes -name "requirements.txt" -print0 | \
    xargs -0 -I {} sh -c 'echo "Installing requirements from: {}" && uv pip install --no-cache-dir -r "{}"' && \
    echo "Custom node dependencies installation completed"

# Create necessary directories
RUN mkdir -p input output temp

# Go back to app root for handler installation
WORKDIR /app

# Copy handler requirements and install with uv (better caching)
COPY handler_requirements.txt ./
RUN uv pip install --no-cache-dir -r handler_requirements.txt

# Copy the enhanced serverless handler (this should be last as it changes most frequently)
COPY handler.py ./

# Health check endpoint for better monitoring (like official)
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8188/queue || exit 1

# For serverless, the handler manages ComfyUI startup internally
CMD ["python", "-u", "handler.py"] 