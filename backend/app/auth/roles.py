ADMIN = "Admin"

AUDITOR = "Auditor"

FINANCE = "Finance"

CENTER_MANAGER = "Center Manager"

CLUSTER_MANAGER = "Cluster Manager"

ZONAL_MANAGER = "Zonal Manager"

HALF_COUNTRY_MANAGER = "Half Country Manager"

# The confirmed real management chain, first-in-line to last:
#   Half Country Manager -> Zonal Manager -> Cluster Manager -> Center Manager
# No Regional Manager -- the organization doesn't have that level.
ALL_ROLES = (
    ADMIN,
    AUDITOR,
    FINANCE,
    CENTER_MANAGER,
    CLUSTER_MANAGER,
    ZONAL_MANAGER,
    HALF_COUNTRY_MANAGER,
)

# Role assigned to anyone who self-registers through the public /auth/register
# endpoint. Privileged roles (Admin, Finance, etc.) can only be granted by an
# existing Admin through an admin-only endpoint (P1) -- never by the user
# themselves at signup. Never remove this default without adding that
# admin-only promotion path first.
DEFAULT_SELF_REGISTER_ROLE = AUDITOR
