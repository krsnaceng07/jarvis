import pytest
from jarvis_media.image_generation.types import (
    GenerateImageParams,
    ImageGenerationProvider,
    ImageGenerationProviderCapabilities,
    ImageGenerationModeCapabilities,
    ImageGenerationEditCapabilities,
    ImageGenerationResult,
    GeneratedImageAsset,
    ImageGenerationProviderConfiguredContext,
    ImageGenerationRequest,
)
from jarvis_media.image_generation.runtime import generate_image
from jarvis_media.image_generation.provider_registry import (
    register_image_generation_provider,
    _providers,
)


class DummyProvider(ImageGenerationProvider):
    def __init__(self, provider_id: str, models: list[str]):
        self.id = provider_id
        self.aliases = []
        self.label = "Dummy Provider"
        self.default_model = models[0] if models else None
        self.default_timeout_ms = 10000
        self.models = models
        self.capabilities = ImageGenerationProviderCapabilities(
            generate=ImageGenerationModeCapabilities(), edit=ImageGenerationEditCapabilities()
        )

    def is_configured(self, ctx: ImageGenerationProviderConfiguredContext) -> bool:
        return True

    async def generate_image(self, req: ImageGenerationRequest) -> ImageGenerationResult:
        if req.model == "fail-model":
            raise ValueError("Intentional failure")
        return ImageGenerationResult(
            images=[GeneratedImageAsset(buffer=b"fake", mime_type="image/png")], model=req.model
        )


@pytest.fixture(autouse=True)
def clean_registry():
    _providers.clear()
    yield
    _providers.clear()


@pytest.mark.asyncio
async def test_generate_image_success():
    provider = DummyProvider("dummy", ["model1", "model2"])
    register_image_generation_provider(provider)

    class FakeConfig:
        agents = type(
            "Agents",
            (),
            {"defaults": type("Defaults", (), {"imageGenerationModel": "dummy/model1"})()},
        )()

    params = GenerateImageParams(cfg=FakeConfig(), prompt="Test prompt")

    result = await generate_image(params)
    assert result.provider == "dummy"
    assert result.model == "model1"
    assert len(result.images) == 1
    assert result.images[0].buffer == b"fake"


@pytest.mark.asyncio
async def test_generate_image_no_candidates():
    # Registry is empty
    params = GenerateImageParams(cfg=None, prompt="Test prompt")
    with pytest.raises(ValueError, match="No image-generation model configured"):
        await generate_image(params)


@pytest.mark.asyncio
async def test_generate_image_all_fail():
    provider = DummyProvider("dummy", ["fail-model"])
    register_image_generation_provider(provider)

    params = GenerateImageParams(cfg=None, prompt="Test prompt", model_override="dummy/fail-model")
    with pytest.raises(RuntimeError, match="All image generation models failed"):
        await generate_image(params)
