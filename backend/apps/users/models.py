from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom user model (AUTH_USER_MODEL='users.User')."""

    email = models.EmailField("邮箱", unique=True)
    nickname = models.CharField("昵称", max_length=64, blank=True, default="")
    avatar = models.URLField("头像", blank=True, default="")
    phone = models.CharField("手机号", max_length=32, blank=True, default="")
    department = models.CharField("部门", max_length=128, blank=True, default="")
    last_login_ip = models.GenericIPAddressField("最后登录IP", null=True, blank=True)

    class Meta:
        db_table = "aits_user"
        verbose_name = "用户"
        verbose_name_plural = "用户"
        ordering = ["-date_joined"]

    def __str__(self):
        return self.nickname or self.username

    @property
    def display_name(self) -> str:
        return self.nickname or self.get_full_name() or self.username

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.strip().lower()
        super().save(*args, **kwargs)
