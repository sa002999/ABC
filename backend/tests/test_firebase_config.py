import os
import unittest
from unittest.mock import patch

import firebase_admin
from firebase_admin import credentials
from google.auth.credentials import AnonymousCredentials

from app.integrations.firebase import firebase_app


class FirebaseConfigTests(unittest.TestCase):
    def test_uses_adc_with_the_configured_firebase_project(self):
        adc = AnonymousCredentials()
        with (
            patch.dict(os.environ, {"FIREBASE_PROJECT_ID": "firebase-project"}, clear=True),
            patch("google.auth.default", return_value=(adc, "vertex-project")),
        ):
            app = firebase_app()
            self.addCleanup(firebase_admin.delete_app, app)
            self.assertEqual(app.project_id, "firebase-project")
            self.assertIsInstance(app.credential, credentials.ApplicationDefault)
            self.assertIs(app.credential.get_credential(), adc)
            self.assertIs(firebase_app(), app)
