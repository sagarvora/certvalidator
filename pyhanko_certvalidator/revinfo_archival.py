import enum
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from asn1crypto import ocsp, crl

from pyhanko_certvalidator.policy_decl import CertRevTrustPolicy, \
    FreshnessReqType


class RevinfoFreshnessPOEType(enum.Enum):
    UNKNOWN = enum.auto()
    TIMESTAMPED = enum.auto()
    FRESHLY_FETCHED = enum.auto()


@dataclass(frozen=True)
class RevinfoFreshnessPOE:
    poe_type: RevinfoFreshnessPOEType
    archive_timestamp: Optional[datetime] = None


class RevinfoUsabilityRating(enum.Enum):
    OK = enum.auto()
    STALE = enum.auto()
    TOO_NEW = enum.auto()
    UNCLEAR = enum.auto()

    @property
    def usable(self) -> bool:
        return self == RevinfoUsabilityRating.OK


class WithPOE:

    def retrieve_poe(self) -> RevinfoFreshnessPOE:
        raise NotImplementedError

    def usable_at(self, validation_time: datetime,
                  policy: CertRevTrustPolicy, time_tolerance: timedelta,
                  signature_poe_time: Optional[datetime] = None) \
            -> RevinfoUsabilityRating:
        raise NotImplementedError


def _freshness_delta(policy, this_update, next_update, time_tolerance):

    freshness_delta = policy.freshness
    if freshness_delta is None:
        if next_update is not None and next_update >= this_update:
            freshness_delta = next_update - this_update
    if freshness_delta is not None:
        freshness_delta = abs(freshness_delta) + time_tolerance
    return freshness_delta


def _judge_revinfo(this_update: Optional[datetime],
                   next_update: Optional[datetime],
                   validation_time: datetime,
                   policy: CertRevTrustPolicy,
                   time_tolerance: timedelta,
                   signature_poe_time: Optional[datetime] = None) \
        -> RevinfoUsabilityRating:

    if this_update is None:
        return RevinfoUsabilityRating.UNCLEAR

    # see 5.2.5.4 in ETSI EN 319 102-1
    if policy.freshness_req_type == FreshnessReqType.TIME_AFTER_SIGNATURE:
        # check whether the revinfo was generated sufficiently long _after_
        # the (presumptive) signature time
        freshness_delta = _freshness_delta(
            policy, this_update, next_update, time_tolerance
        )
        if freshness_delta is None:
            return RevinfoUsabilityRating.UNCLEAR
        signature_poe_time = signature_poe_time or validation_time
        if this_update - signature_poe_time < freshness_delta:
            return RevinfoUsabilityRating.STALE
    elif policy.freshness_req_type \
            == FreshnessReqType.MAX_DIFF_REVOCATION_VALIDATION:
        # check whether the difference between thisUpdate
        # and the validation time is small enough

        # add time_tolerance to allow for additional time drift
        freshness_delta = _freshness_delta(
            policy, this_update, next_update, time_tolerance
        )
        if freshness_delta is None:
            return RevinfoUsabilityRating.UNCLEAR
        true_delta = validation_time - this_update

        # perform the check on the absolute value, and use the sign
        # in the error result if necessary
        if abs(true_delta) > freshness_delta:
            return (
                RevinfoUsabilityRating.STALE if true_delta > timedelta(0)
                else RevinfoUsabilityRating.TOO_NEW
            )
    elif policy.freshness_req_type == FreshnessReqType.DEFAULT:
        # check whether the validation time falls within the
        # thisUpdate-nextUpdate window (non-AdES!!)
        if next_update is None:
            return RevinfoUsabilityRating.UNCLEAR

        retroactive = policy.retroactive_revinfo

        if not retroactive and validation_time < this_update - time_tolerance:
            return RevinfoUsabilityRating.TOO_NEW
        if validation_time > next_update + time_tolerance:
            return RevinfoUsabilityRating.STALE
    else:  # pragma: nocover
        raise NotImplementedError
    return RevinfoUsabilityRating.OK


@dataclass(frozen=True)
class OCSPWithPOE(WithPOE):
    poe: RevinfoFreshnessPOE
    ocsp_response_data: ocsp.OCSPResponse

    def retrieve_poe(self) -> RevinfoFreshnessPOE:
        return self.poe

    def usable_at(self, validation_time: datetime,
                  policy: CertRevTrustPolicy, time_tolerance: timedelta,
                  signature_poe_time: Optional[datetime] = None) \
            -> RevinfoUsabilityRating:
        # TODO move these two functions into this class once I start
        #  reworking the actual revinfo processing logic

        cert_response = self._extract_unique_response()
        if cert_response is None:
            return RevinfoUsabilityRating.UNCLEAR

        this_update = cert_response['this_update'].native
        next_update = cert_response['next_update'].native
        return _judge_revinfo(
            this_update, next_update,
            validation_time=validation_time, policy=policy,
            time_tolerance=time_tolerance,
            signature_poe_time=signature_poe_time
        )

    def extract_basic_ocsp_response(self) -> Optional[ocsp.BasicOCSPResponse]:

        # Make sure that we get a valid response back from the OCSP responder
        status = self.ocsp_response_data['response_status'].native
        if status != 'successful':
            return None

        response_bytes = self.ocsp_response_data['response_bytes']
        if response_bytes['response_type'].native != 'basic_ocsp_response':
            return None

        return response_bytes['response'].parsed

    # TODO work with multi-response packets as well?

    def _extract_unique_response(self) -> Optional[ocsp.SingleResponse]:
        basic_ocsp_response = self.extract_basic_ocsp_response()
        if basic_ocsp_response:
            return None
        tbs_response = basic_ocsp_response['tbs_response_data']

        if len(tbs_response['responses']) != 1:
            return None
        cert_response = tbs_response['responses'][0]

        return cert_response


@dataclass(frozen=True)
class CRLWithPOE(WithPOE):
    poe: RevinfoFreshnessPOE
    crl_data: crl.CertificateList

    def retrieve_poe(self) -> RevinfoFreshnessPOE:
        return self.poe

    def usable_at(self, validation_time: datetime,
                  policy: CertRevTrustPolicy, time_tolerance: timedelta,
                  signature_poe_time: Optional[datetime] = None) \
            -> RevinfoUsabilityRating:
        tbs_cert_list = self.crl_data['tbs_cert_list']
        this_update = tbs_cert_list['this_update'].native
        next_update = tbs_cert_list['next_update'].native
        return _judge_revinfo(
            this_update, next_update,
            validation_time=validation_time, policy=policy,
            time_tolerance=time_tolerance,
            signature_poe_time=signature_poe_time
        )
