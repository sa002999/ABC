"""Decode source images and remove metadata. Person quality is a separate pending check."""
import warnings
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener


register_heif_opener(thumbnails=False, aux_images=False)
MAX_BYTES = 10 * 1024 * 1024
ISSUES = {
    'UNSUPPORTED_FILE': '請使用可正常開啟的單張 JPEG、PNG 或 HEIC 照片。',
    'FILE_TOO_LARGE': '單張照片不可超過 10 MB。',
    'LOW_RESOLUTION': '照片長邊至少需要 1200 像素，請使用較清晰的原始照片。',
    'HIGH_RESOLUTION': '照片長邊不可超過 6000 像素，請先縮小圖片。',
    'NO_PERSON': '未能清楚偵測人物，請上傳單人正面全身照。',
    'MULTIPLE_PEOPLE': '照片中偵測到多位人物，請改用單人照片。',
    'BODY_CROPPED': '請讓頭部、身體、雙腿與雙腳完整入鏡，避免遮擋。',
    'NOT_FRONTAL': '請面向鏡頭站立，避免側身或背對鏡頭。',
    'LOW_LIGHT': '照片中的人物過暗，請在光線充足處重新拍攝。',
    'UPLOAD_EXPIRED': '這次上傳已逾時，請重新選擇照片。',
    'FILE_SIZE_MISMATCH': '實際上傳大小與這次申請不一致，請重新選擇照片。',
}


class InvalidPhoto(Exception):
    def __init__(self, *codes):
        self.codes = list(codes)


def issue_list(codes):
    return [{'code': code, 'message': ISSUES[code]} for code in codes]


def normalize_photo(content, content_type=None):
    if len(content) > MAX_BYTES:
        raise InvalidPhoto('FILE_TOO_LARGE')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                allowed = {'JPEG': ['image/jpeg'], 'PNG': ['image/png'], 'HEIF': ['image/heic', 'image/heif']}
                if image.format not in allowed or (content_type and content_type not in allowed[image.format]):
                    raise InvalidPhoto('UNSUPPORTED_FILE')
                if getattr(image, 'n_frames', 1) != 1:
                    raise InvalidPhoto('UNSUPPORTED_FILE')
                if max(image.size) > 6000:
                    raise InvalidPhoto('HIGH_RESOLUTION')
                if max(image.size) < 1200:
                    raise InvalidPhoto('LOW_RESOLUTION')
                upright = ImageOps.exif_transpose(image).convert('RGBA')
                clean = Image.new('RGB', upright.size, 'white')
                clean.paste(upright, mask=upright.getchannel('A'))
                clean.thumbnail((2400, 2400))
                # New pixel canvas intentionally carries no EXIF, XMP or source filename.
                result = BytesIO()
                clean.save(result, 'JPEG', quality=92, optimize=True)
                return clean, result.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise InvalidPhoto('UNSUPPORTED_FILE') from None


def preview_bytes(image, format='WEBP'):
    small = image.copy()
    small.thumbnail((480, 720))
    output = BytesIO()
    small.save(output, format, quality=82)
    return output.getvalue()
