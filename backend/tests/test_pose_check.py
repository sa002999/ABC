import os
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import mediapipe as mp

from PIL import Image
from app.core.config import DATA_DIR
from app.modules.try_on.pose_check import MODEL, check_pose, pose_issue


class PoseCheckTests(unittest.TestCase):
    def setUp(self):
        self.image = Image.new('RGB', (800, 1200), 'white')

    def landmarks(self):
        return [SimpleNamespace(x=0.5, y=0.5, visibility=0.5, presence=0.5) for _ in range(33)]

    def detect(self, poses):
        with (
            patch.object(mp, 'Image'),
            patch.object(mp.tasks.vision.PoseLandmarker, 'create_from_options') as factory,
        ):
            factory.return_value.__enter__.return_value.detect.return_value.pose_landmarks = poses
            result = pose_issue(self.image)
            self.assertEqual(factory.call_args.args[0].num_poses, 2)
            return result

    def test_reject_no_person_and_multiple_people(self):
        self.assertEqual(self.detect([]), 'NO_PERSON')
        self.assertEqual(self.detect([self.landmarks(), self.landmarks()]), 'MULTIPLE_PEOPLE')

    def test_required_joints_need_visibility_presence_and_image_bounds(self):
        for index in (11, 12, 23, 24, 25, 26, 27, 28):
            for attribute, value in [('visibility', 0.49), ('presence', 0.49), ('visibility', None),
                                     ('presence', None), ('x', -0.01), ('x', 1.01), ('y', -0.01), ('y', 1.01)]:
                with self.subTest(index=index, attribute=attribute, value=value):
                    points = self.landmarks()
                    setattr(points[index], attribute, value)
                    self.assertEqual(self.detect([points]), 'BODY_CROPPED')

    def test_reference_thresholds_are_inclusive_and_do_not_require_face_or_toes(self):
        points = self.landmarks()
        for index in (0, 29, 30, 31, 32):
            points[index].visibility = 0
        points[11].x = 0
        points[12].x = 1
        self.assertIsNone(self.detect([points]))

    @unittest.skipIf(os.getenv('SKIP_MEDIAPIPE_MODEL_TEST') == '1', 'MediaPipe model inference disabled for this run')
    @unittest.skipUnless(MODEL.is_file(), 'Provide data/ml-models/pose_landmarker_lite.task for real model verification')
    def test_supplied_model_rejects_blank_image_and_accepts_reference_photo(self):
        self.assertEqual(pose_issue(self.image), 'NO_PERSON')
        path = DATA_DIR / 'assets' / 'default models' / 'person-1.jpg'
        self.assertTrue(check_pose(path)[0])
