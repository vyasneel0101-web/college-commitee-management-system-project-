"""Changes to a committee's own details."""

from django.db import transaction

from audit import services as audit
from audit.models import AuditAction
from notifications.services import notify_committee


def _describe_changes(form, old_name):
    committee = form.instance
    changes = []
    if "name" in form.changed_data:
        changes.append(f"renamed from {old_name} to {committee.name}")
    if "code" in form.changed_data:
        changes.append(f"code changed to {committee.code}")
    if "description" in form.changed_data:
        changes.append("description updated")
    if "allows_multiple_members" in form.changed_data:
        changes.append(
            "now takes members" if committee.allows_multiple_members
            else "now takes one person in charge and no members"
        )
    if "is_active" in form.changed_data:
        changes.append("made active again" if committee.is_active else "made inactive")
    return changes


@transaction.atomic
def update_committee(*, form, actor, request=None):
    """
    Save edits to a committee's details and tell everyone on it what changed.

    Invariants: nothing is written, and nobody notified, when no field
    changed; the notification and the edit commit together.
    """
    if not form.changed_data:
        return form.instance
    old_name = type(form.instance).objects.values_list("name", flat=True).get(pk=form.instance.pk)
    changes = _describe_changes(form, old_name)
    committee = form.save()
    notify_committee(
        committee=committee,
        message=f"{committee.name}: committee details updated — " + "; ".join(changes) + ".",
    )
    audit.log(
        action=AuditAction.COMMITTEE_UPDATED,
        actor=actor,
        obj=committee,
        summary=f"{committee.name} updated: " + "; ".join(changes),
        detail={"fields": sorted(form.changed_data)},
        request=request,
    )
    return committee
