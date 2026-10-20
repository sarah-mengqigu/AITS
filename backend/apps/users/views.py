from django.contrib.auth import get_user_model
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.serializers import (
    ChangePasswordSerializer,
    LoginSerializer,
    RegisterSerializer,
    UserBriefSerializer,
    UserSerializer,
    issue_tokens,
)

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(issue_tokens(user), status=status.HTTP_201_CREATED)


class LoginView(generics.GenericAPIView):
    serializer_class = LoginSerializer
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        ip = request.META.get("REMOTE_ADDR")
        if ip:
            user.last_login_ip = ip
            user.save(update_fields=["last_login_ip"])
        return Response(issue_tokens(user))


class LogoutView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        refresh = request.data.get("refresh")
        if not refresh:
            return Response({"detail": "未提供 refresh token"}, status=400)
        try:
            RefreshToken(refresh).blacklist()
        except TokenError:
            return Response({"detail": "token 已失效"}, status=400)
        return Response({"detail": "已退出登录"})


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class ChangePasswordView(generics.GenericAPIView):
    serializer_class = ChangePasswordSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "密码修改成功"})


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """Directory of users - readable by any authenticated user."""

    queryset = User.objects.filter(is_active=True)
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    search_fields = ("username", "email", "nickname", "department")
    ordering_fields = ("date_joined", "username")
    filterset_fields = ("is_active", "department")

    def get_serializer_class(self):
        if self.action == "brief":
            return UserBriefSerializer
        return UserSerializer

    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated])
    def brief(self, request):
        users = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(users)
        serializer = UserBriefSerializer(page if page is not None else users, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @action(detail=False, methods=["post"], permission_classes=[IsAdminUser])
    def create_user(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "创建成功"}, status=status.HTTP_201_CREATED)
