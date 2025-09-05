from django.db import models


class RemoteDownload(models.Model):
    download_id = models.CharField(max_length=64, primary_key=True)
    temp_path = models.TextField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"RemoteDownload(download_id={self.download_id})"
