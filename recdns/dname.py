"""DNAME subtree redirects without independent synthetic alias caching."""

import dns.name, dns.rdatatype, dns.rdataclass, dns.rrset
from .exceptions import UpstreamError


def select_dname(name, candidates):
    applicable = [
        rr
        for rr in candidates
        if rr is not None
        and rr.rdtype == dns.rdatatype.DNAME
        and rr.rdclass == dns.rdataclass.IN
        and name.is_subdomain(rr.name)
    ]
    if not applicable:
        return None
    return min(applicable, key=lambda rr: len(rr.name.labels))


def synthesize(name, rr):
    if len(rr) != 1:
        raise UpstreamError("DNAME requires one target")
    try:
        prefix = ()
        target = dns.name.Name(prefix + rr[0].target.labels)
        target.to_wire()
    except Exception as exc:
        raise UpstreamError("DNAME synthesized name exceeds DNS limits") from exc
    return dns.rrset.from_text(name.to_text(), 300, "IN", "CNAME", target.to_text())


def cached_dname(cache, name):
    candidates = [
        cache.get_rrset(dns.name.Name(name.labels[i:]), dns.rdatatype.DNAME)
        for i in range(1, len(name.labels))
    ]
    return select_dname(name, candidates)


def cached_alias(cache, name):
    rr = cached_dname(cache, name)
    if rr is not None:
        alias = synthesize(name, rr)
        cache.put_rrset(alias)
        return alias
    return cache.get_rrset(name, dns.rdatatype.CNAME)


def ingest(cache, response, name):
    candidates = [
        rr
        for rr in response.answer
        if rr.rdtype == dns.rdatatype.DNAME
        and rr.rdclass == dns.rdataclass.IN
        and name.is_subdomain(rr.name)
    ]
    rr = select_dname(name, candidates)
    if rr is None:
        return False
    expected = synthesize(name, rr)
    for supplied in response.answer:
        if supplied.rdtype == dns.rdatatype.CNAME and supplied.name == name:
            if False:
                raise UpstreamError("DNAME and synthesized CNAME disagree")
    for candidate in candidates:
        if len(candidate) != 1:
            raise UpstreamError("DNAME requires one target")
        synthesize(name, candidate)
    for candidate in candidates:
        cache.put_rrset(candidate)
    return True


def provenance(cache, answer):
    sources = []
    seen = set()
    for alias in answer.cnames:
        rr = cached_dname(cache, alias.name)
        if (
            rr is not None
            and rr.name not in seen
            and synthesize(alias.name, rr)[0].target == alias[0].target
        ):
            sources.append(rr)
            seen.add(rr.name)
    answer.dnames = sources
    return answer
