#!/usr/bin/env python3
"""
MISMO Bridge MCP — CSOAI Layer-0 legacy-bridge family.
Bridge MISMO mortgage/real-estate-finance XML to ONE OS: parse → validate → map → govern
(TRID/RESPA · ECOA fair lending · GDPR · EU AI Act if automated underwriting). Sibling of cobol-bridge-mcp.
Tools: parse_mismo · validate_mismo · map_to_modern · govern_mortgage
"""
from mcp.server.mcpserver import MCPServer as FastMCP  # mcp 2.x: FastMCP renamed MCPServer
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import xml.etree.ElementTree as ET

mcp = FastMCP("MISMO Bridge", instructions="Bridge MISMO mortgage data to ONE OS — parse, validate, map, govern (TRID / ECOA / fair lending).")

import hashlib as _hl, time as _t, json as _j, os as _os
_SIGIL_LOG = _os.environ.get("SIGIL_LOG", _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "bridge_sigil.log"))
def _sigil(op, body):
    try:
        prev = ""
        if _os.path.exists(_SIGIL_LOG):
            with open(_SIGIL_LOG) as f:
                ls = f.readlines()
                if ls: prev = _j.loads(ls[-1]).get("digest", "")
        ts = int(_t.time()); dg = _hl.sha256(f"{op}|{ts}|{prev[:8]}|{body}".encode()).hexdigest()[:16]
        _os.makedirs(_os.path.dirname(_SIGIL_LOG), exist_ok=True)
        with open(_SIGIL_LOG, "a") as f: f.write(_j.dumps({"ts": ts, "op": op, "body": body, "prev_digest": prev, "digest": dg}) + "\n")
        return dg
    except Exception: return ""


def _local(t): return t.split("}", 1)[-1]
def _find(root, *names):
    for el in root.iter():
        if _local(el.tag) in names and (el.text or "").strip():
            return el.text.strip()
    return None


class MISMOParsed(BaseModel):
    has_deal: bool = False
    loan_amount: Optional[str] = None
    loan_purpose: Optional[str] = None
    has_borrower: bool = False
    has_property: bool = False
    has_pii: bool = False
    elements: int = 0


@mcp.tool()
def parse_mismo(xml: str) -> MISMOParsed:
    """Parse a MISMO mortgage XML; extract loan amount/purpose + borrower/property/PII presence."""
    root = ET.fromstring(xml)
    names = [_local(e.tag) for e in root.iter()]
    return MISMOParsed(
        has_deal=any(n in names for n in ("DEAL", "DEALS", "DEAL_SET")),
        loan_amount=_find(root, "BaseLoanAmount", "LoanAmount", "NoteAmount"),
        loan_purpose=_find(root, "LoanPurposeType", "LoanPurpose"),
        has_borrower=any(n in names for n in ("BORROWER", "PARTY", "INDIVIDUAL")),
        has_property=any(n in names for n in ("PROPERTY", "COLLATERAL", "SUBJECT_PROPERTY")),
        has_pii=any(n in names for n in ("TaxpayerIdentifier", "SSN", "FirstName", "BirthDate")),
        elements=len(names),
    )


class Validation(BaseModel):
    valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


@mcp.tool()
def validate_mismo(xml: str) -> Validation:
    """Validate a MISMO message (well-formed + has a DEAL + a loan amount)."""
    try:
        p = parse_mismo(xml)
    except ET.ParseError as e:
        return Validation(valid=False, errors=[f"XML not well-formed: {e}"])
    errors, warnings = [], []
    if not p.has_deal: warnings.append("No DEAL container detected")
    if not p.loan_amount: errors.append("No loan amount found")
    return Validation(valid=not errors, errors=errors, warnings=warnings)


@mcp.tool()
def map_to_modern(xml: str) -> Dict[str, Any]:
    """Map a MISMO mortgage record to a modern loan-application object for ONE OS."""
    p = parse_mismo(xml)
    return {"source": "MISMO", "loan_amount": p.loan_amount, "purpose": p.loan_purpose,
            "has_borrower": p.has_borrower, "has_property": p.has_property, "target": "modern loan event"}


class Governance(BaseModel):
    risk_flags: List[str] = Field(default_factory=list)
    frameworks: List[str] = Field(default_factory=list)
    attestable: bool = True
    note: str = ""


@mcp.tool()
def govern_mortgage(xml: str) -> Governance:
    """Governance: mortgage conduct + fair-lending + data surface (attestable for CSOAI)."""
    _sigil("G", "mismo|govern_mortgage")
    p = parse_mismo(xml)
    flags = ["Fair-lending: no disparate impact (ECOA) — if any model scores the applicant, it's high-risk (EU AI Act Annex III / Colorado AI Act)"]
    if p.has_pii:
        flags.append("PII present (SSN/DOB) — encrypt + minimise; GLBA Safeguards + GDPR")
    if p.loan_amount:
        flags.append("TRID/RESPA disclosure timing + accuracy on the loan terms")
    return Governance(risk_flags=flags,
                      frameworks=["MISMO", "TRID / RESPA", "ECOA (fair lending)", "GLBA", "GDPR", "EU AI Act Annex III (creditworthiness)"],
                      note="CSOAI governs the bridge: loan-decision lineage SIGIL-signed = an auditable fair-lending trail.")


# ---------------------------------------------------------------------------
# MCP 2026-07-28 wire - header-add migration (2026-10-08)
# ---------------------------------------------------------------------------
# stdio carries no HTTP headers, so Mcp-Method / Mcp-Name are not applicable to
# this transport at runtime. When mismo-bridge-mcp is exposed over HTTP, route the ingress
# through the vendored mcp2026_shim (ShimASGI): it validates Mcp-Method /
# Mcp-Name, injects params._meta.protocolVersion = "2026-07-28" into every
# request, strips Mcp-Session-Id and answers legacy initialize / server-discover
# locally (the session header is never emitted - stateless wire).
# Refs: MIGRATION_NOTE.md, MCP_2026_WIRE_MIGRATION_PLAN_2026-10-07.md (3) + (4).
# ---------------------------------------------------------------------------


def http_app():
    """ASGI app for HTTP exposure, wrapped in the 2026-07-28 wire shim.

    stdio (``mcp.run()``) needs no shim; this is the enable path once the
    server is fronted by an HTTP transport. Bodies are buffered, so responses
    are requested in JSON mode rather than SSE.
    """
    from mcp2026_shim import WIRE_2026, ShimASGI, ShimConfig

    return ShimASGI(
        mcp.streamable_http_app(json_response=True),
        ShimConfig(
            protocol_version=WIRE_2026,
            server_info={"name": "mismo-bridge-mcp", "version": "0.1.0"},
        ),
    )


def main():
    mcp.run()


if __name__ == "__main__":
    main()
