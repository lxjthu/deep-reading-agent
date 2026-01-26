import os
import json
import hashlib
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class StateManager:
    def __init__(self, db_path="processed_papers.json"):
        self.db_path = os.path.abspath(db_path)
        self.data = self._load_db()

    def _load_db(self):
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load state DB: {e}. Starting fresh.")
                return {}
        return {}

    def _save_db(self):
        try:
            with open(self.db_path, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save state DB: {e}")

    def calculate_hash(self, file_path):
        """Calculates MD5 hash of a file."""
        hash_md5 = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception as e:
            logger.error(f"Error calculating hash for {file_path}: {e}")
            return None

    def is_processed(self, file_path, output_check_func=None):
        """
        Checks if a file has been processed.
        If output_check_func is provided, it also verifies if the output artifacts actually exist.
        output_check_func(output_dir) -> bool
        """
        file_hash = self.calculate_hash(file_path)
        if not file_hash:
            return False

        if file_hash in self.data:
            record = self.data[file_hash]
            if record.get("status") == "completed":
                # Optional: Integrity check
                if output_check_func and record.get("output_dir"):
                    if not output_check_func(record["output_dir"]):
                        logger.warning(f"Record says completed but artifacts missing for {file_path}. Marking as reprocessing.")
                        return False
                return True
        return False

    def mark_started(self, file_path):
        file_hash = self.calculate_hash(file_path)
        if not file_hash:
            return
        
        self.data[file_hash] = {
            "status": "in_progress",
            "filename": os.path.basename(file_path),
            "filepath": file_path,
            "started_at": datetime.now().isoformat(),
            "output_dir": None
        }
        self._save_db()

    def mark_completed(self, file_path, output_dir, paper_type="QUANT"):
        file_hash = self.calculate_hash(file_path)
        if not file_hash:
            return

        # Ensure record exists (if mark_started wasn't called or persisted)
        if file_hash not in self.data:
             self.data[file_hash] = {
                "filename": os.path.basename(file_path),
                "filepath": file_path,
                "started_at": datetime.now().isoformat()
            }

        self.data[file_hash].update({
            "status": "completed",
            "completed_at": datetime.now().isoformat(),
            "output_dir": output_dir,
            "type": paper_type
        })
        self._save_db()

    def mark_failed(self, file_path, error_msg):
        file_hash = self.calculate_hash(file_path)
        if not file_hash:
            return
            
        if file_hash in self.data:
            self.data[file_hash].update({
                "status": "failed",
                "failed_at": datetime.now().isoformat(),
                "error": str(error_msg)
            })
            self._save_db()
