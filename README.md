# 1MG Product Image Studio 🖼️

An automated web tool and CLI utility that scrapes product images from **Tata 1mg**, automatically bypasses dynamic CDN watermarks (`l_watermark_xxx`), segments the foreground subjects, and composites them onto a clean solid white background (`#FFFFFF`) or transparent PNG.

---

## ✨ Features

- **Dynamic Watermark Bypass:** Strips 1mg's on-the-fly Gumlet watermark parameters directly at the CDN layer to fetch the original, uncompressed, high-res source images.
- **AI Background Removal:** Powered by `rembg` (U2-Net / ONNX Runtime) to isolate products.
- **Smart Flat-Packaging Safeguard:** Prevents white product boxes and medicine cartons from being accidentally hollowed out.
- **Clean White Background:** Automatically composites the isolated product onto pure `#FFFFFF` solid white.
- **Batch Processing:** Paste one or dozens of product URLs to process them all at once.
- **Single & Batch ZIP Downloads:** Download individual images or complete per-product and master ZIP bundles.
- **Direct Image Upload:** Also accepts direct file uploads for quick background removal on local photos.

---

## 🚀 Quick Start

### 1. Clone the Repository
```bash
git clone https://github.com/NikhileshAdiyala/1mg-image-cleaner.git
cd 1mg-image-cleaner
```

### 2. Run with `uv` (Recommended - Zero Config)
If you have [uv](https://github.com/astral-sh/uv) installed:
```bash
uv run --python 3.12 --with-requirements requirements.txt uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 3. Run with Standard Virtualenv
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open your browser and visit: **`http://localhost:8000`**

---

## 🛠️ Tech Stack
- **Backend:** FastAPI, Uvicorn, Python 3.12
- **Image Processing:** Rembg (ONNX Runtime, U2-Net), Pillow, NumPy
- **Frontend:** Responsive UI with Tailwind CSS

---

## 📜 License
MIT License
