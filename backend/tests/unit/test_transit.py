import pytest

from app.core.errors import AppError
from app.services.transit import build_transit_request


def test_kmb_eta_request_uses_fixed_provider_and_encoded_path() -> None:
    request = build_transit_request(
        operator="kmb",
        stop_id="stop/id",
        route="960",
        service_type=2,
        language="tc",
    )

    assert request.url == "https://data.etabus.gov.hk/v1/transport/kmb/eta/stop%2Fid/960/2"
    assert request.params == {"lang": "tc"}


def test_mtr_eta_request_uses_fixed_schedule_endpoint() -> None:
    request = build_transit_request(operator="mtr", line="ISL", station="ADM")

    assert request.url == "https://rt.data.gov.hk/v1/transport/mtr/getSchedule.php"
    assert request.params == {"line": "ISL", "sta": "ADM", "lang": "en"}


def test_citybus_and_gmb_eta_requests_use_fixed_provider_hosts() -> None:
    citybus = build_transit_request(
        operator="ctb",
        stop_id="stop-1",
        route="A11",
        company_id="nwfb",
        language="tc",
    )
    gmb = build_transit_request(operator="gmb", stop_id="stop-2")

    assert citybus.url.startswith("https://rt.data.gov.hk/v1.2/transport/citybus/eta/nwfb/")
    assert citybus.params == {"lang": "tc"}
    assert gmb.url == "https://data.etagmb.gov.hk/eta/stop/stop-2"


def test_transit_request_rejects_missing_provider_inputs() -> None:
    with pytest.raises(AppError) as error:
        build_transit_request(operator="mtr", line="ISL")

    assert error.value.error_code == "invalid_transit_query"