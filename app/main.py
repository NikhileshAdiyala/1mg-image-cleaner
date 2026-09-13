import os
import uuid
import shutil
import zipfile
import urllib.request
from typing import List
from pydantic import BaseModel
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from app.processor import fetch_1mg_image_urls, extract_product_slug, process_single_image, HEADERS

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")
OUTPUTS_DIR = os.path.join(STATIC_DIR, "outputs")
os.makedirs(OUTPUTS_DIR, exist_ok=True)

app = FastAPI(title="1MG Product Image Studio")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

class ProcessRequest(BaseModel):
    urls: List[str]
    transparent: bool = False

@app.get("/")
def read_root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

@app.post("/api/process-urls")
async def process_urls(req: ProcessRequest):
    if not req.urls:
        raise HTTPException(status_code=400, detail="No URLs provided.")

    job_id = uuid.uuid4().hex[:8]
    job_dir = os.path.join(OUTPUTS_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    products_out = []
    total_images_processed = 0

    for url in req.urls:
        url = url.strip()
        if not url:
            continue
        slug = extract_product_slug(url)
        prod_dir = os.path.join(job_dir, slug)
        os.makedirs(prod_dir, exist_ok=True)

        try:
            image_urls = fetch_1mg_image_urls(url)
        except Exception as e:
            print(f"Failed to fetch {url}: {e}")
            image_urls = []

        prod_images = []
        for idx, img_url in enumerate(image_urls, 1):
            try:
                img_req = urllib.request.Request(img_url, headers=HEADERS)
                with urllib.request.urlopen(img_req, timeout=15) as resp:
                    raw_bytes = resp.read()

                processed_bytes, ext = process_single_image(raw_bytes, transparent=req.transparent)
                filename = f"image_{idx}_white_bg.{ext}" if not req.transparent else f"image_{idx}_transparent.{ext}"
                filepath = os.path.join(prod_dir, filename)

                with open(filepath, "wb") as f:
                    f.write(processed_bytes)

                prod_images.append({
                    "filename": filename,
                    "processed_url": f"/static/outputs/{job_id}/{slug}/{filename}"
                })
                total_images_processed += 1
            except Exception as err:
                print(f"Error processing image {img_url}: {err}")

        # Create zip for this single product
        prod_zip_name = f"{slug}.zip"
        prod_zip_path = os.path.join(prod_dir, prod_zip_name)
        with zipfile.ZipFile(prod_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for item in prod_images:
                zf.write(os.path.join(prod_dir, item["filename"]), arcname=item["filename"])

        products_out.append({
            "slug": slug,
            "images": prod_images,
            "zip_url": f"/static/outputs/{job_id}/{slug}/{prod_zip_name}"
        })

    # Create master zip for all products in this job
    all_zip_name = f"1mg_processed_{job_id}.zip"
    all_zip_path = os.path.join(job_dir, all_zip_name)
    with zipfile.ZipFile(all_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in products_out:
            for item in p["images"]:
                arcname = os.path.join(p["slug"], item["filename"])
                zf.write(os.path.join(job_dir, p["slug"], item["filename"]), arcname=arcname)

    return {
        "job_id": job_id,
        "total_images": total_images_processed,
        "products": products_out,
        "zip_url": f"/static/outputs/{job_id}/{all_zip_name}"
    }

@app.post("/api/upload-image")
async def upload_image(file: UploadFile = File(...), transparent: bool = Form(False)):
    contents = await file.read()
    processed_bytes, ext = process_single_image(contents, transparent=transparent)
    
    unique_name = f"upload_{uuid.uuid4().hex[:8]}.{ext}"
    upload_dir = os.path.join(OUTPUTS_DIR, "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    out_path = os.path.join(upload_dir, unique_name)

    with open(out_path, "wb") as f:
        f.write(processed_bytes)

    return {
        "filename": unique_name,
        "url": f"/static/outputs/uploads/{unique_name}"
    }

@app.get("/api/health")
def health():
    return {"status": "ok"}
