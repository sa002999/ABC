from pathlib import Path

from PIL import Image, ImageOps
from app.core.config import DATA_DIR

MODEL = DATA_DIR / 'ml-models' / 'pose_landmarker_lite.task'

POSE_MESSAGES = {
    'NO_PERSON': '照片中沒有偵測到清楚的人物，請上傳單人全身照。',
    'MULTIPLE_PEOPLE': '偵測到多位人物，請使用只有一人的照片。',
    'BODY_CROPPED': '人物姿勢或身體範圍不夠清楚，請使用肩膀到腳踝完整入鏡的站姿照片。',
}


def check_pose(path: Path) -> tuple[bool, str]:
    with Image.open(path) as image:
        issue = pose_issue(ImageOps.exif_transpose(image).convert('RGB'))
    return (False, POSE_MESSAGES[issue]) if issue else (True, '已通過單人人物與身體範圍檢查，可嘗試產生試穿圖。')


def pose_issue(image: Image.Image) -> str | None:
    # Load inference dependencies only for new uploads, so existing photos and models remain usable.
    import mediapipe as mp
    import numpy as np

    options = mp.tasks.vision.PoseLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(MODEL)),
        num_poses=2,
    )
    with mp.tasks.vision.PoseLandmarker.create_from_options(options) as detector:
        poses = detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB,
                                         data=np.ascontiguousarray(image))).pose_landmarks

    if not poses:
        return 'NO_PERSON'
    if len(poses) > 1:
        return 'MULTIPLE_PEOPLE'

    landmarks = poses[0]

    def visible(index: int) -> bool:
        point = landmarks[index]
        return (
            (point.visibility or 0) >= 0.5
            and (point.presence or 0) >= 0.5
            and 0 <= point.x <= 1
            and 0 <= point.y <= 1
        )

    # The garment is full length: both sides of the torso and legs need to be visible.
    if not all(visible(index) for index in (11, 12, 23, 24, 25, 26, 27, 28)):
        return 'BODY_CROPPED'
    return None
