"""Project scoped permissions shared by all business modules."""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.common.api.api_exception_handler import BusinessError

ROLE_ORDER = {"viewer": 10, "editor": 20, "admin": 30, "owner": 40}
ROLE_LABELS = {
    "owner": "拥有者",
    "admin": "管理员",
    "editor": "编辑",
    "viewer": "只读",
}


def get_user_role(user, project):
    """Return the user's role on ``project`` (or None)."""
    if not user or not getattr(user, "is_authenticated", False):
        return None
    if getattr(user, "is_superuser", False):
        return "owner"
    if project is None:
        return None
    if project.owner_id == user.id:
        return "owner"
    from apps.projects.models import ProjectMember

    member = ProjectMember.objects.filter(project=project, user=user).first()
    return member.role if member else None


def role_at_least(role, minimum) -> bool:
    return ROLE_ORDER.get(role or "", 0) >= ROLE_ORDER.get(minimum, 0)


def resolve_project(obj):
    """Walk a model instance/queryset-ish object up to its project."""
    if obj is None:
        return None
    project = getattr(obj, "project", None)
    if project is not None:
        return project
    # Some models expose project through a parent relation.
    for attr in ("suite", "scenario", "test_case", "api_spec", "module"):
        parent = getattr(obj, attr, None)
        if parent is not None and parent is not obj:
            found = resolve_project(parent)
            if found is not None:
                return found
    return None


class ProjectRolePermission(BasePermission):
    """Map HTTP action -> minimum required project role.

    Subclasses / viewsets tune ``minimum_role_by_action``.
    """

    message = "没有操作权限"
    default_minimum_role = "editor"
    read_minimum_role = "viewer"
    minimum_role_by_action: dict[str, str] = {}

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        project = resolve_project(obj)
        if project is None:
            return True  # not project scoped (user profile, global config)
        return role_at_least(self.required_role(request, view), self.read_minimum_role) and _ok(
            get_user_role(request.user, project), self.required_role(request, view)
        )

    def required_role(self, request, view) -> str:
        action = getattr(view, "action", None)
        if action in self.minimum_role_by_action:
            return self.minimum_role_by_action[action]
        if request.method in SAFE_METHODS:
            return self.read_minimum_role
        return self.default_minimum_role


def _ok(role, minimum) -> bool:
    return role_at_least(role, minimum)


class IsProjectOwner(ProjectRolePermission):
    default_minimum_role = "owner"
    read_minimum_role = "owner"


class IsProjectAdmin(ProjectRolePermission):
    default_minimum_role = "admin"
    read_minimum_role = "viewer"


def require_project_role(user, project, minimum="editor"):
    role = get_user_role(user, project)
    if not role_at_least(role, minimum):
        raise BusinessError(
            message=f"需要 {ROLE_LABELS.get(minimum, minimum)} 及以上权限",
            code="permission_denied",
            status_code=403,
        )
    return role
