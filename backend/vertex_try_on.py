"""Use the same Google Gen AI recontext_image flow as try_on.py."""
import os
import re
from io import BytesIO

import httpx
from google import genai
from google.genai import errors, types
from google.auth.exceptions import GoogleAuthError
from PIL import Image, ImageOps, UnidentifiedImageError


class GenerationError(Exception):
    def __init__(self, code):
        self.code = code


def configuration():
    project = os.getenv('GOOGLE_CLOUD_PROJECT', '')
    location = os.getenv('VERTEX_TRY_ON_LOCATION') or os.getenv('GOOGLE_CLOUD_LOCATION', '')
    model = os.getenv('VERTEX_TRY_ON_MODEL', 'virtual-try-on-001')
    if not all(re.fullmatch(r'[A-Za-z0-9-]+', value) for value in (project, location, model)):
        raise GenerationError('VERTEX_NOT_CONFIGURED')
    return project, location, model


def clean_result(content):
    if len(content) > 20 * 1024 * 1024:
        raise GenerationError('INVALID_RESULT')
    try:
        with Image.open(BytesIO(content)) as image:
            if image.format not in ('JPEG', 'PNG') or max(image.size)>6000 or min(image.size)<1:
                raise GenerationError('INVALID_RESULT')
            clean = ImageOps.exif_transpose(image).convert('RGB')
            output = BytesIO()
            # Encode fresh pixels so provider metadata is not stored or exposed.
            canvas = Image.new('RGB', clean.size); canvas.paste(clean)
            canvas.save(output, 'JPEG', quality=94)
            return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise GenerationError('INVALID_RESULT') from None


def generate(person, clothing, location=None, model=None, before_call=None):
    project, configured_location, configured_model = configuration()
    location, model = location or configured_location, model or configured_model
    try:
        with genai.Client(vertexai=True,project=project,location=location,
                http_options=types.HttpOptions(timeout=180000,retry_options=types.HttpRetryOptions(attempts=1))) as client:
            if before_call: before_call()
            response=client.models.recontext_image(model=model,
                source=types.RecontextImageSource(
                    person_image=types.Image(image_bytes=person,mime_type='image/jpeg'),
                    product_images=[types.ProductImage(product_image=types.Image(image_bytes=clothing,mime_type='image/jpeg'))]),
                config=types.RecontextImageConfig(number_of_images=1))
        if not response.generated_images or not response.generated_images[0].image or not response.generated_images[0].image.image_bytes:
            raise GenerationError('PROVIDER_REJECTED')
        return clean_result(response.generated_images[0].image.image_bytes)
    except errors.APIError as error:
        code={400:'PROVIDER_REJECTED',401:'VERTEX_CREDENTIALS',403:'VERTEX_PERMISSION',404:'VERTEX_MODEL_UNAVAILABLE',
              429:'PROVIDER_BUSY'}.get(error.code,'PROVIDER_UNAVAILABLE')
        raise GenerationError(code) from None
    except GoogleAuthError:
        raise GenerationError('VERTEX_CREDENTIALS') from None
    except httpx.TimeoutException:
        raise GenerationError('PROVIDER_TIMEOUT') from None
    except httpx.HTTPError:
        raise GenerationError('PROVIDER_UNAVAILABLE') from None
