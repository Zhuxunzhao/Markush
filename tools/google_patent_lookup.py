"""Patent text fetching and image downloading.

Source priority:
  1. Local disk cache (cache/google_patent/<id>/full_text.txt)
  2. Google Patents via google_patent_scraper
  3. FreePatentsOnline (fallback when Google Patents is unreachable)

Image source priority:
  1. patentimages.storage.googleapis.com URLs (embedded in Google Patents HTML)
  2. USPTO PDF extraction via PyMuPDF (fallback for US patents when CDN is blocked)

Image parsing (MarkushGrapher) is handled separately by the pipeline.
"""

from __future__ import annotations
import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md

logger = logging.getLogger("markush.tools.patent_lookup")


# ---------------------------------------------------------------------------
# Source 1: Google Patents
# ---------------------------------------------------------------------------

def _fetch_google_patents(patent_id: str) -> tuple[str, str, str]:
    """Scrape abstract, claims, description from Google Patents.

    Returns (abstract, claims, description). Raises on failure.
    """
    from google_patent_scraper import scraper_class

    scraper = scraper_class()
    err, html_content, url = scraper.request_single_patent(patent_id)

    def _to_md(section):
        if section is None:
            return ""
        text = md(str(section), escape_misc=False).strip()
        return re.sub(r'\n\s*\n\s*[\n\s]*\n', '\n\n', text)

    abstract = _to_md(html_content.find('section', itemprop='abstract'))
    claims = _to_md(html_content.find('section', itemprop='claims'))
    description = _to_md(html_content.find('section', itemprop='description'))
    return abstract, claims, description


# ---------------------------------------------------------------------------
# Source 2: FreePatentsOnline
# ---------------------------------------------------------------------------

_FPO_BASE = "https://www.freepatentsonline.com"
_FPO_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}


def _fpo_patent_id(patent_id: str) -> str:
    """Normalise patent ID for FreePatentsOnline URLs.

    US patents need just the numeric portion (e.g. US20230303562A1 → 20230303562).
    WO/EP patents keep their original form.
    """
    pid = patent_id.upper()
    if pid.startswith("US"):
        # Strip "US" prefix and any trailing kind-code (A1, B2, etc.)
        numeric = re.sub(r'^US', '', pid)
        numeric = re.sub(r'[A-Z]\d*$', '', numeric)
        return numeric
    return patent_id


