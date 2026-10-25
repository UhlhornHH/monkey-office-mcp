#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MonKey Office Connect MCP-Server

A local stdio-MCP server for Hermes Agent (or any MCP-compatible client).
Provides read and write access to MonKey Office via the Connect JSON-API.

Configuration (Environment Variables):
    MONKEY_API_URL      Connect endpoint (default: http://127.0.0.1:8084/monkeyOfficeConnectJSON)
    MONKEY_API_USER     API username (required)
    MONKEY_API_PASS     API password (required)
    MONKEY_FIRMA_NAME   The name of the database/company to use (required)
    MONKEY_APP_PATH     Path to MonKey Office 2026.app (default: /Applications/MonKey Office 2026.app)
    MONKEY_LOG_FILE     Path to log file (default: /tmp/monkey_office_mcp.log)

Requirements:
    pip install mcp requests
"""

import os
import sys
import json
import base64
import logging
import re
import plistlib
from pathlib import Path
from typing import Optional

import requests
from requests.auth import HTTPBasicAuth
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Configuration & Defaults
# ---------------------------------------------------------------------------
API_URL = os.environ.get("MONKEY_API_URL", "http://127.0.0.1:8084/monkeyOfficeConnectJSON")
API_USER = os.environ.get("MONKEY_API_USER", "")
API_PASS = os.environ.get("MONKEY_API_PASS", "")
FIRMA_NAME = os.environ.get("MONKEY_FIRMA_NAME", "")
APP_PATH = Path(os.environ.get("MONKEY_APP_PATH", "/Applications/MonKey Office 2026.app"))
LOG_FILE = os.environ.get("MONKEY_LOG_FILE", "/tmp/monkey_office_mcp.log")

REQUIRED_BUNDLE_NAME_MARKER = "2026"

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stderr),
    ],
)
logger = logging.getLogger("monkey-office-mcp")

# Global state for session and auth
_SESSION: Optional[requests.Session] = None
_AUTH: Optional[HTTPBasicAuth] = None
_FIRMA_ID: str = ""

# ---------------------------------------------------------------------------
# Validation & Connectivity
# ---------------------------------------------------------------------------
def verify_monkey_office_version() -> None:
    """Verify that MonKey Office 2026 is installed."""
    plist_path = APP_PATH / "Contents" / "Info.plist"
    if not plist_path.exists():
        logger.warning(f"MonKey Office 2026 not found at {APP_PATH}. Skipping version check.")
        return

    try:
        info = plistlib.load(plist_path.open("rb"))
    except Exception as exc:
        logger.warning(f"Could not read Info.plist: {exc}")
        return

    bundle_name = info.get("CFBundleName", "")
    if REQUIRED_BUNDLE_NAME_MARKER not in bundle_name:
        logger.warning(f"Installed MonKey Office version '{bundle_name}' might not be 2026.")
    else:
        logger.info(f"MonKey Office version confirmed: {bundle_name}")

def get_auth() -> HTTPBasicAuth:
    """Create HTTPBasicAuth from environment variables."""
    global _AUTH
    if _AUTH is not None:
        return _AUTH
    
    if not API_USER or not API_PASS:
        raise RuntimeError("Environment variables MONKEY_API_USER and MONKEY_API_PASS must be set.")
    
    _AUTH = HTTPBasicAuth(API_USER, API_PASS)
    return _AUTH

def get_session() -> requests.Session:
    """Returns a shared requests session."""
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
    return _SESSION

def get_firma_id() -> str:
    """Resolve the Firma_ID for the configured company name."""
    global _FIRMA_ID
    if _FIRMA_ID:
        return _FIRMA_ID

    if not FIRMA_NAME:
        raise RuntimeError("Environment variable MONKEY_FIRMA_NAME must be set.")

    result = api_call({"firmaList": ""}, firma_id="")
    firmen = _extract_list(result, "firmaListResponse", "FirmaListItem")

    for firma in firmen:
        if firma.get("Bezeichnung") == FIRMA_NAME:
            _FIRMA_ID = firma.get("Firma_ID", "")
            if not _FIRMA_ID:
                raise RuntimeError(f"Company '{FIRMA_NAME}' found, but has no Firma_ID.")
            logger.info(f"Selected database: {_FIRMA_ID} ({FIRMA_NAME})")
            return _FIRMA_ID

    available = [f.get("Bezeichnung", "(unnamed)") for f in firmen]
    raise RuntimeError(
        f"The required database '{FIRMA_NAME}' was not found. "
        f"Available companies: {available}"
    )

def get_headers(firma_id: Optional[str] = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if firma_id is None:
        firma_id = get_firma_id()
    if firma_id:
        headers["mbl-ident"] = firma_id
    return headers

def api_call(
    payload: dict, firma_id: Optional[str] = None, timeout: int = 60
) -> dict:
    """Perform a POST request to MonKey Office Connect."""
    if firma_id:
        if firma_id != get_firma_id():
            raise RuntimeError(
                f"Incorrect Firma_ID '{firma_id}' rejected. "
                f"Only database '{FIRMA_NAME}' is configured."
            )

    auth = get_auth()
    headers = get_headers(firma_id)
    payload_keys = list(payload.keys())
    logger.info(f"API-Call: {payload_keys} -> {API_URL}")

    session = get_session()
    resp = session.post(
        API_URL, json=payload, auth=auth, headers=headers, timeout=timeout
    )
    resp.raise_for_status()
    data = resp.json()
    _check_status(data, payload_keys[0] if payload_keys else "api")
    return data

def _check_status(data: dict, action: str) -> None:
    """Check ReturnStatus in the response and raise Exception on error."""
    response_key = f"{action}Response"
    if response_key not in data:
        return
    status = data[response_key].get("ReturnData", {}).get("ReturnStatus", {})
    code = status.get("Statuscode")
    if code is not None and code != 0:
        msg = status.get("Meldung", "Unknown error")
        logger.error(f"MonKey Office error during {action}: {status}")
        raise RuntimeError(
            f"MonKey Office error during {action}: Statuscode {code} - {msg}"
        )

def _extract_list(data: dict, response_key: str, item_key: str) -> list:
    """Extract a list from the response."""
    if response_key not in data:
        return []
    return_data = data[response_key].get("ReturnData", {})
    items = return_data.get(item_key)
    if items is None:
        return []
    if isinstance(items, list):
        return items
    if isinstance(items, dict):
        return [items]
    return []

def _extract_single(data: dict, response_key: str, item_key: str) -> Optional[dict]:
    """Extract a single object from the response."""
    if response_key not in data:
        return None
    return_data = data[response_key].get("ReturnData", {})
    return return_data.get(item_key)

# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------
mcp = FastMCP("monkey-office-connect")

@mcp.tool()
def list_firmen() -> list:
    """Returns the currently configured company/database."""
    fid = get_firma_id()
    return [{"firma_id": fid, "bezeichnung": FIRMA_NAME}]

@mcp.tool()
def list_buchungen(
    datum_von: str,
    datum_bis: str,
    suchtext: str = "",
    festschreib_status: int = 4,
    belegnr: str = "",
    konto: int = 0,
    konto_soll: int = 0,
    konto_haben: int = 0,
) -> list:
    """Retrieve bookings within a time range.

    Args:
        datum_von: Start date (yyyy-mm-dd)
        datum_bis: End date (yyyy-mm-dd)
        suchtext: Optional search text
        festschreib_status: 1=open, 2=closed, 4=all
        belegnr: Filter by document number
        konto: Filter by account
        konto_soll: Filter by debit account
        konto_haben: Filter by credit account
    """
    filter_obj = {
        "DatumVon": datum_von,
        "DatumBis": datum_bis,
        "FestschreibStatus": festschreib_status,
    }
    if suchtext:
        filter_obj["Suchtext"] = suchtext
    if belegnr:
        filter_obj["BelegNr"] = belegnr
    if konto:
        filter_obj["Konto"] = konto
    if konto_soll:
        filter_obj["KontoSoll"] = konto_soll
    if konto_haben:
        filter_obj["KontoHaben"] = konto_haben

    result = api_call({"buchungList": {"BuchungFilter": filter_obj}})
    return _extract_list(result, "buchungListResponse", "BuchungListItem")

@mcp.tool()
def get_buchung(buchung_id: str) -> dict:
    """Retrieve a single booking including its positions.

    Args:
        buchung_id: The Booking_ID from list_buchungen
    """
    result = api_call({"buchungGet": {"Buchung_ID": buchung_id}})
    return _extract_single(result, "buchungGetResponse", "BuchungItem") or {}

@mcp.tool()
def get_filter_template() -> dict:
    """Returns an empty template for BuchungFilter."""
    result = api_call({"buchungFilterTemplate": ""})
    return (
        _extract_single(result, "buchungFilterTemplateResponse", "BuchungFilter") or {}
    )

@mcp.tool()
def get_buchung_template(positionen_anzahl: int = 1) -> dict:
    """Returns an empty template for BuchungAddItem.

    Args:
        positionen_anzahl: Number of empty positions (default 1)
    """
    result = api_call({"buchungTemplate": ""})
    template = (
        _extract_single(result, "buchungTemplateResponse", "BuchungAddItem") or {}
    )

    positions = []
    for _ in range(max(1, positionen_anzahl)):
        positions.append(
            {
                "Betrag": "",
                "KontoSoll": 0,
                "KontoHaben": 0,
                "Steuersatz": "-",
                "Text": "",
                "Kostenstelle1": "",
                "Kostenstelle2": "",
            }
        )
    template["BuchungPositionItemList"] = {"BuchungPositionAddItem": positions}
    return template

@mcp.tool()
def list_steuersaetze() -> list:
    """List available tax rates."""
    result = api_call({"steuersatzList": ""})
    for key in ("SteuersatzItem", "SteuersatzListItem", "Steuersatz"):
        saetze = _extract_list(result, "steuersatzListResponse", key)
        if saetze:
            return saetze
    return []

@mcp.tool()
def add_buchung(
    datum: str,
    text: str,
    betrag: str,
    konto_soll: int,
    konto_haben: int = 1490,
    steuersatz: str = "-",
    belegnr: str = "",
    referenz: str = "",
    notizen: str = "",
    waehrung: str = "EUR",
    kostenstelle1: str = "",
    kostenstelle2: str = "",
    zusatzliche_positionen_json: str = "[]",
) -> dict:
    """Create a new booking in MonKey Office.

    Args:
        datum: Booking date (yyyy-mm-dd)
        text: Booking text
        betrag: Amount with comma as decimal separator, e.g. '32,00'
        konto_soll: Debit account
        konto_haben: Credit account (default 1490)
        steuersatz: '-', 'VSt19', 'USt19' or others from list_steuersaetze
        belegnr: Optional document number
        referenz: Optional reference
        notizen: Optional notes
        waehrung: Currency (default EUR)
        kostenstelle1: Optional cost center 1
        kostenstelle2: Optional cost center 2
        zusatzliche_positionen_json: JSON list of further BuchungPositionAddItem
    """
    position = {
        "Betrag": betrag,
        "KontoSoll": konto_soll,
        "KontoHaben": konto_haben,
        "Steuersatz": steuersatz,
        "Text": text,
    }
    if kostenstelle1:
        position["Kostenstelle1"] = kostenstelle1
    if kostenstelle2:
        position["Kostenstelle2"] = kostenstelle2

    positions = [position]
    try:
        extra = json.loads(zusatzliche_positionen_json)
        if isinstance(extra, list):
            positions.extend(extra)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in zusatzliche_positionen_json: {exc}")

    item = {
        "Datum": datum,
        "Text": text,
        "Waehrung": waehrung,
        "BuchungPositionItemList": {"BuchungPositionAddItem": positions},
    }
    if belegnr:
        item["BelegNr"] = belegnr
    if referenz:
        item["Referenz"] = referenz
    if notizen:
        item["Notizen"] = notizen

    result = api_call({"buchungAdd": {"BuchungAddItem": item}})
    status = _extract_single(result, "buchungAddResponse", "ReturnStatus") or {}
    return {
        "buchung_id": status.get("Insert_ID"),
        "statuscode": status.get("Statuscode"),
        "meldung": status.get("Meldung"),
    }

@mcp.tool()
def add_attachment(
    buchung_id: str, dateipfad: str, bezeichnung: str = "Beleg"
) -> dict:
    """Attach a PDF to a booking.

    Args:
        buchung_id: The Booking_ID
        dateipfad: Absolute path to the PDF file
        bezeichnung: Label for the attachment (default 'Beleg')
    """
    path = Path(dateipfad)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {dateipfad}")
    if not path.is_file():
        raise ValueError(f"Path is not a file: {dateipfad}")

    data_b64 = base64.b64encode(path.read_bytes()).decode("ascii")

    payload = {
        "buchungAddAttachment": {
            "Buchung_ID": buchung_id,
            "AttachmentAddItem": {
                "Bezeichnung": bezeichnung,
                "Name": path.name,
                "DatenBASE64": data_b64,
            },
        },
    }
    result = api_call(payload, timeout=120)
    status = (
        _extract_single(result, "buchungAddAttachmentResponse", "ReturnStatus") or {}
    )
    return {
        "attachment_id": status.get("Insert_ID"),
        "statuscode": status.get("Statuscode"),
        "meldung": status.get("Meldung"),
    }

@mcp.tool()
def import_buchungen(buchungen_json: str) -> list:
    """Import multiple bookings with optional attachments.

    Args:
        buchungen_json: JSON list of objects with fields as in add_buchung,
                       optionally including 'dateipfad' per booking
    """
    try:
        buchungen = json.loads(buchungen_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}")

    if not isinstance(buchungen, list):
        raise ValueError("buchungen_json must be a JSON list")

    results = []
    for idx, b in enumerate(buchungen):
        dateipfad = b.pop("dateipfad", None)
        try:
            result = add_buchung(**b)
            if dateipfad and result.get("buchung_id"):
                attach_result = add_attachment(result["buchung_id"], dateipfad)
                result["attachment"] = attach_result
            results.append(result)
        except Exception as exc:
            logger.error(f"Error at booking {idx}: {exc}")
            results.append({"fehler": str(exc), "index": idx, "buchung": b})

    return results

if __name__ == "__main__":
    verify_monkey_office_version()
    mcp.run(transport="stdio")
