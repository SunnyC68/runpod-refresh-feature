# Start from RunPod community image with CUDA 12.8, Python 3.12, PyTorch 2.7.1
FROM ashleykleynhans/runpod-base:py312-cu128-torch271

# Performance environment variables (from official ComfyUI Dockerfile)
ENV DEBIAN_FRONTEND=noninteractive
ENV PIP_PREFER_BINARY=1
ENV PYTHONUNBUFFERED=1
ENV CMAKE_BUILD_PARALLEL_LEVEL=8

# Set the working directory
WORKDIR /app

# Install additional system dependencies needed for ComfyUI
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git \
        curl \
        wget \
        build-essential \
        cmake \
        pkg-config \
        libgl1-mesa-glx \
        libgl1 \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender1 \
        libgomp1 \
        libgoogle-perftools4 \
        libtcmalloc-minimal4 \
        ffmpeg \
        libavcodec-dev \
        libavformat-dev \
        libavutil-dev \
        libswscale-dev \
        libopencv-dev \
        python3-opencv \
        libopenblas-dev \
        liblapack-dev \
        libeigen3-dev \
        libatlas-base-dev \
        libjpeg-dev \
        libpng-dev \
        libtiff-dev \
        libwebp-dev \
        zlib1g-dev \
        liblcms2-dev \
        libfreetype6-dev \
        libfribidi-dev \
        libharfbuzz-dev \
        libjpeg-turbo8-dev \
        libopenjp2-7-dev \
        libimagequant-dev \
        libraqm-dev \
        libxcb1-dev \
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

# Install additional Python packages commonly needed by custom nodes
RUN uv pip install --no-cache-dir \
        numpy \
        scipy \
        scikit-image \
        scikit-learn \
        matplotlib \
        seaborn \
        opencv-python \
        opencv-contrib-python \
        Pillow \
        imageio \
        tqdm \
        requests \
        aiohttp \
        websockets \
        psutil \
        GPUtil \
        accelerate \
        diffusers \
        transformers \
        tokenizers \
        safetensors \
        omegaconf \
        pyyaml \
        einops \
        timm \
        open-clip-torch \
        clip-by-openai \
        ftfy \
        regex \
        sentencepiece \
        protobuf \
        && echo "Additional Python packages installation completed"

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