def _fetch_freepatentsonline(patent_id: str) -> tuple[str, str, str]:
    """Scrape abstract, claims, description from freepatentsonline.com.

    Returns (abstract, claims, description). Raises on failure.
    """
    url = f"{_FPO_BASE}/{_fpo_patent_id(patent_id)}.html"
    resp = requests.get(url, headers=_FPO_HEADERS, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    def _get_section(title_text: str) -> str:
        for div in soup.find_all("div", class_="disp_elm_title"):
            if title_text in div.get_text():
                nxt = div.find_next_sibling()
                if nxt:
                    return nxt.get_text(separator="\n", strip=True)
        return ""

    abstract = _get_section("Abstract")
    claims = _get_section("Claims")
    description = _get_section("Description")
    return abstract, claims, description


# ---------------------------------------------------------------------------
# Unified fetch with fallback
# ---------------------------------------------------------------------------

def get_fulltext_patent_scrap(patent_id: str) -> tuple[str, str, str]:
    """Fetch patent text, trying Google Patents first then FreePatentsOnline.

    Returns (abstract_text, claim_text, description_text).
    """
    # Try Google Patents first
    try:
        abstract, claims, description = _fetch_google_patents(patent_id)
        if claims:
            logger.info(f"Fetched {patent_id} from Google Patents")
            return abstract, claims, description
    except Exception as e:
        logger.warning(f"Google Patents failed for {patent_id}: {e}")

    # Fallback: FreePatentsOnline
    logger.info(f"Trying FreePatentsOnline for {patent_id}…")
    abstract, claims, description = _fetch_freepatentsonline(patent_id)
    if not claims:
        raise RuntimeError(
            f"Could not retrieve patent text for {patent_id} from any source."
        )
    logger.info(f"Fetched {patent_id} from FreePatentsOnline")
    return abstract, claims, description


# ---------------------------------------------------------------------------
# Image extraction and downloading
# ---------------------------------------------------------------------------

def extract_image_urls(text: str) -> tuple[str, list[str]]:
    """Strip inline image markdown and return (cleaned_text, image_url_list)."""
    pattern = r'\[\!\[.*?\]\((https://patentimages\.storage\.googleapis\.com/[^"]+?.png)\)\].*?\n'
    text = re.sub(pattern, r'\1\n', text)
    urls = re.findall(
        r'https://patentimages\.storage\.googleapis\.com/[^"\s]+?.png', text
    )
    seen: set = set()
    urls = [u for u in urls if not (u in seen or seen.add(u))]
    return text, urls


def _download_single(link: str, path: str, cache_path: str) -> None:
    """Download one image; records 404s."""
    if os.path.exists(path):
        return
    url_404_path = os.path.join(cache_path, "url_404_list.json")
    try:
        resp = requests.get(link, timeout=10)
    except Exception:
        return
    if resp.status_code == 200:
        with open(path, "wb") as f:
            f.write(resp.content)
    else:
        try:
            with open(url_404_path) as f:
                lst = json.load(f)
        except Exception:
            lst = []
        if link not in lst:
            lst.append(link)
        with open(url_404_path, "w") as f:
            json.dump(lst, f)


def download_images_only(
    image_links: list[str], cache_path: str, max_workers: int = 10
) -> list[dict]:
    """Download images to disk without parsing them."""
    url_404_path = os.path.join(cache_path, "url_404_list.json")
    if not os.path.exists(url_404_path):
        with open(url_404_path, "w") as f:
            json.dump([], f)

    image_paths = [
        os.path.join(cache_path, f"image_{i+1}.png")
        for i in range(len(image_links))
    ]

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = [
            ex.submit(_download_single, link, path, cache_path)
            for link, path in zip(image_links, image_paths)
        ]
        for f in as_completed(futs):
            f.result()

    return [
        {"link": link, "path": path, "markush": False, "caption": "", "smi": "", "score": 0.0}
        for link, path in zip(image_links, image_paths)
    ]


# ---------------------------------------------------------------------------
# USPTO PDF fallback (for US patents when Google CDN is blocked)
# ---------------------------------------------------------------------------

_USPTO_PDF_URL = "https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/{patent_id}"
_MIN_IMAGE_BYTES = 2048  # skip tiny images (logos, bullets, etc.)


def _is_us_patent(patent_id: str) -> bool:
    return patent_id.upper().startswith("US")


def _extract_images_from_pdf(pdf_bytes: bytes, cache_path: str) -> list[dict]:
    """Extract all raster images from a PDF and save as image_N.png."""
    import fitz  # PyMuPDF

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    results = []
    idx = 1
    seen_xrefs: set[int] = set()

    for page in doc:
        for img_info in page.get_images(full=True):
            xref = img_info[0]
            if xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)

            try:
                pix = fitz.Pixmap(doc, xref)
                if pix.n > 4:  # CMYK → convert to RGB
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                png_bytes = pix.tobytes("png")
                if len(png_bytes) < _MIN_IMAGE_BYTES:
                    continue
                path = os.path.join(cache_path, f"image_{idx}.png")
                with open(path, "wb") as f:
                    f.write(png_bytes)
                results.append({"link": "", "path": path, "markush": False, "caption": "", "smi": "", "score": 0.0})
                idx += 1
            except Exception as e:
                logger.debug(f"Skipping PDF image xref={xref}: {e}")

    doc.close()
    return results


def _uspto_pdf_id(patent_id: str) -> str:
    """Normalise patent ID for the USPTO PDF download endpoint.

    The endpoint requires just the numeric portion:
      US20230303562A1  → 20230303562
      US10676478B2     → 10676478
    """
    pid = patent_id.upper()
    numeric = re.sub(r'^US', '', pid)
    numeric = re.sub(r'[A-Z]\d*$', '', numeric)
    return numeric


