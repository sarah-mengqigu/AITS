"""Uniform DRF exception envelope.

Every error response has the shape::

    {"code": "validation_error", "message": "...", "errors": {...},
     "detail": "...", "status_code": 400}

Front-end only needs to read ``message`` / ``errors``.
"""

import logging

from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.db import IntegrityError
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)


class BusinessError(APIException):
    """Domain level error carrying a stable machine readable code."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "业务处理失败"
    default_code = "business_error"

    def __init__(self, message=None, code=None, status_code=None, extra=None):
        self.message = message or self.default_detail
        self.biz_code = code or self.default_code
        self.extra = extra or {}
        if status_code is not None:
            self.status_code = status_code
        super().__init__(self.message)


def _message_from_detail(detail):
    if isinstance(detail, dict):
        first = next(iter(detail.values()), "")
        return _message_from_detail(first)
    if isinstance(detail, (list, tuple)):
        return _message_from_detail(detail[0]) if detail else ""
    return str(detail)


def custom_exception_handler(exc, context):
    """Attach a stable envelope while keeping DRF semantics."""
    if isinstance(exc, BusinessError):
        return Response(
            {
                "code": exc.biz_code,
                "message": exc.message,
                "errors": exc.extra or {},
                "status_code": exc.status_code,
            },
            status=exc.status_code,
        )

    if isinstance(exc, (Http404, ObjectDoesNotExist)):
        return Response(
            {"code": "not_found", "message": "资源不存在", "errors": {}, "status_code": 404},
            status=status.HTTP_404_NOT_FOUND,
        )

    if isinstance(exc, (DjangoPermissionDenied,)):
        return Response(
            {"code": "permission_denied", "message": "没有操作权限", "errors": {},
             "status_code": 403},
            status=status.HTTP_403_FORBIDDEN,
        )

    if isinstance(exc, IntegrityError):
        logger.warning("integrity error: %s", exc)
        return Response(
            {"code": "conflict", "message": "数据冲突或违反唯一约束", "errors": {},
             "status_code": 409},
            status=status.HTTP_409_CONFLICT,
        )

    response = drf_exception_handler(exc, context)
    if response is None:
        logger.exception("unhandled exception: %s", exc)
        return Response(
            {"code": "internal_error", "message": "服务器内部错误", "errors": {},
             "status_code": 500},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    detail = response.data
    code = "error"
    if isinstance(exc, ValidationError):
        code = "validation_error"
    elif response.status_code == 401:
        code = "unauthorized"
    elif response.status_code == 403:
        code = "permission_denied"
    elif response.status_code == 404:
        code = "not_found"
    elif response.status_code == 429:
        code = "throttled"

    message = _message_from_detail(detail) or code
    errors = detail if isinstance(detail, (dict, list)) else {}

    response.data = {
        "code": code,
        "message": message,
        "errors": errors,
        "status_code": response.status_code,
    }
    return response
