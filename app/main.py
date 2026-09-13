import os
import re
import uuid
import shutil
import zipfile
import base64
import urllib.request
from urllib.parse import urlparse
from typing import List, Optional
from pydantic import BaseModel
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from app.processor import fetch_1mg_image_urls, extract_product_slug, process_single_image, HEADERS

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")

IS_SERVERLESS = bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))

if IS_SERVERLESS:
    OUTPUTS_DIR = "/tmp/outputs"
    os.environ["U2NET_HOME"] = "/tmp/.u2net"
else:
    OUTPUTS_DIR = os.path.join(STATIC_DIR, "outputs")

os.makedirs(OUTPUTS_DIR, exist_ok=True)

app = FastAPI(title="1MG Product Image Studio")

app.mount("/static/outputs", StaticFiles(directory=OUTPUTS_DIR), name="outputs")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

def sanitize_filename(name: str) -> str:
    if not name:
        return ""
    # Strip illegal filename characters
    sanitized = re.sub(r'[\\/*?:"<>|]', "", name).strip()
    sanitized = re.sub(r'\s+', "_", sanitized)
    return sanitized

def parse_url_line(raw_line: str, default_name: Optional[str] = None) -> tuple[str, Optional[str]]:
    raw_line = raw_line.strip()
    if not raw_line:
        return "", None

    url = raw_line
    custom_name = None

    if "," in raw_line:
        parts = raw_line.split(",", 1)
        url = parts[0].strip()
        custom_name = parts[1].strip()
    elif "|" in raw_line:
        parts = raw_line.split("|", 1)
        url = parts[0].strip()
        custom_name = parts[1].strip()
    elif "\t" in raw_line:
        parts = raw_line.split("\t", 1)
        url = parts[0].strip()
        custom_name = parts[1].strip()
    else:
        parts = raw_line.split(maxsplit=1)
        if len(parts) == 2 and (parts[0].startswith("http://") or parts[0].startswith("https://")):
            url = parts[0].strip()
            custom_name = parts[1].strip()
        else:
            url = raw_line.strip()
            custom_name = None

    if not custom_name and default_name:
        custom_name = default_name.strip()

    return url, custom_name

class ProcessRequest(BaseModel):
    urls: List[str]
    custom_name: Optional[str] = None
    default_custom_name: Optional[str] = None
    transparent: bool = False
    mode: Optional[str] = "white"  # "white", "transparent", or "raw_only"
    include_raw: bool = True

@app.get("/")
def read_root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

