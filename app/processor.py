import os
import re
import urllib.request
from urllib.parse import urlparse
from io import BytesIO
from PIL import Image
from rembg import remove, new_session
import numpy as np

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# Pre-initialize rembg session
session = new_session("u2net")

def extract_product_slug(url: str) -> str:
    path = urlparse(url).path.strip("/")
    slug = path.split("/")[-1]
    return slug or "product"

def fetch_1mg_image_urls(url: str) -> list[str]:
    """
    Extracts raw image source URLs from 1mg product page without dynamic watermark parameters.
    """
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        html = resp.read().decode("utf-8")

    # Match 32-character hex product image filenames (standard for 1mg products)
    hex_matches = re.findall(r'https://onemg\.gumlet\.io/[^\s\"\'<>]*/([a-f0-9]{32}\.(?:jpg|jpeg|png|webp))', html)
    if hex_matches:
        unique_urls = []
        for img_file in hex_matches:
            clean_url = f"https://onemg.gumlet.io/{img_file}"
            if clean_url not in unique_urls:
                unique_urls.append(clean_url)
        return unique_urls

    # Fallback for pages without standard hex hashes
    raw_matches = re.findall(r'https://onemg\.gumlet\.io/[^\s\"\'<>]+', html)
    clean_urls = []

    for u in raw_matches:
        # Ignore ads, diagnostics, and banners
        if any(x in u for x in ["marketing", "diagnostics", "banner", ".svg"]):
            continue

        # Extract base image path by removing watermark and sizing transformations
        clean = re.sub(r'l_watermark_[^/]*/', '', u)
        clean = re.sub(r'a_ignore,[^/]*/', '', clean)
        clean = clean.split("?")[0]

        # Valid image extensions
        if clean.endswith((".jpg", ".jpeg", ".png", ".webp")):
            if clean not in clean_urls:
                clean_urls.append(clean)

    return clean_urls

def process_single_image(image_bytes: bytes, transparent: bool = False) -> tuple[bytes, str]:
    """
    Removes background and composites to pure white (or leaves transparent).
    Protects flat packaging box scans from accidental erosion.
    """
    cutout_bytes = remove(image_bytes, session=session)
    cutout_img = Image.open(BytesIO(cutout_bytes)).convert("RGBA")
    raw_img = Image.open(BytesIO(image_bytes)).convert("RGBA")

    # Check if rembg accidentally hollowed out a solid white product box
    img_white_arr = np.array(cutout_img.convert("L"))
    img_raw_arr = np.array(raw_img.convert("L"))

    # If cutout erased >85% of pixels but raw image had significant content
    # (indicating the product packaging surface itself was white)
    white_cutout_ratio = np.mean(img_white_arr > 250)
    white_raw_ratio = np.mean(img_raw_arr > 250)

    is_flat_packaging = white_cutout_ratio > 0.85 and white_raw_ratio < 0.75

    out_io = BytesIO()
    if transparent:
        if is_flat_packaging:
            raw_img.save(out_io, format="PNG")
        else:
            cutout_img.save(out_io, format="PNG")
        return out_io.getvalue(), "png"
    else:
        if is_flat_packaging:
            raw_img.convert("RGB").save(out_io, format="JPEG", quality=95)
        else:
            white_canvas = Image.new("RGBA", cutout_img.size, (255, 255, 255, 255))
            final_img = Image.alpha_composite(white_canvas, cutout_img).convert("RGB")
            final_img.save(out_io, format="JPEG", quality=95)
        return out_io.getvalue(), "jpg"
