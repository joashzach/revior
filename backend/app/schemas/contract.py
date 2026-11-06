"""Pydantic mirror of ``stranded-network-frontend-API-contract.md`` §4–§5 (exact field names)."""
from __future__ import annotations

from typing import Any, Literal

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, field_validator

PassengerState = Literal["REGISTERED", "BOOKED", "AFFECTED", "REQUESTED", "HELD", "CONFIRMED",
                         "WAITLISTED", "UNRESOLVED", "RESOLVED_ALT", "REOFFER"]
ServiceMode = Literal["local_train", "bus", "charter_bus", "shuttle"]
ServiceStatus = Literal["scheduled", "delayed", "cancelled", "running", "completed", "rerouted"]
AllocationStatus = Literal["held", "swap_held", "confirmed", "declined", "expired", "released"]
ChoiceRank = Literal["1", "2", "auto", "cascade", "claim", "swap"]
DisruptionType = Literal["cancellation", "delay", "closure"]
BatchStatus = Literal["open", "closed", "allocated"]
AlternativeType = Literal["LATER_SERVICE", "MULTI_LEG", "POD", "ALT_HUB", "WAIT_DELAYED"]
PodStatus = Literal["forming", "full", "confirmed", "departed", "cancelled"]
NeedsClass = Literal["accessible", "priority", "general"]
NodeKind = Literal["rail_station", "bus_stop", "hub_only"]


