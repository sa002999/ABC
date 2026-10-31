from app.core.config import BACKEND_DIR, RUNTIME_DIR
from app.integrations.s3 import check_upload_cors, private_bucket, s3_client
from dotenv import dotenv_values
from fastapi import HTTPException
import json
import os


def check_react():
    config=dotenv_values(BACKEND_DIR.parent/'frontend'/'.env.local')
    if config.get('VITE_FIREBASE_PROJECT_ID')!=os.getenv('FIREBASE_PROJECT_ID'):
        raise RuntimeError('Frontend/backend Firebase project mismatch')
    print('Firebase frontend/backend project: matches')
    missing=[]
    for origin in ('http://127.0.0.1:8000','http://localhost:8000','http://127.0.0.1:5173','http://localhost:5173'):
        try:
            check_upload_cors(origin)
            print('S3 upload origin OK:',origin)
        except HTTPException as error:
            if error.detail.get('code')!='PHOTO_CORS_UNAVAILABLE': raise
            missing.append(origin)
            print('S3 upload origin unavailable:',origin,error.detail.get('code'))
    if missing: print('Those origins use the authenticated API photo-transfer fallback.')


def configure_react_cors():
    client=s3_client();bucket=private_bucket()
    rules=client.get_bucket_cors(Bucket=bucket)['CORSRules']
    backup=RUNTIME_DIR / 'verification'/'s3-cors-before-react.json'
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists(): backup.write_text(json.dumps({'CORSRules':rules},indent=2),encoding='utf-8')
    if not any(rule.get('ID')=='react-local-development' for rule in rules):
        rules.append({'ID':'react-local-development','AllowedOrigins':['http://127.0.0.1:5173','http://localhost:5173'],
            'AllowedMethods':['POST'],'AllowedHeaders':['content-type'],'ExposeHeaders':['ETag'],'MaxAgeSeconds':600})
        client.put_bucket_cors(Bucket=bucket,CORSConfiguration={'CORSRules':rules})
    check_react()
