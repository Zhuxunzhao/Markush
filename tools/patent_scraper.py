"""专利爬取工具 — 从 Google Patents 获取专利文本和图片

Images are downloaded to disk only; Markush parsing happens later in the
pipeline via MarkushGrapherTool (infringement.py step 2).
"""

from __future__ import annotations
import logging
import os

from schemas.types import PatentDocument, PatentImage
from tools.google_patent_lookup import google_patent_scrap

logger = logging.getLogger("markush.tools.scraper")


class PatentScraperTool:
    def __init__(self, config: dict):
        self.cache_root = config["patent"]["cache_root"]
        if not os.path.isabs(self.cache_root):
            project_root = os.path.join(os.path.dirname(__file__), "..")
            self.cache_root = os.path.normpath(
                os.path.join(project_root, self.cache_root)
            )

    def fetch(self, patent_id: str) -> PatentDocument:
        """获取专利文档（优先从缓存读取）。

        Images are downloaded to disk; markush parsing is NOT done here.
        MarkushGrapherTool in the pipeline handles image recognition.
        """
        cache_path = os.path.join(self.cache_root, patent_id)
        logger.info(f"Fetching patent {patent_id} (cache: {cache_path})")

        result = google_patent_scrap(cache_path, patent_id)

        text_dict = result.get("text", {})
        image_list = result.get("images", [])

        images = [
            PatentImage(
                path=img_data.get("path", ""),
                link=img_data.get("link", ""),
                structure=None,
            )
            for img_data in image_list
            if os.path.exists(img_data.get("path", ""))
        ]

        doc = PatentDocument(
            patent_id=patent_id,
            claims_text=text_dict.get("claim", ""),
            description_text=text_dict.get("description", ""),
            abstract_text=text_dict.get("abstract", ""),
            full_text=text_dict.get("full", ""),
            images=images,
            markush_structures=[],
        )
        logger.info(f"Patent {patent_id}: {len(images)} image(s) available")
        return doc
