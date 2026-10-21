"""Read-only order register rows; document snapshots stay authoritative."""

from django.utils.translation import gettext_lazy as _

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


def _describe_change(order, person, action):
    """Describe this order's action, independently of a later assignment status."""
    messages = {
        "appointed": (
            _("%(name)s appointed as %(role)s to %(committee)s."),
            _("%(name)s appointed to %(committee)s."),
            _("Appointed"), "pill-correction",
        ),
        "removed": (
            _("%(name)s removed as %(role)s from %(committee)s."),
            _("%(name)s removed from %(committee)s."),
            _("Removed"), "pill-cancelled",
        ),
        "withdrawn": (
            _("The appointment of %(name)s as %(role)s to %(committee)s was withdrawn."),
            _("The appointment of %(name)s to %(committee)s was withdrawn."),
            _("Withdrawn"), "pill-cancelled",
        ),
        "restored": (
            _("%(name)s restored as %(role)s to %(committee)s."),
            _("%(name)s restored to their previous assignment in %(committee)s."),
            _("Restored"), "pill-active",
        ),
    }
    with_role, without_role, label, tag = messages[action]
    person.update(
        summary=(with_role if person["role"] else without_role) % {
            "name": " ".join(filter(None, (person["salutation"], person["name"]))),
            "role": person["role"],
            "committee": (
                order.render_context.get("committee_name") or order.committee.name
            ).rstrip(" ,;:."),
        },
        action_label=label,
        action_tag=tag,
    )


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
                person = {**person, "label": label, "tag": tag}
                _describe_change(order, person, key)
                people.append(person)
        return people

    people = _source_people(order)
    for person in people:
        if order.order_type == OrderType.RELINQUISHMENT:
            _describe_change(order, person, "removed")
            person["label"] = _("Removal cancelled") if order.is_cancelled else _("Relinquished")
            person["tag"] = "pill-cancelled" if order.is_cancelled else "pill-history"
        else:
            _describe_change(order, person, "appointed")
            person["label"] = person.get("label", _("See order details"))
            person["tag"] = {
                "ACTIVE": "pill-active",
                "CANCELLED": "pill-cancelled",
            }.get(person.get("status"), "pill-history")
    return people


def register_change_notes(order):
    """Explain supersession/cancellation using recorded facts, without any writes."""
    context = order.render_context
    notes = []
    previous = context.get("previous_holder_name")
    if order.order_type == OrderType.ASSIGNMENT and previous:
        notes.append({
            "label": _("Superseded"),
            "tag": "pill-history",
            "message": _("This order superseded the previous assignment of %(name)s.")
            % {"name": previous},
        })
    if order.order_type == OrderType.CORRIGENDUM and context.get("cancelled_order_no"):
        notes.append({
            "label": _("Order cancelled"),
            "tag": "pill-cancelled",
            "message": _("Order %(number)s was cancelled by this correction.")
            % {"number": context["cancelled_order_no"]},
            "reason": context.get("cancellation_reason", ""),
        })
    if order.is_cancelled:
        message = _("This order was later cancelled.")
        if order.cancelled_by_order_id:
            message = _("This order was later cancelled by order %(number)s.") % {
                "number": order.cancelled_by_order.order_no,
            }
        notes.append({
            "label": _("Later cancelled"),
            "tag": "pill-cancelled",
            "message": message,
        })
    return notes
