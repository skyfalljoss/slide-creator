import asyncio

from app.models.schemas import SlideData
from app.services.media.image_prompts import build_image_prompt, build_stock_query
from app.services.media.image_service import CloudflareImageService, StockPhotoService


class SlideImageResolver:
    """Shared slide image policy for generation and refinement."""

    def __init__(
        self,
        image_service: CloudflareImageService | None = None,
        stock_service: StockPhotoService | None = None,
    ) -> None:
        self.image_service = image_service or CloudflareImageService()
        self.stock_service = stock_service or StockPhotoService()

    def needs_image(self, slide: SlideData) -> bool:
        if slide.chart_data:
            return False
        if slide.layout in ("title", "section_divider", "chart"):
            return True
        return (slide.variant or "") in {"cover", "split_image", "quote", "closing"}

    async def resolve(self, slide: SlideData) -> str | None:
        if self.stock_service.enabled:
            stock = await self.stock_service.search_image(build_stock_query(slide))
            if stock:
                return stock
        return await self.image_service.generate_image(build_image_prompt(slide))

    async def resolve_many(self, slides: list[SlideData], *, concurrency: int = 4) -> None:
        semaphore = asyncio.Semaphore(concurrency)

        async def resolve_one(slide: SlideData) -> None:
            if not self.needs_image(slide):
                return
            async with semaphore:
                image_b64 = await self.resolve(slide)
            if image_b64:
                slide.image_b64 = image_b64

        await asyncio.gather(*(resolve_one(slide) for slide in slides))
