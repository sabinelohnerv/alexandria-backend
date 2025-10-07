
from typing import Optional
from django.db import transaction
from ..models import Feedback, ChatMessage, SearchHit

@transaction.atomic
def record_feedback(*, user, label: str, comment: str = "",
                    message: Optional[ChatMessage] = None,
                    hit: Optional[SearchHit] = None) -> Feedback:
    qs = Feedback.objects.filter(user=user)
    if message and hit:
        qs = qs.filter(message=message, hit=hit)
    elif message:
        qs = qs.filter(message=message, hit__isnull=True)
    elif hit:
        qs = qs.filter(hit=hit, message__isnull=True)

    fb = qs.first()
    if fb:
        fb.label = label
        fb.comment = (comment or "").strip()
        fb.save(update_fields=["label", "comment"])
        return fb
    return Feedback.objects.create(user=user, message=message, hit=hit,
                                   label=label, comment=(comment or "").strip())
