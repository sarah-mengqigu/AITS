"""Shared abstract models used across every AITS business app."""

import uuid

from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    """Adds created/updated timestamps to a model."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        abstract = True


class UUIDTimeStampedModel(TimeStampedModel):
    """Timestamps plus a client friendly UUID public identifier."""

    uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)

    class Meta:
        abstract = True


class SoftDeleteQuerySet(models.QuerySet):
    def alive(self):
        return self.filter(is_deleted=False)

    def soft_delete(self):
        return self.update(is_deleted=True)


class SoftDeleteModel(models.Model):
    is_deleted = models.BooleanField(default=False, db_index=True, verbose_name="已删除")
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = SoftDeleteQuerySet.as_manager()

    class Meta:
        abstract = True


class UserOwnedModel(TimeStampedModel):
    """Convenience mixin for objects that record their creator."""

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        abstract = True
