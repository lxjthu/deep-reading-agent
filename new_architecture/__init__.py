"""新架构 - 对话式论文分析引擎"""

from .config import Config
from .paper_cache import PaperCache, PaperMetadata
from .conversation_engine import ConversationEngine, TurnResult
from .analysis_dimensions import (
    ANALYSIS_DIMENSIONS,
    detect_paper_type,
    get_recommended_questions,
)

__all__ = [
    "Config",
    "PaperCache",
    "PaperMetadata",
    "ConversationEngine",
    "TurnResult",
    "ANALYSIS_DIMENSIONS",
    "detect_paper_type",
    "get_recommended_questions",
]
