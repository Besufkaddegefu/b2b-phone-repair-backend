import os
import uuid
from typing import BinaryIO, List, Optional
from urllib.parse import urljoin

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import get_settings

settings = get_settings()


class MediaStorage:
    """Cloudflare R2 / S3 compatible media storage."""
    
    def __init__(self):
        self.enabled = bool(settings.R2_ACCOUNT_ID and settings.R2_ACCESS_KEY_ID and settings.R2_SECRET_ACCESS_KEY)
        self.bucket_name = settings.R2_BUCKET_NAME
        self.public_url = settings.R2_PUBLIC_URL
        
        if self.enabled:
            self.client = boto3.client(
                "s3",
                endpoint_url=f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
                aws_access_key_id=settings.R2_ACCESS_KEY_ID,
                aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
                config=Config(
                    signature_version="s3v4",
                    retries={"max_attempts": 3},
                ),
                region_name="auto",
            )
        else:
            self.client = None
    
    def _generate_key(self, filename: str, folder: str = "listings") -> str:
        """Generate unique object key."""
        ext = os.path.splitext(filename)[1].lower()
        unique_id = uuid.uuid4().hex[:12]
        return f"{folder}/{unique_id}{ext}"
    
    async def upload_file(
        self,
        file: BinaryIO,
        filename: str,
        content_type: str,
        folder: str = "listings",
    ) -> Optional[str]:
        """Upload file to R2/S3 and return public URL."""
        if not self.enabled or not self.client:
            return None
        
        key = self._generate_key(filename, folder)
        
        try:
            # Reset file pointer
            file.seek(0)
            
            self.client.upload_fileobj(
                file,
                self.bucket_name,
                key,
                ExtraArgs={
                    "ContentType": content_type,
                    "ACL": "public-read",
                },
            )
            
            # Return public URL
            if self.public_url:
                return urljoin(self.public_url.rstrip("/") + "/", key)
            else:
                return f"https://{self.bucket_name}.{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com/{key}"
                
        except ClientError as e:
            print(f"R2 upload error: {e}")
            return None
    
    async def upload_bytes(
        self,
        data: bytes,
        filename: str,
        content_type: str,
        folder: str = "listings",
    ) -> Optional[str]:
        """Upload bytes to R2/S3 and return public URL."""
        if not self.enabled or not self.client:
            return None
        
        key = self._generate_key(filename, folder)
        
        try:
            self.client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=data,
                ContentType=content_type,
                ACL="public-read",
            )
            
            if self.public_url:
                return urljoin(self.public_url.rstrip("/") + "/", key)
            else:
                return f"https://{self.bucket_name}.{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com/{key}"
                
        except ClientError as e:
            print(f"R2 upload error: {e}")
            return None
    
    async def delete_file(self, url: str) -> bool:
        """Delete file from R2/S3 by URL."""
        if not self.enabled or not self.client:
            return False
        
        # Extract key from URL
        if self.public_url and url.startswith(self.public_url):
            key = url[len(self.public_url):].lstrip("/")
        else:
            # Try to extract from standard S3 URL
            parts = url.split("/")
            if len(parts) >= 4:
                key = "/".join(parts[3:])
            else:
                return False
        
        try:
            self.client.delete_object(Bucket=self.bucket_name, Key=key)
            return True
        except ClientError as e:
            print(f"R2 delete error: {e}")
            return False
    
    async def delete_files(self, urls: List[str]) -> int:
        """Delete multiple files."""
        deleted = 0
        for url in urls:
            if await self.delete_file(url):
                deleted += 1
        return deleted
    
    async def generate_presigned_url(
        self,
        filename: str,
        content_type: str,
        folder: str = "listings",
        expiration: int = 3600,
    ) -> Optional[dict]:
        """Generate presigned POST URL for direct browser upload."""
        if not self.enabled or not self.client:
            return None
        
        key = self._generate_key(filename, folder)
        
        try:
            post = self.client.generate_presigned_post(
                Bucket=self.bucket_name,
                Key=key,
                Fields={"Content-Type": content_type, "acl": "public-read"},
                Conditions=[
                    {"Content-Type": content_type},
                    {"acl": "public-read"},
                    ["content-length-range", 0, 10 * 1024 * 1024],  # 10MB max
                ],
                ExpiresIn=expiration,
            )
            
            public_url = urljoin(self.public_url.rstrip("/") + "/", key) if self.public_url else f"https://{self.bucket_name}.{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com/{key}"
            
            return {
                "url": post["url"],
                "fields": post["fields"],
                "public_url": public_url,
                "key": key,
            }
        except ClientError as e:
            print(f"Presigned URL error: {e}")
            return None
    
    def get_public_url(self, key: str) -> str:
        """Get public URL for a key."""
        if self.public_url:
            return urljoin(self.public_url.rstrip("/") + "/", key)
        return f"https://{self.bucket_name}.{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com/{key}"


# Global instance
media_storage = MediaStorage()


async def upload_listing_images(
    files: List[BinaryIO],
    filenames: List[str],
    content_types: List[str],
) -> List[str]:
    """Upload multiple listing images."""
    urls = []
    for file, filename, content_type in zip(files, filenames, content_types):
        url = await media_storage.upload_file(file, filename, content_type, "listings")
        if url:
            urls.append(url)
    return urls


async def delete_listing_images(urls: List[str]) -> int:
    """Delete listing images."""
    return await media_storage.delete_files(urls)


async def get_upload_presigned_url(
    filename: str,
    content_type: str,
) -> Optional[dict]:
    """Get presigned URL for direct upload."""
    return await media_storage.generate_presigned_url(filename, content_type, "listings")