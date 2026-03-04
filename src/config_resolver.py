from dataclasses import dataclass

import addressing
import domain_settings


@dataclass(frozen=True)
class DomainContext:
    # Resolved per-domain configuration with env-first precedence.
    domain: str | None
    settings: domain_settings.DomainSettings | None
    failure_notification: str | None
    failback_address: str | None


def resolve_domain_context(*values: str | None) -> DomainContext:
    # Resolve domain settings using env vars first, then Azure Table fallback.
    domain_hint = addressing.extract_domain_hint(*values)
    if not domain_hint:
        return DomainContext(
            domain=None,
            settings=None,
            failure_notification=None,
            failback_address=None,
        )

    settings = domain_settings.lookup_domain_settings(domain_hint)
    return DomainContext(
        domain=domain_hint,
        settings=settings,
        failure_notification=addressing.lookup_failure_notification_address(domain_hint, settings),
        failback_address=addressing.lookup_failback_address(domain_hint),
    )
