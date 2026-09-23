"""The explicit applicant status transition table.

Deliberately a plain Python dict of allowed `from -> {to, ...}` moves, not a
general state-machine library or a database-stored table -- this pipeline
is fixed and small (module scope), and an explicit, readable table is
easier to audit against the agreed pipeline than a more general mechanism
would be. Enforced by `app.routers.status.transition_applicant`, which
rejects anything not in this table with a 422 naming the invalid
transition (never a 500) -- see that router for the enforcement and the
database write.

Transition table (module 02 scope):

    IMPORTED -> APPLIED
    APPLIED -> IN_PROCESS
    IN_PROCESS -> ON_HOLD
    ON_HOLD -> IN_PROCESS
    IN_PROCESS -> ADMISSION_OFFERED
    ADMISSION_OFFERED -> ADMISSION_TAKEN
    {APPLIED, IN_PROCESS, ON_HOLD, ADMISSION_OFFERED} -> REJECTED
    {APPLIED, IN_PROCESS, ON_HOLD, ADMISSION_OFFERED} -> WITHDRAWN

`REJECTED` and `WITHDRAWN` are terminal: no entry for either as a
dictionary key below, so any transition attempted *from* one of them finds
no allowed set at all and is rejected the same way an unrecognized
`from_status` would be. `ADMISSION_TAKEN` is likewise terminal for this
module's status pipeline -- the applicant's story continues in
`finance_record`/`payment_claim` from that point, not through further
`application_status_event` rows. `IMPORTED` has no direct path to
`REJECTED`/`WITHDRAWN` in this table -- the module prompt lists only
`APPLIED, IN_PROCESS, ON_HOLD, ADMISSION_OFFERED` as the sources those two
terminal states are reachable from, so an application must move to
`APPLIED` at minimum before it can be rejected or withdrawn.
"""

from app.models.enums import ApplicationStatus

ALLOWED_TRANSITIONS: dict[ApplicationStatus, frozenset[ApplicationStatus]] = {
    ApplicationStatus.IMPORTED: frozenset({ApplicationStatus.APPLIED}),
    ApplicationStatus.APPLIED: frozenset(
        {ApplicationStatus.IN_PROCESS, ApplicationStatus.REJECTED, ApplicationStatus.WITHDRAWN}
    ),
    ApplicationStatus.IN_PROCESS: frozenset(
        {
            ApplicationStatus.ON_HOLD,
            ApplicationStatus.ADMISSION_OFFERED,
            ApplicationStatus.REJECTED,
            ApplicationStatus.WITHDRAWN,
        }
    ),
    ApplicationStatus.ON_HOLD: frozenset(
        {
            ApplicationStatus.IN_PROCESS,
            ApplicationStatus.REJECTED,
            ApplicationStatus.WITHDRAWN,
        }
    ),
    ApplicationStatus.ADMISSION_OFFERED: frozenset(
        {
            ApplicationStatus.ADMISSION_TAKEN,
            ApplicationStatus.REJECTED,
            ApplicationStatus.WITHDRAWN,
        }
    ),
    # ADMISSION_TAKEN, REJECTED, WITHDRAWN: deliberately absent as keys --
    # all three are terminal, so .get(status, frozenset()) below correctly
    # finds no allowed destinations for any of them.
}


def is_transition_allowed(from_status: ApplicationStatus, to_status: ApplicationStatus) -> bool:
    return to_status in ALLOWED_TRANSITIONS.get(from_status, frozenset())
