class ViewOnlyAdminMixin:
    """
    Admin for official records: browsable, never added, changed or deleted
    here. Orders and assignments change only through their services.
    """

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