def download_images_from_uspto_pdf(patent_id: str, cache_path: str) -> list[dict]:
    """Download USPTO PDF and extract embedded images. US patents only."""
    if not _is_us_patent(patent_id):
        return []

    url = _USPTO_PDF_URL.format(patent_id=_uspto_pdf_id(patent_id))
    logger.info(f"Trying USPTO PDF for {patent_id}: {url}")
    try:
        resp = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
    except Exception as e:
        logger.warning(f"USPTO PDF request failed for {patent_id}: {e}")
        return []

    if resp.status_code != 200 or "pdf" not in resp.headers.get("content-type", "").lower():
        logger.warning(f"USPTO PDF not available for {patent_id} (status={resp.status_code})")
        return []

    logger.info(f"USPTO PDF downloaded for {patent_id} ({len(resp.content)//1024} KB), extracting images…")
    images = _extract_images_from_pdf(resp.content, cache_path)
    logger.info(f"Extracted {len(images)} image(s) from USPTO PDF for {patent_id}")
    return images


# ---------------------------------------------------------------------------
# Main entry: google_patent_scrap
# ---------------------------------------------------------------------------

def google_patent_scrap(cache_path: str, patent_id: str) -> dict:
    """Fetch patent text and download images (no image parsing).

    Returns:
        {
          "text": {"full": ..., "abstract": ..., "claim": ..., "description": ...},
          "images": [{"link": ..., "path": ..., "markush": False, ...}, ...]
        }
    """
    if os.path.exists(os.path.join(cache_path, "full_text.txt")):
        result = _load_from_cache(cache_path)
        # If no images were found in cache, try USPTO PDF fallback
        downloaded = [d for d in result["images"] if os.path.exists(d.get("path", ""))]
        if not downloaded:
            pdf_images = download_images_from_uspto_pdf(patent_id, cache_path)
            if pdf_images:
                result["images"] = pdf_images
        return result

    print(f"Cache not found — fetching {patent_id}…")
    os.makedirs(cache_path, exist_ok=True)
    with open(os.path.join(cache_path, "url_404_list.json"), "w") as f:
        json.dump([], f)

    abstract_text, claim_text, description_text = get_fulltext_patent_scrap(patent_id)
    full_text = "\n\n\n".join([abstract_text, claim_text, description_text])
    text_dict = {
        "full": full_text,
        "abstract": abstract_text,
        "claim": claim_text,
        "description": description_text,
    }

    for key, text in text_dict.items():
        with open(os.path.join(cache_path, f"{key}_text.txt"), "w") as f:
            f.write(text)

    _, image_links = extract_image_urls(full_text)
    image_dicts = download_images_only(image_links, cache_path)

    downloaded = [d for d in image_dicts if os.path.exists(d["path"])]
    if not downloaded:
        image_dicts = download_images_from_uspto_pdf(patent_id, cache_path)

    return {"text": text_dict, "images": image_dicts}


def _load_from_cache(cache_path: str) -> dict:
    """Load patent from disk cache (text + already-downloaded images)."""
    text_keys = ["full", "abstract", "claim", "description"]
    text_dict: dict[str, str] = {}
    for key in text_keys:
        with open(os.path.join(cache_path, f"{key}_text.txt")) as f:
            text_dict[key] = f.read()

    _, image_links = extract_image_urls(text_dict["full"])

    url_404_path = os.path.join(cache_path, "url_404_list.json")
    links_404: list[str] = []
    if os.path.exists(url_404_path):
        with open(url_404_path) as f:
            links_404 = json.load(f)

    image_paths = [
        os.path.join(cache_path, f"image_{i+1}.png")
        for i in range(len(image_links))
    ]

    missing = [
        (link, path)
        for link, path in zip(image_links, image_paths)
        if not os.path.exists(path) and link not in links_404
    ]
    if missing:
        print(f"Re-downloading {len(missing)} missing image(s)…")
        with ThreadPoolExecutor(max_workers=10) as ex:
            futs = [
                ex.submit(_download_single, link, path, cache_path)
                for link, path in missing
            ]
            for f in as_completed(futs):
                f.result()

    image_dicts = [
        {"link": link, "path": path, "markush": False, "caption": "", "smi": "", "score": 0.0}
        for link, path in zip(image_links, image_paths)
    ]
    print(f"Loaded from cache: {cache_path} ({len(image_dicts)} image(s))")
    return {"text": text_dict, "images": image_dicts}
