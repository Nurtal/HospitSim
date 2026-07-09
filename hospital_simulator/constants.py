"""Constants and enumerations for the simulation framework."""

from __future__ import annotations


class ServiceType:
    """Hospital services managed by the simulator."""

    EMERGENCY_DEPARTMENT = "ED"
    INTENSIVE_CARE_UNIT = "ICU"
    Ward = "ward"
    operating_rooms = "operating_roots"
    radiology = "radiology"
    outpatient_clinics = "outpatient_clinic"


class DispositionType:
    """Possible outcomes at the end of a patient's stay."""

    DISCHARGE_HOME = "discharge_home"
    DISCHARGE_ANOTHER_FACILITY = "discharge_another_facility"
    TRANSFER_TO_ICU = "transfer_to_icu"
    TRANSFER_TO_WARD = "transfer_to_ward"
    DEATH = "death"