# ---- core ------------------------------------------------------------------------------------
# lenient format check (persona/seed addresses use the reserved .test TLD, which EmailStr rejects)
Email = Annotated[str, StringConstraints(strip_whitespace=True, max_length=254,
                                         pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]


class Needs(BaseModel):
    wheelchair: bool = False
    elderly: bool = False
    with_children: bool = False
    medical: bool = False
    connection_deadline_at: str | None = None


class NodeRef(BaseModel):
    id: int
    code: str
    name: str
    lat: float
    lng: float
    kind: NodeKind
    is_hub: bool
    is_default_hub: bool


class ServiceSummary(BaseModel):
    id: int
    code: str
    label: str
    mode: ServiceMode
    status: ServiceStatus
    delay_minutes: int
    depart_at: str
    arrive_at: str
    origin: NodeRef
    destination: NodeRef
    accessible: bool


class PassengerOut(BaseModel):
    id: int
    name: str
    email: str | None
    phone: str | None
    is_seeded: bool
    is_demo_persona: bool
    hub: NodeRef
    destination: NodeRef
    party_size: int
    needs: Needs
    allow_auto: bool
    state: PassengerState
    ticket_id: str
    affected_at: str | None


class Ticket(BaseModel):
    ticket_id: str
    service: ServiceSummary


class Leg(BaseModel):
    service: ServiceSummary
    from_: NodeRef = Field(alias="from", serialization_alias="from")
    to: NodeRef
    depart_at: str
    arrive_at: str
    has_seats: bool

    model_config = {"populate_by_name": True}


class Option(BaseModel):
    option_id: str
    request_service_id: int
    label: str
    mode: ServiceMode
    legs: list[Leg]
    depart_at: str
    eta_at: str
    transfers: int
    is_multi_leg: bool
    seats_left: int
    accessible_seats_left: int
    is_full: bool
    meets_deadline: bool
    accessible: bool


class BatchOut(BaseModel):
    id: int
    status: BatchStatus
    opens_at: str
    closes_at: str


class RequestOut(BaseModel):
    id: int
    batch: BatchOut
    choice1_service_id: int | None
    choice2_service_id: int | None
    any_fastest: bool


class AllocationOut(BaseModel):
    id: int
    service: ServiceSummary
    seat_count: int
    seats: list[str]
    choice_rank: ChoiceRank
    status: AllocationStatus
    is_primary: bool
    hold_expires_at: str | None
    score: float
    explanation: str


class WaitlistPosition(BaseModel):
    service_id: int
    label: str
    position: int
    total: int
    is_swap: bool


class PodMember(BaseModel):
    passenger_id: int
    name: str
    seat_count: int


class PodOut(BaseModel):
    id: int
    origin: NodeRef
    destination: NodeRef
    mode: Literal["cab", "auto"]
    capacity: int
    seats_taken: int
    status: PodStatus
    members: list[PodMember]
    route_km: float
    fare_total: float
    fare_per_seat: float


class Alternative(BaseModel):
    type: AlternativeType
    ref: str
    title: str
    description: str
    eta_at: str | None
    legs: list[Leg]
    pod: PodOut | None
    requires_allocation: bool


class MyStatus(BaseModel):
    state: PassengerState
    batch: BatchOut | None
    allocation: AllocationOut | None
    swap_offer: AllocationOut | None
    waitlist: list[WaitlistPosition]
    resolved_alternative: Alternative | None
    headline: str
    server_time: str


class Why(BaseModel):
    score: float
    breakdown: dict[str, float]
    explanation: str
    decision_explanation: str | None
    rule_version: int
    weights: dict[str, float]
    waitlist: list[WaitlistPosition]


class Persona(BaseModel):
    id: int
    title: str
    emoji: str
    summary: str
    destination: NodeRef
    party_size: int
    needs: Needs
    is_taken: bool


class NotificationOut(BaseModel):
    id: int
    template: str
    title: str
    body: str
    created_at: str
    read: bool


# ---- requests --------------------------------------------------------------------------------
class NeedsIn(BaseModel):
    wheelchair: bool = False
    elderly: bool = False
    with_children: bool = False
    medical: bool = False
    connection_deadline_at: str | None = None


class RegisterIn(BaseModel):
    scenario: str | None = None
    name: str = Field(min_length=1, max_length=120)
    email: Email
    password: str = Field(min_length=6, max_length=128)
    phone: str | None = None
    hub_node_id: int | None = None
    destination_node_id: int
    needs: NeedsIn = NeedsIn()
    party_size: int = Field(default=1, ge=1, le=6)
    allow_auto: bool = True


class LoginIn(BaseModel):
    scenario: str | None = None
    email: Email
    password: str


class QrLoginIn(BaseModel):
    token: str


class OpsLoginIn(BaseModel):
    password: str


class DemoClaimIn(BaseModel):
    scenario: str | None = None
    persona_id: int | None = None
    surprise: bool = False


class DemoSwitchIn(BaseModel):
    mode: Literal["next", "pick"]
    persona_id: int | None = None


class PatchMeIn(BaseModel):
    destination_node_id: int | None = None
    hub_node_id: int | None = None
    needs: NeedsIn | None = None
    party_size: int | None = Field(default=None, ge=1, le=6)
    allow_auto: bool | None = None


class RequestIn(BaseModel):
    choice1_service_id: int | None = None
    choice2_service_id: int | None = None
    any_fastest: bool = False


class AllocationActionIn(BaseModel):
    allocation_id: int | None = None


class SwapIn(BaseModel):
    service_id: int


class ClaimIn(BaseModel):
    service_id: int


class AltAcceptIn(BaseModel):
    type: AlternativeType
    ref: str


class PodCreateIn(BaseModel):
    destination_node_id: int
    mode: Literal["cab", "auto"]


class NotifReadIn(BaseModel):
    ids: list[int]


class HubsNearbyIn(BaseModel):
    scenario: str | None = None
    lat: float | None = None
    lng: float | None = None


class DisruptionIn(BaseModel):
    type: DisruptionType
    service_id: int | None = None
    edge_id: int | None = None
    delay_minutes: int | None = Field(default=None, ge=1, le=600)
    reason: str = ""


class AddServiceIn(BaseModel):
    label: str
    mode: Literal["charter_bus", "shuttle"]
    stop_node_ids: list[int] = Field(min_length=2)
    depart_in_minutes: int = Field(ge=0, le=720)
    total_seats: int = Field(ge=1, le=300)
    accessible_seats: int = Field(default=0, ge=0)

    @field_validator("accessible_seats")
    @classmethod
    def _acc(cls, v, info):
        if "total_seats" in info.data and v > info.data["total_seats"]:
            raise ValueError("accessible_seats cannot exceed total_seats")
        return v


class RunIn(BaseModel):
    mode: Literal["greedy", "ortools"] = "greedy"


class WeightsIn(BaseModel):
    weights: dict[str, float]


class OpenBookingIn(BaseModel):
    enabled: bool


class StressIn(BaseModel):
    requests: int = Field(default=1000, ge=1, le=5000)
    seats: int = Field(default=10, ge=1, le=200)


class ConfigPatch(BaseModel):
    batch_window_seconds: int | None = Field(default=None, ge=1, le=3600)
    hold_seconds: int | None = Field(default=None, ge=1, le=7200)
    auto_run_on_batch_close: bool | None = None
    delay_threshold_minutes: int | None = Field(default=None, ge=0, le=600)
    hub_radius_km: float | None = Field(default=None, gt=0, le=200)
    open_booking_enabled: bool | None = None
    sim_speed: float | None = Field(default=None, gt=0, le=1000)
    demo_mode: bool | None = None
    join_qr_mode: Literal["corner", "fullscreen", "hidden"] | None = None


class ScenarioConfig(BaseModel):
    batch_window_seconds: int
    hold_seconds: int
    auto_run_on_batch_close: bool
    delay_threshold_minutes: int
    hub_radius_km: float
    open_booking_enabled: bool
    sim_speed: float
    demo_mode: bool
    join_qr_mode: Literal["corner", "fullscreen", "hidden"]


# ---- responses -------------------------------------------------------------------------------
class HealthOut(BaseModel):
    status: str
    db: str
    version: str
    server_time: str


class ActiveScenarioOut(BaseModel):
    slug: str
    name: str
    default_hub: NodeRef
    join_url: str
    demo_mode: bool


class AuthOut(BaseModel):
    token: str
    passenger: PassengerOut


class RegisterOut(AuthOut):
    ticket: Ticket


class DemoClaimOut(AuthOut):
    persona: Persona


class TokenOut(BaseModel):
    token: str


class HubEntry(BaseModel):
    hub: NodeRef
    distance_km: float | None
    is_default: bool


class HubsNearbyOut(BaseModel):
    hubs: list[HubEntry]
    selected_hub_id: int
    reason: Literal["nearest", "default"]


class Items(BaseModel):
    items: list[Any]


class PersonaList(BaseModel):
    items: list[Persona]


class NodeList(BaseModel):
    items: list[NodeRef]


class TripDisruption(BaseModel):
    id: int
    type: DisruptionType
    reason: str
    created_at: str


class TripOut(BaseModel):
    ticket: Ticket
    disruption: TripDisruption | None
    headline: str


class OptionsOut(BaseModel):
    items: list[Option]
    batch: BatchOut | None


class AlternativesOut(BaseModel):
    items: list[Alternative]


class PodsOut(BaseModel):
    items: list[PodOut]


class LoginQrOut(BaseModel):
    url: str
    expires_at: str


class NotificationsOut(BaseModel):
    items: list[NotificationOut]


class Paginated(BaseModel):
    items: list[Any]
    page: int
    page_size: int
    total: int
