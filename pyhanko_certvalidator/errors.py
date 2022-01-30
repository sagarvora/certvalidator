# coding: utf-8
from typing import TypeVar

from pyhanko_certvalidator._state import ValProcState


class PathError(Exception):

    pass


class PathBuildingError(PathError):

    pass


class CertificateFetchError(PathBuildingError):
    pass


class DuplicateCertificateError(PathError):

    pass


class CRLValidationError(Exception):

    pass


class CRLNoMatchesError(CRLValidationError):

    pass


class CRLFetchError(CRLValidationError):
    pass


class CRLValidationIndeterminateError(CRLValidationError):

    @property
    def failures(self):
        return self.args[1]


class OCSPValidationError(Exception):

    pass


class OCSPNoMatchesError(OCSPValidationError):

    pass


class OCSPValidationIndeterminateError(OCSPValidationError):

    @property
    def failures(self):
        return self.args[1]


class OCSPFetchError(OCSPValidationError):
    pass


class ValidationError(Exception):

    pass


TPathErr = TypeVar('TPathErr', bound='PathValidationError')


class PathValidationError(ValidationError):

    @classmethod
    def from_state(cls, msg, proc_state: ValProcState) -> TPathErr:
        return cls(
            msg,
            is_ee_cert=proc_state.is_ee_cert,
            is_side_validation=proc_state.is_side_validation
        )

    def __init__(self, msg, *, is_ee_cert: bool, is_side_validation: bool):
        self.is_ee_cert = is_ee_cert
        self.is_side_validation = is_side_validation
        self.failure_msg = msg
        super().__init__(msg)


class RevokedError(PathValidationError):

    pass


class ExpiredError(PathValidationError):
    pass


class NotYetValidError(PathValidationError):
    pass


class InvalidCertificateError(PathValidationError):

    def __init__(self, msg, is_ee_cert=True, is_side_validation=False):
        super().__init__(
            msg, is_ee_cert=is_ee_cert, is_side_validation=is_side_validation
        )


class InvalidAttrCertificateError(InvalidCertificateError):
    pass
