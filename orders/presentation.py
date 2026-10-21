"""Read-only order register rows; document snapshots stay authoritative."""

from django.utils.translation import gettext as _

from .models import OrderType


def _person(snapshot=None, assignment=None):
    """Use the saved document identity, with live details only for older contexts."""
    if snapshot is not None:
        detail = ", ".join(
            str(snapshot[key])
            for key in ("designation", "department")
            if snapshot.get(key)
        )
        return {
            "name": snapshot.get("name", ""),
            "salutation": snapshot.get("salutation", ""),
            "role": snapshot.get("role", ""),
            "detail": detail,
        }
    return {
        "name": assignment.holder_name,
        "salutation": assignment.holder.salutation,
        "role": str(assignment.get_role_display()),
        "detail": assignment.holder_detail,
    }


def _source_people(order):
    """Return named recipients without querying when the view has prefetched relations."""
    context = order.render_context
    if order.order_type == OrderType.RELINQUISHMENT and context.get("removed"):
        return [_person(snapshot) for snapshot in context["removed"]]
    relation = (
        order.created_assignments
        if order.order_type == OrderType.ASSIGNMENT
        else order.ended_assignments
    )
    assignments = list(relation.all())
    snapshots = context.get("member_list", []) if order.order_type == OrderType.ASSIGNMENT else []
    if assignments:
        people = []
        for index, assignment in enumerate(assignments):
            # Creation order (pk) matches the document's member-list sequence.
            snapshot = snapshots[index] if len(snapshots) == len(assignments) else None
            person = _person(snapshot, assignment)
            person.update(status=assignment.status, label=str(assignment.get_status_display()))
            people.append(person)
        return people
    if snapshots:
        return [_person(snapshot) for snapshot in snapshots]
    if context.get("faculty_name"):
        return [
            _person({
                "name": context["faculty_name"],
                "salutation": context.get("faculty_salutation", ""),
                "designation": context.get("faculty_designation", ""),
                "department": context.get("faculty_department", ""),
                "role": context.get("assignment_role", ""),
            })
        ]
    return []


def register_recipients(order):
    """Pair each recipient with a current assignment status or historical order effect.

    Invariant: no writes or changes to saved contexts/documents. Corrections use
    saved identities; unavailable historical details are never guessed by name.
    """
    if order.order_type == OrderType.CORRIGENDUM:
        sources = list(order.cancels.all())
        people = []
        for key, label, tag, source_type in (
            ("withdrawn", _("Withdrawn"), "pill-cancelled", OrderType.ASSIGNMENT),
            ("restored", _("Restored"), "pill-active", OrderType.RELINQUISHMENT),
        ):
            candidates = [
                person
                for source in sources
                if source.order_type == source_type
                for person in _source_people(source)
            ]
            for name in order.render_context.get(key, []):
                match = next((i for i, person in enumerate(candidates) if person["name"] == name), None)
                person = candidates.pop(match) if match is not None else _person({"name": name})
                people.append({**person, "label": label, "tag": tag})
        return people

    people = _source_people(order)
    for person in people:
        if order.order_type == OrderType.RELINQUISHMENT:
            person["label"] = _("Removal cancelled") if order.is_cancelled else _("Relinquished")
            person["tag"] = "pill-cancelled" if order.is_cancelled else "pill-history"
        else:
            person["label"] = person.get("label", _("See order details"))
            person["tag"] = {
                "ACTIVE": "pill-active",
                "CANCELLED": "pill-cancelled",
            }.get(person.get("status"), "pill-history")
    return people