@app.post("/api/process-urls")
async def process_urls(req: ProcessRequest):
    if not req.urls:
        raise HTTPException(status_code=400, detail="No URLs provided.")

    mode = req.mode or ("transparent" if req.transparent else "white")
    is_raw_only = (mode == "raw_only")
    is_transparent = (mode == "transparent")
    include_raw = req.include_raw or is_raw_only

    job_id = uuid.uuid4().hex[:8]
    job_dir = os.path.join(OUTPUTS_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    products_out = []
    total_images_processed = 0
    seen_folders = {}

    default_name = (req.custom_name or req.default_custom_name or "").strip() or None

    for raw_entry in req.urls:
        url, custom_name = parse_url_line(raw_entry, default_name=default_name)
        if not url:
            continue

        slug = extract_product_slug(url)
        clean_name = sanitize_filename(custom_name) if custom_name else slug
        base_name = clean_name or "product"

        # Ensure directory uniqueness in this job run
        if base_name in seen_folders:
            seen_folders[base_name] += 1
            folder_name = f"{base_name}_{seen_folders[base_name]}"
        else:
            seen_folders[base_name] = 1
            folder_name = base_name

        prod_dir = os.path.join(job_dir, folder_name)
        os.makedirs(prod_dir, exist_ok=True)
        raw_dir = os.path.join(prod_dir, "raw")
        if include_raw:
            os.makedirs(raw_dir, exist_ok=True)

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

                # Detect file extension of the raw image
                url_path = urlparse(img_url).path
                ext_candidate = os.path.splitext(url_path)[1].lstrip(".").lower()
                raw_ext = "jpg" if ext_candidate in ["jpg", "jpeg"] else (ext_candidate if ext_candidate in ["png", "webp"] else "jpg")

                if idx == 1:
                    clean_basename = f"{base_name}.Main"
                else:
                    pt_num = idx - 1
                    clean_basename = f"{base_name}.PT{pt_num:02d}"

                raw_filename = f"{clean_basename}.raw.{raw_ext}"
                raw_url = None
                raw_data_url = None

                if include_raw:
                    raw_filepath = os.path.join(raw_dir, raw_filename)
                    with open(raw_filepath, "wb") as f:
                        f.write(raw_bytes)
                    raw_url = f"/static/outputs/{job_id}/{folder_name}/raw/{raw_filename}"
                    raw_mime = "png" if raw_ext == "png" else "jpeg"
                    raw_data_url = f"data:image/{raw_mime};base64,{base64.b64encode(raw_bytes).decode('utf-8')}"

                proc_filename = None
                processed_url = None
                proc_data_url = None

                if not is_raw_only:
                    processed_bytes, ext = process_single_image(raw_bytes, transparent=is_transparent)
                    proc_filename = f"{clean_basename}.{ext}"
                    filepath = os.path.join(prod_dir, proc_filename)
                    with open(filepath, "wb") as f:
                        f.write(processed_bytes)
                    processed_url = f"/static/outputs/{job_id}/{folder_name}/{proc_filename}"
                    proc_mime = "png" if ext == "png" else "jpeg"
                    proc_data_url = f"data:image/{proc_mime};base64,{base64.b64encode(processed_bytes).decode('utf-8')}"

                prod_images.append({
                    "filename": proc_filename or raw_filename,
                    "processed_filename": proc_filename,
                    "processed_url": processed_url,
                    "processed_data_url": proc_data_url,
                    "raw_filename": raw_filename if include_raw else None,
                    "raw_url": raw_url if include_raw else None,
                    "raw_data_url": raw_data_url
                })
                total_images_processed += 1
            except Exception as err:
                print(f"Error processing image {img_url}: {err}")

        # Create zip for processed images of this product (if available)
        prod_clean_zip_name = f"{base_name}.zip"
        prod_clean_zip_path = os.path.join(prod_dir, prod_clean_zip_name)
        has_prod_clean = False
        with zipfile.ZipFile(prod_clean_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for item in prod_images:
                if item.get("processed_filename"):
                    p_path = os.path.join(prod_dir, item["processed_filename"])
                    if os.path.exists(p_path):
                        zf.write(p_path, arcname=item["processed_filename"])
                        has_prod_clean = True

        # Create zip for raw images of this product (if available)
        prod_raw_zip_name = f"{base_name}_raw.zip"
        prod_raw_zip_path = os.path.join(prod_dir, prod_raw_zip_name)
        has_prod_raw = False
        if include_raw:
            with zipfile.ZipFile(prod_raw_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for item in prod_images:
                    if item.get("raw_filename"):
                        r_path = os.path.join(raw_dir, item["raw_filename"])
                        if os.path.exists(r_path):
                            zf.write(r_path, arcname=item["raw_filename"])
                            has_prod_raw = True

        products_out.append({
            "slug": slug,
            "custom_name": base_name,
            "folder_name": folder_name,
            "images": prod_images,
            "zip_url": f"/static/outputs/{job_id}/{folder_name}/{prod_clean_zip_name}" if has_prod_clean else (f"/static/outputs/{job_id}/{folder_name}/{prod_raw_zip_name}" if has_prod_raw else None),
            "clean_zip_url": f"/static/outputs/{job_id}/{folder_name}/{prod_clean_zip_name}" if has_prod_clean else None,
            "raw_zip_url": f"/static/outputs/{job_id}/{folder_name}/{prod_raw_zip_name}" if has_prod_raw else None,
        })

    # Master zip for processed images
    all_clean_zip_name = f"1mg_processed_{job_id}.zip"
    all_clean_zip_path = os.path.join(job_dir, all_clean_zip_name)
    has_all_clean = False
    with zipfile.ZipFile(all_clean_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in products_out:
            folder_name = p.get("folder_name", p["custom_name"])
            for item in p["images"]:
                if item.get("processed_filename"):
                    clean_file = os.path.join(job_dir, folder_name, item["processed_filename"])
                    if os.path.exists(clean_file):
                        zf.write(clean_file, arcname=os.path.join(folder_name, item["processed_filename"]))
                        has_all_clean = True

    # Master zip for raw images
    all_raw_zip_name = f"1mg_raw_{job_id}.zip"
    all_raw_zip_path = os.path.join(job_dir, all_raw_zip_name)
    has_all_raw = False
    if include_raw:
        with zipfile.ZipFile(all_raw_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in products_out:
                folder_name = p.get("folder_name", p["custom_name"])
                for item in p["images"]:
                    if item.get("raw_filename"):
                        raw_file = os.path.join(job_dir, folder_name, "raw", item["raw_filename"])
                        if os.path.exists(raw_file):
                            zf.write(raw_file, arcname=os.path.join(folder_name, item["raw_filename"]))
                            has_all_raw = True

    # Master bundle zip (clean + raw)
    all_bundle_zip_name = f"1mg_bundle_{job_id}.zip"
    all_bundle_zip_path = os.path.join(job_dir, all_bundle_zip_name)
    has_bundle = False
    if has_all_clean and has_all_raw:
        with zipfile.ZipFile(all_bundle_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in products_out:
                folder_name = p.get("folder_name", p["custom_name"])
                for item in p["images"]:
                    if item.get("processed_filename"):
                        clean_file = os.path.join(job_dir, folder_name, item["processed_filename"])
                        if os.path.exists(clean_file):
                            zf.write(clean_file, arcname=os.path.join(folder_name, "clean", item["processed_filename"]))
                            has_bundle = True
                    if item.get("raw_filename"):
                        raw_file = os.path.join(job_dir, folder_name, "raw", item["raw_filename"])
                        if os.path.exists(raw_file):
                            zf.write(raw_file, arcname=os.path.join(folder_name, "raw", item["raw_filename"]))
                            has_bundle = True

    default_zip_url = f"/static/outputs/{job_id}/{all_clean_zip_name}" if has_all_clean else (f"/static/outputs/{job_id}/{all_raw_zip_name}" if has_all_raw else None)

    return {
        "job_id": job_id,
        "mode": mode,
        "total_images": total_images_processed,
        "products": products_out,
        "zip_url": default_zip_url,
        "clean_zip_url": f"/static/outputs/{job_id}/{all_clean_zip_name}" if has_all_clean else None,
        "raw_zip_url": f"/static/outputs/{job_id}/{all_raw_zip_name}" if has_all_raw else None,
        "bundle_zip_url": f"/static/outputs/{job_id}/{all_bundle_zip_name}" if has_bundle else None
    }

@app.post("/api/upload-image")
async def upload_image(
    file: UploadFile = File(...),
    custom_name: Optional[str] = Form(None),
    transparent: bool = Form(False)
):
    contents = await file.read()
    processed_bytes, ext = process_single_image(contents, transparent=transparent)

    clean_custom = sanitize_filename(custom_name) if custom_name else None
    raw_ext = "jpg"
    if file.filename and "." in file.filename:
        raw_ext = file.filename.rsplit(".", 1)[-1].lower()

    if clean_custom:
        unique_name = f"{clean_custom}.Main.{ext}"
        unique_raw_name = f"{clean_custom}.Main.raw.{raw_ext}"
    else:
        uid = uuid.uuid4().hex[:8]
        unique_name = f"upload_{uid}.{ext}"
        unique_raw_name = f"upload_{uid}.raw.{raw_ext}"

    upload_dir = os.path.join(OUTPUTS_DIR, "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    out_path = os.path.join(upload_dir, unique_name)
    raw_path = os.path.join(upload_dir, unique_raw_name)

    with open(out_path, "wb") as f:
        f.write(processed_bytes)

    with open(raw_path, "wb") as f:
        f.write(contents)

    proc_mime = "png" if ext == "png" else "jpeg"
    raw_mime = "png" if raw_ext == "png" else "jpeg"

    return {
        "filename": unique_name,
        "url": f"/static/outputs/uploads/{unique_name}",
        "data_url": f"data:image/{proc_mime};base64,{base64.b64encode(processed_bytes).decode('utf-8')}",
        "raw_filename": unique_raw_name,
        "raw_url": f"/static/outputs/uploads/{unique_raw_name}",
        "raw_data_url": f"data:image/{raw_mime};base64,{base64.b64encode(contents).decode('utf-8')}"
    }

@app.get("/api/health")
def health():
    return {"status": "ok"}
