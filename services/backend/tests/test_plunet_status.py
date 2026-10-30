import pytest

from app.domain.enums import TaskStatus
from app.domain.plunet_status import plunet_status_name, task_status_from_plunet


@pytest.mark.parametrize(
    ("plunet", "expected"),
    [
        ("IN_PREPERATION", TaskStatus.PENDING),
        ("REQUESTED", TaskStatus.WAITING),
        ("ASSIGNED_WAITING", TaskStatus.WAITING),
        ("IN_PROGRESS", TaskStatus.RUNNING),
        ("DELIVERED", TaskStatus.DONE),
        ("APPROVED", TaskStatus.DONE),
        ("PAYED", TaskStatus.DONE),
        ("CANCELED", TaskStatus.CANCELLED),
        (1, TaskStatus.RUNNING),
        ("7", TaskStatus.WAITING),
    ],
)
def test_task_status_from_plunet(plunet, expected):
    assert task_status_from_plunet(plunet) == expected


def test_overdue_is_a_flag_not_a_state():
    assert task_status_from_plunet("OVERDUE") is None
    assert plunet_status_name(13) == "OVERDUE"
