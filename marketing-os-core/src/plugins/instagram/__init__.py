"""Instagram — the first official channel plugin of the platform.

Importing this package registers every Instagram module in the global
plugin registry (decorator side effect).
"""

from src.plugins.instagram.intelligence.priorizer import InstagramPriorizer
from src.plugins.instagram.intelligence.decision_maker import InstagramDecisionMaker
from src.plugins.instagram.execution.reels_specialist import ReelsSpecialist
from src.plugins.instagram.execution.carousel_specialist import CarouselSpecialist

__all__ = [
    "InstagramPriorizer",
    "InstagramDecisionMaker",
    "ReelsSpecialist",
    "CarouselSpecialist",
]
