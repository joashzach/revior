"""GtfsRtAdapter - documented stub, intentionally not implemented (PRD F22).

A real implementation would poll a GTFS-Realtime feed (TripUpdates / ServiceAlerts), map
trip ids to ``services.code`` and translate delays/cancellations into ``stream_service_updates``
events that the disruption service consumes exactly like operator actions.
"""
from app.adapters.base import TransportDataAdapter


class GtfsRtAdapter(TransportDataAdapter):
    def load_network(self):
        raise NotImplementedError("GTFS-RT adapter is a documented extension point")

    def load_services(self):
        raise NotImplementedError

    def stream_service_updates(self):
        raise NotImplementedError
