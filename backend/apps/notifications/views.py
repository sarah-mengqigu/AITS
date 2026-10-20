"""通知中心 API 视图。

端点（前缀 ``/api/notifications/``）：

* ``channels/``     全局渠道（读：登录用户；写：is_staff）
* ``receivers/``    项目级接收对象 CRUD（写：项目 admin+；project 为空：is_staff）
* ``email-config/`` SMTP 单例（读：登录用户；写：is_staff；password 掩码）
* ``test/``         发送测试通知（receiver_id 或 channel_code + webhook_url）
* ``logs/``         通知日志（按可访问项目过滤）
"""

from django.db.models import Q
from rest_framework import mixins, status, viewsets
from rest_framework.permissions import SAFE_METHODS, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import (
    OpenApiTypes,
    extend_schema,
    extend_schema_view,
)


from apps.common.api.api_exception_handler import BusinessError
from apps.common.permissions import require_project_role
from apps.notifications.models import (
    EmailConfig,
    NotificationChannel,
    NotificationLog,
    NotificationReceiver,
)
from apps.notifications.serializers import (
    EmailConfigSerializer,
    NotificationChannelSerializer,
    NotificationLogSerializer,
    NotificationReceiverSerializer,
)
from apps.notifications.services import send_test_notification
from apps.projects.views import projects_for


class NotificationChannelViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Global channel catalogue. Only staff may create/update."""

    queryset = NotificationChannel.objects.all().order_by("id")
    serializer_class = NotificationChannelSerializer
    filterset_fields = ("channel_code", "is_active")
    search_fields = ("name", "description", "channel_code")
    ordering_fields = ("id", "channel_code", "created_at")

    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [IsAuthenticated()]
        return [IsAuthenticated(), IsAdminUser()]


class NotificationReceiverViewSet(viewsets.ModelViewSet):
    """Project scoped notification receivers."""

    queryset = NotificationReceiver.objects.select_related("project", "channel")
    serializer_class = NotificationReceiverSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ("project", "channel", "is_active", "channel__channel_code")
    search_fields = ("name", "description", "webhook_url", "target_address")
    ordering_fields = ("id", "created_at", "updated_at")

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if getattr(user, "is_superuser", False):
            return queryset
        visibility = Q(project__in=projects_for(user))
        if getattr(user, "is_staff", False):
            # staff 可维护 project 为空的全局接收对象
            visibility |= Q(project__isnull=True)
        return queryset.filter(visibility)

    # -- permission helpers -------------------------------------------------
    def _require_write(self, project):
        user = self.request.user
        if project is None:
            if not getattr(user, "is_staff", False):
                raise BusinessError(
                    message="全局接收对象仅管理员可维护",
                    code="permission_denied",
                    status_code=403,
                )
            return
        require_project_role(user, project, "admin")

    def perform_create(self, serializer):
        self._require_write(serializer.validated_data.get("project"))
        serializer.save()

    def perform_update(self, serializer):
        current_project = getattr(serializer.instance, "project", None)
        new_project = serializer.validated_data.get("project", current_project)
        self._require_write(current_project)
        if new_project is not current_project:
            self._require_write(new_project)
        serializer.save()

    def perform_destroy(self, instance):
        self._require_write(instance.project)
        instance.delete()


class EmailConfigView(APIView):
    """Singleton SMTP config: GET / PUT / PATCH ``/api/notifications/email-config/``."""

    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [IsAuthenticated()]
        return [IsAuthenticated(), IsAdminUser()]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        config = EmailConfig.get_solo() or EmailConfig()
        return Response(EmailConfigSerializer(config).data)

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    def put(self, request):
        return self._write(request, partial=False)

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    def patch(self, request):
        return self._write(request, partial=True)

    def _write(self, request, partial):
        config = EmailConfig.get_solo()
        if config is None:
            config = EmailConfig()
        serializer = EmailConfigSerializer(
            config, data=request.data, partial=partial
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class NotificationTestView(APIView):
    """POST ``/api/notifications/test/`` -> actually send and write a log."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        receiver = self._resolve_receiver(request)
        channel_code = request.data.get("channel_code") or ""
        webhook_url = (
            request.data.get("webhook_url") or request.data.get("webhook") or ""
        )
        target_address = request.data.get("target_address") or ""
        title = request.data.get("title") or "通知测试"
        content = request.data.get("content") or request.data.get("markdown") or None

        if receiver is None:
            # 未指定项目接收对象时，是全局原始渠道测试，仅管理员可用。
            if not getattr(request.user, "is_staff", False):
                raise BusinessError(
                    message="仅管理员可测试全局渠道",
                    code="permission_denied",
                    status_code=403,
                )
            if not channel_code:
                raise BusinessError(
                    message="缺少 receiver_id 或 channel_code", code="missing_parameter"
                )

        result = send_test_notification(
            receiver=receiver,
            channel_code=channel_code or None,
            webhook_url=webhook_url,
            target_address=target_address,
            project=getattr(receiver, "project", None) if receiver else None,
            title=title,
            content=content,
        )
        return Response(result, status=status.HTTP_200_OK)

    def _resolve_receiver(self, request):
        receiver_id = request.data.get("receiver_id")
        if receiver_id in (None, ""):
            return None
        receiver = (
            NotificationReceiver.objects.select_related("project", "channel")
            .filter(pk=receiver_id)
            .first()
        )
        if receiver is None:
            raise BusinessError(
                message="通知接收对象不存在", code="not_found", status_code=404
            )
        user = request.user
        if getattr(user, "is_superuser", False):
            return receiver
        if receiver.project is None:
            if not getattr(user, "is_staff", False):
                raise BusinessError(
                    message="无权操作该接收对象",
                    code="permission_denied",
                    status_code=403,
                )
            return receiver
        require_project_role(user, receiver.project, "editor")
        return receiver


class NotificationLogViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Read-only notification audit logs."""

    queryset = NotificationLog.objects.select_related("project", "receiver")
    serializer_class = NotificationLogSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ("project", "status", "channel_code", "receiver", "scheduled_task_id")
    search_fields = ("title", "content", "scheduled_task_name", "error_message")
    ordering_fields = ("id", "created_at", "status")

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if getattr(user, "is_superuser", False):
            return queryset
        visibility = Q(project__in=projects_for(user))
        if getattr(user, "is_staff", False):
            # staff 也能看到全局渠道测试产生的日志（project 为空）
            visibility |= Q(project__isnull=True)
        return queryset.filter(visibility).distinct()
